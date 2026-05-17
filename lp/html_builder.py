"""生成されたコピーをもとにLP HTMLを構築するモジュール"""
import os
import re
import base64
import mimetypes
from pathlib import Path


_PAIN_ASSETS_DIR    = Path(__file__).parent / "assets" / "pain"
_MENU_ASSETS_DIR    = Path(__file__).parent / "assets" / "menu"
_HERO_ASSETS_DIR    = Path(__file__).parent / "assets" / "hero"
_COUPON_BANNER_IMG  = Path(__file__).parent / "assets" / "coupon_banner.png"
_LAUREL_IMG         = Path(__file__).parent / "assets" / "laurel.png"
_REASONS_ASSETS_DIR = Path(__file__).parent / "assets" / "reasons"

# キーワード → イラストファイル名マップ（先にマッチしたものを使用）
_REASON_ILLUST_MAP = [
    (["施術", "手技", "マッサージ", "整体", "鍼", "骨盤", "矯正"],       "treatment"),
    (["カウンセリング", "ヒアリング", "問診", "丁寧な説明", "説明"],       "checklist"),
    (["スタッフ", "専門", "資格", "国家", "経験", "技術", "施術者"],       "staff"),
    (["効果", "改善", "変化", "結果", "喜び", "満足", "実感"],             "result"),
    (["相談", "コミュニケーション", "対応", "寄り添", "お話"],             "consultation"),
    (["家族", "子連れ", "ファミリー", "お子様", "一緒"],                   "family"),
    (["実績", "症例", "確認", "記録", "管理"],                            "checklist"),
    (["予約", "スケジュール", "営業時間", "時間", "営業"],                 "schedule"),
    (["料金", "価格", "費用", "コスト", "お値段", "安心価格"],             "price"),
    (["安心", "信頼", "心", "ケア", "サポート"],                          "care"),
    (["No.1", "1位", "受賞", "評価", "ナンバーワン", "口コミ"],           "award"),
    (["無料", "初回", "0円", "クーポン", "お試し"],                       "free"),
    (["駐車場", "駐車", "車", "カーナビ"],                                "parking"),
    (["駅", "アクセス", "交通", "電車", "バス", "徒歩"],                  "station"),
    (["産後", "赤ちゃん", "育児", "妊娠", "ベビー"],                      "baby"),
    (["バリアフリー", "車椅子", "高齢者", "シニア"],                       "wheelchair"),
    (["衛生", "消毒", "感染", "清潔感", "換気"],                          "hygiene"),
    (["清潔", "綺麗", "整った", "空間"],                                  "clean"),
    (["肩", "首", "肩こり"],                                              "shoulder"),
    (["腰", "腰痛", "ぎっくり"],                                          "back"),
    (["足", "脚", "膝", "むくみ", "ひざ"],                                "leg"),
]

def _match_reason_illust(title: str, body: str = "") -> str:
    """理由テキストにマッチするイラストのパスを返す。タイトル優先、なければbodyも確認。"""
    for text in [title, body]:
        for keywords, key in _REASON_ILLUST_MAP:
            if any(kw in text for kw in keywords):
                p = _REASONS_ASSETS_DIR / f"{key}.png"
                if p.exists():
                    return str(p)
    return ""

_MENU_KEYWORD_MAP = [
    (["肩こり", "肩", "首"],         "katakori"),
    (["腰痛", "腰"],                  "koshi"),
    (["骨盤", "産後"],               "kotsuban"),
    (["脚", "足", "むくみ", "下肢"], "ashi"),
]

def _match_menu_photo(name: str, gender_prefix: str) -> tuple[str, str]:
    """コース名にマッチする (写真パス, ラベルPNGパス) を返す。デフォルトは zentai。"""
    key = "zentai"
    for keywords, k in _MENU_KEYWORD_MAP:
        if any(kw in name for kw in keywords):
            key = k
            break
    col = f"{gender_prefix}_a"
    photo = _MENU_ASSETS_DIR / f"{key}_{col}.jpg"
    label = _MENU_ASSETS_DIR / f"label_{key}.png"
    return (str(photo) if photo.exists() else "", str(label) if label.exists() else "")

_PAIN_KEYWORD_MAP = [
    (["肩こり", "首・肩", "首肩", "肩が凝", "首が痛"], "katakori"),
    (["肩の痛", "肩が痛", "肩に痛"],                   "kata_itami"),
    (["腰", "腰痛"],                                    "koshi_itami"),
    (["疲れ", "だるい", "重い", "疲労", "むくみ"],      "karada_omoi"),
    (["足", "脚", "ひざ", "膝"],                        "ashi_itami"),
    (["猫背", "姿勢", "背中"],                          "neko_ze"),
    (["頭痛", "頭が"],                                  "zutsuu"),
    (["産後", "骨盤"],                                  "sango"),
]

_PAIN_FALLBACK_ORDER = ["katakori", "koshi_itami", "karada_omoi", "kata_itami", "neko_ze", "zutsuu", "ashi_itami"]

def _match_pain_photo(pain_text: str, gender_prefix: str, used: set | None = None) -> str:
    """悩みテキストにマッチする写真パスを返す。使用済み写真は避ける。"""
    if used is None:
        used = set()
    for keywords, key in _PAIN_KEYWORD_MAP:
        if any(kw in pain_text for kw in keywords):
            p = _PAIN_ASSETS_DIR / f"{gender_prefix}_{key}.jpg"
            if p.exists() and str(p) not in used:
                return str(p)
    # fallback: 未使用のものを順番に試す
    for key in _PAIN_FALLBACK_ORDER:
        p = _PAIN_ASSETS_DIR / f"{gender_prefix}_{key}.jpg"
        if p.exists() and str(p) not in used:
            return str(p)
    p = _PAIN_ASSETS_DIR / f"{gender_prefix}_katakori.jpg"
    return str(p) if p.exists() else ""


def _parse_stat(item: str):
    """'施術実績 5,000人以上' → (label='施術実績', num='5,000', unit='人以上')"""
    m = re.search(r'([\d,]+\.?\d*%?)', item)
    if m:
        num   = m.group(1)
        label = item[:m.start()].strip().rstrip('　 ')
        unit  = item[m.end():].strip()
        # コロン・読点・句点以降の説明文を除去
        unit = re.split(r'[：。、\s]{1}', unit)[0].strip()
        return label, num, unit
    return item, "", ""

_OUTPUT_DIR = Path(__file__).parent / "output"

def _to_html_path(photo_path: str) -> str:
    abs_photo = Path(photo_path).resolve()
    return os.path.relpath(abs_photo, _OUTPUT_DIR)

def _to_data_uri(photo_path: str) -> str:
    p = Path(photo_path).resolve()
    mime, _ = mimetypes.guess_type(str(p))
    mime = mime or "image/jpeg"
    data = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


COLOR_THEMES = {
    "natural_green": {"primary": "#4A7C59"},
    "trust_navy":    {"primary": "#2C4A7C"},
    "warm_beige":    {"primary": "#C4956A"},
    "clear_sky":     {"primary": "#4A90C4"},
    "elegant_rose":  {"primary": "#C4607A"},
    "deep_brown":    {"primary": "#6B4C3B"},
    "salon_coral":   {"primary": "#D4714E"},
}

# person icon SVG (アバター用)
_PERSON_SVG = '<svg viewBox="0 0 24 24" fill="white" xmlns="http://www.w3.org/2000/svg" style="width:28px;height:28px;"><path d="M12 12c2.76 0 5-2.24 5-5s-2.24-5-5-5-5 2.24-5 5 2.24 5 5 5zm0 2c-3.33 0-10 1.67-10 5v2h20v-2c0-3.33-6.67-5-10-5z"/></svg>'


def build_lp_html(hearing: dict, copy: dict, embed_images: bool = False) -> str:
    shop_name     = hearing.get("shop_name", "")
    shop_type     = hearing.get("shop_type", "")
    location      = hearing.get("location", "")
    phone         = hearing.get("phone", "")
    line_url      = hearing.get("line_url", "#")
    booking_url   = hearing.get("booking_url", "")
    map_embed_url = hearing.get("map_embed_url", "")
    _coupon       = hearing.get("coupon") or {}
    coupon_title  = hearing.get("coupon_title") or _coupon.get("title", "")
    coupon_orig   = hearing.get("coupon_original_price") or _coupon.get("original_price", "")
    coupon_price  = hearing.get("coupon_price") or _coupon.get("coupon_price", "")
    photos        = hearing.get("photos", {})
    open_hours      = hearing.get("open_hours", "")
    regular_holiday = hearing.get("regular_holiday", "")
    # 旧フォーマット後方互換
    _legacy_bh      = hearing.get("business_hours", "")
    if not open_hours and _legacy_bh:
        open_hours = _legacy_bh
    business_hours  = open_hours  # CTAセクション等の既存参照用
    address       = hearing.get("address", location)
    target        = hearing.get("target", "")
    owner_name    = hearing.get("owner_name", "")
    owner_message = hearing.get("owner_message", "")
    owner_qualifications = hearing.get("owner_qualifications", "")
    _cta_raw  = hearing.get("cta_type", ["line"])
    cta_types = _cta_raw if isinstance(_cta_raw, list) else [_cta_raw]

    theme_key     = hearing.get("color_theme", "natural_green")
    color_primary = COLOR_THEMES.get(theme_key, COLOR_THEMES["natural_green"])["primary"]

    cta_s         = copy.get("cta_section", {})
    pain          = copy.get("pain_section", {})
    solution      = copy.get("solution_section", {})
    achievements  = copy.get("achievements_section", {})
    menu_s        = copy.get("menu_section", {})
    faq_sec       = copy.get("faq_section", {})

    coupon_btn    = "LINEで今すぐクーポンを獲得する" if coupon_title else "LINEで無料相談"
    cta_button    = coupon_btn
    cta_headline  = cta_s.get("headline", "")
    cta_body      = cta_s.get("body", "")
    cta_note      = cta_s.get("note", "")

    def photo_exists(key: str) -> bool:
        p = photos.get(key, "")
        return bool(p and Path(p).exists())

    def photo_url(key: str) -> str:
        p = photos.get(key, "")
        if not p:
            return ""
        return _to_data_uri(p) if embed_images else _to_html_path(p)

    # ── 性別プレフィックス（hero fallback でも使う）────
    _gender_prefix = "f" if any(kw in target for kw in ["女性", "女", "ママ", "産後"]) else "m"

    # ── ヒーロー ──────────────────────────────────────
    hero_has_photo = photo_exists("hero")
    if hero_has_photo:
        _hero_src = photo_url("hero")
    else:
        for _fb in [
            _HERO_ASSETS_DIR / "default.jpg",
            _MENU_ASSETS_DIR / f"zentai_{_gender_prefix}_a.jpg",
        ]:
            if _fb.exists():
                _hero_src = _to_data_uri(str(_fb)) if embed_images else str(_fb)
                break
        else:
            _hero_src = ""
    # ── ヒーロー強み（solutionのpoints先頭3件、なければデフォルト）──
    _hero_strength_titles = [p["title"] for p in solution.get("points", [])[:3]]
    if not _hero_strength_titles:
        _hero_strength_titles = [
            f"丁寧なカウンセリングで根本から改善",
            f"土日祝も対応・完全予約制で通いやすい",
            f"経験豊富なスタッフが一人ひとりに寄り添う",
        ]
    _hero_strengths_html = "".join(
        f'<li class="hero-st-item"><span class="hero-st-icon">✓</span>{t}</li>'
        for t in _hero_strength_titles
    )
    _hero_micro = "＼ 友だち追加・登録無料 ／"

    # ── CTAボタン ──────────────────────────────────────
    def _cta_buttons(line_cls="btn-p", tel_cls="btn-d", booking_cls="btn-o") -> str:
        out = ""
        if "line"    in cta_types:                    out += f'<a href="{line_url}" class="{line_cls}">▶ {cta_button}</a>'
        if "booking" in cta_types and booking_url:    out += f'<a href="{booking_url}" class="{booking_cls}">📅 Web予約</a>'
        if "phone"   in cta_types and phone:          out += f'<div class="tel-cta-wrap" style="align-items:center;"><span class="tel-cta-label">電話でのご予約はこちらから</span><a href="tel:{phone}" class="btn-tel">☎ {phone}</a></div>'
        return out

    _hearing_ach   = [a for a in hearing.get("achievements", []) if a.strip()]
    _ai_ach_items  = achievements.get("items", [])
    achievement_items = _hearing_ach if _hearing_ach else _ai_ach_items

    # ── イントロ右カラム写真 ───────────────────────────
    intro_photo_html = ""
    for key in ["interior", "exterior", "treatment"]:
        if photo_exists(key):
            intro_photo_html = f'<img src="{photo_url(key)}" alt="院内" style="width:100%;height:100%;object-fit:cover;display:block;">'
            break

    # ── お悩みカード ───────────────────────────────────
    pain_items = pain.get("items", [])
    pain_cards_html = ""
    _used_pain_photos: set = set()
    for item in pain_items[:3]:
        # 新形式: {"text": "...", "sub": "..."} / 旧形式: "文字列"
        if isinstance(item, dict):
            _text = item.get("text", "")
            _sub  = item.get("sub", "")
        else:
            _text = item
            _sub  = ""
        _matched_path = _match_pain_photo(_text, _gender_prefix, _used_pain_photos)
        if _matched_path:
            _used_pain_photos.add(_matched_path)
        if _matched_path:
            _src = _to_data_uri(_matched_path) if embed_images else _matched_path
            _circle_inner = f'<img src="{_src}" alt="" class="pain-card-img">'
        else:
            _circle_inner = '<div class="pain-card-img-blank"></div>'
        _sub_html = f'<p class="pain-card-sub">{_sub}</p>' if _sub else ""
        pain_cards_html += f"""
        <div class="pain-card fadein">
          <div class="pain-card-circle-wrap">
            <div class="pain-card-ring"></div>
            <div class="pain-card-circle">{_circle_inner}</div>
          </div>
          <p class="pain-card-text">{_text}</p>
          {_sub_html}
        </div>"""

    # ── 選ばれる理由 ───────────────────────────────────
    _hearing_strengths = [s for s in hearing.get("strengths", []) if s.strip()]
    _ai_points = solution.get("points", [])
    _points = _ai_points[:len(_hearing_strengths)] if _hearing_strengths else _ai_points

    points_html = ""
    for i, p in enumerate(_points, 1):
        _matched = _match_reason_illust(p.get("title", ""), p.get("body", ""))
        if _matched:
            _isrc = _to_data_uri(_matched) if embed_images else _matched
            _illust_html = f'<img src="{_isrc}" alt="" class="reason-illust">'
        else:
            _illust_html = ""
        points_html += f"""
        <div class="reason-card fadein">
          <div class="reason-badge">理由{i}</div>
          <div class="reason-card-body">
            <p class="reason-title">{p['title']}</p>
            <p class="reason-text">{p['body']}</p>
          </div>
          {_illust_html}
        </div>"""

    # ── 実績 ───────────────────────────────────────────
    _laurel_src = _to_data_uri(str(_LAUREL_IMG)) if (embed_images and _LAUREL_IMG.exists()) else str(_LAUREL_IMG)
    stats_html = ""
    for item in achievement_items:
        lbl, num, unit = _parse_stat(item)
        if num:
            stats_html += (
                f'<div class="stat-cell fadein">'
                f'<div class="stat-wreath-wrap">'
                f'<img src="{_laurel_src}" class="stat-wreath-img" alt="">'
                f'<div class="stat-inner">'
                f'<p class="stat-label">{lbl}</p>'
                f'<div class="stat-num-row">'
                f'<p class="stat-num-inner">{num}</p>'
                f'{"<p class=\"stat-unit\">" + unit + "</p>" if unit else ""}'
                f'</div>'
                f'</div>'
                f'</div>'
                f'</div>'
            )
        else:
            stats_html += (
                f'<div class="stat-cell fadein">'
                f'<div class="stat-wreath-wrap">'
                f'<img src="{_laurel_src}" class="stat-wreath-img" alt="">'
                f'<div class="stat-inner"><div class="stat-num-row"><p class="stat-num-inner">{item}</p></div></div>'
                f'</div>'
                f'</div>'
            )

    # ── スタッフ ───────────────────────────────────────
    _staff_bg_path = Path(__file__).parent / "assets" / "staff_card_bg.png"
    _staff_bg_uri  = _to_data_uri(str(_staff_bg_path)) if _staff_bg_path.exists() else ""
    staff_photo_html = (
        f'<img src="{photo_url("staff")}" alt="院長" class="staff-photo">'
        if photo_exists("staff") else ""
    )
    show_staff = photo_exists("owner") or photo_exists("staff") or owner_name or owner_message
    _intro_owner_html = (
        f'<div class="intro-owner-circle"><img src="{photo_url("staff")}" alt="院長"></div>'
        if photo_exists("staff") else ""
    )

    # ── ギャラリー ─────────────────────────────────────
    gallery_html = ""
    for key, alt in [("exterior","外観"),("interior","院内"),("staff","スタッフ"),("treatment","施術")]:
        if photo_exists(key):
            gallery_html += f'<img src="{photo_url(key)}" alt="{alt}" class="gallery-img">'

    # ── 口コミ ─────────────────────────────────────────
    voices_html = ""
    for t in copy.get("testimonials_section", {}).get("items", []):
        voices_html += f"""
        <div class="voice-card fadein">
          <div class="voice-avatar">{_PERSON_SVG}</div>
          <p class="voice-name">{t['name']}</p>
          <p class="voice-comment">{t['comment']}</p>
        </div>"""

    # ── メニューカード ─────────────────────────────────
    menu_cards_html = ""
    for item in hearing.get("main_menu", []):
        _photo_path, _ = _match_menu_photo(item["name"], _gender_prefix)
        if _photo_path:
            _msrc = _to_data_uri(_photo_path) if embed_images else _photo_path
            _mphoto_html = f'<img src="{_msrc}" alt="{item["name"]}" class="menu-card-img">'
        else:
            _mphoto_html = '<div class="menu-card-img-blank"></div>'
        _orig_price = item.get("original_price", "")
        _desc       = item.get("description", "")
        menu_cards_html += f"""
        <div class="menu-card fadein">
          {_mphoto_html}
          <div class="menu-card-inner">
            <p class="menu-card-name">{item['name']}</p>
            {f'<p class="menu-card-desc">{_desc}</p>' if _desc else f'<p class="menu-card-time">{item["time"]}</p>'}
            <div class="menu-card-price-wrap">
              {f'<p class="menu-card-orig">通常 {_orig_price}</p>' if _orig_price else ''}
              <p class="menu-card-price">{item['price']}<span class="menu-card-tax">（税込）</span></p>
            </div>
          </div>
        </div>"""

    # ── FAQ ────────────────────────────────────────────
    faq_html = ""
    for item in hearing.get("faq", []):
        faq_html += f"""
        <details class="faq-item">
          <summary class="faq-q"><span class="faq-icon-q">Q</span>{item['q']}</summary>
          <div class="faq-a"><span class="faq-icon-a">A</span>{item['a']}</div>
        </details>"""

    # ── クーポンバナー ─────────────────────────────────
    coupon_banner_html = ""
    if coupon_title:
        _banner_src = (
            _to_data_uri(str(_COUPON_BANNER_IMG)) if (embed_images and _COUPON_BANNER_IMG.exists())
            else str(_COUPON_BANNER_IMG)
        )
        _orig_overlay = (
            f'<span class="cp-overlay-orig">{coupon_orig}</span>'
            if coupon_orig else ""
        )
        _new_overlay = (
            f'<span class="cp-overlay-new">{coupon_price}</span>'
            if coupon_price else ""
        )
        coupon_banner_html = (
            f'<div class="coupon-banner-wrap" onclick="location.href=\'{line_url}\'" style="cursor:pointer;">'
            f'<img src="{_banner_src}" alt="LINEクーポンバナー">'
            f'{_orig_overlay}{_new_overlay}'
            f'</div>'
        )

    # ── CTA価格表示（ボトムCTA用） ──────────────────────
    cta_price_html = ""
    if coupon_orig and coupon_price:
        cta_price_html = (
            f'<p style="color:rgba(255,255,255,0.8);font-size:14px;margin-top:6px;">'
            f'<s style="opacity:.55;">{coupon_orig}</s>'
            f' → <span style="font-size:20px;font-weight:900;">{coupon_price}</span></p>'
        )

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{shop_name} | {location}の{shop_type}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Josefin+Sans:wght@600;700&family=Noto+Sans+JP:wght@400;600;700;900&family=Noto+Serif+JP:wght@700;900&family=Playfair+Display:ital@1&display=swap" rel="stylesheet">
  <style>
    :root {{
      --p:      {color_primary};
      --dark:   #1a1a1a;
      --cream:  #f5ede0;
      --gray:   #f4f2ef;
      --text:   #444;
      --bd:     #e5ddd5;
      --sans:   "Noto Sans JP", "Hiragino Sans", sans-serif;
      --serif:  "Noto Serif JP", serif;
      --latin:  "Josefin Sans", sans-serif;
    }}
    *  {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: var(--sans); color: var(--text); line-height: 1.8; background: #fff; }}
    img  {{ max-width: 100%; height: auto; display: block; }}
    a    {{ text-decoration: none; color: inherit; }}

    /* ─── HEADER ──────────────────────────────────── */
    .hdr-wrap {{ position: sticky; top: 0; z-index: 200; background: #fff; border-bottom: 1px solid var(--bd); box-shadow: 0 1px 8px rgba(0,0,0,0.05); }}
    .hdr {{ max-width: 1400px; margin: 0 auto; padding: 10px 24px; display: flex; align-items: center; justify-content: space-between; gap: 12px; }}
    .hdr-logo {{ display: flex; flex-direction: column; gap: 6px; flex-shrink: 0; }}
    .hdr-logo-eyebrow {{ font-size: 9px; color: var(--p); letter-spacing: 0.12em; line-height: 1; font-weight: 600; }}
    .hdr-logo-en  {{ font-family: var(--latin); font-size: 18px; font-weight: 700; color: var(--dark); letter-spacing: 0.12em; line-height: 1; }}
    .hdr-nav {{ display: flex; list-style: none; flex-wrap: nowrap; white-space: nowrap; }}
    .hdr-nav a {{ font-size: 12px; color: #666; padding: 6px 8px; display: block; transition: color .2s; }}
    .hdr-nav a:hover {{ color: var(--p); }}
    .hdr-right {{ display: flex; align-items: center; gap: 16px; flex-shrink: 0; }}
    .hdr-tel-label {{ font-size: 9px; color: #bbb; text-align: right; }}
    .hdr-tel {{ font-family: var(--latin); font-size: 19px; font-weight: 700; color: var(--dark); letter-spacing: 0.04em; }}
    .hdr-btn {{ background: var(--p); color: #fff; font-size: 12px; font-weight: 700; padding: 9px 18px; border-radius: 4px; white-space: nowrap; }}
    .hamburger {{ display: none; flex-direction: column; justify-content: space-between; width: 26px; height: 18px; background: none; border: none; cursor: pointer; padding: 0; }}
    .hamburger span {{ display: block; width: 100%; height: 2.5px; background: var(--dark); border-radius: 2px; }}
    @media (max-width: 900px) {{ .hdr-nav, .hdr-right {{ display: none; }} .hamburger {{ display: flex; }} }}

    /* ─── DRAWER ──────────────────────────────────── */
    .drawer {{ position: fixed; top: 0; right: 0; width: min(300px,90%); height: 100%; background: var(--dark); z-index: 1000; display: flex; flex-direction: column; padding: 24px; transform: translateX(100%); transition: transform .3s ease; overflow-y: auto; }}
    .drawer.open {{ transform: translateX(0); }}
    .drawer-close {{ align-self: flex-end; background: none; border: none; color: #fff; font-size: 26px; cursor: pointer; margin-bottom: 24px; }}
    .drawer-nav {{ display: flex; flex-direction: column; margin-bottom: 32px; }}
    .drawer-link {{ color: #fff; font-size: 15px; font-weight: 600; padding: 14px 0; border-bottom: 1px solid rgba(255,255,255,.1); }}
    .drawer-cta {{ display: flex; flex-direction: column; gap: 12px; }}
    .drawer-btn-p {{ display: block; background: var(--p); color: #fff; font-size: 15px; font-weight: 700; padding: 14px; border-radius: 8px; text-align: center; }}
    .drawer-btn-d {{ display: block; background: #fff; color: var(--dark); font-size: 15px; font-weight: 700; padding: 14px; border-radius: 8px; text-align: center; }}
    .drawer-overlay {{ display: none; position: fixed; inset: 0; background: rgba(0,0,0,.5); z-index: 999; }}
    .drawer-overlay.open {{ display: block; }}

    /* ─── HERO ────────────────────────────────────── */
    .hero {{ background: #fff; overflow: hidden; }}
    .hero-inner {{ display: grid; grid-template-columns: 45fr 55fr; }}
    .hero-text {{ padding: 72px 0 72px 48px; display: flex; flex-direction: column; justify-content: center; align-items: flex-end; text-align: right; position: relative; }}
    .hero-eyebrow {{ font-family: var(--latin); font-size: 10px; font-weight: 700; color: var(--p); letter-spacing: .22em; text-transform: uppercase; position: absolute; top: 28px; left: 48px; }}
    .hero-catch {{ font-family: var(--serif); font-size: clamp(26px,3.2vw,44px); font-weight: 900; color: var(--dark); line-height: 1.5; margin-bottom: 16px; }}
    .hero-rule  {{ width: 32px; height: 3px; background: var(--p); margin-bottom: 24px; margin-left: auto; }}
    .hero-bottom {{ display: flex; align-items: center; gap: 32px; justify-content: flex-end; }}
    .hero-strengths {{ list-style: none; display: flex; flex-direction: column; gap: 14px; }}
    .hero-st-item {{ display: flex; align-items: center; gap: 10px; font-size: 19px; font-weight: 700; color: var(--p); line-height: 1.5; }}
    .hero-st-icon {{ width: 24px; height: 24px; border-radius: 50%; background: var(--p); color: #fff; font-size: 11px; font-weight: 700; display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; }}
    .hero-btn-wrap {{ display: flex; flex-direction: column; align-items: center; gap: 8px; flex-shrink: 0; }}
    .hero-btn-micro {{ font-size: 11px; color: #888; white-space: nowrap; }}
    .hero-btns  {{ display: flex; gap: 12px; flex-wrap: wrap; justify-content: flex-end; }}
    .hero-img-col {{ position: relative; overflow: hidden; }}
    .hero-img-col::before {{ content: ""; position: absolute; inset: 0; z-index: 1; background: linear-gradient(to right, #fff 0%, rgba(255,255,255,.6) 10%, rgba(255,255,255,0) 28%); pointer-events: none; }}
    .hero-img {{ width: 100%; height: 100%; object-fit: cover; object-position: center top; display: block; }}

    /* ─── BUTTONS ─────────────────────────────────── */
    .btn-p {{ background: var(--p); color: #fff; font-size: 14px; font-weight: 700; padding: 14px 28px; border-radius: 6px; display: inline-block; transition: opacity .2s; }}
    .btn-p:hover {{ opacity: .88; }}
    .btn-d {{ background: var(--dark); color: #fff; font-size: 14px; font-weight: 700; padding: 14px 28px; border-radius: 6px; display: inline-block; }}
    .tel-cta-wrap {{ display: flex; flex-direction: column; align-items: flex-end; gap: 5px; }}
    .tel-cta-label {{ font-size: 10px; color: #888; letter-spacing: .04em; }}
    .btn-tel {{ background: #FF6B00; color: #fff; font-size: 16px; font-weight: 700; padding: 13px 24px; border-radius: 6px; display: inline-flex; align-items: center; gap: 10px; transition: opacity .2s; }}
    .btn-tel:hover {{ opacity: .88; }}
    .btn-o {{ border: 2px solid var(--p); color: var(--p); font-size: 14px; font-weight: 700; padding: 12px 28px; border-radius: 6px; display: inline-block; }}

    /* ─── SECTION COMMON ──────────────────────────── */
    .sec       {{ padding: 80px 24px; }}
    .sec-white {{ background: #fff; }}
    .sec-cream {{ background: var(--cream); }}
    .sec-gray  {{ background: var(--gray); }}
    .sec-in    {{ max-width: 960px; margin: 0 auto; }}
    .sec-hd    {{ margin-bottom: 48px; }}
    .sec-hd.center {{ text-align: center; }}
    .sec-en    {{ font-family: var(--latin); display: block; font-size: 10px; font-weight: 700; letter-spacing: .24em; text-transform: uppercase; color: var(--p); margin-bottom: 6px; }}
    .sec-ja    {{ font-family: var(--serif); font-size: clamp(24px,3vw,38px); font-weight: 900; color: var(--dark); line-height: 1.4; margin-bottom: 12px; }}
    .sec-ja::after {{ content: ""; display: block; width: 32px; height: 3px; background: var(--p); margin-top: 12px; }}
    .sec-hd.center .sec-ja::after {{ margin: 12px auto 0; }}
    .sec-lead  {{ font-size: 14px; color: #666; line-height: 1.9; }}

    /* ─── INTRO 2COL ──────────────────────────────── */
    .intro-wrap {{ background: #f2f2f0; padding: 36px 48px; }}
    .intro-2col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
    .intro-left {{ display: grid; grid-template-columns: 1fr 1fr; background: #fff; border: 1px solid #e0e0e0; box-shadow: 0 4px 20px rgba(0,0,0,0.07); overflow: hidden; }}
    .intro-info {{ padding: 40px 36px; display: flex; flex-direction: column; justify-content: center; }}
    .intro-logo-en  {{ font-family: var(--latin); font-size: clamp(15px,1.8vw,20px); font-weight: 700; color: var(--dark); letter-spacing: .12em; }}
    .intro-logo-ja  {{ font-size: 11px; color: #aaa; letter-spacing: .08em; padding-bottom: 18px; border-bottom: 1px solid #e8e8e8; margin-bottom: 22px; }}
    .intro-list {{ list-style: none; display: flex; flex-direction: column; gap: 16px; }}
    .intro-row  {{ display: flex; align-items: flex-start; gap: 10px; }}
    .intro-icon {{ font-size: 13px; opacity: .55; flex-shrink: 0; margin-top: 2px; }}
    .intro-row-body {{ display: flex; flex-direction: column; }}
    .intro-row-label {{ font-size: 9px; color: #aaa; letter-spacing: .1em; margin-bottom: 2px; }}
    .intro-row-val   {{ font-size: 12px; color: var(--dark); line-height: 1.6; font-weight: 500; }}
    .intro-photo {{ padding: 20px 20px 20px 0; display: flex; align-items: center; }}
    .intro-photo img {{ width: 100%; height: 100%; object-fit: cover; display: block; border-radius: 4px; }}
    .intro-photo-blank {{ width: 100%; height: 100%; min-height: 180px; background: #e8e8e8; border-radius: 4px; display: block; }}
    .intro-target {{ background: color-mix(in srgb, var(--p) 80%, #fff); padding: 24px 40px; display: flex; align-items: center; gap: 32px; border: 1px solid rgba(255,255,255,.2); box-shadow: 0 4px 20px rgba(0,0,0,0.12); }}
    .intro-target-body {{ flex: 1; display: flex; flex-direction: column; justify-content: center; }}
    .intro-target-ja   {{ font-family: var(--serif); font-size: clamp(16px,1.8vw,22px); font-weight: 700; color: #fff; line-height: 1.65; margin-bottom: 28px; }}
    .intro-checks {{ list-style: none; display: flex; flex-direction: column; gap: 16px; }}
    .intro-check-item {{ display: flex; align-items: flex-start; gap: 10px; font-size: 15px; color: rgba(255,255,255,.92); line-height: 1.6; }}
    .intro-check-icon {{ flex-shrink: 0; margin-top: 3px; width: 19px; height: 19px; background: rgba(255,255,255,.3); border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 10px; color: #fff; font-weight: 900; }}
    .intro-owner-circle {{ width: 280px; height: auto; min-height: 160px; align-self: stretch; border-radius: 16px; overflow: hidden; flex-shrink: 0; border: 3px solid rgba(255,255,255,.4); box-shadow: 0 4px 16px rgba(0,0,0,0.2); }}
    .intro-owner-circle img {{ width: 100%; height: 100%; object-fit: cover; object-position: center top; display: block; }}
    @media (max-width: 900px)  {{ .intro-wrap {{ padding: 24px; }} .intro-2col {{ grid-template-columns: 1fr; }} .intro-photo {{ padding: 0 16px 16px; min-height: 200px; }} }}
    @media (max-width: 540px)  {{ .intro-left {{ grid-template-columns: 1fr; }} .intro-info {{ padding: 28px 24px; }} .intro-target {{ padding: 28px 24px; }} }}

    /* ─── PAIN ────────────────────────────────────── */
    .pain-wide {{ max-width: 1160px; margin: 0 auto; padding: 0 32px; }}
    .pain-grid {{ display: grid; grid-template-columns: repeat(3,1fr); gap: 48px 32px; }}
    .pain-card {{ display: flex; flex-direction: column; align-items: center; text-align: center; }}
    .pain-card-circle-wrap {{ position: relative; width: 180px; height: 180px; margin-bottom: 24px; flex-shrink: 0; }}
    .pain-card-ring {{ position: absolute; inset: -10px; border-radius: 50%; border: 2px solid var(--p); opacity: .22; pointer-events: none; }}
    .pain-card-circle {{ width: 180px; height: 180px; border-radius: 50%; overflow: hidden; box-shadow: 0 6px 22px rgba(0,0,0,.13); }}
    .pain-card-img {{ width: 100%; height: 100%; object-fit: cover; object-position: center 10%; display: block; }}
    .pain-card-img-blank {{ width: 100%; height: 100%; background: linear-gradient(135deg,var(--cream),#d6cfc8); display: block; }}
    .pain-card-text {{ font-size: 17px; font-weight: 700; color: var(--p); line-height: 1.6; margin-bottom: 10px; }}
    .pain-card-sub {{ font-size: 13px; color: #777; line-height: 1.75; }}
    .empathy-strip {{ margin-top: 56px; padding: 28px 40px; text-align: center; border-top: 2px solid var(--p); border-bottom: 2px solid var(--p); font-size: clamp(18px,2.2vw,26px); font-weight: 700; color: var(--p); line-height: 1.7; }}
    @media (max-width: 900px) {{ .pain-grid {{ grid-template-columns: repeat(2,1fr); }} }}
    @media (max-width: 560px) {{ .pain-grid {{ grid-template-columns: 1fr; gap: 40px; }} .pain-card-circle-wrap {{ width: 150px; height: 150px; }} .pain-card-circle {{ width: 150px; height: 150px; }} .pain-wide {{ padding: 0 20px; }} }}

    /* ─── REASONS ─────────────────────────────────── */
    .reason-wide {{ max-width: 1160px; margin: 0 auto; padding: 0 48px; }}
    .reason-wide .sec-hd {{ margin-bottom: 16px; }}
    .reason-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 24px; padding-top: 20px; }}
    .reason-card {{ background: #fff; border: 1.5px solid var(--bd); border-radius: 16px; padding: 52px 24px 28px 28px; position: relative; box-shadow: 0 3px 16px rgba(0,0,0,.06); display: flex; flex-direction: row; align-items: center; gap: 20px; margin-top: 56px; }}
    .reason-badge {{ position: absolute; top: -56px; left: 20px; width: 96px; height: 96px; border-radius: 50%; background: var(--p); color: #fff; font-size: 22px; font-weight: 700; display: flex; align-items: center; justify-content: center; box-shadow: 0 3px 12px rgba(0,0,0,.18); }}
    .reason-card-body {{ flex: 1; display: flex; flex-direction: column; gap: 8px; padding-top: 6px; }}
    .reason-illust {{ width: 100px; height: 100px; object-fit: contain; flex-shrink: 0; }}
    .reason-title {{ font-family: var(--serif); font-size: 17px; font-weight: 700; color: var(--dark); line-height: 1.5; }}
    .reason-text  {{ font-size: 13px; color: #666; line-height: 1.9; }}
    @media (max-width: 900px) {{ .reason-grid {{ grid-template-columns: 1fr; }} .reason-wide {{ padding: 0 24px; }} }}

    /* ─── STAFF ───────────────────────────────────── */
    .staff-card-mobile-hd {{ display: none; width: 100%; text-align: center; margin-bottom: 20px; }}
    .staff-card-eyebrow {{ font-size: 11px; color: #aaa; letter-spacing: .22em; display: flex; align-items: center; justify-content: center; gap: 12px; margin-bottom: 8px; }}
    .staff-card-eyebrow::before,.staff-card-eyebrow::after {{ content: ""; flex: 1; max-width: 48px; height: 1px; background: #ccc; }}
    .staff-card-mobile-title {{ font-family: var(--serif); font-size: clamp(24px,3vw,36px); font-weight: 900; color: var(--dark); letter-spacing: 0.4em; }}
    .staff-card {{ max-width: 860px; margin: 0 auto; border-radius: 11px; padding: 12% 2% 3%; box-sizing: border-box; display: flex; align-items: flex-start; gap: 0; background-size: 100% auto; background-position: top center; background-repeat: no-repeat; background-color: #faf7f2; }}
    .staff-left {{ width: 39%; flex-shrink: 0; display: flex; flex-direction: column; align-items: center; gap: 3px; padding-top: 4%; margin-left: -2%; }}
    .staff-circle {{ width: 75%; aspect-ratio: 1/1; border-radius: 50%; overflow: hidden; border: 2px solid #c8a96e; }}
    .staff-circle img {{ width: 100%; height: 100%; object-fit: cover; object-position: center top; display: block; }}
    .staff-circle-blank {{ width: 100%; height: 100%; background: transparent; }}
    .staff-info-name {{ font-size: clamp(18px,2.5vw,28px); font-family: var(--serif); font-weight: 700; color: var(--dark); text-align: center; margin-top: 16%; }}
    .staff-info-quals {{ font-size: clamp(7px,0.85vw,11px); color: var(--p); line-height: 1.6; text-align: center; }}
    .staff-right {{ flex: 1; padding-left: 0%; padding-top: 9%; padding-right: 4%; margin-left: -1%; }}
    .staff-card-msg {{ font-size: clamp(10px,1.4vw,17px); color: #444; line-height: 1.93; }}
    @media (max-width: 1100px) {{
      .staff-card {{ padding: 28px 20px 24px; background-image: none !important; background: #faf7f2; border: 1px solid #e2d9ce; border-radius: 16px; flex-direction: column; align-items: center; }}
      .staff-card-mobile-hd {{ display: block; }}
      .staff-left {{ width: 100%; margin-left: 0; padding-top: 0; }}
      .staff-circle {{ width: 120px; aspect-ratio: unset; height: 120px; }}
      .staff-info-name {{ font-size: 18px; margin-top: 12px; }}
      .staff-info-quals {{ font-size: 12px; }}
      .staff-right {{ padding: 16px 0 0; width: 100%; margin-left: 0; }}
      .staff-card-msg {{ font-size: 15px; line-height: 1.9; }}
    }}

    /* ─── STATS ───────────────────────────────────── */
    .hero-stats {{ margin-top: 32px; display: flex; flex-wrap: nowrap; gap: 0px; justify-content: center; overflow: visible; width: 100%; align-self: center; }}
    .stats-row {{ display: flex; flex-wrap: wrap; justify-content: center; gap: 32px; background: #fff; }}
    .stat-cell {{ text-align: center; display: flex; align-items: center; justify-content: center; background: #fff; }}
    .stat-wreath-wrap {{ position: relative; width: clamp(140px,17vw,220px); height: clamp(140px,17vw,220px); display: flex; align-items: center; justify-content: center; background: #fff; }}
    .stat-wreath-img {{ position: absolute; inset: 0; width: 100%; height: 100%; object-fit: contain; }}
    .stat-inner {{ position: relative; z-index: 1; display: flex; flex-direction: column; align-items: center; gap: 4px; padding-top: 28px; }}
    .stat-label {{ font-size: 18px; font-weight: 700; color: var(--dark); letter-spacing: .02em; line-height: 1.4; white-space: nowrap; }}
    .stat-num-row {{ display: flex; align-items: flex-end; gap: 2px; justify-content: center; white-space: nowrap; }}
    .stat-num-inner {{ font-family: var(--latin); font-size: clamp(28px,4vw,52px); font-weight: 700; color: var(--dark); line-height: 1; text-align: center; white-space: nowrap; }}
    .stat-unit  {{ font-family: var(--latin); font-size: clamp(18px,2.5vw,32px); font-weight: 700; color: var(--dark); line-height: 1.15; min-height: 0; white-space: nowrap; }}
    @media (max-width: 480px) {{ .stat-wreath-wrap {{ width: 170px; height: 170px; }} }}

    /* ─── GALLERY ─────────────────────────────────── */
    .gallery {{ display: grid; grid-template-columns: repeat(auto-fit,minmax(180px,1fr)); gap: 12px; }}
    .gallery-img {{ width: 100%; aspect-ratio: 4/3; object-fit: cover; border-radius: 8px; }}

    /* ─── VOICES ──────────────────────────────────── */
    .voices-grid {{ display: grid; grid-template-columns: repeat(3,1fr); gap: 20px; }}
    .voice-card  {{ background: #fff; border-radius: 10px; padding: 28px 24px; box-shadow: 0 2px 12px rgba(0,0,0,.06); }}
    .voice-avatar {{ width: 48px; height: 48px; border-radius: 50%; background: var(--p); display: flex; align-items: center; justify-content: center; margin-bottom: 14px; }}
    .voice-name   {{ font-size: 14px; font-weight: 700; color: var(--p); margin-bottom: 10px; letter-spacing: .04em; }}
    .voice-comment {{ font-size: 16px; color: #555; line-height: 1.9; }}
    @media (max-width: 700px) {{ .voices-grid {{ grid-template-columns: 1fr; }} }}

    /* ─── MENU ────────────────────────────────────── */
    .menu-grid {{ display: grid; grid-template-columns: repeat(3,1fr); gap: 20px; }}
    .menu-card  {{ background: #fff; border-radius: 10px; overflow: hidden; border: 1px solid var(--bd); display: flex; flex-direction: column; box-shadow: 0 2px 12px rgba(0,0,0,.06); }}
    .menu-card-img {{ width: 100%; aspect-ratio: 4/3; object-fit: cover; object-position: center; display: block; }}
    .menu-card-img-blank {{ width: 100%; aspect-ratio: 4/3; background: linear-gradient(135deg,var(--cream),#e0d5c8); display: block; }}
    .menu-card-inner {{ padding: 20px 20px 24px; flex: 1; display: flex; flex-direction: column; }}
    .menu-card-name  {{ font-family: var(--serif); font-size: 18px; font-weight: 700; color: var(--dark); margin-bottom: 8px; line-height: 1.5; }}
    .menu-card-desc  {{ font-size: 14px; color: #888; line-height: 1.7; margin-bottom: 14px; flex: 1; }}
    .menu-card-time  {{ font-size: 13px; color: #aaa; margin-bottom: 8px; }}
    .menu-card-price-wrap {{ margin-top: auto; }}
    .menu-card-orig  {{ font-size: 13px; color: #bbb; text-decoration: line-through; margin-bottom: 4px; }}
    .menu-card-price {{ font-family: var(--latin); font-size: 26px; font-weight: 700; color: var(--p); line-height: 1; }}
    .menu-card-tax   {{ font-family: var(--sans); font-size: 12px; color: #999; font-weight: 400; margin-left: 2px; }}
    @media (max-width: 900px) {{ .menu-grid {{ grid-template-columns: repeat(2,1fr); }} }}
    @media (max-width: 500px) {{ .menu-grid {{ grid-template-columns: 1fr; }} }}

    /* ─── COUPON ──────────────────────────────────── */
    .coupon-banner-wrap {{ position: relative; display: block; max-width: 720px; margin: 32px auto; cursor: pointer; }}
    .coupon-banner-wrap img {{ width: 100%; display: block; border-radius: 12px; box-shadow: 0 4px 24px rgba(0,0,0,0.12); }}
    .cp-overlay-orig {{ position: absolute; left: 41%; top: 58%; transform: translate(-50%,-50%); font-size: clamp(20px,2.7vw,36px); font-weight: 900; color: #555; text-decoration: line-through; white-space: nowrap; pointer-events: none; }}
    .cp-overlay-new  {{ position: absolute; left: 75%; top: 58%; transform: translate(-50%,-50%); font-size: clamp(24px,3.2vw,42px); font-weight: 900; color: #FF6B00; white-space: nowrap; pointer-events: none; }}
    .cp-meta  {{ font-size: 12px; color: #999; margin-bottom: 20px; display: flex; gap: 16px; justify-content: center; }}
    .cp-note  {{ font-size: 12px; color: #bbb; margin-top: 12px; }}

    /* ─── FAQ ─────────────────────────────────────── */
    .faq-item {{ border-bottom: 1px solid var(--bd); }}
    .faq-q {{ list-style: none; padding: 20px 0; cursor: pointer; font-weight: 700; font-size: 18px; display: flex; align-items: flex-start; gap: 14px; }}
    .faq-q::-webkit-details-marker {{ display: none; }}
    .faq-a {{ padding: 0 0 20px 44px; font-size: 17px; color: #555; display: flex; gap: 14px; line-height: 1.85; }}
    .faq-icon-q,.faq-icon-a {{ flex-shrink: 0; width: 28px; height: 28px; border-radius: 50%; background: var(--p); color: #fff; font-weight: 900; font-size: 13px; display: inline-flex; align-items: center; justify-content: center; }}
    .faq-icon-a {{ background: var(--dark); }}

    /* ─── BOTTOM CTA ──────────────────────────────── */
    .cta-bottom {{ background: var(--gray); padding: 64px 32px; }}
    .cta-bottom-in {{ max-width: 960px; margin: 0 auto; text-align: center; }}
    @media (max-width: 700px) {{ .cta-bottom {{ padding: 40px 20px; }} }}

    /* ─── ACCESS ──────────────────────────────────── */
    .access-tbl {{ width: 100%; border-collapse: collapse; }}
    .access-tbl td {{ padding: 14px 0; border-bottom: 1px solid var(--bd); font-size: 14px; vertical-align: top; }}
    .access-tbl td:first-child {{ width: 88px; font-weight: 700; color: var(--p); padding-right: 16px; white-space: nowrap; font-family: var(--latin); font-size: 12px; letter-spacing: .06em; }}
    .map-wrap {{ margin-top: 24px; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 12px rgba(0,0,0,.08); }}
    .map-wrap iframe {{ width: 100%; height: 360px; border: 0; display: block; }}

    /* ─── FOOTER ──────────────────────────────────── */
    .footer {{ background: var(--p); padding: 56px 32px 0; }}
    .footer-inner {{ max-width: 960px; margin: 0 auto; display: flex; flex-direction: column; align-items: center; gap: 28px; text-align: center; }}
    .footer-logo-en {{ font-family: var(--latin); font-size: 22px; font-weight: 700; color: #fff; letter-spacing: .12em; }}
    .footer-logo-ja {{ font-size: 11px; color: rgba(255,255,255,.6); margin-top: 4px; }}
    .footer-cta {{ display: flex; align-items: center; justify-content: center; gap: 12px; flex-wrap: wrap; }}
    .footer-nav {{ display: flex; flex-wrap: wrap; justify-content: center; list-style: none; }}
    .footer-nav a {{ font-size: 12px; color: rgba(255,255,255,.7); padding: 6px 12px; display: block; transition: color .2s; }}
    .footer-nav a:hover {{ color: #fff; }}
    .footer-copy {{ text-align: center; padding: 20px 16px; font-size: 11px; color: rgba(255,255,255,.4); margin-top: 32px; border-top: 1px solid rgba(255,255,255,.15); }}

    /* ─── ANIMATION ───────────────────────────────── */
    .fadein {{ opacity: 0; transform: translateY(18px); transition: opacity .6s ease, transform .6s ease; }}
    .fadein.visible {{ opacity: 1; transform: translateY(0); }}

    /* ─── RESPONSIVE ──────────────────────────────── */
    @media (max-width: 1100px) {{
      /* Hero → 1カラム化 */
      .hero-inner {{ grid-template-columns: 1fr; }}
      .hero-img-col {{ height: 300px; order: -1; }}
      .hero-img-col::before {{ background: linear-gradient(to bottom, rgba(255,255,255,0) 55%, #fff 100%); }}
      .hero-text {{ padding: 32px 24px 40px; align-items: flex-start; text-align: left; }}
      .hero-rule {{ margin-left: 0; }}
      .hero-bottom {{ flex-direction: column; align-items: flex-start; gap: 20px; width: 100%; }}
      .hero-btn-wrap {{ width: 100%; align-items: center; text-align: center; align-self: center; }}
      .hero-btn-wrap .btn-p {{ width: 100%; text-align: center; font-size: 16px; padding: 16px; display: block; }}
      .hero-stats {{ justify-content: center; gap: 0; }}
      .hero-stats .stat-wreath-wrap {{ width: 160px; height: 160px; }}
      .hero-stats .stat-label {{ font-size: 12px; }}
      .hero-stats .stat-num-inner {{ font-size: clamp(18px,4vw,28px); }}
      .hero-stats .stat-unit {{ font-size: clamp(12px,2.5vw,18px); }}
      .hero-stats .stat-inner {{ padding-top: 16px; }}
      /* Intro */
      .intro-wrap {{ padding: 20px; }}
      .intro-2col {{ grid-template-columns: 1fr; }}
      .intro-left {{ grid-template-columns: 1fr; }}
      .intro-photo {{ display: none; }}
      .intro-target {{ padding: 28px 20px; gap: 20px; }}
      .intro-owner-circle {{ width: 140px; height: 90px; }}
    }}
    @media (max-width: 768px) {{
      /* Sections */
      .sec {{ padding: 48px 20px; }}
      .sec-ja::after {{ margin-left: auto; margin-right: auto; }}
      /* Reasons */
      .reason-wide {{ padding: 0 20px; }}
      .reason-grid {{ grid-template-columns: 1fr; gap: 20px; }}
      .reason-card {{ flex-direction: column; align-items: flex-start; }}
      .reason-illust {{ width: 80px; height: 80px; align-self: flex-end; }}
      /* Pain */
      .pain-wide {{ padding: 0 20px; }}
      .pain-grid {{ grid-template-columns: repeat(2,1fr); gap: 32px 20px; }}
      .pain-card-circle-wrap {{ width: 140px; height: 140px; }}
      .pain-card-circle {{ width: 140px; height: 140px; }}
      .empathy-strip {{ padding: 20px 20px; margin-top: 32px; }}
      /* Staff */
      .staff-wrap {{ flex-direction: column; gap: 24px; }}
      .staff-photo {{ width: 100%; max-width: 260px; }}
      /* Voices */
      .voices-grid {{ grid-template-columns: 1fr; }}
      /* Menu */
      .menu-grid {{ grid-template-columns: repeat(2,1fr); gap: 12px; }}
      /* FAQ */
      .faq-q {{ font-size: 15px; }}
      .faq-a {{ font-size: 14px; padding-left: 32px; }}
      /* CTA Bottom */
      .cta-bottom {{ padding: 40px 20px; }}
      /* Footer */
      .footer {{ padding: 40px 20px 0; }}
      .footer-cta {{ flex-direction: column; align-items: center; gap: 16px; }}
      .footer-nav {{ gap: 0; }}
    }}
    @media (max-width: 480px) {{
      .hero-img-col {{ height: 220px; }}
      .hero-catch {{ font-size: clamp(22px,6.5vw,32px); }}
      .hero-stats .stat-wreath-wrap {{ width: 120px; height: 120px; }}
      .hero-stats .stat-label {{ font-size: 11px; }}
      .hero-stats .stat-num-inner {{ font-size: clamp(16px,4vw,22px); }}
      .hero-stats .stat-inner {{ padding-top: 12px; }}
      .pain-grid {{ grid-template-columns: 1fr; }}
      .reason-card {{ padding: 52px 20px 24px 20px; }}
      .menu-grid {{ grid-template-columns: 1fr; }}
      .sec-ja {{ font-size: clamp(20px,5.5vw,28px); }}
    }}
  </style>
</head>
<body>

<!-- ■ HEADER -->
<div class="hdr-wrap">
  <div class="hdr">
    <div class="hdr-logo">
      <span class="hdr-logo-eyebrow">{location} — {shop_type}</span>
      <span class="hdr-logo-en">{shop_name.upper()}</span>
    </div>
    <nav><ul class="hdr-nav">
      <li><a href="#pain">お悩み</a></li>
      <li><a href="#reasons">選ばれる理由</a></li>
      <li><a href="#voices">お客様の声</a></li>
      <li><a href="#menu">メニュー</a></li>
      <li><a href="#faq">よくある質問</a></li>
      <li><a href="#access">アクセス</a></li>
    </ul></nav>
    <div class="hdr-right">
      {'<div class="tel-cta-wrap" style="align-items:flex-end;"><span class="tel-cta-label">電話でのご予約はこちらから</span><a href="tel:' + phone + '" class="btn-tel" style="font-size:13px;padding:9px 16px;">☎ ' + phone + '</a></div>' if 'phone' in cta_types and phone else ''}
      {'<div class="tel-cta-wrap" style="align-items:center;"><span class="tel-cta-label">24時間受付中</span><a href="' + booking_url + '" class="btn-o" style="font-size:12px;padding:9px 14px;white-space:nowrap;">📅 Web予約</a></div>' if 'booking' in cta_types and booking_url else ''}
      <div class="tel-cta-wrap" style="align-items:center;">
        <span class="tel-cta-label">＼ 30秒でカンタン登録 ／</span>
        <a href="{line_url}" class="hdr-btn">▶ {cta_button}</a>
      </div>
    </div>
    <button class="hamburger" id="hamburgerBtn"><span></span><span></span><span></span></button>
  </div>
</div>

<!-- ■ DRAWER -->
<div class="drawer" id="drawer">
  <button class="drawer-close" id="drawerClose">✕</button>
  <nav class="drawer-nav">
    <a href="#pain"    class="drawer-link">お悩み</a>
    <a href="#reasons" class="drawer-link">選ばれる理由</a>
    <a href="#voices"  class="drawer-link">お客様の声</a>
    <a href="#menu"    class="drawer-link">メニュー・料金</a>
    <a href="#faq"     class="drawer-link">よくある質問</a>
    <a href="#access"  class="drawer-link">アクセス</a>
  </nav>
  <div class="drawer-cta">
    <a href="{line_url}" class="drawer-btn-p">▶ {coupon_btn}</a>
    {f'<a href="tel:{phone}" class="drawer-btn-d">📞 {phone}</a>' if phone else ''}
  </div>
</div>
<div class="drawer-overlay" id="drawerOverlay"></div>

<!-- ■ HERO -->
<section class="hero">
  <div class="hero-inner">
    <div class="hero-text">
      <h1 class="hero-catch">{copy.get('catch_copy','').replace(chr(10),'<br>')}</h1>
      <div class="hero-bottom">
        <ul class="hero-strengths">{_hero_strengths_html}</ul>
        <div class="hero-btn-wrap">
          <p class="hero-btn-micro">{_hero_micro}</p>
          <a href="{line_url}" class="btn-p">▶ {cta_button}</a>
        </div>
      </div>
      {f'<div class="hero-stats">{stats_html}</div>' if stats_html else ''}
    </div>
    {f'<div class="hero-img-col"><img src="{_hero_src}" alt="{shop_name}" class="hero-img"></div>' if _hero_src else ''}
  </div>
</section>

<!-- ■ INTRO 2COL -->
<div class="intro-wrap">
<div class="intro-2col">
  <div class="intro-left">
    <div class="intro-info">
      <p class="intro-logo-en">{shop_name}</p>
      <p class="intro-logo-ja">{shop_type}</p>
      <ul class="intro-list">
        {f'<li class="intro-row"><span class="intro-icon">🕐</span><span class="intro-row-body"><span class="intro-row-label">営業時間</span><span class="intro-row-val">{open_hours}</span></span></li>' if open_hours else ''}
        {f'<li class="intro-row"><span class="intro-icon">📅</span><span class="intro-row-body"><span class="intro-row-label">定休日</span><span class="intro-row-val">{regular_holiday}</span></span></li>' if regular_holiday else ''}
        {f'<li class="intro-row"><span class="intro-icon">📍</span><span class="intro-row-body"><span class="intro-row-label">アクセス</span><span class="intro-row-val">{address}</span></span></li>' if address else ''}
        {f'<li class="intro-row"><span class="intro-icon">📞</span><span class="intro-row-body"><span class="intro-row-label">電話番号</span><span class="intro-row-val">{phone}</span></span></li>' if phone else ''}
      </ul>
    </div>
    <div class="intro-photo">
      {intro_photo_html if intro_photo_html else '<div class="intro-photo-blank"></div>'}
    </div>
  </div>
  <div class="intro-target">
    <div class="intro-target-body">
      <p class="intro-target-ja">{shop_name}はこんな方たちのための場所です</p>
      <ul class="intro-checks">
        {"".join(f'<li class="intro-check-item"><span class="intro-check-icon">✓</span>{item.get("text", item) if isinstance(item, dict) else item}</li>' for item in pain_items[:4])}
      </ul>
    </div>
    {_intro_owner_html}
  </div>
</div>
</div>

<!-- ■ クーポン -->
{f'''<div class="sec sec-cream" style="padding-top:48px;padding-bottom:48px;">
  <div style="max-width:960px;margin:0 auto;padding:0 24px;">
    <div class="sec-hd center" style="margin-bottom:24px;">
      <h2 class="sec-ja">今ならLINE限定の特別クーポンプレゼント中</h2>
    </div>
    {coupon_banner_html}
  </div>
</div>''' if coupon_banner_html else ''}

<!-- ■ お悩み -->
<div class="sec sec-white" id="pain">
  <div class="pain-wide">
    <div class="sec-hd center">
      <h2 class="sec-ja">こんなお悩みありませんか？</h2>
    </div>
    <div class="pain-grid">{pain_cards_html}</div>
    {f'<p class="empathy-strip">{copy.get("empathy_text","")}</p>' if copy.get("empathy_text") else ''}
  </div>
</div>

<!-- ■ 選ばれる理由 -->
<div class="sec sec-gray" id="reasons">
  <div class="reason-wide">
    <div class="sec-hd center">
      <h2 class="sec-ja">{shop_name}が選ばれる理由</h2>
      <p class="sec-lead">{solution.get('body','')}</p>
    </div>
    <div class="reason-grid">{points_html}</div>
  </div>
</div>

<!-- ■ スタッフ -->
{f'''<div class="sec sec-white">
  <div class="sec-in">
    <div class="staff-card" style="background-image:url('{_staff_bg_uri}')">
      <div class="staff-card-mobile-hd">
        <p class="staff-card-eyebrow">院長からのメッセージ</p>
        <h2 class="staff-card-mobile-title">ごあいさつ</h2>
      </div>
      <div class="staff-left">
        <div class="staff-circle">
          {"<img src='" + photo_url("owner") + "' alt='院長'>" if photo_exists("owner") else ("<img src='" + photo_url("staff") + "' alt='院長'>" if photo_exists("staff") else "<div class='staff-circle-blank'></div>")}
        </div>
        {"<p class='staff-info-name'>" + owner_name + "</p>" if owner_name else ""}
        {"<p class='staff-info-quals'>" + owner_qualifications.replace(" / ","<br>") + "</p>" if owner_qualifications else ""}
      </div>
      <div class="staff-right">
        <p class="staff-card-msg">{owner_message or f"当院は{location}で{shop_type}として多くの患者様のお悩みに向き合ってきました。お一人おひとりの状態をしっかりカウンセリングし、根本から改善するアプローチで施術しています。"}</p>
      </div>
    </div>
  </div>
</div>''' if show_staff else ''}

<!-- ■ ギャラリー -->
{f'''<div class="sec sec-gray">
  <div class="sec-in">
    <div class="sec-hd center">
      <h2 class="sec-ja">院内・スタッフのご紹介</h2>
    </div>
    <div class="gallery">{gallery_html}</div>
  </div>
</div>''' if gallery_html else ''}

<!-- ■ お客様の声 -->
<div class="sec sec-cream" id="voices">
  <div class="sec-in">
    <div class="sec-hd center">
      <h2 class="sec-ja">{copy.get('testimonials_section', {}).get('headline','お客様の声')}</h2>
    </div>
    <div class="voices-grid">{voices_html}</div>
  </div>
</div>

<!-- ■ メニュー・料金 -->
<div class="sec sec-white" id="menu">
  <div class="sec-in">
    <div class="sec-hd center">
      <h2 class="sec-ja">{menu_s.get('headline','メニュー・料金')}</h2>
      {f'<p class="sec-lead">{menu_s.get("lead","")}</p>' if menu_s.get('lead') else ''}
    </div>
    <div class="menu-grid">{menu_cards_html}</div>
  </div>
</div>

<!-- ■ FAQ -->
<div class="sec sec-gray" id="faq">
  <div class="sec-in">
    <div class="sec-hd center">
      <h2 class="sec-ja">{faq_sec.get('headline','よくある質問')}</h2>
    </div>
    {faq_html}
  </div>
</div>

<!-- ■ ボトムCTA -->
<div class="cta-bottom">
  <div class="cta-bottom-in">
    <div class="sec-hd center">
      <h2 class="sec-ja">気になることや聞きたいことなどあれば<br>お気軽にLINEからご相談ください</h2>
    </div>
    {coupon_banner_html if coupon_banner_html else f'<div style="margin-top:32px;"><a href="{line_url}" class="btn-p" style="font-size:18px;padding:18px 48px;">▶ {cta_button}</a></div>'}
  </div>
</div>

<!-- ■ アクセス -->
<div class="sec sec-white" id="access">
  <div class="sec-in">
    <div class="sec-hd center">
      <h2 class="sec-ja">アクセス・診療時間</h2>
    </div>
    <table class="access-tbl">
      <tr><td>店舗名</td><td>{shop_name}</td></tr>
      <tr><td>住所</td><td>{address or location}</td></tr>
      {f'<tr><td>電話番号</td><td>{phone}</td></tr>' if phone else ''}
      {f'<tr><td>営業時間</td><td>{business_hours}</td></tr>' if business_hours else ''}
    </table>
    {f'<div class="map-wrap"><iframe src="{map_embed_url}" allowfullscreen loading="lazy" referrerpolicy="no-referrer-when-downgrade"></iframe></div>' if map_embed_url else ''}
  </div>
</div>

<!-- ■ FOOTER -->
<footer class="footer">
  <div class="footer-inner">
    <div>
      <p class="footer-logo-en">{shop_name}</p>
      <p class="footer-logo-ja">{shop_type}</p>
    </div>
    <div class="footer-cta">
      {'<div class="tel-cta-wrap" style="align-items:center;"><span class="tel-cta-label" style="color:rgba(255,255,255,.6);">電話でのご予約はこちらから</span><a href="tel:' + phone + '" class="btn-tel" style="font-size:13px;padding:9px 16px;">☎ ' + phone + '</a></div>' if 'phone' in cta_types and phone else ''}
      {'<div class="tel-cta-wrap" style="align-items:center;"><span class="tel-cta-label" style="color:rgba(255,255,255,.6);">24時間受付中</span><a href="' + booking_url + '" class="btn-o" style="font-size:12px;padding:9px 14px;white-space:nowrap;border-color:#fff;color:#fff;">📅 Web予約</a></div>' if 'booking' in cta_types and booking_url else ''}
      <div class="tel-cta-wrap" style="align-items:center;">
        <span class="tel-cta-label" style="color:rgba(255,255,255,.6);">＼ 30秒でカンタン登録 ／</span>
        <a href="{line_url}" class="hdr-btn" style="background:#fff;color:var(--p);">▶ {cta_button}</a>
      </div>
    </div>
    <ul class="footer-nav">
      <li><a href="#pain">お悩み</a></li>
      <li><a href="#reasons">選ばれる理由</a></li>
      <li><a href="#voices">お客様の声</a></li>
      <li><a href="#menu">メニュー</a></li>
      <li><a href="#faq">よくある質問</a></li>
      <li><a href="#access">アクセス</a></li>
    </ul>
    <p class="footer-copy" style="width:100%;">&copy; 2025 {shop_name}. All rights reserved.</p>
  </div>
</footer>

<script>
  const observer = new IntersectionObserver(
    (entries) => entries.forEach(e => {{ if (e.isIntersecting) e.target.classList.add('visible'); }}),
    {{ threshold: 0.1 }}
  );
  document.querySelectorAll('.fadein').forEach(el => observer.observe(el));

  const drawer  = document.getElementById('drawer');
  const overlay = document.getElementById('drawerOverlay');
  const open    = () => {{ drawer.classList.add('open'); overlay.classList.add('open'); document.body.style.overflow='hidden'; }};
  const close   = () => {{ drawer.classList.remove('open'); overlay.classList.remove('open'); document.body.style.overflow=''; }};
  document.getElementById('hamburgerBtn').addEventListener('click', open);
  document.getElementById('drawerClose').addEventListener('click', close);
  overlay.addEventListener('click', close);
  document.querySelectorAll('.drawer-link,.drawer-btn-p,.drawer-btn-d').forEach(el => el.addEventListener('click', close));
</script>
</body>
</html>"""
