"""LP制作代行サービス サーバー"""
import ftplib
import io
import json
import os
import shutil
import urllib.parse
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

load_dotenv()

from lp.generator import generate_lp_copy, SYSTEM_PROMPT
from lp.html_builder import build_lp_html

app = FastAPI(title="LP制作代行サービス")

_BASE     = Path(__file__).parent
FORM_PATH = _BASE / "lp" / "form.html"
PHOTOS_DIR = _BASE / "tmp" / "photos"
OUTPUT_DIR = _BASE / "tmp" / "output"


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

        # 一時ファイルを削除
        try:
            shutil.rmtree(photo_dir)
        except Exception:
            pass

        return {
            "success": True,
            "public_url": public_url,
            "ftp_error": ftp_error,
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}\n{traceback.format_exc()}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8080, reload=False)
