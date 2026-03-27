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
    host     = os.getenv("XSERVER_FTP_HOST", "")
    user     = os.getenv("XSERVER_FTP_USER", "")
    password = os.getenv("XSERVER_FTP_PASS", "")
    base_url = os.getenv("XSERVER_BASE_URL", "https://visionroom.jp/lp/")

    if not all([host, user, password]):
        raise ValueError("FTP認証情報が設定されていません")

    remote_dir  = "/" + slug
    remote_file = remote_dir + "/index.html"

    with ftplib.FTP_TLS() as ftp:
        ftp.connect(host, 21, timeout=30)
        ftp.auth()
        ftp.login(user, password)
        ftp.prot_p()
        ftp.set_pasv(True)
        try:
            ftp.mkd(remote_dir)
        except ftplib.error_perm:
            pass
        ftp.storbinary(f"STOR {remote_file}", io.BytesIO(html.encode("utf-8")))

    return base_url.rstrip("/") + "/" + urllib.parse.quote(slug) + "/"


@app.get("/", response_class=HTMLResponse)
async def root():
    return FORM_PATH.read_text(encoding="utf-8")


@app.get("/lp/form", response_class=HTMLResponse)
async def get_form():
    return FORM_PATH.read_text(encoding="utf-8")


@app.post("/lp/catchcopy")
async def generate_catchcopy(hearing: str = Form(...)):
    hearing_dict: dict = json.loads(hearing)
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    prompt = f"""以下のヒアリングシートをもとに、LPのメインキャッチコピー候補を5つ生成してください。

【ヒアリングシート】
{json.dumps(hearing_dict, ensure_ascii=False, indent=2)}

【要件】
- 各コピーは20〜30文字
- ターゲットの悩みや感情に直接刺さる表現
- 5つはそれぞれ切り口を変える（問いかけ型・断言型・共感型・数字型・ベネフィット型）

【出力形式】
JSONのみ出力してください。
{{"catchcopy_candidates": ["コピー1", "コピー2", "コピー3", "コピー4", "コピー5"]}}"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()

    data = json.loads(raw)
    return {"success": True, "candidates": data.get("catchcopy_candidates", [])}


@app.post("/lp/generate")
async def generate_lp(
    hearing:   str        = Form(...),
    hero:      UploadFile = File(None),
    exterior:  UploadFile = File(None),
    interior:  UploadFile = File(None),
    staff:     UploadFile = File(None),
    treatment: UploadFile = File(None),
):
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
    try:
        public_url = _ftp_deploy(html, url_slug)
    except Exception as e:
        print(f"⚠️ FTPデプロイ失敗: {e}")

    # 一時ファイルを削除
    try:
        shutil.rmtree(photo_dir)
    except Exception:
        pass

    return {
        "success": True,
        "public_url": public_url,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8080, reload=False)
