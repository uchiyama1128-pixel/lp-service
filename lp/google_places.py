"""Google Places API — 店名+住所からPlace IDと口コミURLを取得"""
import urllib.parse
import httpx


def get_review_url(shop_name: str, address: str, api_key: str) -> tuple[str, str]:
    """
    店名と住所からGoogleマップの口コミ投稿URLを返す。

    Returns:
        (place_id, review_url)  — 見つからない場合は ("", "")
    """
    if not api_key:
        return "", ""

    query = f"{shop_name} {address}".strip()
    params = {
        "query": query,
        "key": api_key,
        "language": "ja",
        "fields": "place_id,name,formatted_address",
    }
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"

    try:
        res = httpx.get(url, params=params, timeout=10)
        res.raise_for_status()
        data = res.json()

        if data.get("status") != "OK":
            print(f"Places API: {data.get('status')} — {data.get('error_message', '')}")
            return "", ""

        results = data.get("results", [])
        if not results:
            return "", ""

        place_id = results[0].get("place_id", "")
        if not place_id:
            return "", ""

        review_url = f"https://search.google.com/local/writereview?placeid={place_id}"
        return place_id, review_url

    except Exception as e:
        print(f"Places API エラー: {e}")
        return "", ""
