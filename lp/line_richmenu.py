"""LINE リッチメニュー作成モジュール"""
import urllib.parse
import httpx


LINE_API = "https://api.line.me/v2/bot"
LINE_DATA_API = "https://api-data.line.me/v2/bot"

RICHMENU_WIDTH = 2500
RICHMENU_HEIGHT = 1686
CELL_W1 = 833   # 列1・3の幅
CELL_W2 = 834   # 列2の幅（中央）
CELL_H = 843    # 行の高さ


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def build_areas(
    treatment_url: str,
    homepage_url: str,
    booking_url: str,
    review_form_url: str,
    map_url: str,
    phone: str,
) -> list:
    """6エリアのアクション定義を返す"""
    return [
        # Row 1
        {
            "bounds": {"x": 0, "y": 0, "width": CELL_W1, "height": CELL_H},
            "action": {"type": "uri", "label": "施術内容", "uri": treatment_url},
        },
        {
            "bounds": {"x": CELL_W1, "y": 0, "width": CELL_W2, "height": CELL_H},
            "action": {"type": "uri", "label": "ホームページ", "uri": homepage_url},
        },
        {
            "bounds": {"x": CELL_W1 + CELL_W2, "y": 0, "width": CELL_W1, "height": CELL_H},
            "action": {"type": "uri", "label": "LINEで予約", "uri": booking_url},
        },
        # Row 2
        {
            "bounds": {"x": 0, "y": CELL_H, "width": CELL_W1, "height": CELL_H},
            "action": {
                "type": "uri",
                "label": "口コミでクーポンプレゼント",
                "uri": review_form_url,
            },
        },
        {
            "bounds": {"x": CELL_W1, "y": CELL_H, "width": CELL_W2, "height": CELL_H},
            "action": {"type": "uri", "label": "地図", "uri": map_url},
        },
        {
            "bounds": {"x": CELL_W1 + CELL_W2, "y": CELL_H, "width": CELL_W1, "height": CELL_H},
            "action": {"type": "uri", "label": "電話お問い合わせ", "uri": f"tel:{phone}"},
        },
    ]


def create_richmenu(token: str, areas: list, shop_name: str) -> str:
    """リッチメニューを作成してIDを返す"""
    payload = {
        "size": {"width": RICHMENU_WIDTH, "height": RICHMENU_HEIGHT},
        "selected": True,
        "name": f"{shop_name} リッチメニュー",
        "chatBarText": "メニューを開く",
        "areas": areas,
    }
    res = httpx.post(f"{LINE_API}/richmenu", headers=_headers(token), json=payload, timeout=15)
    res.raise_for_status()
    return res.json()["richMenuId"]


def upload_richmenu_image(token: str, richmenu_id: str, image_path: str) -> None:
    """リッチメニュー画像をアップロードする"""
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "image/png",
    }
    res = httpx.post(
        f"{LINE_DATA_API}/richmenu/{richmenu_id}/content",
        headers=headers,
        content=image_bytes,
        timeout=30,
    )
    res.raise_for_status()


def set_default_richmenu(token: str, richmenu_id: str) -> None:
    """デフォルトリッチメニューとして設定する"""
    res = httpx.post(
        f"{LINE_API}/user/all/richmenu/{richmenu_id}",
        headers=_headers(token),
        timeout=15,
    )
    res.raise_for_status()


def setup_richmenu(
    token: str,
    shop_name: str,
    treatment_url: str,
    homepage_url: str,
    booking_url: str,
    review_form_url: str,
    map_url: str,
    phone: str,
    image_path: str,
) -> str:
    """リッチメニューの作成・画像アップロード・デフォルト設定を一括実行。richMenuIdを返す"""
    areas = build_areas(treatment_url, homepage_url, booking_url, review_form_url, map_url, phone)
    richmenu_id = create_richmenu(token, areas, shop_name)
    upload_richmenu_image(token, richmenu_id, image_path)
    set_default_richmenu(token, richmenu_id)
    return richmenu_id
