"""LP制作代行サービス サーバー"""
import ftplib
import io
import json
import os
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
LINE_SETUP_PATH = _BASE / "lp" / "line_setup.html"
DASHBOARD_PATH  = _BASE / "lp" / "dashboard.html"
PHOTOS_DIR = _BASE / "tmp" / "photos"
OUTPUT_DIR = _BASE / "tmp" / "output"
HEARING_DIR = _BASE / "tmp" / "hearings"
RICHMENU_IMAGE = _BASE / "static" / "richmenu.png"

HEARING_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(_BASE / "static")), name="static")


def _ftp_deploy(html: str, slug: str) -> str:
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

        # 既存ディレクトリと被った場合はランダム4文字を末尾に付ける
        final_slug = slug
        try:
            ftp.cwd("/" + slug)
            suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
            final_slug = f"{slug}-{suffix}"
        except ftplib.error_perm:
            pass  # ディレクトリなし → そのまま使用

        remote_dir  = "/" + final_slug
        remote_file = remote_dir + "/index.html"
        ftp.mkd(remote_dir)
        ftp.storbinary(f"STOR {remote_file}", io.BytesIO(html.encode("utf-8")))

    return base_url.rstrip("/") + "/" + urllib.parse.quote(final_slug) + "/"


@app.get("/", response_class=HTMLResponse)
async def root():
    return FORM_PATH.read_text(encoding="utf-8")


@app.get("/lp/form", response_class=HTMLResponse)
async def get_form():
    return FORM_PATH.read_text(encoding="utf-8")


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
            query = urllib.parse.quote(f"{shop_name} {address}")
            hearing_dict["map_embed_url"] = f"https://maps.google.com/maps?q={query}&output=embed&z=16"

        # 写真の一時保存
        photo_dir = PHOTOS_DIR / shop_name
        photo_dir.mkdir(parents=True, exist_ok=True)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        photos = {}
        for field_name, upload in [
            ("hero", hero), ("exterior", exterior),
            ("interior", interior), ("staff", staff), ("treatment", treatment),
        ]:
            if upload and upload.filename:
                suffix = Path(upload.filename).suffix or ".jpg"
                dest = photo_dir / f"{field_name}{suffix}"
                with dest.open("wb") as f:
                    shutil.copyfileobj(upload.file, f)
                photos[field_name] = str(dest)

        hearing_dict["photos"] = photos

        # コピー生成
        copy = generate_lp_copy(hearing_dict)

        # HTML生成（画像base64埋め込み）
        html = build_lp_html(hearing_dict, copy, embed_images=True)

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
            (HEARING_DIR / f"{saved_slug}.json").write_text(
                json.dumps(hearing_dict, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as e:
            print(f"⚠️ hearing保存失敗: {e}")

        # 一時ファイルを削除
        try:
            shutil.rmtree(photo_dir)
        except Exception:
            pass

        return {
            "success": True,
            "public_url": public_url,
            "ftp_error": ftp_error,
            "line_setup_url": f"/{url_slug}/line-setup" if public_url else "",
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}\n{traceback.format_exc()}")


@app.get("/lp/hearing/{slug}")
async def get_hearing(slug: str):
    """LP登録済みhearingデータをスラッグで取得"""
    path = HEARING_DIR / f"{slug}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="hearing not found")
    data = json.loads(path.read_text(encoding="utf-8"))
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
    path = HEARING_DIR / f"{slug}.json"
    if not path.exists():
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
        path = HEARING_DIR / f"{slug}.json"
        if not path.exists():
            raise HTTPException(status_code=404, detail="LP情報が見つかりません")
        data = json.loads(path.read_text(encoding="utf-8"))

        shop_name_for_account = data.get("shop_name", slug)
        harness_url_val = os.getenv("LINE_HARNESS_API_URL", "https://line-crm-worker.uchiyama1128.workers.dev")
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

        form_description = json.dumps({
            "google_maps_url": google_review_url,
            "coupon_text": review_coupon_text,
            "revisit_coupon_text": revisit_coupon_text,
            "revisit_coupon_timing_days": revisit_coupon_timing,
        }, ensure_ascii=False)

        if not harness_key:
            # APIキー未設定の場合はフォーム作成をスキップ
            pass
        elif form_id:
            # 既存フォームを更新
            httpx.put(
                f"{harness_url}/api/forms/{form_id}",
                headers={"Authorization": f"Bearer {harness_key}", "Content-Type": "application/json"},
                json={"description": form_description},
                timeout=10,
            )
        else:
            # 新規フォーム作成
            form_res = httpx.post(
                f"{harness_url}/api/forms",
                headers={"Authorization": f"Bearer {harness_key}", "Content-Type": "application/json"},
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

        # 口コミボタンのLIFF URL（クライアント専用フォームID）
        liff_base = os.getenv("LIFF_URL", "https://liff.line.me/2009607643-QGWpmKya")
        review_form_url = f"{liff_base}?page=review&formId={form_id}" if form_id else f"{liff_base}?page=review"

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
        harness_worker_url = os.getenv("LINE_HARNESS_API_URL", "https://line-crm-worker.uchiyama1128.workers.dev")
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
                survey_url_for_scenario = data.get("survey_url", "")
                liff_url = os.getenv("LIFF_URL", "https://liff.line.me/2009607643-QGWpmKya")
                scenario_result = build_scenarios_for_client(
                    harness_url=harness_url_base,
                    harness_key=harness_key,
                    line_account_id=data["line_account_id"],
                    shop_name=shop_name,
                    owner_name=owner_name,
                    booking_url=booking_url_for_scenario,
                    survey_url=survey_url_for_scenario,
                    review_url=google_review_url or "",
                    form_url=review_form_url,
                    slug=slug,
                    liff_url=liff_url,
                )
                data["_qr_url"]           = scenario_result["qr_url"]
                data["_entry_route_id"]   = scenario_result["entry_route_id"]
                data["_checkin_qr_url"]   = scenario_result["checkin_qr_url"]
                data["_checkin_route_id"] = scenario_result["checkin_route_id"]
            except Exception as e:
                scenario_error = str(e)

        # 結果を保存
        data["_rich_menu_id"] = rich_menu_id
        data["_form_id"] = form_id
        data["_google_review_url"] = google_review_url
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        return {
            "success": True,
            "rich_menu_id": rich_menu_id,
            "form_id": form_id,
            "google_review_url": google_review_url or "（Google Places APIキー未設定のため未取得）",
            "qr_url": scenario_result["qr_url"] if scenario_result else None,
            "ref_code": scenario_result["ref_code"] if scenario_result else None,
            "checkin_qr_url": scenario_result["checkin_qr_url"] if scenario_result else None,
            "dashboard_url": f"/{slug}/dashboard",
            "scenario_error": scenario_error or None,
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}\n{traceback.format_exc()}")


@app.get("/{slug}/dashboard", response_class=HTMLResponse)
async def get_dashboard(slug: str):
    """クライアントダッシュボード"""
    path = HEARING_DIR / f"{slug}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="LP情報が見つかりません")
    data = json.loads(path.read_text(encoding="utf-8"))

    harness_url_val = os.getenv("LINE_HARNESS_API_URL", "https://line-crm-worker.uchiyama1128.workers.dev")
    harness_key_val = os.getenv("LINE_HARNESS_API_KEY", "")
    headers = {"Authorization": f"Bearer {harness_key_val}", "Content-Type": "application/json"}

    # シナリオステップ取得
    scenarios_html = ""
    if harness_key_val and data.get("line_account_id"):
        try:
            res = httpx.get(
                f"{harness_url_val}/api/scenarios",
                headers=headers,
                params={"lineAccountId": data["line_account_id"]},
                timeout=10,
            )
            if res.is_success:
                for s in res.json().get("data", []):
                    steps_res = httpx.get(
                        f"{harness_url_val}/api/scenarios/{s['id']}/steps",
                        headers=headers,
                        timeout=10,
                    )
                    steps_html = ""
                    if steps_res.is_success:
                        for st in sorted(steps_res.json().get("data", []), key=lambda x: x.get("stepOrder", 0)):
                            delay = st.get("delayMinutes", 0)
                            delay_label = "即時" if delay == 0 else f"{delay // 1440}日後 {st.get('deliveryHour', '')}時"
                            content = st.get("messageContent", "").replace("\n", "<br>")
                            steps_html += f"""<div class="step-item">
                              <span class="step-badge">STEP {st.get('stepOrder', '')}</span>
                              <span class="step-timing">{delay_label}</span>
                              <div class="step-content">{content}</div>
                            </div>"""
                    trigger = s.get("triggerType", "")
                    trigger_label = {"friend_add": "友だち追加時", "tag_added": "タグ付与時"}.get(trigger, trigger)
                    scenarios_html += f"""<details class="scenario-block">
                      <summary>{s['name']} <span class="trigger-badge">{trigger_label}</span></summary>
                      <div class="steps-wrap">{steps_html}</div>
                    </details>"""
        except Exception:
            scenarios_html = "<p style='color:#888;font-size:13px;'>シナリオ情報を取得できませんでした</p>"

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

    html = DASHBOARD_PATH.read_text(encoding="utf-8")
    html = html.replace("{{SHOP_NAME}}", shop_name)
    html = html.replace("{{LP_URL}}", lp_url)
    html = html.replace("{{LP_QR_BLOCK}}", _qr_block(lp_qr_img, lp_qr_url, "qr_lp.png"))
    html = html.replace("{{CHECKIN_QR_BLOCK}}", _qr_block(checkin_qr_img, checkin_qr_url, "qr_checkin.png"))
    html = html.replace("{{SCENARIOS_HTML}}", scenarios_html)
    return html


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
