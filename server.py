"""LP制作代行サービス サーバー"""
import ftplib
import io
import json
import os
import secrets
import shutil
import urllib.parse
from pathlib import Path

import httpx

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

from lp.generator import generate_lp_copy, SYSTEM_PROMPT
from lp.html_builder import build_lp_html
from lp.line_richmenu import setup_richmenu
from lp.google_places import get_review_url
from lp.scenario_builder import build_scenarios_for_client

app = FastAPI(title="LP制作代行サービス")

_BASE     = Path(__file__).parent
FORM_PATH = _BASE / "lp" / "form.html"
LINE_HEARING_PATH = _BASE / "lp" / "line_hearing.html"
LINE_SETUP_PATH = _BASE / "lp" / "line_setup.html"
DASHBOARD_PATH  = _BASE / "lp" / "dashboard.html"
PHOTOS_DIR = _BASE / "tmp" / "photos"
OUTPUT_DIR = _BASE / "tmp" / "output"
HEARING_DIR = _BASE / "tmp" / "hearings"
RICHMENU_IMAGE = _BASE / "static" / "richmenu.png"

HEARING_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(_BASE / "static")), name="static")

# ─── Cloudflare R2 写真ストア ────────────────────────────────────────
_R2_BUCKET         = os.getenv("R2_BUCKET", "lp-photos")
_R2_ACCESS_KEY_ID  = os.getenv("R2_ACCESS_KEY_ID", "")
_R2_SECRET_KEY     = os.getenv("R2_SECRET_ACCESS_KEY", "")

def _r2_client():
    import boto3
    from botocore.config import Config
    return boto3.client(
        "s3",
        endpoint_url=f"https://{os.getenv('CF_ACCOUNT_ID','')}.r2.cloudflarestorage.com",
        aws_access_key_id=_R2_ACCESS_KEY_ID,
        aws_secret_access_key=_R2_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )

def _r2_upload(data: bytes, key: str, content_type: str = "image/jpeg") -> str:
    if not _R2_ACCESS_KEY_ID or not _R2_SECRET_KEY:
        return ""
    _r2_client().put_object(Bucket=_R2_BUCKET, Key=key, Body=data, ContentType=content_type)
    return key

def _r2_download(key: str) -> bytes | None:
    if not _R2_ACCESS_KEY_ID or not _R2_SECRET_KEY:
        return None
    try:
        res = _r2_client().get_object(Bucket=_R2_BUCKET, Key=key)
        return res["Body"].read()
    except Exception:
        return None

def _resolve_photos(photos: dict, slug: str) -> dict:
    """R2キー（r2://...）をローカル一時ファイルに展開して返す"""
    resolved = {}
    for k, v in photos.items():
        if isinstance(v, str) and v.startswith("r2://"):
            key = v[5:]
            data = _r2_download(key)
            if data:
                suffix = Path(key).suffix or ".jpg"
                tmp = PHOTOS_DIR / slug / f"{k}{suffix}"
                tmp.parent.mkdir(parents=True, exist_ok=True)
                tmp.write_bytes(data)
                resolved[k] = str(tmp)
        else:
            resolved[k] = v
    return resolved

# ─── owner_message 整形ヘルパー ──────────────────────────────────────
def _polish_text(raw: str, prompt: str) -> str:
    """テキストをClaudeで整形する汎用関数（失敗時は元テキストを返す）"""
    if not raw:
        return raw
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return raw
    try:
        client = anthropic.Anthropic(api_key=api_key)
        result = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt + f"\n\n元の文章：\n{raw}"}],
        )
        return result.content[0].text.strip()
    except Exception:
        return raw


def _polish_owner_message(raw: str) -> str:
    """院長の想いをLINEメッセージ向けに整形する"""
    return _polish_text(raw, (
        "以下の院長の想いを、LINEメッセージ向けに整えてください。\n\n"
        "条件：\n"
        "- 敬語・丁寧語で、自然な話し言葉にする\n"
        "- 2〜3文に収める\n"
        "- 院長本人が話している一人称の文体\n"
        "- 整えた文章だけ出力する（前置きや説明文は不要）"
    ))


def _polish_wrong_approach(raw: str) -> str:
    """よくある間違いをLINEメッセージの一節として自然な敬語に整形する"""
    return _polish_text(raw, (
        "以下の「よくある間違ったケア・誤解」を、LINEメッセージの一節として整えてください。\n\n"
        "条件：\n"
        "- 読者（患者さん）に語りかける丁寧な話し言葉\n"
        "- 上から目線にならず、共感・気づきを促すトーン\n"
        "- 2〜3文に収める\n"
        "- 整えた文章だけ出力する（前置きや説明文は不要）"
    ))


# ─── Cloudflare D1 hearing ストア ────────────────────────────────────
_CF_ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID", "")
_CF_D1_DB_ID   = os.getenv("CF_D1_DB_ID", "05d8fa48-a20c-465d-850f-e022493f95c2")
_CF_API_TOKEN  = os.getenv("CF_API_TOKEN", "")

def _d1q(sql: str, params: list | None = None) -> list[dict]:
    if not _CF_ACCOUNT_ID or not _CF_API_TOKEN:
        return []
    url = f"https://api.cloudflare.com/client/v4/accounts/{_CF_ACCOUNT_ID}/d1/database/{_CF_D1_DB_ID}/query"
    res = httpx.post(
        url,
        headers={"Authorization": f"Bearer {_CF_API_TOKEN}", "Content-Type": "application/json"},
        json={"sql": sql, "params": params or []},
        timeout=10,
    )
    if not res.is_success:
        return []
    return res.json().get("result", [{}])[0].get("results", [])

def get_hearing(slug: str) -> dict | None:
    """D1からhearingデータを取得（なければローカルファイルにフォールバック）"""
    rows = _d1q("SELECT data FROM lp_hearings WHERE slug = ?", [slug])
    if rows:
        return json.loads(rows[0]["data"])
    # フォールバック：既存ローカルファイル
    local = HEARING_DIR / f"{slug}.json"
    if local.exists():
        return json.loads(local.read_text(encoding="utf-8"))
    return None

def save_hearing(slug: str, data: dict) -> None:
    """D1にhearingデータを保存（ローカルファイルにも同時書き込み）"""
    payload = json.dumps(data, ensure_ascii=False)
    existing = _d1q("SELECT slug FROM lp_hearings WHERE slug = ?", [slug])
    if existing:
        _d1q("UPDATE lp_hearings SET data = ?, updated_at = datetime('now') WHERE slug = ?", [payload, slug])
    else:
        _d1q("INSERT INTO lp_hearings (slug, data) VALUES (?, ?)", [slug, payload])
    # ローカルにも保持（フォールバック用）
    HEARING_DIR.mkdir(parents=True, exist_ok=True)
    (HEARING_DIR / f"{slug}.json").write_text(payload, encoding="utf-8")


def _ftp_deploy(html: str, slug: str, overwrite: bool = False) -> str:
    import random, string

    host     = os.getenv("XSERVER_FTP_HOST", "")
    user     = os.getenv("XSERVER_FTP_USER", "")
    password = os.getenv("XSERVER_FTP_PASS", "")
    base_url = os.getenv("XSERVER_BASE_URL", "https://visionroom.jp/lp/")

    if not all([host, user, password]):
        raise ValueError("FTP認証情報が設定されていません")

    with ftplib.FTP_TLS() as ftp:
        ftp.connect(host, 21, timeout=30)
        ftp.auth()
        ftp.login(user, password)
        ftp.prot_p()
        ftp.set_pasv(True)

        final_slug = slug
        dir_exists = False
        try:
            ftp.cwd("/" + slug)
            dir_exists = True
        except ftplib.error_perm:
            pass

        if dir_exists and not overwrite:
            # 新規生成時：既存ディレクトリと被ったらランダムサフィックス
            suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
            final_slug = f"{slug}-{suffix}"
            ftp.cwd("/")

        remote_dir  = "/" + final_slug
        remote_file = remote_dir + "/index.html"
        if not dir_exists or not overwrite:
            ftp.mkd(remote_dir)
        ftp.storbinary(f"STOR {remote_file}", io.BytesIO(html.encode("utf-8")))

    return base_url.rstrip("/") + "/" + urllib.parse.quote(final_slug) + "/"


@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def root(request: Request):
    if request.method == "HEAD":
        from fastapi.responses import Response
        return Response(status_code=200)
    return FORM_PATH.read_text(encoding="utf-8")


@app.get("/lp/form", response_class=HTMLResponse)
async def get_form():
    return FORM_PATH.read_text(encoding="utf-8")


@app.get("/api/webhook-url")
async def get_webhook_url():
    harness_url = os.getenv("LINE_HARNESS_API_URL", "https://line-crm-worker.marunage-crm.workers.dev")
    return {"webhook_url": f"{harness_url}/webhook"}


@app.get("/line-form", response_class=HTMLResponse)
async def get_line_form():
    return LINE_HEARING_PATH.read_text(encoding="utf-8")


@app.post("/line-only/hearing")
async def post_line_only_hearing(request: Request):
    """LINE構築専用ヒアリング（LP生成なし）"""
    try:
        body = await request.json()
        shop_name = (body.get("shop_name") or "").strip()
        if not shop_name:
            raise HTTPException(status_code=400, detail="店名・院名を入力してください")

        import re, unicodedata
        # ASCII文字のみのslugを生成（日本語はHarnessのQR ref_codeに使えないため）
        normalized = unicodedata.normalize('NFKD', shop_name)
        ascii_only = normalized.encode('ascii', 'ignore').decode('ascii')
        url_slug = re.sub(r'[^\w\-]', '', ascii_only.lower().replace(' ', '-').replace('　', '-'))
        if not url_slug:
            # 日本語店名などASCIIが残らない場合はランダムトークン
            url_slug = secrets.token_urlsafe(8).lower()

        hearing = dict(body)
        if not hearing.get("_dashboard_token"):
            hearing["_dashboard_token"] = secrets.token_urlsafe(24)

        # lp_url を _lp_url としても保存（LINE設定ページで参照）
        if hearing.get("lp_url") and not hearing.get("_lp_url"):
            hearing["_lp_url"] = hearing["lp_url"]

        save_hearing(url_slug, hearing)

        return {"success": True, "line_setup_url": f"/{url_slug}/line-setup"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/lp/preview", response_class=HTMLResponse)
async def lp_preview():
    """API不要のLPプレビュー（ボタン・レイアウト確認用）"""
    from lp.html_builder import build_lp_html
    hearing = {
        "shop_name": "サンプル整体院", "shop_type": "整体院", "location": "東京都渋谷区",
        "address": "東京都渋谷区〇〇1-2-3", "phone": "03-1234-5678",
        "line_url": "https://line.me/R/ti/p/@example",
        "booking_url": "https://coubic.com/example",
        "cta_type": ["line", "phone", "booking"],
        "color_theme": "natural_green",
        "target": "肩こりや腰痛に悩む30〜50代の女性",
        "open_hours": "10:00〜20:00（最終受付 19:00）",
        "regular_holiday": "毎週火曜日",
        "coupon_title": "初回体験クーポン", "coupon_original_price": "8,000円", "coupon_price": "3,980円",
        "owner_name": "山田 太郎", "owner_message": "患者様一人ひとりに寄り添った施術を心がけています。当院では根本原因にアプローチし、再発しない体づくりをサポートしています。お体のことで何かお困りの際は、どうぞお気軽にご相談ください。",
        "owner_qualifications": "柔道整復師 / 鍼灸師",
        "main_menu": [
            {"name": "全身整体コース", "time": "60分", "price": "6,600円", "description": "全身のバランスを整えます"},
            {"name": "腰痛専門コース", "time": "45分", "price": "5,500円", "original_price": "8,000円", "description": "腰痛に特化した施術"},
            {"name": "肩こり解消コース", "time": "30分", "price": "3,300円", "description": "肩まわりを集中ケア"},
        ],
        "faq": [
            {"q": "初めてでも大丈夫ですか？", "a": "はい、初めての方も安心してお越しください。丁寧にカウンセリングを行います。"},
            {"q": "予約は必要ですか？", "a": "完全予約制ですので、事前にご予約をお願いしています。"},
        ],
        "photos": {
            "hero":      str(Path(__file__).parent / "lp/assets/hero/default.jpg"),
            "staff":     str(Path(__file__).parent / "lp/assets/menu/zentai_f_a.jpg"),
            "interior":  str(Path(__file__).parent / "lp/assets/menu/koshi_f_a.jpg"),
            "exterior":  str(Path(__file__).parent / "lp/assets/menu/katakori_f_a.jpg"),
            "treatment": str(Path(__file__).parent / "lp/assets/menu/ashi_f_a.jpg"),
        },
    }
    copy = {
        "catch_copy": "その痛み、もう我慢しなくていい",
        "sub_copy": "根本から改善する整体で、毎日を快適に過ごしましょう",
        "pain_section": {"headline": "こんなお悩みはありませんか？", "items": [
            {"text": "慢性的な肩こり・首の痛み", "sub": "デスクワークや育児で肩が張り、夜も眠れないほどつらい"},
            {"text": "腰痛がなかなか治らない", "sub": "湿布や市販薬を使っても、すぐにまた痛みが戻ってしまう"},
            {"text": "疲れが取れない・体が重い", "sub": "しっかり寝ても疲労感が残り、仕事や家事に集中できない"},
        ]},
        "empathy_text": "「どこに行っても改善しない」「忙しくて通えない」そのお悩み、サンプル整体院にお任せください。",
        "solution_section": {"headline": "選ばれる理由", "body": "独自の整体メソッドで根本から改善します。", "points": [
            {"title": "丁寧なカウンセリング", "body": "お身体の状態を詳しくお聞きし、最適な施術プランをご提案します。"},
            {"title": "経験豊富なスタッフ", "body": "国家資格を持つ施術者が責任を持って対応いたします。"},
            {"title": "完全予約制で安心", "body": "待ち時間なし。ご都合に合わせてご予約いただけます。"},
        ]},
        "achievements_section": {"headline": "実績・数字で見る", "items": ["施術実績 5,000人以上", "顧客満足度 98%", "リピート率 92%"]},
        "testimonials_section": {"headline": "お客様の声", "items": [
            {"name": "30代女性・会社員", "comment": "産後から続いていた腰痛が、3回の施術でほぼ気にならなくなりました。もっと早く来ればよかったです！"},
            {"name": "40代男性・デスクワーク", "comment": "慢性的な肩こりが改善され、仕事の集中力も上がりました。毎月通っています。"},
            {"name": "50代女性・主婦", "comment": "先生の説明がわかりやすく、安心して施術を受けられました。体が軽くなりました。"},
        ]},
        "menu_section": {"headline": "メニュー・料金", "lead": "お身体の状態に合わせてコースをお選びください。"},
        "faq_section": {"headline": "よくある質問"},
        "cta_section": {"headline": "まずは気軽にご相談ください", "body": "初回限定クーポンご利用で、通常8,000円が3,980円に。", "button_text": "LINEで予約", "note": "友だち追加・登録無料"},
    }
    return build_lp_html(hearing, copy, embed_images=True)


@app.post("/lp/catchcopy")
async def generate_catchcopy(hearing: str = Form(...)):
    try:
        hearing_dict: dict = json.loads(hearing)
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY が設定されていません")

        client = anthropic.Anthropic(api_key=api_key)

        prompt = f"""以下のヒアリングシートをもとに、LPのメインキャッチコピーをカテゴリ別に生成してください。

【ヒアリングシート】
{json.dumps(hearing_dict, ensure_ascii=False, indent=2)}

【要件】
- 各コピーは15〜35文字
- ターゲットの悩みや感情に直接刺さる表現
- markdownの**や##は使わない

【カテゴリと生成数】
1. 悩み訴求型：ターゲットの痛みや不満を直接突く（3案）
2. 結果・変化型：施術後の変化・ビフォーアフターを訴える（3案）
3. 共感・感情型：「わかる、つらいよね」と寄り添う表現（2案）
4. 信頼・実績型：数字・権威・実績で安心感を出す（2案）
5. 問いかけ型：読んだ人が「自分のことだ」と感じる問い（2案）

【出力形式】
JSONのみ出力してください。
{{
  "categories": [
    {{"label": "悩み訴求型", "candidates": ["コピー1", "コピー2", "コピー3"]}},
    {{"label": "結果・変化型", "candidates": ["コピー1", "コピー2", "コピー3"]}},
    {{"label": "共感・感情型", "candidates": ["コピー1", "コピー2"]}},
    {{"label": "信頼・実績型", "candidates": ["コピー1", "コピー2"]}},
    {{"label": "問いかけ型", "candidates": ["コピー1", "コピー2"]}}
  ]
}}"""

        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        data = json.loads(raw)
        return {"success": True, "categories": data.get("categories", [])}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/lp/generate")
async def generate_lp(
    hearing:   str        = Form(...),
    hero:      UploadFile = File(None),
    exterior:  UploadFile = File(None),
    interior:  UploadFile = File(None),
    owner:     UploadFile = File(None),
    staff:     UploadFile = File(None),
    treatment: UploadFile = File(None),
):
    try:
        hearing_dict: dict = json.loads(hearing)
        shop_name = hearing_dict.get("shop_name", "shop")
        url_slug  = hearing_dict.get("url_slug", "").strip() or shop_name

        # 住所からマップURL自動生成
        address = hearing_dict.get("address", "")
        if address and not hearing_dict.get("map_embed_url"):
            query = urllib.parse.quote(address)
            hearing_dict["map_embed_url"] = f"https://www.google.com/maps?q={query}&output=embed&z=16"

        # 写真の一時保存
        photo_dir = PHOTOS_DIR / shop_name
        photo_dir.mkdir(parents=True, exist_ok=True)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        photos = {}
        for field_name, upload in [
            ("hero", hero), ("exterior", exterior),
            ("interior", interior), ("owner", owner), ("staff", staff), ("treatment", treatment),
        ]:
            if upload and upload.filename:
                suffix = Path(upload.filename).suffix or ".jpg"
                data = await upload.read()
                # R2にアップロード
                key = f"photos/{url_slug}/{field_name}{suffix}"
                r2_key = _r2_upload(data, key, f"image/{suffix.lstrip('.')}")
                if r2_key:
                    photos[field_name] = f"r2://{r2_key}"
                else:
                    # フォールバック：ローカル保存
                    dest = photo_dir / f"{field_name}{suffix}"
                    dest.write_bytes(data)
                    photos[field_name] = str(dest)

        hearing_dict["photos"] = photos
        # HTML生成用にR2キーをローカルに展開
        hearing_dict_for_build = {**hearing_dict, "photos": _resolve_photos(photos, url_slug)}

        # コピー生成
        copy = generate_lp_copy(hearing_dict_for_build)

        # HTML生成（画像base64埋め込み）
        html = build_lp_html(hearing_dict_for_build, copy, embed_images=True)

        # ローカル保存（常に実行）
        try:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            (OUTPUT_DIR / f"{url_slug}.html").write_text(html, encoding="utf-8")
        except Exception as e:
            print(f"⚠️ ローカル保存失敗: {e}")

        # FTPデプロイ
        public_url = ""
        ftp_error = ""
        try:
            public_url = _ftp_deploy(html, url_slug)
        except Exception as e:
            ftp_error = str(e)
            print(f"⚠️ FTPデプロイ失敗: {e}")

        # hearingデータをスラッグで保存（LINE設定ページで再利用）
        try:
            saved_slug = url_slug if not ftp_error else url_slug
            hearing_dict["_lp_url"] = public_url
            hearing_dict["_lp_copy"] = copy  # 高速リビルド用にcopyを保存
            # ダッシュボード用ランダムトークン（未設定の場合のみ発行）
            if not hearing_dict.get("_dashboard_token"):
                hearing_dict["_dashboard_token"] = secrets.token_urlsafe(24)
            save_hearing(saved_slug, hearing_dict)
        except Exception as e:
            print(f"⚠️ hearing保存失敗: {e}")

        # 一時ファイルを削除
        try:
            shutil.rmtree(photo_dir)
        except Exception:
            pass

        return {
            "success": True,
            "public_url": public_url or f"/lp/local/{url_slug}",
            "ftp_error": ftp_error,
            "line_setup_url": f"/{url_slug}/line-setup",
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}\n{traceback.format_exc()}")


@app.patch("/lp/hearing/{slug}")
async def update_hearing(slug: str, request: Request):
    """hearing の一部フィールドを更新し、保存済みcopyでLPを高速リビルド（AI再生成なし）"""
    data = get_hearing(slug)
    if data is None:
        raise HTTPException(status_code=404, detail="hearing not found")
    updates = await request.json()
    data.update(updates)
    save_hearing(slug, data)
    copy = data.get("_lp_copy")
    if not copy:
        raise HTTPException(status_code=400, detail="No saved copy. Run full rebuild first.")
    try:
        data_for_build = {**data, "photos": _resolve_photos(data.get("photos", {}), slug)}
        html = build_lp_html(data_for_build, copy, embed_images=True)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUTPUT_DIR / f"{slug}.html").write_text(html, encoding="utf-8")
        existing_url = data.get("_lp_url", "")
        base_url = os.getenv("XSERVER_BASE_URL", "https://visionroom.jp/lp/")
        deploy_slug = existing_url.replace(base_url, "").strip("/") if existing_url.startswith(base_url) else slug
        public_url = _ftp_deploy(html, deploy_slug, overwrite=True)
        return {"success": True, "public_url": public_url}
    except Exception as e:
        import traceback
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}\n{traceback.format_exc()}")


@app.post("/lp/rebuild/{slug}")
async def rebuild_lp(slug: str):
    """保存済みhearingデータからLPを再生成してFTPデプロイ"""
    data = get_hearing(slug)
    if data is None:
        raise HTTPException(status_code=404, detail="hearing not found")
    try:
        data_for_build = {**data, "photos": _resolve_photos(data.get("photos", {}), slug)}
        copy = data.get("_lp_copy") or generate_lp_copy(data_for_build)
        html = build_lp_html(data_for_build, copy, embed_images=True)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUTPUT_DIR / f"{slug}.html").write_text(html, encoding="utf-8")
        public_url = ""
        ftp_error = ""
        try:
            # 既存LP URLのパス部分を取り出して上書きデプロイ
            existing_url = data.get("_lp_url", "")
            base_url = os.getenv("XSERVER_BASE_URL", "https://visionroom.jp/lp/")
            if existing_url and existing_url.startswith(base_url):
                deploy_slug = existing_url.replace(base_url, "").strip("/")
            else:
                deploy_slug = slug
            public_url = _ftp_deploy(html, deploy_slug, overwrite=True)
        except Exception as e:
            ftp_error = str(e)
        if public_url:
            data["_lp_url"] = public_url
            data["_lp_copy"] = copy
            save_hearing(slug, data)
        return {"success": True, "public_url": public_url or f"/lp/local/{slug}", "ftp_error": ftp_error or None}
    except Exception as e:
        import traceback
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}\n{traceback.format_exc()}")


@app.get("/lp/local/{slug}", response_class=HTMLResponse)
async def serve_local_lp(slug: str):
    """ローカル生成済みLPを表示（FTPなしで確認用）"""
    path = OUTPUT_DIR / f"{slug}.html"
    if not path.exists():
        raise HTTPException(status_code=404, detail="LP not found. まず生成してください。")
    return path.read_text(encoding="utf-8")


@app.get("/lp/hearing/{slug}")
async def get_hearing_endpoint(slug: str):
    """LP登録済みhearingデータをスラッグで取得"""
    data = get_hearing(slug)
    if data is None:
        raise HTTPException(status_code=404, detail="hearing not found")
    return {
        "success": True,
        "hearing": {
            "shop_name": data.get("shop_name", ""),
            "phone": data.get("phone", ""),
            "booking_url": data.get("booking_url", ""),
            "address": data.get("address", ""),
        },
        "lp_url": data.get("_lp_url", ""),
    }


@app.get("/{slug}/line-setup", response_class=HTMLResponse)
async def get_line_setup(slug: str):
    """LINE設定ページ"""
    if get_hearing(slug) is None:
        raise HTTPException(status_code=404, detail=f"スラッグ '{slug}' のLP情報が見つかりません")
    return LINE_SETUP_PATH.read_text(encoding="utf-8")


@app.post("/{slug}/line-setup")
async def post_line_setup(slug: str, request: Request):
    """リッチメニューを作成してLINEに設置"""
    try:
        body = await request.json()
        line_token = body.get("line_token", "").strip()
        channel_secret_input = body.get("channel_secret", "").strip()
        channel_id_input = body.get("channel_id", "").strip()

        if not line_token:
            raise HTTPException(status_code=400, detail="line_token は必須です")
        if not channel_secret_input:
            raise HTTPException(status_code=400, detail="channel_secret は必須です")
        if not channel_id_input:
            raise HTTPException(status_code=400, detail="channel_id は必須です")

        # hearing読み込み
        data = get_hearing(slug)
        if data is None:
            raise HTTPException(status_code=404, detail="LP情報が見つかりません")

        shop_name_for_account = data.get("shop_name", slug)
        harness_url_val = os.getenv("LINE_HARNESS_API_URL", "https://line-crm-worker.marunage-crm.workers.dev")
        harness_key_val = os.getenv("LINE_HARNESS_API_KEY", "")
        harness_headers = {"Authorization": f"Bearer {harness_key_val}", "Content-Type": "application/json"}

        # LINE Harnessにアカウントを自動登録（既存の場合は更新）
        if harness_key_val and channel_id_input:
            try:
                # 既存アカウントを検索
                accounts_res = httpx.get(
                    f"{harness_url_val}/api/line-accounts",
                    headers=harness_headers,
                    timeout=10,
                )
                existing_account_id = None
                if accounts_res.is_success:
                    for acc in accounts_res.json().get("data", []):
                        if str(acc.get("channelId", "")) == channel_id_input:
                            existing_account_id = acc["id"]
                            break

                if existing_account_id:
                    # 既存アカウントのtoken/secretを更新
                    httpx.put(
                        f"{harness_url_val}/api/line-accounts/{existing_account_id}",
                        headers=harness_headers,
                        json={
                            "channelAccessToken": line_token,
                            "channelSecret": channel_secret_input,
                            "name": shop_name_for_account,
                        },
                        timeout=10,
                    )
                    data["line_account_id"] = existing_account_id
                else:
                    # 新規アカウント登録
                    create_res = httpx.post(
                        f"{harness_url_val}/api/line-accounts",
                        headers=harness_headers,
                        json={
                            "channelId": channel_id_input,
                            "name": shop_name_for_account,
                            "channelAccessToken": line_token,
                            "channelSecret": channel_secret_input,
                        },
                        timeout=10,
                    )
                    if create_res.is_success:
                        data["line_account_id"] = create_res.json()["data"]["id"]
            except Exception:
                pass

        shop_name = data.get("shop_name", slug)
        phone = data.get("phone", "")
        address = data.get("address", "")
        lp_url = data.get("_lp_url", "")
        booking_url = data.get("booking_url", "") or lp_url
        homepage_url = lp_url
        treatment_url = (lp_url.rstrip("/") + "#menu") if lp_url else lp_url

        # 地図URL生成
        map_query = urllib.parse.quote(f"{shop_name} {address}")
        map_url = f"https://maps.google.com/maps?q={map_query}"

        # Google Places APIでPlace IDと口コミURLを自動取得
        google_api_key = os.getenv("GOOGLE_PLACES_API_KEY", "")
        _, google_review_url = get_review_url(shop_name, address, google_api_key)
        # 感想特典・再来院クーポン情報
        review_coupon_name = data.get("review_coupon_name", "次回来院クーポン")
        review_coupon_discount = data.get("review_coupon_discount", "")
        review_coupon_text = f"{review_coupon_name}（{review_coupon_discount}）" if review_coupon_discount else review_coupon_name

        revisit_coupon_name = data.get("revisit_coupon_name", "再来院クーポン")
        revisit_coupon_discount = data.get("revisit_coupon_discount", "")
        revisit_coupon_text = f"{revisit_coupon_name}（{revisit_coupon_discount}）" if revisit_coupon_discount else revisit_coupon_name
        revisit_coupon_timing = data.get("revisit_coupon_timing", "14")

        # LINE Harness APIでクライアント専用フォームを作成
        harness_url = harness_url_val
        harness_key = harness_key_val
        form_id = data.get("_form_id", "")
        shinsatsu_form_id = data.get("_shinsatsu_form_id", "")

        form_description = json.dumps({
            "google_maps_url": google_review_url,
            "coupon_text": review_coupon_text,
            "revisit_coupon_text": revisit_coupon_text,
            "revisit_coupon_timing_days": revisit_coupon_timing,
            "add_tag_on_submit": f"{shop_name}_再来院",
        }, ensure_ascii=False)

        _harness_headers = {"Authorization": f"Bearer {harness_key}", "Content-Type": "application/json"}

        if not harness_key:
            pass
        else:
            # 感想フォーム（施術後フィードバック）
            if form_id:
                httpx.put(
                    f"{harness_url}/api/forms/{form_id}",
                    headers=_harness_headers,
                    json={"description": form_description},
                    timeout=10,
                )
            else:
                form_res = httpx.post(
                    f"{harness_url}/api/forms",
                    headers=_harness_headers,
                    json={
                        "name": f"感想フォーム - {shop_name}",
                        "description": form_description,
                        "fields": [
                            {"name": "stars", "label": "評価", "type": "number", "required": True},
                            {"name": "comment", "label": "ご感想", "type": "textarea", "required": False},
                        ],
                        "saveToMetadata": True,
                    },
                    timeout=10,
                )
                if form_res.is_success:
                    form_id = form_res.json().get("data", {}).get("id", "")

            # 問診票フォーム（来院前の事前ヒアリング）
            shinsatsu_fields = [
                {"name": "complaint", "label": "どのようなことにお悩みで来院されましたか？", "type": "textarea", "required": True},
                {"name": "condition", "label": "そのお悩みの状態を教えてください", "type": "select",
                 "options": ["治りかけ", "変化なし", "悪い", "かなり悪い（日常生活に支障）"], "required": True},
                {"name": "since_when", "label": "上記症状はいつからですか？", "type": "textarea", "required": True},
                {"name": "symptom_time", "label": "一番症状が現れるのはいつですか？", "type": "select",
                 "options": ["朝", "昼", "夕方", "夜"], "required": True},
                {"name": "cause", "label": "思い当たる原因はありますか？", "type": "textarea", "required": True},
                {"name": "treatment_history", "label": "お悩みに関して、どこかで治療されましたか？", "type": "select",
                 "options": ["治療してない", "病院", "鍼灸院・整体院", "その他"], "required": True},
                {"name": "notes", "label": "そのほかに事前に伝えたいことがありましたらご記載ください（任意）", "type": "textarea", "required": False},
                {"name": "patient_name", "label": "名前", "type": "text", "required": True},
                {"name": "phone", "label": "電話番号", "type": "text", "required": True},
            ]
            if not shinsatsu_form_id:
                s_form_res = httpx.post(
                    f"{harness_url}/api/forms",
                    headers=_harness_headers,
                    json={
                        "name": f"問診票 - {shop_name}",
                        "description": "来院前の事前問診票",
                        "fields": shinsatsu_fields,
                        "saveToMetadata": True,
                    },
                    timeout=10,
                )
                if s_form_res.is_success:
                    shinsatsu_form_id = s_form_res.json().get("data", {}).get("id", "")

        # 口コミボタンのLIFF URL（クライアント専用フォームID）
        liff_base = os.getenv("LIFF_URL", "https://liff.line.me/2009607643-QGWpmE45")
        _laccount_id = data.get("line_account_id", "")
        review_form_url = f"{liff_base}?page=review&formId={form_id}&account={_laccount_id}" if form_id else f"{liff_base}?page=review&account={_laccount_id}"
        shinsatsu_form_url = f"{liff_base}?page=form&id={shinsatsu_form_id}" if shinsatsu_form_id else ""

        rich_menu_id = setup_richmenu(
            token=line_token,
            shop_name=shop_name,
            treatment_url=treatment_url,
            homepage_url=homepage_url,
            booking_url=booking_url,
            review_form_url=review_form_url,
            map_url=map_url,
            phone=phone,
            image_path=str(RICHMENU_IMAGE),
        )

        # ── Webhook URL を LINE チャンネルに自動設定 ─────────────────
        harness_worker_url = os.getenv("LINE_HARNESS_API_URL", "https://line-crm-worker.marunage-crm.workers.dev")
        webhook_endpoint = f"{harness_worker_url}/webhook"
        try:
            httpx.put(
                "https://api.line.me/v2/bot/channel/webhook/endpoint",
                headers={"Authorization": f"Bearer {line_token}", "Content-Type": "application/json"},
                json={"webhookEndpointUrl": webhook_endpoint},
                timeout=10,
            )
        except Exception:
            pass  # webhook設定失敗は致命的ではない

        # ── シナリオ・タグ・専用QR 自動生成 ──────────────────────────
        scenario_result = None
        scenario_error = ""
        harness_url_base = harness_url_val
        if harness_key and data.get("line_account_id"):
            try:
                owner_name = data.get("owner_name") or data.get("doctor_name") or shop_name
                booking_url_for_scenario = booking_url or data.get("_lp_url", "")
                liff_url = os.getenv("LIFF_URL", "https://liff.line.me/2009607643-QGWpmE45")
                _coupon_obj     = data.get("coupon") or {}
                coupon_title    = data.get("coupon_title") or _coupon_obj.get("title", "初回限定クーポン")
                coupon_orig     = data.get("coupon_original_price") or _coupon_obj.get("original_price", "")
                coupon_price_v  = data.get("coupon_price") or _coupon_obj.get("coupon_price", "")
                coupon_disc_str = f"通常{coupon_orig}→{coupon_price_v}" if (coupon_orig and coupon_price_v) else coupon_price_v
                scenario_result = build_scenarios_for_client(
                    harness_url=harness_url_base,
                    harness_key=harness_key,
                    line_account_id=data["line_account_id"],
                    shop_name=shop_name,
                    owner_name=owner_name,
                    booking_url=booking_url_for_scenario,
                    review_url=google_review_url or "",
                    form_url=review_form_url,
                    slug=slug,
                    liff_url=liff_url,
                    coupon_name=coupon_title,
                    coupon_discount=coupon_disc_str,
                    revisit_coupon_name=revisit_coupon_name,
                    revisit_coupon_discount=revisit_coupon_discount,
                    revisit_coupon_timing=int(revisit_coupon_timing),
                    shinsatsu_form_url=shinsatsu_form_url,
                    shinsatsu_form_id=shinsatsu_form_id,
                    owner_message=_polish_owner_message(data.get("owner_message", "")),
                    main_focus=data.get("main_focus", ""),
                    wrong_approach=_polish_wrong_approach(data.get("wrong_approach", "")),
                    lp_url=data.get("_lp_url") or data.get("lp_url", ""),
                )
                data["_qr_url"]           = scenario_result["qr_url"]
                data["_entry_route_id"]   = scenario_result["entry_route_id"]
                data["_checkin_qr_url"]   = scenario_result["checkin_qr_url"]
                data["_checkin_route_id"] = scenario_result["checkin_route_id"]
                data["_scenario_ids"]     = list(scenario_result["scenario_ids"].values())
                # チェックインシナリオ（C・D）のIDを別途保持（予約設定時に停止するため）
                data["_checkin_scenario_ids"] = [
                    v for k, v in scenario_result["scenario_ids"].items()
                    if "シナリオC" in k or "シナリオD" in k
                ]
            except Exception as e:
                scenario_error = str(e)

        # 結果を保存
        data["_rich_menu_id"] = rich_menu_id
        data["_form_id"] = form_id
        data["_shinsatsu_form_id"] = shinsatsu_form_id
        data["_google_review_url"] = google_review_url
        save_hearing(slug, data)

        return {
            "success": True,
            "rich_menu_id": rich_menu_id,
            "form_id": form_id,
            "google_review_url": google_review_url or "（Google Places APIキー未設定のため未取得）",
            "qr_url": scenario_result["qr_url"] if scenario_result else None,
            "ref_code": scenario_result["ref_code"] if scenario_result else None,
            "checkin_qr_url": scenario_result["checkin_qr_url"] if scenario_result else None,
            "dashboard_url": f"/{slug}/dashboard/{data.get('_dashboard_token', '')}",
            "scenario_error": scenario_error or None,
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}\n{traceback.format_exc()}")


def _render_flex_preview(content: str) -> str:
    """Flex JSONをHTML視覚プレビューに変換"""
    try:
        flex = json.loads(content)
        header = flex.get("header", {})
        body   = flex.get("body", {})
        footer = flex.get("footer", {})
        parts  = []

        hc = header.get("contents", [])
        if hc:
            bg   = header.get("backgroundColor", "#2C4A7C")
            text = hc[0].get("text", "")
            parts.append(f'<div style="background:{bg};color:#fff;padding:8px 12px;font-size:13px;font-weight:700;text-align:center;border-radius:6px 6px 0 0">{text}</div>')

        bc = body.get("contents", [])
        body_html = ""
        for item in bc:
            if item.get("type") == "text":
                sz  = "18px" if item.get("size") == "xxl" else "12px"
                fw  = "700"  if item.get("weight") == "bold" else "400"
                col = item.get("color", "#333")
                body_html += f'<div style="font-size:{sz};font-weight:{fw};color:{col};text-align:center;padding:3px 0">{item["text"]}</div>'
        if body_html:
            parts.append(f'<div style="background:#fff;padding:10px 12px;border-left:1px solid #e0e6f0;border-right:1px solid #e0e6f0">{body_html}</div>')

        fc2 = footer.get("contents", [])
        if fc2:
            btn   = fc2[0]
            label = btn.get("action", {}).get("label", "ボタン")
            col   = btn.get("color", "#2C4A7C")
            parts.append(f'<div style="padding:8px;border:1px solid #e0e6f0;border-top:none;border-radius:0 0 6px 6px;background:#fafbfc"><div style="background:{col};color:#fff;padding:8px 0;border-radius:4px;text-align:center;font-size:13px;font-weight:600">{label}</div></div>')

        if not parts:
            return '[Flex]'
        return f'<div style="border:1px solid #ddd;border-radius:6px;overflow:hidden;max-width:280px;margin-top:6px">{"".join(parts)}</div>'
    except Exception:
        return f'<span style="font-size:11px;color:#aaa">[Flex]</span>'


@app.get("/{slug}/dashboard/{token}", response_class=HTMLResponse)
async def get_dashboard(slug: str, token: str):
    """クライアントダッシュボード"""
    data = get_hearing(slug)
    if data is None:
        raise HTTPException(status_code=404, detail="LP情報が見つかりません")
    if data.get("_dashboard_token") != token:
        raise HTTPException(status_code=403, detail="URLが正しくありません")

    harness_url_val = os.getenv("LINE_HARNESS_API_URL", "https://line-crm-worker.marunage-crm.workers.dev")
    harness_key_val = os.getenv("LINE_HARNESS_API_KEY", "")
    headers = {"Authorization": f"Bearer {harness_key_val}", "Content-Type": "application/json"}

    # シナリオステップ取得（このクライアントのIDのみ）
    scenarios_html = ""
    scenario_ids = data.get("_scenario_ids", [])
    if harness_key_val and scenario_ids:
        try:
            for sid in scenario_ids:
                res = httpx.get(
                    f"{harness_url_val}/api/scenarios/{sid}",
                    headers=headers,
                    timeout=10,
                )
                if not res.is_success:
                    continue
                s = res.json().get("data", {})
                steps_html = ""
                for st in sorted(s.get("steps", []), key=lambda x: x.get("stepOrder", 0)):
                    delay    = st.get("delayMinutes", 0)
                    hour     = st.get("deliveryHour")
                    hour_str = f" {hour}時" if hour is not None else ""
                    if delay == 0 and hour is None:
                        delay_label = "即時"
                    elif delay == 0:
                        delay_label = f"当日{hour_str}"
                    else:
                        delay_label = f"+{delay // 1440}日後{hour_str}"
                    import html as _html
                    msg_type = st.get("messageType", "text")
                    raw_content = st.get("messageContent", "")
                    step_id = st.get("id", "")
                    escaped = _html.escape(raw_content)
                    if msg_type == "flex":
                        content_html = _render_flex_preview(raw_content)
                        edit_btn = ""
                        editor_html = ""
                    else:
                        content_html = raw_content.replace("\n", "<br>")
                        edit_btn = f"""<button class="step-edit-btn" onclick="editStep(this)" data-scenario-id="{sid}" data-step-id="{step_id}" data-content="{escaped}">編集</button>"""
                        editor_html = f"""<div class="step-editor" id="step-editor-{step_id}" style="display:none;">
                        <textarea class="step-textarea" id="step-ta-{step_id}">{escaped}</textarea>
                        <div class="step-editor-actions">
                          <button class="btn-save-step" onclick="saveStep('{sid}','{step_id}')">保存</button>
                          <button class="btn-cancel-step" onclick="cancelEdit('{step_id}')">キャンセル</button>
                        </div>
                      </div>"""
                    steps_html += f"""<div class="step-item" data-step-id="{step_id}" data-scenario-id="{sid}">
                      <div class="step-item-header">
                        <span class="step-badge">STEP {st.get('stepOrder', '')}</span>
                        <span class="step-timing">{delay_label}</span>
                        {edit_btn}
                      </div>
                      <div class="step-content" id="step-content-{step_id}">{content_html}</div>
                      {editor_html}
                    </div>"""
                trigger = s.get("triggerType", "")
                trigger_label = {"friend_add": "友だち追加時", "tag_added": "タグ付与時"}.get(trigger, trigger)
                scenarios_html += f"""<details class="scenario-block">
                  <summary>{s.get('name', '')} <span class="trigger-badge">{trigger_label}</span></summary>
                  <div class="steps-wrap">{steps_html}</div>
                </details>"""
        except Exception:
            scenarios_html = "<p style='color:#888;font-size:13px;'>シナリオ情報を取得できませんでした</p>"
    elif not scenario_ids:
        scenarios_html = "<p style='color:#888;font-size:13px;'>LINE設定完了後にシナリオが表示されます</p>"

    # ── リマインダーシナリオ（次回予約）の表示 ────────────────────────
    import html as _html
    reminder_id = data.get("_reminder_id", "")
    shop_name_for_remind = data.get("shop_name", "")
    reminder_html = ""
    if harness_key_val:
        try:
            # リマインダーが未作成なら作成して保存
            if not reminder_id:
                r = httpx.post(
                    f"{harness_url_val}/api/reminders",
                    headers=headers,
                    json={"name": f"シナリオE｜次回予約リマインド【{shop_name_for_remind}】",
                          "lineAccountId": data.get("line_account_id", "")},
                    timeout=10,
                )
                if r.is_success:
                    reminder_id = r.json()["data"]["id"]
                    _msg_3days = (
                        f"{{{{name}}}}さん\n"
                        f"3日後（{{{{next_appointment}}}}）がご来院の日となります。\n\n"
                        f"以下に予約内容の詳細をお送りいたしますので、改めてご確認ください。\n\n"
                        f"お気をつけてご来院くださいませ。"
                    )
                    _msg_today = (
                        f"{{{{name}}}}さん\n"
                        f"本日（{{{{next_appointment}}}}）がご来院の日となります。\n\n"
                        f"以下に予約内容の詳細をお送りいたしますので、改めてご確認ください。\n\n"
                        f"お気をつけてご来院くださいませ。"
                    )
                    for offset, msg in [(-4320, _msg_3days), (0, _msg_today)]:
                        httpx.post(f"{harness_url_val}/api/reminders/{reminder_id}/steps", headers=headers,
                                   json={"offsetMinutes": offset, "messageType": "text", "messageContent": msg}, timeout=10)
                    data["_reminder_id"] = reminder_id
                    save_hearing(slug, data)

            if reminder_id:
                rr = httpx.get(f"{harness_url_val}/api/reminders/{reminder_id}", headers=headers, timeout=10)
                if rr.is_success:
                    rd = rr.json().get("data", {})
                    rsteps_html = ""
                    for rst in sorted(rd.get("steps", []), key=lambda x: x.get("offsetMinutes", 0)):
                        offset_min = rst.get("offsetMinutes", 0)
                        if offset_min < 0:
                            days = abs(offset_min) // 1440
                            timing_label = f"{days}日前"
                        elif offset_min == 0:
                            timing_label = "当日"
                        else:
                            timing_label = f"+{offset_min // 1440}日後"
                        rst_id = rst.get("id", "")
                        raw_c = rst.get("messageContent", "")
                        esc_c = _html.escape(raw_c)
                        rsteps_html += f"""<div class="step-item" data-step-id="{rst_id}">
                          <div class="step-item-header">
                            <span class="step-badge">予約{timing_label}</span>
                            <button class="step-edit-btn" onclick="editReminderStep(this)" data-reminder-id="{reminder_id}" data-step-id="{rst_id}" data-content="{esc_c}">編集</button>
                          </div>
                          <div class="step-content" id="step-content-{rst_id}">{raw_c.replace(chr(10), '<br>')}</div>
                          <div class="step-editor" id="step-editor-{rst_id}" style="display:none;">
                            <textarea class="step-textarea" id="step-ta-{rst_id}">{esc_c}</textarea>
                            <div class="step-editor-actions">
                              <button class="btn-save-step" onclick="saveReminderStep('{reminder_id}','{rst_id}')">保存</button>
                              <button class="btn-cancel-step" onclick="cancelEdit('{rst_id}')">キャンセル</button>
                            </div>
                          </div>
                        </div>"""
                    reminder_html = f"""<details class="scenario-block reminder-block">
                      <summary>シナリオE｜次回予約リマインド【{shop_name_for_remind}】 <span class="trigger-badge reminder-badge">予約日ベース</span></summary>
                      <p style="font-size:12px;color:#888;padding:10px 16px 0;">顧客の次回予約日を入力すると、設定した日数前に自動でLINEが届きます</p>
                      <div class="steps-wrap">{rsteps_html}</div>
                    </details>"""
        except Exception:
            pass
    scenarios_html += reminder_html

    # QRコードURL
    lp_qr_url      = data.get("_qr_url", "")
    checkin_qr_url = data.get("_checkin_qr_url", "")
    lp_url         = data.get("_lp_url", "")
    shop_name      = data.get("shop_name", "")

    qr_api = "https://api.qrserver.com/v1/create-qr-code/?size=200x200&data="

    lp_qr_img      = qr_api + urllib.parse.quote(lp_qr_url)      if lp_qr_url      else ""
    checkin_qr_img = qr_api + urllib.parse.quote(checkin_qr_url) if checkin_qr_url else ""

    def _qr_block(img_url: str, raw_url: str, filename: str) -> str:
        if not img_url:
            return '<div class="no-qr">LINE設定後に生成</div>'
        return f'''<img src="{img_url}" alt="QR">
          <div class="qr-url-text">{raw_url}</div>
          <a class="btn-dl" href="{img_url}" download="{filename}" target="_blank">画像を保存</a>'''

    # LP URLセクション（LINE-onlyの場合は既存LP URLを表示、未設定なら非表示）
    if lp_url:
        lp_url_section = f'''<div class="section">
      <div class="section-title">ホームページ・LP URL</div>
      <div class="lp-url-box"><a href="{lp_url}" target="_blank" rel="noopener">{lp_url}</a></div>
    </div>'''
    else:
        lp_url_section = ""

    html = DASHBOARD_PATH.read_text(encoding="utf-8")
    html = html.replace("{{SHOP_NAME}}", shop_name)
    html = html.replace("{{LP_URL_SECTION}}", lp_url_section)
    html = html.replace("{{LP_QR_BLOCK}}", _qr_block(lp_qr_img, lp_qr_url, "qr_lp.png"))
    html = html.replace("{{CHECKIN_QR_BLOCK}}", _qr_block(checkin_qr_img, checkin_qr_url, "qr_checkin.png"))
    html = html.replace("{{SCENARIOS_HTML}}", scenarios_html)
    return html


@app.get("/{slug}/customers/{token}")
async def get_customers(slug: str, token: str):
    """顧客一覧プロキシ（APIキーをサーバー側で保持）"""
    data = get_hearing(slug)
    if data is None:
        raise HTTPException(status_code=404, detail="Not found")
    if data.get("_dashboard_token") != token:
        raise HTTPException(status_code=403, detail="Forbidden")

    account_id = data.get("line_account_id", "")
    form_id = data.get("_form_id", "")
    shinsatsu_form_id = data.get("_shinsatsu_form_id", "")
    harness_url = os.getenv("LINE_HARNESS_API_URL", "https://line-crm-worker.marunage-crm.workers.dev")
    harness_key = os.getenv("LINE_HARNESS_API_KEY", "")
    if not harness_key or not account_id:
        return {"friends": [], "submissions": {}}

    headers = {"Authorization": f"Bearer {harness_key}", "Content-Type": "application/json"}

    # 友だち一覧
    friends = []
    try:
        res = httpx.get(f"{harness_url}/api/friends?lineAccountId={account_id}&limit=200", headers=headers, timeout=10)
        if res.is_success:
            items = res.json().get("data", {}).get("items", [])
            # line_login_subが設定されているレコードはMessaging API userIdが正しいレコード
            # line_user_idが他レコードのline_login_subと一致する場合は重複（プロバイダーミスマッチで誤作成）→除外
            login_subs = {f.get("lineLoginSub") or f.get("line_login_sub") for f in items if f.get("lineLoginSub") or f.get("line_login_sub")}
            def _meta(f):
                raw = f.get("metadata") or "{}"
                return json.loads(raw) if isinstance(raw, str) else (raw or {})
            friends = [
                {
                    "id": f.get("id"),
                    "display_name": f.get("displayName") or f.get("display_name") or "不明",
                    "picture_url": f.get("pictureUrl") or f.get("picture_url") or "",
                    "checkin_count": _meta(f).get("checkin_count", 0),
                    "next_appointment": _meta(f).get("next_appointment", ""),
                    "created_at": f.get("createdAt") or f.get("created_at") or "",
                }
                for f in items
                if (f.get("lineUserId") or f.get("line_user_id")) not in login_subs
            ]
    except Exception:
        pass

    # フォーム回答（感想・問診票）
    submissions: dict = {}
    for fid_key, fid in [("review", form_id), ("shinsatsu", shinsatsu_form_id)]:
        if not fid:
            continue
        try:
            res = httpx.get(f"{harness_url}/api/forms/{fid}/submissions", headers=headers, timeout=10)
            if res.is_success:
                subs = res.json().get("data", [])
                for s in subs:
                    friend_id = s.get("friendId") or s.get("friend_id") or ""
                    if not friend_id:
                        continue
                    if friend_id not in submissions:
                        submissions[friend_id] = {}
                    raw = s.get("data", {})
                    if isinstance(raw, str):
                        raw = json.loads(raw)
                    submissions[friend_id][fid_key] = {
                        "data": raw,
                        "created_at": s.get("createdAt") or s.get("created_at") or "",
                    }
        except Exception:
            pass

    return {"friends": friends, "submissions": submissions}


@app.post("/{slug}/appointment/{friend_id}/{token}")
async def set_appointment(slug: str, friend_id: str, token: str, request: Request):
    """次回予約日の設定・更新・削除"""
    data = get_hearing(slug)
    if data is None:
        raise HTTPException(status_code=404, detail="Not found")
    if data.get("_dashboard_token") != token:
        raise HTTPException(status_code=403, detail="Forbidden")

    body = await request.json()
    appointment_date = body.get("appointment_date", "").strip()  # "YYYY-MM-DD" or ""
    appointment_time = body.get("appointment_time", "").strip()  # "HH:MM" or ""

    harness_url = os.getenv("LINE_HARNESS_API_URL", "https://line-crm-worker.marunage-crm.workers.dev")
    harness_key = os.getenv("LINE_HARNESS_API_KEY", "")
    if not harness_key:
        raise HTTPException(status_code=500, detail="API key not configured")
    headers = {"Authorization": f"Bearer {harness_key}", "Content-Type": "application/json"}
    shop_name = data.get("shop_name", "")

    # 日本語表示用の日時文字列を生成: "5月25日 14:00" など
    next_appointment_display = ""
    if appointment_date:
        try:
            from datetime import datetime as _dt
            d = _dt.strptime(appointment_date, "%Y-%m-%d")
            next_appointment_display = f"{d.month}月{d.day}日"
            if appointment_time:
                next_appointment_display += f" {appointment_time}"
        except Exception:
            next_appointment_display = appointment_date
            if appointment_time:
                next_appointment_display += f" {appointment_time}"

    # 1. friendのmetadataにnext_appointmentを保存（表示用日本語文字列）
    httpx.put(
        f"{harness_url}/api/friends/{friend_id}/metadata",
        headers=headers,
        json={"next_appointment": next_appointment_display},
        timeout=10,
    )

    # 2. チェックインシナリオ（C・D）を停止 — 予約済みなので再来院促進は不要
    # _checkin_scenario_ids 未設定の場合は _scenario_ids からC・Dを名前で特定して自動補完
    checkin_scenario_ids = data.get("_checkin_scenario_ids", [])
    if not checkin_scenario_ids:
        all_ids = data.get("_scenario_ids", [])
        if all_ids:
            try:
                resolved = []
                for sid in all_ids:
                    r = httpx.get(f"{harness_url}/api/scenarios/{sid}", headers=headers, timeout=5)
                    if r.is_success:
                        name = r.json().get("data", {}).get("name", "")
                        if "シナリオC" in name or "シナリオD" in name:
                            resolved.append(sid)
                if resolved:
                    checkin_scenario_ids = resolved
                    data["_checkin_scenario_ids"] = resolved
                    save_hearing(slug, data)
            except Exception:
                pass
    for sid in checkin_scenario_ids:
        try:
            httpx.delete(
                f"{harness_url}/api/scenarios/{sid}/enroll/{friend_id}",
                headers=headers, timeout=10,
            )
        except Exception:
            pass

    # 3. 既存リマインダー登録をキャンセル
    try:
        remind_res = httpx.get(f"{harness_url}/api/friends/{friend_id}/reminders", headers=headers, timeout=10)
        if remind_res.is_success:
            for fr in remind_res.json().get("data", []):
                if fr.get("status") == "active":
                    httpx.delete(f"{harness_url}/api/friend-reminders/{fr['id']}", headers=headers, timeout=10)
    except Exception:
        pass

    if not appointment_date:
        return {"success": True, "next_appointment": ""}

    # 4. リマインダーテンプレートを取得または作成
    reminder_id = data.get("_reminder_id", "")
    if not reminder_id:
        r = httpx.post(
            f"{harness_url}/api/reminders",
            headers=headers,
            json={"name": f"次回予約リマインド【{shop_name}】", "lineAccountId": data.get("line_account_id", "")},
            timeout=10,
        )
        if r.is_success:
            reminder_id = r.json()["data"]["id"]
            # ステップ追加: 3日前・当日（{{name}}・{{next_appointment}}で自動挿入）
            msg_3days = (
                f"{{{{name}}}}さん\n"
                f"3日後（{{{{next_appointment}}}}）がご来院の日となります。\n\n"
                f"以下に予約内容の詳細をお送りいたしますので、改めてご確認ください。\n\n"
                f"お気をつけてご来院くださいませ。"
            )
            msg_today = (
                f"{{{{name}}}}さん\n"
                f"本日（{{{{next_appointment}}}}）がご来院の日となります。\n\n"
                f"以下に予約内容の詳細をお送りいたしますので、改めてご確認ください。\n\n"
                f"お気をつけてご来院くださいませ。"
            )
            for offset, msg in [
                (-4320, msg_3days),
                (0,     msg_today),
            ]:
                httpx.post(
                    f"{harness_url}/api/reminders/{reminder_id}/steps",
                    headers=headers,
                    json={"offsetMinutes": offset, "messageType": "text", "messageContent": msg},
                    timeout=10,
                )
            data["_reminder_id"] = reminder_id
            save_hearing(slug, data)

    # 5. 新しいリマインダー登録（targetDateは日付のみ）
    if reminder_id:
        httpx.post(
            f"{harness_url}/api/reminders/{reminder_id}/enroll/{friend_id}",
            headers=headers,
            json={"targetDate": appointment_date},
            timeout=10,
        )

    return {"success": True, "next_appointment": next_appointment_display}


@app.patch("/{slug}/scenario-step/{token}")
async def update_scenario_step(slug: str, token: str, request: Request):
    """シナリオステップの文面更新プロキシ"""
    data = get_hearing(slug)
    if data is None:
        raise HTTPException(status_code=404, detail="Not found")
    if data.get("_dashboard_token") != token:
        raise HTTPException(status_code=403, detail="Forbidden")

    body = await request.json()
    scenario_id = body.get("scenario_id", "")
    step_id = body.get("step_id", "")
    message_content = body.get("message_content", "")
    if not scenario_id or not step_id or not message_content:
        raise HTTPException(status_code=400, detail="scenario_id, step_id, message_content are required")

    # このslugのシナリオか確認
    allowed_ids = data.get("_scenario_ids", [])
    if scenario_id not in allowed_ids:
        raise HTTPException(status_code=403, detail="Scenario not found for this account")

    harness_url = os.getenv("LINE_HARNESS_API_URL", "https://line-crm-worker.marunage-crm.workers.dev")
    harness_key = os.getenv("LINE_HARNESS_API_KEY", "")
    headers = {"Authorization": f"Bearer {harness_key}", "Content-Type": "application/json"}

    res = httpx.put(
        f"{harness_url}/api/scenarios/{scenario_id}/steps/{step_id}",
        headers=headers,
        json={"messageContent": message_content},
        timeout=10,
    )
    if not res.is_success:
        raise HTTPException(status_code=500, detail=f"更新失敗: {res.text}")

    return {"success": True}


@app.patch("/{slug}/reminder-step/{token}")
async def update_reminder_step(slug: str, token: str, request: Request):
    """リマインダーステップの文面更新プロキシ"""
    data = get_hearing(slug)
    if data is None:
        raise HTTPException(status_code=404, detail="Not found")
    if data.get("_dashboard_token") != token:
        raise HTTPException(status_code=403, detail="Forbidden")

    body = await request.json()
    reminder_id = body.get("reminder_id", "")
    step_id = body.get("step_id", "")
    message_content = body.get("message_content", "")
    if not reminder_id or not step_id or not message_content:
        raise HTTPException(status_code=400, detail="reminder_id, step_id, message_content are required")

    if data.get("_reminder_id") != reminder_id:
        raise HTTPException(status_code=403, detail="Reminder not found for this account")

    harness_url = os.getenv("LINE_HARNESS_API_URL", "https://line-crm-worker.marunage-crm.workers.dev")
    harness_key = os.getenv("LINE_HARNESS_API_KEY", "")
    headers = {"Authorization": f"Bearer {harness_key}", "Content-Type": "application/json"}

    # リマインダーステップはDELETE→POSTで更新（PUTエンドポイントがないため）
    # まず既存ステップのoffsetMinutesを取得してから再作成
    rr = httpx.get(f"{harness_url}/api/reminders/{reminder_id}", headers=headers, timeout=10)
    if not rr.is_success:
        raise HTTPException(status_code=500, detail="リマインダー取得失敗")
    steps = rr.json().get("data", {}).get("steps", [])
    target = next((s for s in steps if s.get("id") == step_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Step not found")

    offset = target.get("offsetMinutes", 0)
    msg_type = target.get("messageType", "text")

    # 削除して再作成
    httpx.delete(f"{harness_url}/api/reminders/{reminder_id}/steps/{step_id}", headers=headers, timeout=10)
    res = httpx.post(f"{harness_url}/api/reminders/{reminder_id}/steps", headers=headers,
                     json={"offsetMinutes": offset, "messageType": msg_type, "messageContent": message_content}, timeout=10)
    if not res.is_success:
        raise HTTPException(status_code=500, detail=f"更新失敗: {res.text}")

    return {"success": True}


@app.delete("/admin/clear-all-data")
async def clear_all_data(secret: str = ""):
    """全テストデータを削除（Renderローカル＋Xサーバー両方）"""
    if secret != os.getenv("ADMIN_SECRET", ""):
        raise HTTPException(status_code=403, detail="forbidden")

    # Renderローカルデータ削除
    deleted_local = []
    for d in [HEARING_DIR, PHOTOS_DIR, OUTPUT_DIR]:
        if d.exists():
            for f in d.iterdir():
                if f.is_file():
                    f.unlink()
                    deleted_local.append(f.name)
                elif f.is_dir():
                    shutil.rmtree(f)
                    deleted_local.append(f.name)

    # Xサーバー FTP削除
    host     = os.getenv("XSERVER_FTP_HOST", "")
    user     = os.getenv("XSERVER_FTP_USER", "")
    password = os.getenv("XSERVER_FTP_PASS", "")
    deleted_ftp = []
    ftp_error = ""

    if all([host, user, password]):
        try:
            def _ftp_rmdir_recursive(ftp, path):
                """FTPディレクトリを再帰的に削除"""
                try:
                    ftp.cwd(path)
                except ftplib.error_perm:
                    return
                items = []
                ftp.retrlines("LIST", items.append)
                for item in items:
                    parts = item.split(None, 8)
                    if len(parts) < 9:
                        continue
                    name = parts[8]
                    if name in (".", ".."):
                        continue
                    full = f"{path}/{name}"
                    if item.startswith("d"):
                        _ftp_rmdir_recursive(ftp, full)
                        try:
                            ftp.rmd(full)
                        except Exception:
                            pass
                    else:
                        try:
                            ftp.delete(full)
                        except Exception:
                            pass

            with ftplib.FTP_TLS() as ftp:
                ftp.connect(host, 21, timeout=30)
                ftp.auth()
                ftp.login(user, password)
                ftp.prot_p()
                ftp.set_pasv(True)

                # /lp/ 直下のディレクトリ一覧を取得して全削除
                lp_root = "/lp"
                try:
                    ftp.cwd(lp_root)
                except ftplib.error_perm:
                    ftp_error = f"{lp_root} ディレクトリが見つかりません"
                else:
                    items = []
                    ftp.retrlines("LIST", items.append)
                    for item in items:
                        parts = item.split(None, 8)
                        if len(parts) < 9:
                            continue
                        name = parts[8]
                        if name in (".", ".."):
                            continue
                        full_path = f"{lp_root}/{name}"
                        if item.startswith("d"):
                            _ftp_rmdir_recursive(ftp, full_path)
                            try:
                                ftp.rmd(full_path)
                                deleted_ftp.append(name)
                            except Exception as e:
                                ftp_error += f" rmd({name})失敗: {e}"
                        else:
                            try:
                                ftp.delete(full_path)
                                deleted_ftp.append(name)
                            except Exception as e:
                                ftp_error += f" delete({name})失敗: {e}"
        except Exception as e:
            ftp_error = str(e)

    return {
        "deleted_local": deleted_local,
        "deleted_ftp": deleted_ftp,
        "ftp_error": ftp_error or None,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8080, reload=False)
