"""
LINE Harness シナリオ自動生成モジュール

LP設定完了後に以下を自動生成:
1. タグ3本 (新規LP経由 / 初来院 / 既存顧客)
2. シナリオ6本 + 全ステップ
3. 専用エントリールート (QRコード用)
"""
import hashlib
import json
import re
import unicodedata
import httpx


def _ascii_ref_slug(slug: str) -> str:
    """slug を Harness ref_code 用 ASCII に変換（日本語はハッシュ fallback）"""
    n = unicodedata.normalize('NFKD', slug)
    a = n.encode('ascii', 'ignore').decode('ascii')
    clean = re.sub(r'[^\w\-]', '', a.lower().replace(' ', '-'))
    if not clean:
        clean = 'r' + hashlib.sha256(slug.encode()).hexdigest()[:7]
    return clean

# ─── テンプレート置換 ─────────────────────────────────────────────
def _replace(text: str, shop_name: str, owner_name: str, booking_url: str,
             survey_url: str, review_url: str, form_url: str) -> str:
    return (text
        .replace("【院名】", shop_name)
        .replace("【院長名】", owner_name)
        .replace("【予約URL】", booking_url or "https://example.com/booking")
        .replace("【アンケートURL】", survey_url or "https://example.com/survey")
        .replace("【GoogleマップURL】", review_url or "https://maps.google.com")
        .replace("【LINEフォームURL】", form_url or "https://example.com/form")
    )


# ─── Flexメッセージビルダー ────────────────────────────────────────
def _flex_button(label: str, url: str, color: str = "#2C4A7C") -> str:
    """ボタン1つだけのflex（フッターのみ）"""
    return json.dumps({
        "type": "bubble",
        "footer": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "contents": [{
                "type": "button",
                "style": "primary",
                "color": color,
                "action": {"type": "uri", "label": label, "uri": url}
            }]
        }
    }, ensure_ascii=False)


def _flex_coupon(coupon_name: str, coupon_discount: str, booking_url: str) -> str:
    """クーポンリッチメッセージ（クーポン情報＋予約ボタン）"""
    discount_text = coupon_discount if coupon_discount else "特別割引"
    return json.dumps({
        "type": "bubble",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#2C4A7C",
            "paddingAll": "16px",
            "contents": [{
                "type": "text",
                "text": coupon_name or "初回限定クーポン",
                "color": "#ffffff",
                "weight": "bold",
                "size": "lg",
                "align": "center"
            }]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "contents": [
                {
                    "type": "text",
                    "text": discount_text,
                    "size": "xxl",
                    "weight": "bold",
                    "color": "#C0182E",
                    "align": "center"
                },
                {
                    "type": "text",
                    "text": "ご来院時にこの画面をスタッフへご提示ください",
                    "size": "xs",
                    "color": "#888888",
                    "align": "center",
                    "wrap": True
                }
            ]
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [{
                "type": "button",
                "style": "primary",
                "color": "#2C4A7C",
                "action": {
                    "type": "uri",
                    "label": "今すぐ予約する →",
                    "uri": booking_url or "https://example.com/booking"
                }
            }]
        }
    }, ensure_ascii=False)


def _flex_revisit_coupon(coupon_name: str, coupon_discount: str, booking_url: str) -> str:
    """再来院クーポンリッチメッセージ"""
    discount_text = coupon_discount if coupon_discount else "次回割引"
    return json.dumps({
        "type": "bubble",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#00897B",
            "paddingAll": "16px",
            "contents": [{
                "type": "text",
                "text": coupon_name or "次回来院クーポン",
                "color": "#ffffff",
                "weight": "bold",
                "size": "lg",
                "align": "center"
            }]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "contents": [
                {
                    "type": "text",
                    "text": discount_text,
                    "size": "xxl",
                    "weight": "bold",
                    "color": "#00695C",
                    "align": "center"
                },
                {
                    "type": "text",
                    "text": "ご来院時にこの画面をスタッフへご提示ください",
                    "size": "xs",
                    "color": "#888888",
                    "align": "center",
                    "wrap": True
                }
            ]
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [{
                "type": "button",
                "style": "primary",
                "color": "#00897B",
                "action": {
                    "type": "uri",
                    "label": "予約する →",
                    "uri": booking_url or "https://example.com/booking"
                }
            }]
        }
    }, ensure_ascii=False)


# ─── シナリオC ステップビルダー ──────────────────────────────────
def _build_c_steps(R, shop_name, shinsatsu_form_url, _btn_form, _btn_form_r,
                   _btn_booking, frc, rv_days: int, step10_delay: int,
                   tag_re_checkin: str = "") -> list:
    """シナリオC（初来院）のステップリストを動的に構築"""
    cond_tag = f"{shop_name}_感想クーポン配布済み"

    tag_re_checkin = tag_re_checkin or f"{shop_name}_再来院"

    steps = [
        # Day0 即時（チェックイン直後）問診票 ＋ 再来院タグあり＝2回目以降→スキップ（nextStepOnFalseは後で確定）
        {"stepOrder": 1, "delayMinutes": 0, "deliveryHour": None, "messageType": "text",
         "messageContent": R("{{name}}さん、本日はご来院ありがとうございます！\n\n施術をより効果的にするために、簡単な問診票にご回答をお願いします。\n受付にお声がけいただく前に、ご回答いただけると助かります。"),
         "conditionType": "tag_not_exists", "conditionValue": tag_re_checkin},
        {"stepOrder": 2, "delayMinutes": 0, "deliveryHour": None, "messageType": "flex",
         "messageContent": _flex_button("問診票に回答する →", shinsatsu_form_url or "https://example.com/form")},
        # Day0 当日20時 感想フォーム案内
        {"stepOrder": 3, "delayMinutes": 0, "deliveryHour": 20, "messageType": "text",
         "messageContent": R("{{name}}さん、本日はご来院いただきありがとうございました。\n\nお体の調子はいかがでしょうか？\n\n施術を受けての感想を、ぜひ聞かせてください。\nご回答いただいた方全員に、次回来院時に使えるクーポンをプレゼントしています。")},
        {"stepOrder": 4, "delayMinutes": 0, "deliveryHour": 20, "messageType": "flex",
         "messageContent": _btn_form,
         "conditionType": "tag_not_exists", "conditionValue": cond_tag, "nextStepOnFalse": 5},
        # Day1 翌日20時 フォームリマインド
        {"stepOrder": 5, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
         "messageContent": R("{{name}}さん、こんにちは。\n昨日ご案内した感想フォーム、まだでしたらこちらからどうぞ。\n\nご回答いただいた方全員に、次回来院クーポンをお届けしています。"),
         "conditionType": "tag_not_exists", "conditionValue": cond_tag, "nextStepOnFalse": 6},
        {"stepOrder": 6, "delayMinutes": 0, "deliveryHour": 20, "messageType": "flex",
         "messageContent": _btn_form_r,
         "conditionType": "tag_not_exists", "conditionValue": cond_tag, "nextStepOnFalse": 7},
        # Day3 セルフケア
        {"stepOrder": 7, "delayMinutes": 2880, "deliveryHour": 20, "messageType": "text",
         "messageContent": R("{{name}}さん、こんにちは。【院長名】です。\n\nご来院から3日が経ちました。お体の調子はいかがでしょうか？\n\n施術の効果を長持ちさせるために、自宅でできる簡単なケアをご紹介します。\n\n【セルフケア3選】\n・肩をゆっくり後ろに大きく回す（10回）\n・首を左右にゆっくり倒して10秒キープ（各1回）\n・仰向けで膝を抱えて、腰をやさしくストレッチ（30秒）\n\n1日2〜3分でできますので、ぜひ毎日続けてみてください。")},
        # Day5 経過確認
        {"stepOrder": 8, "delayMinutes": 2880, "deliveryHour": 20, "messageType": "text",
         "messageContent": R("{{name}}さん、その後お体の調子はいかがですか？\n\nご来院から5日が経ちました。\n\n「良くなってきた」という変化を感じていただけていれば嬉しいですし、「なんか戻ってきた気がする」という場合もぜひ教えてください。\n\nどんな小さなことでも、お気軽にこちらのLINEへご連絡ください。")},
        # Day7 再来院の必要性（Doc1参照）
        {"stepOrder": 9, "delayMinutes": 2880, "deliveryHour": 20, "messageType": "text",
         "messageContent": R("{{name}}さん、こんにちは。【院長名】です。\n\nご来院から1週間が経ちました。\n\n実は、施術から1週間ほど経つと、日常の姿勢や動作のクセによって体に再び負担がかかりやすくなる時期です。\n\n「調子が良くなってきた」と感じているときこそ、次の一手を打つタイミング。\n\n一度の施術で改善を感じても、深い部分の筋肉や姿勢のクセはまだ改善途中のことがほとんどです。\n\nこのまま放置してしまうと、また同じ症状が戻ってきてしまう可能性があります。\n\n何かお体のことでご不安な点があれば、いつでもこちらのLINEにご連絡ください。")},
    ]

    # Day10 施術間隔の重要性（rv_days > 10 の場合のみ）Doc3参照
    if rv_days > 10:
        steps.append(
            {"stepOrder": 10, "delayMinutes": 4320, "deliveryHour": 20, "messageType": "text",
             "messageContent": R("{{name}}さん、こんにちは。\n\n体の改善スピードを上げるために、大切なことをお伝えしますね。\n\nそれは「施術の間隔を空けすぎないこと」です。\n\nせっかく整えたバランスも、時間が経つにつれてどうしても元の状態に戻ろうとします。\n\n2回目の施術を2週間以内に受けることで、\n\n✅ 改善の実感がずっと早くなる\n✅ 再発しにくい体づくりにつながる\n\nと言われています。\n\n何かお体のことでご不安な点があれば、いつでもこちらのLINEにご連絡ください。")}
        )
        n_step = 11
        n_delay = max(0, rv_days - 10) * 1440  # Day10 → DayN
    else:
        n_step = 10
        n_delay = max(0, rv_days - 7) * 1440   # Day7 → DayN

    # DayN クーポン配布（Doc4参照）
    steps.extend([
        {"stepOrder": n_step, "delayMinutes": n_delay, "deliveryHour": 20, "messageType": "text",
         "messageContent": R(f"{{{{name}}}}さん、こんにちは。\n\nご来院から{rv_days}日が経ちました。\n\n少し振り返ってみてください——\n初めてご来院いただいたとき、体の状態はどうでしたか？\n\nあの頃の不調が、少しずつまた戻ってきてはいませんか？\n\n体は、定期的にケアを続けることで「良い状態」が当たり前になっていきます。逆に間隔が空いてしまうと、また振り出しに近い状態に戻ってしまうことも。\n\n今日がちょうど、次のケアのベストタイミングです。\n\n再来院クーポンをお届けしますので、ぜひご来院にお役立てください。")},
        {"stepOrder": n_step + 1, "delayMinutes": 0, "deliveryHour": 20, "messageType": "flex",
         "messageContent": frc},
        {"stepOrder": n_step + 2, "delayMinutes": 0, "deliveryHour": 20, "messageType": "flex",
         "messageContent": _btn_booking},
        # DayN+3 フォローアップ1（クーポン配布から3日後）
        {"stepOrder": n_step + 3, "delayMinutes": 3 * 1440, "deliveryHour": 20, "messageType": "text",
         "messageContent": R(f"{{{{name}}}}さん、こんにちは。\n\n先日お届けした再来院クーポン、もうご確認いただけましたか？\n\n一度の施術で改善を感じていただけても、多くの方は2回目・3回目の施術を受けることで体の土台がしっかり安定してきます。\n\n逆に、ここで間隔が空いてしまうと、せっかくの改善がリセットされてしまうことも少なくありません。\n\nクーポンをぜひこの機会にご活用ください😊")},
        {"stepOrder": n_step + 4, "delayMinutes": 0, "deliveryHour": 20, "messageType": "flex",
         "messageContent": _btn_booking},
        # DayN+7 フォローアップ2（クーポン配布から7日後）
        {"stepOrder": n_step + 5, "delayMinutes": 4 * 1440, "deliveryHour": 20, "messageType": "text",
         "messageContent": R(f"{{{{name}}}}さん、こんにちは。\n\n再来院クーポンのご案内、最後のお知らせです。\n\n「行こうと思っていたけど、なかなか…」\nそういう方、本当に多いです。\n\nでも、体の不調は放置するほど、回復にも時間がかかるようになってしまいます。\n\nあの頃の症状がまた戻ってしまう前に、一度体を診させてください。\n\nクーポンをお持ちのうちに、ぜひご来院お待ちしています。")},
        {"stepOrder": n_step + 6, "delayMinutes": 0, "deliveryHour": 20, "messageType": "flex",
         "messageContent": _btn_booking},
    ])

    # STEP1のnextStepOnFalseを最終ステップの次番号に確定（スキップ先）
    last_order = max(s["stepOrder"] for s in steps)
    steps[0]["nextStepOnFalse"] = last_order + 1

    return steps


# ─── シナリオテンプレート ─────────────────────────────────────────
def _scenario_templates(shop_name: str, owner_name: str, booking_url: str,
                        survey_url: str, review_url: str, form_url: str,
                        tag_lp: str, tag_checkin: str, tag_existing: str, tag_re_checkin: str,
                        tag_survey_done: str = "アンケート回答済み",
                        coupon_name: str = "初回限定クーポン",
                        coupon_discount: str = "",
                        revisit_coupon_name: str = "次回来院クーポン",
                        revisit_coupon_discount: str = "",
                        review_coupon_tag_id: str = "",
                        revisit_coupon_timing: int = 14,
                        shinsatsu_form_url: str = "") -> list[dict]:
    """6本のシナリオ定義を返す"""
    R = lambda t: _replace(t, shop_name, owner_name, booking_url, survey_url, review_url, form_url)

    # クーポンflex（即時生成）
    fc  = _flex_coupon(coupon_name, coupon_discount, booking_url)
    frc = _flex_revisit_coupon(revisit_coupon_name, revisit_coupon_discount, booking_url)

    # 再来院クーポン配信タイミング（日数）
    # Day7(STEP9)からの追加delay
    _rv_days = max(7, revisit_coupon_timing)
    _step10_delay = (_rv_days - 7) * 1440  # STEP9(Day7)からN日後まで

    _btn_survey  = _flex_button("クーポンを受け取る →", survey_url or "https://example.com/survey")
    _btn_booking = _flex_button("今すぐ予約する →", booking_url or "https://example.com/booking")
    _btn_form    = _flex_button("次回クーポンをもらう →", form_url or "https://example.com/form")
    _btn_form_r  = _flex_button("感想フォームはこちら →", form_url or "https://example.com/form")
    _btn_review  = _flex_button("Googleの口コミを投稿する →", review_url or "https://maps.google.com", color="#E65100")

    return [
        # ─── シナリオA｜友だち登録直後（アンケート誘導） ─────────────
        {
            "name": f"シナリオA｜新規LP経由【{shop_name}】",
            "triggerType": "friend_add",
            "steps": [
                {"stepOrder": 1, "delayMinutes": 0, "deliveryHour": None, "messageType": "text",
                 "messageContent": R("{{name}}さん、はじめまして！【院長名】です。\n\nご登録ありがとうございます。\n\n下のアンケートにお答えいただいた方に、初回体験クーポンをプレゼントしています。\nぜひご回答ください！")},
                {"stepOrder": 2, "delayMinutes": 0, "deliveryHour": None, "messageType": "flex",
                 "messageContent": _flex_button("アンケートに答える →", shinsatsu_form_url or form_url or "https://example.com/form")},
            ],
        },
        # ─── シナリオB｜アンケート回答後クーポン配布→予約フォロー ──────
        {
            "name": f"シナリオB｜アンケート後クーポン配布【{shop_name}】",
            "triggerType": "tag_added",
            "triggerTagName": tag_survey_done,
            "steps": [
                {"stepOrder": 1, "delayMinutes": 0, "deliveryHour": None, "messageType": "text",
                 "messageContent": R("{{name}}さん、アンケートのご回答ありがとうございます！\n\n初回来院時に使えるクーポンをプレゼントします。\nぜひご来院の際にお役立てください。")},
                {"stepOrder": 2, "delayMinutes": 0, "deliveryHour": None, "messageType": "flex",
                 "messageContent": fc},
                {"stepOrder": 3, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、こんにちは。\n【院名】の【院長名】です。\n\n最近、こんなことはありませんか？\n\n・朝起きたとき、体が重い\n・夕方になると肩や首がパンパンになる\n・マッサージに行っても、しばらくするとまた戻る\n\nこれらは「疲れているから」ではなく、体のバランスが崩れているサインです。\n\nクーポンを使って、一度体験してみませんか？"),
                 "conditionType": "tag_not_exists", "conditionValue": tag_checkin, "nextStepOnFalse": 15},
                {"stepOrder": 4, "delayMinutes": 0, "deliveryHour": 20, "messageType": "flex",
                 "messageContent": _btn_booking,
                 "conditionType": "tag_not_exists", "conditionValue": tag_checkin, "nextStepOnFalse": 15},
                {"stepOrder": 5, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、こんにちは。\n\n体のお悩みを抱えたまま毎日を過ごすのは、思っている以上に消耗するものです。\n\n実際にご来院された方からは、\n\n「あんなに悩んでいたのに、なぜもっと早く来なかったんだろう」\n\nという言葉をよくいただきます。\n\nクーポンの期限もあと少しです。"),
                 "conditionType": "tag_not_exists", "conditionValue": tag_checkin, "nextStepOnFalse": 15},
                {"stepOrder": 6, "delayMinutes": 0, "deliveryHour": 20, "messageType": "flex",
                 "messageContent": _btn_booking,
                 "conditionType": "tag_not_exists", "conditionValue": tag_checkin, "nextStepOnFalse": 15},
                {"stepOrder": 7, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、こんにちは。\n\n「行きたいとは思っているけれど、なんとなく先延ばし…」\n\nそういう方、実はとても多いです。最初の一歩が一番難しいと思いますが、ご来院いただいた方のほぼ全員が「来てよかった」とおっしゃっています。"),
                 "conditionType": "tag_not_exists", "conditionValue": tag_checkin, "nextStepOnFalse": 15},
                {"stepOrder": 8, "delayMinutes": 0, "deliveryHour": 20, "messageType": "flex",
                 "messageContent": _btn_booking,
                 "conditionType": "tag_not_exists", "conditionValue": tag_checkin, "nextStepOnFalse": 15},
                {"stepOrder": 9, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、こんにちは。\n\nクーポンの期限が明日までとなりました。\n\nもし予定が合わない日があれば、お気軽に相談してください。日程の調整もできます。"),
                 "conditionType": "tag_not_exists", "conditionValue": tag_checkin, "nextStepOnFalse": 15},
                {"stepOrder": 10, "delayMinutes": 0, "deliveryHour": 20, "messageType": "flex",
                 "messageContent": _btn_booking,
                 "conditionType": "tag_not_exists", "conditionValue": tag_checkin, "nextStepOnFalse": 15},
                {"stepOrder": 11, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、こんにちは。\n\nお送りしていたクーポン、実は本日が最終日です。\n\n「行こうと思っていたけど、まだで…」という方、今日がラストチャンスです。"),
                 "conditionType": "tag_not_exists", "conditionValue": tag_checkin, "nextStepOnFalse": 15},
                {"stepOrder": 12, "delayMinutes": 0, "deliveryHour": 20, "messageType": "flex",
                 "messageContent": _btn_booking,
                 "conditionType": "tag_not_exists", "conditionValue": tag_checkin, "nextStepOnFalse": 15},
                {"stepOrder": 13, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、こんにちは。\n\n少し時間が経ちましたが、改めてご案内させてください。\n\n体のお悩みは、放置するほど改善に時間がかかるケースが多いです。早めにご来院いただくほど、回復も早くなります。"),
                 "conditionType": "tag_not_exists", "conditionValue": tag_checkin, "nextStepOnFalse": 15},
                {"stepOrder": 14, "delayMinutes": 0, "deliveryHour": 20, "messageType": "flex",
                 "messageContent": _btn_booking,
                 "conditionType": "tag_not_exists", "conditionValue": tag_checkin, "nextStepOnFalse": 15},
            ],
        },
        # ─── シナリオC｜初来院チェックイン ────────────────────────────
        # delayMinutes は前のステップからの累積経過時間
        # Day0→Day1→Day3→Day5→Day7→(Day10)→Day{_rv_days}
        {
            "name": f"シナリオC｜初来院チェックイン【{shop_name}】",
            "triggerType": "tag_added",
            "triggerTagName": tag_checkin,
            "steps": _build_c_steps(R, shop_name, shinsatsu_form_url or form_url,
                                     _btn_form, _btn_form_r,
                                     _btn_booking, frc, _rv_days, _step10_delay,
                                     tag_re_checkin=tag_re_checkin),
        },
        # ─── シナリオC-分岐A｜口コミ候補（星4〜5） ─────────────────
        {
            "name": f"シナリオC-分岐A｜口コミ候補（星4〜5）【{shop_name}】",
            "triggerType": "tag_added",
            "triggerTagName": "口コミ候補",
            "steps": [
                {"stepOrder": 1, "delayMinutes": 0, "deliveryHour": None, "messageType": "text",
                 "messageContent": R("{{name}}さん、嬉しいお声をありがとうございます。\n\nお約束の次回来院クーポンをお届けします。")},
                {"stepOrder": 2, "delayMinutes": 0, "deliveryHour": None, "messageType": "flex",
                 "messageContent": frc},
                {"stepOrder": 3, "delayMinutes": 0, "deliveryHour": None, "messageType": "text",
                 "messageContent": R("一つお願いがあります。\n\n先ほどご入力いただいた内容を、Googleマップの口コミとして投稿していただけませんか？\n\n同じようなお悩みを抱えて、どこに行けばいいか迷っている方の大きな参考になります。\n{{name}}さんの体験が、誰かの最初の一歩を後押しできるかもしれません。\n\n📋 コピー用テキスト（長押しでコピー）：\n{{metadata.comment}}\n\nコピーできたら、次のボタンからGoogleマップを開いて貼り付けるだけです。\n新たに文章を考える必要はありません。")},
                {"stepOrder": 6, "delayMinutes": 0, "deliveryHour": None, "messageType": "flex",
                 "messageContent": _btn_review},
            ],
        },
        # ─── シナリオC-分岐B｜改善フィードバック（星1〜3） ──────────
        {
            "name": f"シナリオC-分岐B｜改善フィードバック（星1〜3）【{shop_name}】",
            "triggerType": "tag_added",
            "triggerTagName": "改善フィードバック",
            "steps": [
                {"stepOrder": 1, "delayMinutes": 0, "deliveryHour": None, "messageType": "text",
                 "messageContent": R("{{name}}さん、正直なご意見をありがとうございます。\n\nご期待に沿えなかった点があったようで、大変申し訳ありません。\n\nお約束のクーポンをお届けします。")},
                {"stepOrder": 2, "delayMinutes": 0, "deliveryHour": None, "messageType": "flex",
                 "messageContent": frc},
                {"stepOrder": 3, "delayMinutes": 0, "deliveryHour": None, "messageType": "text",
                 "messageContent": R("もし差し支えなければ、気になった点をこのLINEに直接メッセージいただけますか。\nいただいたご意見は、施術の改善に活かしてまいります。")},
            ],
        },
        # ─── シナリオD｜既存顧客チェックイン ─────────────────────────
        # 口コミ依頼なし。Day0→Day3→Day5→Day7→Day{_rv_days}
        {
            "name": f"シナリオD｜既存顧客チェックイン【{shop_name}】",
            "triggerType": "tag_added",
            "triggerTagName": tag_re_checkin,
            "steps": [
                # Day0 即時
                {"stepOrder": 1, "delayMinutes": 0, "deliveryHour": None, "messageType": "text",
                 "messageContent": R("{{name}}さん、本日もご来院ありがとうございます！\n\nまたお会いできて嬉しいです。今日もしっかり整えていきましょう。")},
                # Day3 20時 セルフケア
                {"stepOrder": 2, "delayMinutes": 3 * 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、こんにちは。【院長名】です。\n\nご来院から3日が経ちました。お体の調子はいかがでしょうか？\n\n自宅でできる簡単なケアをご紹介します。\n\n・肩をゆっくり後ろに大きく回す（10回）\n・首を左右にゆっくり倒して10秒キープ（各1回）\n・仰向けで膝を抱えて、腰をやさしくストレッチ（30秒）\n\n1日2〜3分でできますので、ぜひ続けてみてください。")},
                # Day5 20時 経過確認
                {"stepOrder": 3, "delayMinutes": 2 * 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、その後お体の調子はいかがですか？\n\nご来院から5日が経ちました。\n\n「だいぶ楽になった」という変化を感じていただけていれば嬉しいですし、「少し戻ってきた」という場合もぜひ教えてください。\n\n何かあればいつでもこちらのLINEへご連絡ください。")},
                # Day7 20時 次回ケアの必要性
                {"stepOrder": 4, "delayMinutes": 2 * 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、こんにちは。【院長名】です。\n\nご来院から1週間が経ちました。\n\n体の歪みや筋肉の緊張は、日常の姿勢や動作のクセによって少しずつ元に戻ろうとします。\n\n「調子が良いときこそ来院する」習慣が、長期的に体を良い状態に保つ一番の近道です。\n\n次回のケアのタイミングを一緒に考えましょう。")},
                # DayN 再来院クーポン配布
                {"stepOrder": 5, "delayMinutes": max(0, _rv_days - 7) * 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R(f"{{{{name}}}}さん、こんにちは。\n\nご来院から{_rv_days}日が経ちました。\n\n体は、定期的にケアを続けることで「良い状態」が当たり前になっていきます。\n\nそろそろ次のケアのタイミングです。再来院クーポンをお届けしますので、ぜひご活用ください。")},
                {"stepOrder": 6, "delayMinutes": 0, "deliveryHour": 20, "messageType": "flex",
                 "messageContent": frc},
                {"stepOrder": 7, "delayMinutes": 0, "deliveryHour": 20, "messageType": "flex",
                 "messageContent": _btn_booking},
                # DayN+3 フォローアップ1
                {"stepOrder": 8, "delayMinutes": 3 * 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R(f"{{{{name}}}}さん、こんにちは。\n\n先日お届けした再来院クーポン、もうご確認いただけましたか？\n\n定期的に通っていただいているお客様ほど、体の変化が早く・長持ちします。\n\nせっかく整えた体をキープするために、ぜひこの機会にご来院ください。")},
                {"stepOrder": 9, "delayMinutes": 0, "deliveryHour": 20, "messageType": "flex",
                 "messageContent": _btn_booking},
                # DayN+7 フォローアップ2（最後）
                {"stepOrder": 10, "delayMinutes": 4 * 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R(f"{{{{name}}}}さん、こんにちは。\n\n再来院クーポンのご案内、最後のお知らせです。\n\n「行こうと思っていたけれど、なかなか…」そういう方、とても多いです。\n\nでも間隔が空くほど、体は元の状態に戻りやすくなります。今まで積み上げてきたケアを活かすためにも、ぜひご来院をお待ちしています。")},
                {"stepOrder": 11, "delayMinutes": 0, "deliveryHour": 20, "messageType": "flex",
                 "messageContent": _btn_booking},
            ],
        },
    ]


# ─── メイン生成関数 ────────────────────────────────────────────────
def build_scenarios_for_client(
    harness_url: str,
    harness_key: str,
    line_account_id: str,
    shop_name: str,
    owner_name: str,
    booking_url: str,
    survey_url: str,
    review_url: str,
    form_url: str,
    slug: str,
    liff_url: str,
    coupon_name: str = "初回限定クーポン",
    coupon_discount: str = "",
    revisit_coupon_name: str = "次回来院クーポン",
    revisit_coupon_discount: str = "",
    revisit_coupon_timing: int = 14,
    shinsatsu_form_url: str = "",
    shinsatsu_form_id: str = "",
) -> dict:
    """
    LINE Harnessにクライアント専用のシナリオ・タグ・QRを一括生成する。

    Returns:
        {
          "qr_url": str,          # 友だち追加QRコードURL
          "entry_route_id": str,
          "scenario_ids": {...},
          "tag_ids": {...},
        }
    """
    headers = {
        "Authorization": f"Bearer {harness_key}",
        "Content-Type": "application/json",
    }

    # ── タグ名定義 ──────────────────────────────────────────────────
    tag_names = {
        "lp":            f"{shop_name}_LP経由",
        "checkin":       "初来院済み",           # チェックインエンドポイントと一致
        "existing":      f"{shop_name}_既存顧客",
        "re_checkin":    "既存顧客",              # チェックインエンドポイントと一致
        "survey_done":   "アンケート回答済み",
        "high_rating":   "口コミ候補",
        "low_rating":    "改善フィードバック",
        "review_coupon": f"{shop_name}_感想クーポン配布済み",
    }

    # ── タグ作成（既存タグは再利用） ───────────────────────────────
    # まず全タグを取得して name→id マップを作成
    existing_tags_res = httpx.get(f"{harness_url}/api/tags", headers=headers, timeout=15)
    existing_name_to_id: dict[str, str] = {}
    if existing_tags_res.is_success:
        for t in existing_tags_res.json().get("data", []):
            existing_name_to_id[t["name"]] = t["id"]

    tag_ids = {}
    for key, name in tag_names.items():
        if name in existing_name_to_id:
            # 既存タグを再利用
            tag_ids[key] = existing_name_to_id[name]
        else:
            res = httpx.post(
                f"{harness_url}/api/tags",
                headers=headers,
                json={"name": name},
                timeout=15,
            )
            if res.is_success:
                tag_ids[key] = res.json()["data"]["id"]
            else:
                raise RuntimeError(f"タグ作成失敗 ({name}): {res.text}")

    # ── シナリオテンプレート取得 ────────────────────────────────────
    # survey_url 未設定の場合は form_url（感想フォーム）にフォールバック
    effective_survey_url = survey_url or form_url
    templates = _scenario_templates(
        shop_name=shop_name,
        owner_name=owner_name,
        booking_url=booking_url,
        survey_url=effective_survey_url,
        review_url=review_url,
        form_url=form_url,
        tag_lp=tag_names["lp"],
        tag_checkin=tag_names["checkin"],
        tag_existing=tag_names["existing"],
        tag_re_checkin=tag_names["re_checkin"],
        tag_survey_done=tag_names["survey_done"],
        coupon_name=coupon_name,
        coupon_discount=coupon_discount,
        revisit_coupon_name=revisit_coupon_name,
        revisit_coupon_discount=revisit_coupon_discount,
        review_coupon_tag_id=tag_ids.get("review_coupon", ""),
        revisit_coupon_timing=revisit_coupon_timing,
        shinsatsu_form_url=shinsatsu_form_url,
    )

    # ── 既存シナリオ一覧取得（重複防止） ──────────────────────────
    existing_scenarios_res = httpx.get(
        f"{harness_url}/api/scenarios",
        headers=headers,
        params={"lineAccountId": line_account_id},
        timeout=15,
    )
    existing_scenario_names: dict[str, str] = {}  # name → id
    if existing_scenarios_res.is_success:
        for s in existing_scenarios_res.json().get("data", []):
            existing_scenario_names[s["name"]] = s["id"]

    # ── シナリオ + ステップ作成 ─────────────────────────────────────
    scenario_ids = {}
    for tmpl in templates:
        # 同名シナリオが既存なら再利用
        if tmpl["name"] in existing_scenario_names:
            scenario_ids[tmpl["name"]] = existing_scenario_names[tmpl["name"]]
            continue

        # triggerTagName → triggerTagId 解決（全タグ対象）
        trigger_tag_id = None
        trigger_tag_name = tmpl.get("triggerTagName")
        if trigger_tag_name:
            for k, name in tag_names.items():
                if name == trigger_tag_name:
                    trigger_tag_id = tag_ids.get(k)
                    break

        s_res = httpx.post(
            f"{harness_url}/api/scenarios",
            headers=headers,
            json={
                "name": tmpl["name"],
                "triggerType": tmpl["triggerType"],
                "triggerTagId": trigger_tag_id,
                "lineAccountId": line_account_id,
                "isActive": True,
            },
            timeout=15,
        )
        if not s_res.is_success:
            raise RuntimeError(f"シナリオ作成失敗 ({tmpl['name']}): {s_res.text}")

        scenario_id = s_res.json()["data"]["id"]
        scenario_ids[tmpl["name"]] = scenario_id

        # ステップ追加
        for step in tmpl["steps"]:
            step_body = {
                "stepOrder":      step["stepOrder"],
                "delayMinutes":   step["delayMinutes"],
                "deliveryHour":   step.get("deliveryHour"),
                "messageType":    step["messageType"],
                "messageContent": step["messageContent"],
            }
            if step.get("conditionType"):
                step_body["conditionType"]  = step["conditionType"]
                step_body["conditionValue"] = step.get("conditionValue", "")
            if step.get("nextStepOnFalse"):
                step_body["nextStepOnFalse"] = step["nextStepOnFalse"]

            st_res = httpx.post(
                f"{harness_url}/api/scenarios/{scenario_id}/steps",
                headers=headers,
                json=step_body,
                timeout=15,
            )
            if not st_res.is_success:
                raise RuntimeError(f"ステップ作成失敗 (step{step['stepOrder']}): {st_res.text}")

    # ── エントリールート（QR）作成（既存は再利用） ──────────────────
    existing_er = httpx.get(f"{harness_url}/api/entry-routes", headers=headers, timeout=15)
    existing_routes: dict[str, str] = {}  # ref_code → id
    if existing_er.is_success:
        for er in existing_er.json().get("data", []):
            rc = er.get("ref_code") or er.get("refCode", "")
            if rc:
                existing_routes[rc] = er["id"]

    def _ensure_entry_route(ref_code: str, name: str, tag_id: str) -> str:
        if ref_code in existing_routes:
            return existing_routes[ref_code]
        er_res = httpx.post(
            f"{harness_url}/api/entry-routes",
            headers=headers,
            json={
                "refCode":       ref_code,
                "name":          name,
                "tagId":         tag_id,
                "lineAccountId": line_account_id,
                "redirectUrl":   None,
            },
            timeout=15,
        )
        if not er_res.is_success:
            raise RuntimeError(f"エントリールート作成失敗 ({name}): {er_res.text}")
        return er_res.json()["data"]["id"]

    # 問診フォームの on_submit_tag_id を「アンケート回答済み」に設定
    if shinsatsu_form_id and "survey_done" in tag_ids:
        httpx.put(
            f"{harness_url}/api/forms/{shinsatsu_form_id}",
            headers=headers,
            json={"onSubmitTagId": tag_ids["survey_done"]},
            timeout=15,
        )

    # ref_code は ASCII のみ（日本語slugはハッシュに変換）
    ref_slug = _ascii_ref_slug(slug)

    # LP経由QR — ネイティブ友だち追加URL（LIFF不要・離脱防止）
    lp_ref_code = f"lp-{ref_slug}"
    lp_route_id = _ensure_entry_route(lp_ref_code, f"LP経由_{shop_name}", tag_ids["lp"])

    # bot の basicId を取得してネイティブ友だち追加URLを生成
    bot_basic_id: str | None = None
    try:
        acct_res = httpx.get(
            f"{harness_url}/api/line-accounts/{line_account_id}",
            headers=headers,
            timeout=10,
        )
        if acct_res.is_success:
            token = acct_res.json().get("data", {}).get("channelAccessToken")
            if token:
                bot_res = httpx.get(
                    "https://api.line.me/v2/bot/info",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10,
                )
                if bot_res.is_success:
                    bot_basic_id = bot_res.json().get("basicId")
    except Exception:
        pass

    lp_qr_url = (
        f"https://line.me/R/ti/p/{bot_basic_id}"
        if bot_basic_id
        else f"{harness_url}/auth/line?ref={lp_ref_code}&account={line_account_id}"
    )

    # 来院チェックインQR（初回・再来院兼用。シナリオC/Dは再来院タグで分岐）
    checkin_ref_code = f"checkin-{ref_slug}"
    checkin_route_id = _ensure_entry_route(checkin_ref_code, f"来院チェックイン_{shop_name}", tag_ids["checkin"])
    checkin_qr_url   = f"{harness_url}/auth/line?ref={checkin_ref_code}&account={line_account_id}&page=checkin"

    return {
        "qr_url":           lp_qr_url,
        "entry_route_id":   lp_route_id,
        "ref_code":         lp_ref_code,
        "checkin_qr_url":   checkin_qr_url,
        "checkin_route_id": checkin_route_id,
        "checkin_ref_code": checkin_ref_code,
        "scenario_ids":     scenario_ids,
        "tag_ids":          tag_ids,
    }
