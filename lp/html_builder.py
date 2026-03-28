"""生成されたコピーをもとにLP HTMLを構築するモジュール"""
import os
import base64
import mimetypes
from pathlib import Path

_OUTPUT_DIR = Path(__file__).parent / "output"

def _to_html_path(photo_path: str) -> str:
    """CWD相対パスをHTML出力ディレクトリからの相対パスに変換する"""
    abs_photo = Path(photo_path).resolve()
    return os.path.relpath(abs_photo, _OUTPUT_DIR)

def _to_data_uri(photo_path: str) -> str:
    """画像ファイルをbase64 data URIに変換する（サーバーアップ用）"""
    p = Path(photo_path).resolve()
    mime, _ = mimetypes.guess_type(str(p))
    mime = mime or "image/jpeg"
    data = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


COLOR_THEMES = {
    "natural_green": {"primary": "#4A7C59", "accent": "#f67f37"},
    "trust_navy":    {"primary": "#2C4A7C", "accent": "#f67f37"},
    "warm_beige":    {"primary": "#C4956A", "accent": "#e05c6e"},
    "clear_sky":     {"primary": "#4A90C4", "accent": "#f67f37"},
    "elegant_rose":  {"primary": "#C4607A", "accent": "#f67f37"},
    "deep_brown":    {"primary": "#6B4C3B", "accent": "#f67f37"},
}


def build_lp_html(hearing: dict, copy: dict, embed_images: bool = False) -> str:
    shop_name    = hearing.get("shop_name", "")
    shop_type    = hearing.get("shop_type", "")
    location     = hearing.get("location", "")
    phone        = hearing.get("phone", "")
    line_url      = hearing.get("line_url", "#")
    booking_url   = hearing.get("booking_url", "")
    map_embed_url = hearing.get("map_embed_url", "")
    coupon        = hearing.get("coupon", {})
    photos       = hearing.get("photos", {})
    business_hours = hearing.get("business_hours", "")
    owner_name    = hearing.get("owner_name", "")
    owner_message = hearing.get("owner_message", "")
    owner_qualifications = hearing.get("owner_qualifications", "")
    # cta_type はリスト or 文字列どちらでも受け付ける
    _cta_raw  = hearing.get("cta_type", ["line"])
    cta_types = _cta_raw if isinstance(_cta_raw, list) else [_cta_raw]

    theme_key = hearing.get("color_theme", "natural_green")
    theme = COLOR_THEMES.get(theme_key, COLOR_THEMES["natural_green"])
    color_primary = theme["primary"]
    color_accent  = theme["accent"]

    cta_s        = copy.get("cta_section", {})
    pain         = copy.get("pain_section", {})
    solution     = copy.get("solution_section", {})
    achievements = copy.get("achievements_section", {})
    testimonials = copy.get("testimonials_section", {})
    menu_s       = copy.get("menu_section", {})
    faq_sec      = copy.get("faq_section", {})

    coupon_offer  = coupon.get("offer", "")
    coupon_btn    = f"LINEで{coupon.get('title','初回限定クーポン')}を受け取る" if coupon else "LINEで無料相談"
    cta_button    = coupon_btn
    cta_headline = cta_s.get("headline", "")
    cta_body     = cta_s.get("body", "")
    cta_note     = cta_s.get("note", "")

    def photo_exists(key: str) -> bool:
        p = photos.get(key, "")
        return bool(p and Path(p).exists())

    def photo_url(key: str) -> str:
        p = photos.get(key, "")
        if not p:
            return ""
        if embed_images:
            return _to_data_uri(p)
        return _to_html_path(p)

    # ヒーロー：2カラム（左:テキスト白背景 / 右:写真＋境界にほんの少しフェード）
    hero_has_photo  = photo_exists("hero")
    hero_photo_path = photo_url("hero") if hero_has_photo else ""
    hero_text_color  = "#1a1a1a"
    hero_label_style = f"color: {color_primary}; border: 1px solid {color_primary};"
    hero_sub_style   = "color: #444;"
    if hero_has_photo:
        hero_img_html = f"""<div class="hero-img-col">
        <div class="hero-img-fade"></div>
        <img src="{hero_photo_path}" alt="{shop_name}" class="hero-img">
      </div>"""
    else:
        hero_img_html = ""

    # CTAボタンHTML生成（cta_types の選択に基づく）
    def _cta_buttons(line_cls="btn-cta-line", tel_cls="btn-cta-tel", booking_cls="btn-cta-line") -> str:
        btns = ""
        if "line" in cta_types:
            btns += f'<a href="{line_url}" class="{line_cls}">▶ {cta_button}</a>'
        if "booking" in cta_types and booking_url:
            btns += f'<a href="{booking_url}" class="{booking_cls}">📅 Web予約はこちら</a>'
        if "phone" in cta_types and phone:
            btns += f'<a href="tel:{phone}" class="{tel_cls}">📞 電話で予約する</a>'
        return btns

    # バッジ（実績から3つ）
    achievement_items = achievements.get("items", [])
    badges_html = ""
    for item in achievement_items[:3]:
        badges_html += f'<div class="hero-badge">{item}</div>'

    # スタッフ写真
    staff_html = ""
    if photo_exists("staff"):
        staff_html = f'<img src="{photo_url("staff")}" alt="院長・スタッフ" class="staff-photo">'

    # 施術写真
    treatment_html = ""
    if photo_exists("treatment"):
        treatment_html = f'<img src="{photo_url("treatment")}" alt="施術風景" class="section-photo">'

    # 外観・内観写真
    gallery_items_html = ""
    for key, alt in [("exterior","外観"),("interior","院内"),("staff","スタッフ"),("treatment","施術")]:
        if photo_exists(key):
            gallery_items_html += f'<img src="{photo_url(key)}" alt="{alt}" class="gallery-img">'

    gallery_section = ""
    if gallery_items_html:
        gallery_section = f"""
  <section class="section">
    <h2 class="section-title">院内・スタッフのご紹介</h2>
    <div class="gallery">{gallery_items_html}</div>
  </section>"""

    # CTAセクション用クーポン価格HTML（f-string内バックスラッシュ回避）
    cta_coupon_price_html = ""
    if coupon and coupon.get("original_price") and coupon.get("coupon_price"):
        orig = coupon["original_price"]
        price = coupon["coupon_price"]
        cta_coupon_price_html = (
            f'<p style="font-size:14px;color:rgba(255,255,255,0.8);margin-top:8px;">'
            f'<s style="opacity:.6;">{orig}</s> → '
            f'<span style="font-size:20px;font-weight:900;">{price}</span></p>'
        )

    # クーポンバナー
    coupon_banner_html = ""
    if coupon:
        meta_items = ""
        if coupon.get("deadline"):
            meta_items += f'<span>{coupon["deadline"]}</span>'
        if coupon.get("limit"):
            meta_items += f'<span>{coupon["limit"]}</span>'
        price_html = ""
        if coupon.get("original_price") and coupon.get("coupon_price"):
            price_html = f"""<div class="coupon-price">
            <span class="coupon-original">{coupon['original_price']}</span>
            <span>→</span>
            <span class="coupon-new">{coupon['coupon_price']}</span>
          </div>"""
        coupon_banner_html = f"""<div class="coupon-banner">
          <span class="coupon-label">{coupon.get('title','初回限定クーポン')}</span>
          <p class="coupon-offer">{coupon.get('offer','')}</p>
          {price_html}
          <p class="coupon-meta">{meta_items}</p>
          <a href="{line_url}" class="btn-cta-line">▶ {cta_button}</a>
          <p style="font-size:12px;color:#999;margin-top:10px;">{coupon.get('note','')}</p>
        </div>"""

    # 悩みリスト
    pain_items_html = "".join(
        f'<li class="pain-item"><span class="pain-check">✗</span>{item}</li>'
        for item in pain.get("items", [])
    )

    # 選ばれる理由（5つ）
    points_html = ""
    for i, p in enumerate(solution.get("points", []), 1):
        points_html += f"""
        <div class="reason-card fadein">
          <div class="reason-num">{i:02d}</div>
          <div class="reason-body">
            <div class="reason-title">{p['title']}</div>
            <div class="reason-text">{p['body']}</div>
          </div>
        </div>"""

    # 実績数字
    stats_html = ""
    for item in achievement_items:
        stats_html += f'<div class="stat-card fadein">{item}</div>'

    # 口コミ
    testimonials_html = ""
    for t in copy.get("testimonials_section", {}).get("items", []):
        testimonials_html += f"""
        <div class="voice-card fadein">
          <p class="voice-comment">「{t['comment']}」</p>
          <p class="voice-name">— {t['name']}</p>
        </div>"""

    # メニュー（アコーディオン）
    menu_accordion_html = ""
    for i, item in enumerate(hearing.get("main_menu", [])):
        open_attr = "open" if i == 0 else ""
        menu_accordion_html += f"""
        <details class="menu-accordion" {open_attr}>
          <summary class="menu-summary">
            <span class="menu-name">{item['name']}</span>
            <span class="menu-price">{item['price']}</span>
          </summary>
          <div class="menu-detail">
            <p>施術時間：{item['time']}</p>
          </div>
        </details>"""

    # FAQ（アコーディオン）
    faq_accordion_html = ""
    for item in hearing.get("faq", []):
        faq_accordion_html += f"""
        <details class="faq-accordion">
          <summary class="faq-q"><span class="faq-icon">Q</span>{item['q']}</summary>
          <div class="faq-a"><span class="faq-icon faq-icon-a">A</span>{item['a']}</div>
        </details>"""

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{shop_name} | {location}の{shop_type}</title>
  <style>
    :root {{
      --green:  {color_primary};
      --orange: {color_accent};
      --navy:   #1e477d;
      --dark:   #1a1a1a;
      --gray:   #f7f7f7;
      --text:   #333;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: "Hiragino Sans", "Noto Sans JP", sans-serif; color: var(--text); line-height: 1.8; }}
    img {{ max-width: 100%; height: auto; display: block; }}
    a {{ text-decoration: none; color: inherit; }}

    /* ===== ハンバーガー ===== */
    .hamburger {{
      display: none; flex-direction: column; justify-content: space-between;
      width: 28px; height: 20px; background: none; border: none; cursor: pointer;
      flex-shrink: 0; padding: 0;
    }}
    .hamburger span {{
      display: block; width: 100%; height: 3px;
      background: var(--green); border-radius: 2px;
    }}
    @media (max-width: 768px) {{
      .hamburger {{ display: flex; }}
    }}

    /* ===== ドロワーメニュー ===== */
    .drawer {{
      position: fixed; top: 0; left: 0; width: 100%; height: 100%;
      background: var(--green); z-index: 1000;
      display: flex; flex-direction: column;
      padding: 24px;
      transform: translateY(-100%);
      transition: transform 0.3s ease;
    }}
    .drawer.open {{ transform: translateY(0); }}
    .drawer-close {{
      align-self: flex-end; background: none; border: none;
      color: #fff; font-size: 28px; cursor: pointer; margin-bottom: 24px;
    }}
    .drawer-nav {{ display: flex; flex-direction: column; gap: 4px; margin-bottom: 32px; }}
    .drawer-link {{
      color: #fff; font-size: 18px; font-weight: 700;
      padding: 14px 0; border-bottom: 1px solid rgba(255,255,255,0.2);
      text-align: center;
    }}
    .drawer-cta {{ text-align: center; }}
    .drawer-cta-label {{ font-size: 13px; color: rgba(255,255,255,0.8); margin-bottom: 8px; }}
    .drawer-btn-tel {{
      display: block; background: #fff; color: var(--green);
      font-size: 17px; font-weight: 700; padding: 16px;
      border-radius: 8px; margin-bottom: 4px;
    }}
    .drawer-btn-line {{
      display: block; background: var(--orange); color: #fff;
      font-size: 15px; font-weight: 700; padding: 16px;
      border-radius: 8px;
    }}
    .drawer-overlay {{
      display: none; position: fixed; inset: 0;
      background: rgba(0,0,0,0.4); z-index: 999;
    }}
    .drawer-overlay.open {{ display: block; }}

    /* ===== グローバルナビ ===== */
    nav.gnav {{
      background: var(--green);
      position: sticky; top: 0; z-index: 190;
      overflow-x: auto; white-space: nowrap;
    }}
    nav.gnav ul {{
      display: flex; list-style: none; justify-content: center;
      max-width: 1200px; margin: 0 auto; padding: 0 16px;
    }}
    nav.gnav ul li a {{
      display: block; color: #fff; font-size: 13px; font-weight: 700;
      padding: 12px 18px; opacity: 0.85; transition: opacity 0.2s;
    }}
    nav.gnav ul li a:hover {{ opacity: 1; background: rgba(0,0,0,0.1); }}

    /* ===== ヘッダー ===== */
    .header-nav-wrap {{ position: sticky; top: 0; z-index: 200; }}
    header {{
      background: #fff; border-bottom: 2px solid var(--green);
      padding: 10px 24px;
      display: flex; align-items: center; justify-content: space-between; gap: 12px;
    }}
    .header-logo-wrap {{ display: flex; flex-direction: column; white-space: nowrap; min-width: 0; flex-shrink: 1; overflow: hidden; }}
    .header-location {{ font-size: 10px; color: #999; line-height: 1; margin-bottom: 2px; white-space: nowrap; }}
    .header-logo {{ font-size: clamp(14px, 3.5vw, 18px); font-weight: 900; color: var(--green); line-height: 1; white-space: nowrap; }}
    .header-btns {{ display: flex; gap: 8px; flex-shrink: 0; }}
    @media (max-width: 768px) {{
      .header-btns {{ display: none; }}
      .gnav {{ display: none; }}
    }}
    .btn-tel {{
      background: var(--green); color: #fff;
      font-size: 13px; font-weight: 700;
      padding: 8px 18px; border-radius: 6px;
    }}
    .btn-line {{
      background: var(--orange); color: #fff;
      font-size: 13px; font-weight: 700;
      padding: 8px 18px; border-radius: 6px;
    }}

    /* ===== ヒーロー ===== */
    .hero {{ background: #fff; min-height: 480px; overflow: hidden; }}
    .hero-layout {{
      display: flex; align-items: stretch; min-height: 480px;
    }}
    .hero-text-col {{
      flex: 1; padding: 80px 48px 80px 40px;
      display: flex; flex-direction: column; justify-content: center;
      background: #fff; z-index: 1;
    }}
    .hero-img-col {{
      flex: 1; position: relative; overflow: hidden;
    }}
    .hero-img {{
      width: 100%; height: 100%; object-fit: cover; object-position: center; display: block;
    }}
    .hero-img-fade {{
      position: absolute; top: 0; left: 0; width: 60px; height: 100%; z-index: 1;
      background: linear-gradient(90deg, #fff, transparent);
    }}
    .hero-catch {{ font-size: clamp(24px, 3.5vw, 40px); font-weight: 900; line-height: 1.35; margin-bottom: 16px; color: {hero_text_color}; }}
    .hero-sub {{ font-size: 15px; margin-bottom: 28px; {hero_sub_style} }}
    .hero-badges {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 28px; }}
    .hero-badge {{
      background: var(--green); color: #fff;
      font-size: 12px; font-weight: 700; padding: 5px 14px; border-radius: 50px;
    }}
    .hero-btns {{ display: flex; gap: 12px; flex-wrap: wrap; }}
    .btn-cta-tel {{
      background: #ffde47; color: #1a1a1a;
      font-size: 16px; font-weight: 700; padding: 16px 32px; border-radius: 10px;
    }}
    .btn-cta-line {{
      background: var(--orange); color: #fff;
      font-size: 16px; font-weight: 700; padding: 16px 32px; border-radius: 10px;
    }}

    /* ===== セクション共通 ===== */
    .section {{ padding: 72px 24px; max-width: 800px; margin: 0 auto; }}
    .section-bg {{ background: var(--gray); }}
    .section-title {{
      font-size: clamp(22px, 3.5vw, 30px); font-weight: 900; text-align: center;
      margin-bottom: 12px; color: var(--dark);
    }}
    .section-title::after {{
      content: ""; display: block; width: 48px; height: 4px;
      background: var(--green); margin: 10px auto 0;
    }}
    .section-lead {{ text-align: center; color: #666; margin-bottom: 36px; font-size: 15px; }}

    /* ===== 悩みセクション ===== */
    .pain-list {{ list-style: none; max-width: 600px; margin: 0 auto; }}
    .pain-item {{
      display: flex; align-items: flex-start; gap: 12px;
      background: #fff; margin-bottom: 12px; padding: 16px 20px;
      border-left: 4px solid #e74c3c; border-radius: 4px; font-size: 16px;
    }}
    .pain-check {{ color: #e74c3c; font-weight: 900; font-size: 18px; flex-shrink: 0; }}
    .empathy {{ text-align: center; margin-top: 28px; font-size: 15px; color: #666; font-style: italic; }}

    /* ===== 選ばれる理由 ===== */
    .reasons {{ display: flex; flex-direction: column; gap: 20px; }}
    .reason-card {{
      display: flex; align-items: flex-start; gap: 20px;
      background: #fff; border-radius: 10px; padding: 24px;
      box-shadow: 0 2px 12px rgba(0,0,0,0.06);
    }}
    .reason-num {{
      flex-shrink: 0; width: 48px; height: 48px; border-radius: 50%;
      background: var(--green); color: #fff;
      font-size: 18px; font-weight: 900;
      display: flex; align-items: center; justify-content: center;
    }}
    .reason-body {{ flex: 1; }}
    .reason-title {{ font-size: 16px; font-weight: 700; margin-bottom: 6px; }}
    .reason-text {{ font-size: 14px; color: #555; line-height: 1.7; }}

    /* ===== 実績 ===== */
    .stats {{ display: flex; flex-wrap: wrap; gap: 16px; justify-content: center; }}
    .stat-card {{
      background: var(--navy); color: #fff;
      padding: 20px 28px; border-radius: 10px;
      font-size: 15px; font-weight: 700; text-align: center;
      min-width: 160px;
    }}

    /* ===== ギャラリー ===== */
    .gallery {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; }}
    .gallery-img {{ width: 100%; aspect-ratio: 4/3; object-fit: cover; border-radius: 8px; }}

    /* ===== スタッフ ===== */
    .staff-wrap {{ display: flex; gap: 32px; align-items: flex-start; flex-wrap: wrap; }}
    .staff-photo {{ width: 200px; border-radius: 10px; flex-shrink: 0; }}
    .staff-text {{ flex: 1; min-width: 220px; }}
    .owner-name {{ font-size: 18px; font-weight: 700; margin-bottom: 4px; color: var(--dark); }}
    .owner-quals {{ font-size: 13px; color: #777; margin-bottom: 12px; }}

    /* ===== お客様の声 ===== */
    .voices {{ display: grid; gap: 16px; }}
    .voice-card {{
      background: #fff; border: 1px solid #e0e0e0; border-radius: 10px; padding: 24px;
    }}
    .voice-comment {{ font-size: 15px; margin-bottom: 10px; line-height: 1.8; }}
    .voice-name {{ font-size: 13px; color: #888; text-align: right; }}

    /* ===== メニュー アコーディオン ===== */
    .menu-accordion {{
      background: #fff; border: 1px solid #e0e0e0; border-radius: 8px;
      margin-bottom: 10px; overflow: hidden;
    }}
    .menu-summary {{
      padding: 18px 20px; cursor: pointer; list-style: none;
      display: flex; justify-content: space-between; align-items: center;
      background: var(--green); color: #fff; font-weight: 700;
    }}
    .menu-summary::-webkit-details-marker {{ display: none; }}
    .menu-summary::after {{ content: "＋"; font-size: 18px; }}
    details[open] .menu-summary::after {{ content: "－"; }}
    .menu-price {{ font-size: 18px; font-weight: 900; }}
    .menu-detail {{ padding: 16px 20px; font-size: 14px; color: #555; }}

    /* ===== FAQ アコーディオン ===== */
    .faq-accordion {{
      border-bottom: 1px solid #e0e0e0; overflow: hidden;
    }}
    .faq-q {{
      padding: 18px 0; cursor: pointer; list-style: none;
      font-weight: 700; font-size: 15px;
      display: flex; align-items: flex-start; gap: 12px;
    }}
    .faq-q::-webkit-details-marker {{ display: none; }}
    .faq-a {{
      padding: 0 0 18px 44px; font-size: 14px; color: #555;
      display: flex; gap: 12px;
    }}
    .faq-icon {{
      display: inline-flex; align-items: center; justify-content: center;
      width: 28px; height: 28px; border-radius: 50%;
      background: var(--green); color: #fff; font-weight: 900; font-size: 13px;
      flex-shrink: 0;
    }}
    .faq-icon-a {{ background: var(--orange); }}

    /* ===== クーポンバナー ===== */
    .coupon-banner {{
      background: linear-gradient(135deg, #fff8e1, #fff3cd);
      border: 2px dashed var(--orange); border-radius: 12px;
      padding: 28px 32px; text-align: center; margin: 40px 0;
    }}
    .coupon-label {{
      display: inline-block; background: var(--orange); color: #fff;
      font-size: 12px; font-weight: 700; padding: 3px 14px; border-radius: 50px;
      margin-bottom: 12px; letter-spacing: 0.06em;
    }}
    .coupon-offer {{ font-size: clamp(20px, 3vw, 28px); font-weight: 900; color: #1a1a1a; margin-bottom: 8px; }}
    .coupon-price {{
      display: flex; align-items: center; justify-content: center; gap: 12px;
      margin-bottom: 10px;
    }}
    .coupon-original {{ font-size: 16px; color: #999; text-decoration: line-through; }}
    .coupon-new {{ font-size: 28px; font-weight: 900; color: #e74c3c; }}
    .coupon-meta {{ font-size: 13px; color: #888; margin-bottom: 20px; }}
    .coupon-meta span {{ display: inline-block; margin: 0 8px; }}
    .coupon-meta span::before {{ content: "⚠ "; }}
    .coupon-banner .btn-cta-line {{
      display: block; width: 100%; font-size: clamp(13px, 3.5vw, 16px);
      padding: 16px 12px; white-space: nowrap; overflow: hidden;
      text-overflow: ellipsis;
    }}

    /* ===== CTA セクション ===== */
    .cta-section {{
      background: var(--navy); color: #fff; text-align: center; padding: 80px 24px;
    }}
    .cta-headline {{ font-size: clamp(22px, 4vw, 34px); font-weight: 900; margin-bottom: 16px; }}
    .cta-body {{ font-size: 16px; opacity: 0.88; margin-bottom: 36px; }}
    .cta-btns {{ display: flex; gap: 16px; justify-content: center; flex-wrap: wrap; }}
    .cta-btn-tel {{
      background: #ffde47; color: #1a1a1a;
      font-size: 18px; font-weight: 700; padding: 20px 48px; border-radius: 10px;
    }}
    .cta-btn-line {{
      background: var(--orange); color: #fff;
      font-size: 18px; font-weight: 700; padding: 20px 48px; border-radius: 10px;
    }}
    .cta-note {{ font-size: 13px; opacity: 0.65; margin-top: 16px; }}

    /* ===== アクセス ===== */
    .access-info {{ display: grid; gap: 10px; font-size: 15px; margin-bottom: 32px; }}
    .access-row {{ display: flex; gap: 16px; padding: 12px 0; border-bottom: 1px solid #eee; }}
    .access-label {{ font-weight: 700; color: var(--green); width: 80px; flex-shrink: 0; }}
    .map-wrap {{ border-radius: 12px; overflow: hidden; }}
    .map-wrap iframe {{ width: 100%; height: 360px; border: 0; display: block; }}

    /* ===== フッター ===== */
    footer {{ background: #111; color: #888; text-align: center; padding: 24px; font-size: 13px; }}

    /* ===== アニメーション ===== */
    .fadein {{ opacity: 0; transform: translateY(20px); transition: opacity 0.6s ease, transform 0.6s ease; }}
    .fadein.visible {{ opacity: 1; transform: translateY(0); }}

    /* ===== レスポンシブ ===== */
    @media (max-width: 600px) {{
      .hero-layout {{ flex-direction: column; }}
      .hero-text-col {{ padding: 48px 16px 32px; }}
      .hero-img-col {{ height: 240px; }}
      .hero-img-fade {{ width: 0; height: 40px; width: 100%;
        background: linear-gradient(180deg, #fff, transparent); }}
      .hero-btns {{ flex-direction: column; }}
      .btn-cta-tel, .btn-cta-line {{ text-align: center; }}
      .cta-btns {{ flex-direction: column; align-items: center; }}
      .staff-photo {{ width: 100%; }}
    }}
  </style>
</head>
<body>

  <div class="header-nav-wrap">
  <!-- ヘッダー -->
  <header>
    <div class="header-logo-wrap">
      <span class="header-location">{location} / {shop_type}</span>
      <span class="header-logo">{shop_name}</span>
    </div>
    <div class="header-btns">
      {f'<a href="tel:{phone}" class="btn-tel">📞 {phone}</a>' if phone else ''}
      <a href="{line_url}" class="btn-line">▶ LINEで予約</a>
    </div>
    <!-- ハンバーガーボタン（スマホのみ表示） -->
    <button class="hamburger" id="hamburgerBtn" aria-label="メニューを開く">
      <span></span><span></span><span></span>
    </button>
  </header>

  <!-- グローバルナビ（PC） -->
  <nav class="gnav">
    <ul>
      <li><a href="#reasons">選ばれる理由</a></li>
      <li><a href="#voices">お客様の声</a></li>
      <li><a href="#menu">メニュー・料金</a></li>
      <li><a href="#faq">よくある質問</a></li>
      <li><a href="#access">アクセス</a></li>
    </ul>
  </nav>
  </div>

  <!-- ドロワーメニュー（スマホ） -->
  <div class="drawer" id="drawer">
    <button class="drawer-close" id="drawerClose">✕</button>
    <nav class="drawer-nav">
      <a href="#reasons" class="drawer-link">選ばれる理由</a>
      <a href="#voices" class="drawer-link">お客様の声</a>
      <a href="#menu" class="drawer-link">メニュー・料金</a>
      <a href="#faq" class="drawer-link">よくある質問</a>
      <a href="#access" class="drawer-link">アクセス</a>
    </nav>
    <div class="drawer-cta">
      <p class="drawer-cta-label">電話でのご予約はこちら</p>
      {f'<a href="tel:{phone}" class="drawer-btn-tel">📞 {phone}</a>' if phone else ''}
      <p class="drawer-cta-label" style="margin-top:16px;">24時間受付中</p>
      <a href="{line_url}" class="drawer-btn-line">▶ {coupon_btn}</a>
    </div>
  </div>
  <div class="drawer-overlay" id="drawerOverlay"></div>

  <!-- ヒーロー -->
  <div class="hero">
    <div class="hero-layout">
      <div class="hero-text-col">
        <h1 class="hero-catch">{copy.get('catch_copy', '')}</h1>
        <p class="hero-sub">{copy.get('sub_copy', '')}</p>
        <div class="hero-badges">{badges_html}</div>
        <div class="hero-btns">
          {_cta_buttons()}
        </div>
      </div>
      {hero_img_html}
    </div>
  </div>

  <!-- クーポンバナー（ヒーロー直下） -->
  {f'<div style="max-width:800px;margin:0 auto;padding:0 24px;">{coupon_banner_html}</div>' if coupon_banner_html else ''}

  <!-- 悩みセクション -->
  <div class="section-bg">
    <div class="section">
      <h2 class="section-title">{pain.get('headline', 'こんな悩みありませんか？')}</h2>
      <ul class="pain-list">{pain_items_html}</ul>
      <p class="empathy">{copy.get('empathy_text', '')}</p>
    </div>
  </div>

  <!-- 選ばれる理由 -->
  <div class="section" id="reasons">
    <h2 class="section-title">{shop_name}が選ばれる5つの理由</h2>
    <p class="section-lead">{solution.get('body', '')}</p>
    <div class="reasons">{points_html}</div>
  </div>

  <!-- 実績 -->
  <div class="section-bg">
    <div class="section">
      <h2 class="section-title">{achievements.get('headline', '実績・数字で見る')}</h2>
      <div class="stats">{stats_html}</div>
    </div>
  </div>

  <!-- ギャラリー -->
  {gallery_section}

  <!-- スタッフ・院長あいさつ -->
  {f'''
  <div class="section">
    <h2 class="section-title">院長からのメッセージ</h2>
    <div class="staff-wrap">
      {staff_html}
      <div class="staff-text">
        {'<p class="owner-name">' + owner_name + '</p>' if owner_name else ''}
        {'<p class="owner-quals">' + owner_qualifications + '</p>' if owner_qualifications else ''}
        <p>{owner_message if owner_message else f'当院は{location}で{shop_type}として多くの患者様のお体のお悩みに向き合ってきました。お一人おひとりの状態をしっかりとカウンセリングし、根本的な原因から改善するアプローチで施術しています。お気軽にご相談ください。'}</p>
      </div>
    </div>
  </div>
  ''' if (photo_exists("staff") or owner_name or owner_message) else ''}

  <!-- お客様の声 -->
  <div class="section-bg" id="voices">
    <div class="section">
      <h2 class="section-title">{testimonials.get('headline', 'お客様の声')}</h2>
      <div class="voices">{testimonials_html}</div>
    </div>
  </div>

  <!-- メニュー -->
  <div class="section" id="menu">
    <h2 class="section-title">{menu_s.get('headline', 'メニュー・料金')}</h2>
    <p class="section-lead">{menu_s.get('lead', '')}</p>
    {menu_accordion_html}
  </div>

  <!-- FAQ -->
  <div class="section-bg" id="faq">
    <div class="section">
      <h2 class="section-title">{faq_sec.get('headline', 'よくある質問')}</h2>
      {faq_accordion_html}
    </div>
  </div>

  <!-- CTA -->
  <div class="cta-section">
    <p class="cta-headline">{cta_headline}</p>
    <p class="cta-body">{cta_body}</p>
    {f'''<div style="background:rgba(255,255,255,0.1);border:1px dashed rgba(255,255,255,0.4);border-radius:10px;padding:16px 24px;margin-bottom:24px;display:inline-block;">
      <p style="font-size:13px;color:rgba(255,255,255,0.7);margin-bottom:4px;">{coupon.get("title","初回限定クーポン")}</p>
      <p style="font-size:20px;font-weight:900;color:#fff;">{coupon.get("offer","")}</p>
      {cta_coupon_price_html}
    </div>''' if coupon else ''}
    <div class="cta-btns">
      <a href="{line_url}" class="cta-btn-line">▶ {cta_button}</a>
    </div>
    <p class="cta-note">{coupon.get('note', cta_note)}</p>
  </div>

  <!-- アクセス情報 -->
  <div class="section" id="access">
    <h2 class="section-title">アクセス・診療時間</h2>
    <div class="access-info">
      <div class="access-row"><span class="access-label">院名</span><span>{shop_name}</span></div>
      <div class="access-row"><span class="access-label">住所</span><span>{location}</span></div>
      {f'<div class="access-row"><span class="access-label">電話</span><span>{phone}</span></div>' if phone else ''}
      {f'<div class="access-row"><span class="access-label">営業時間</span><span>{business_hours}</span></div>' if business_hours else ''}
    </div>
    {f'<div class="map-wrap"><iframe src="{map_embed_url}" allowfullscreen loading="lazy" referrerpolicy="no-referrer-when-downgrade"></iframe></div>' if map_embed_url else ''}
  </div>

  <footer>
    <p>{shop_name} &nbsp;{location}&nbsp; &copy; 2025</p>
  </footer>

  <script>
    // スクロールアニメーション
    const observer = new IntersectionObserver((entries) => {{
      entries.forEach(e => {{ if (e.isIntersecting) e.target.classList.add('visible'); }});
    }}, {{ threshold: 0.15 }});
    document.querySelectorAll('.fadein').forEach(el => observer.observe(el));

    // ハンバーガーメニュー
    const drawer = document.getElementById('drawer');
    const overlay = document.getElementById('drawerOverlay');
    const openBtn = document.getElementById('hamburgerBtn');
    const closeBtn = document.getElementById('drawerClose');

    function openDrawer() {{
      drawer.classList.add('open');
      overlay.classList.add('open');
      document.body.style.overflow = 'hidden';
    }}
    function closeDrawer() {{
      drawer.classList.remove('open');
      overlay.classList.remove('open');
      document.body.style.overflow = '';
    }}

    openBtn.addEventListener('click', openDrawer);
    closeBtn.addEventListener('click', closeDrawer);
    overlay.addEventListener('click', closeDrawer);
    document.querySelectorAll('.drawer-link, .drawer-btn-tel, .drawer-btn-line').forEach(el => {{
      el.addEventListener('click', closeDrawer);
    }});
  </script>

</body>
</html>"""
