"""
LINE Harness シナリオ自動生成モジュール

LP設定完了後に以下を自動生成:
1. タグ3本 (新規LP経由 / 初来院 / 既存顧客)
2. シナリオ6本 + 全ステップ
3. 専用エントリールート (QRコード用)
"""
import json
import re
import httpx

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


# ─── シナリオテンプレート ─────────────────────────────────────────
def _scenario_templates(shop_name: str, owner_name: str, booking_url: str,
                        survey_url: str, review_url: str, form_url: str,
                        tag_lp: str, tag_checkin: str, tag_existing: str,
                        coupon_name: str = "初回限定クーポン",
                        coupon_discount: str = "",
                        revisit_coupon_name: str = "次回来院クーポン",
                        revisit_coupon_discount: str = "",
                        review_coupon_tag_id: str = "") -> list[dict]:
    """6本のシナリオ定義を返す"""
    R = lambda t: _replace(t, shop_name, owner_name, booking_url, survey_url, review_url, form_url)

    # クーポンflex（即時生成）
    fc  = _flex_coupon(coupon_name, coupon_discount, booking_url)
    frc = _flex_revisit_coupon(revisit_coupon_name, revisit_coupon_discount, booking_url)

    def _fb(body: str, btn_label: str, btn_url: str, color: str = "#2C4A7C") -> str:
        """テキストボディ＋ボタンフッターのflex"""
        return json.dumps({
            "type": "bubble",
            "body": {
                "type": "box", "layout": "vertical", "spacing": "md",
                "contents": [{"type": "text", "text": body, "wrap": True}]
            },
            "footer": {
                "type": "box", "layout": "vertical",
                "contents": [{"type": "button", "style": "primary", "color": color,
                    "action": {"type": "uri", "label": btn_label, "uri": btn_url}}]
            }
        }, ensure_ascii=False)

    return [
        # ─── シナリオA｜新規LP経由（アンケート前） ───────────────────
        {
            "name": f"シナリオA｜新規LP経由（アンケート前）【{shop_name}】",
            "triggerType": "friend_add",
            "triggerTagName": None,
            "steps": [
                {"stepOrder": 1, "delayMinutes": 0, "deliveryHour": None, "messageType": "flex",
                 "messageContent": _fb(
                     R("{{name}}さん、はじめまして。\n【院名】の【院長名】です。\n\nLINEへのご登録、ありがとうございます！\n\nご登録いただいた方全員に、初回来院時に使えるクーポンをプレゼントしています。\n\nクーポンを受け取るには、1〜2分の簡単なアンケートにご回答いただくだけ！\n\nぜひご協力ください。"),
                     "アンケートに回答してクーポンを受け取る →",
                     survey_url or "https://example.com/survey"
                 )},
                {"stepOrder": 2, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "flex",
                 "messageContent": _fb(
                     R("{{name}}さん、こんにちは。\n【院名】の【院長名】です。\n\n昨日ご案内したクーポン、まだお受け取りになっていませんか？\n\nアンケートへのご回答（1〜2分）でそのままお受け取りいただけます。"),
                     "アンケートに回答してクーポンを受け取る →",
                     survey_url or "https://example.com/survey"
                 )},
                {"stepOrder": 3, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "flex",
                 "messageContent": _fb(
                     R("{{name}}さん、【院長名】です。\n\nクーポンのご案内、最後のご連絡です。\n\nアンケートにご回答いただくだけでお受け取りいただけます。所要時間は1〜2分ほどです。"),
                     "アンケートに回答してクーポンを受け取る →",
                     survey_url or "https://example.com/survey"
                 )},
                {"stepOrder": 4, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、こんにちは。\n【院名】の【院長名】です。\n\n今日は少し、お体のことをお伝えさせてください。\n\n肩こりや腰痛は、「痛みがないから大丈夫」ではなく、気づかないうちに積み重なっているケースがほとんどです。\n\n特にデスクワークや立ち仕事が多い方は、定期的なケアを習慣にするだけで、体の変わり方が全然違ってきます。\n\n気になることがあれば、いつでもこちらのLINEにメッセージをください。")},
            ],
        },
        # ─── シナリオB｜アンケート回答後 ─────────────────────────────
        {
            "name": f"シナリオB｜アンケート回答後【{shop_name}】",
            "triggerType": "tag_added",
            "triggerTagName": f"{shop_name}_アンケート回答済み",
            "steps": [
                {"stepOrder": 1, "delayMinutes": 0, "deliveryHour": None, "messageType": "text",
                 "messageContent": R("{{name}}さん、アンケートへのご回答ありがとうございます！\n\nお約束のクーポンをお届けします。\nこの機会にぜひ一度、体の状態を診させてください。")},
                {"stepOrder": 2, "delayMinutes": 0, "deliveryHour": None, "messageType": "flex",
                 "messageContent": fc},
                {"stepOrder": 3, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "flex",
                 "messageContent": _fb(
                     R("{{name}}さん、こんにちは。\n【院名】の【院長名】です。\n\n最近、こんなことはありませんか？\n\n・朝起きたとき、体が重い\n・夕方になると肩や首がパンパンになる\n・マッサージに行っても、しばらくするとまた戻る\n\nこれらは「疲れているから」ではなく、体のバランスが崩れているサインです。\n\nクーポンを使って、一度体験してみませんか？"),
                     "今すぐ予約する →",
                     booking_url or "https://example.com/booking"
                 )},
                {"stepOrder": 4, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "flex",
                 "messageContent": _fb(
                     R("{{name}}さん、こんにちは。\n\n体のお悩みを抱えたまま毎日を過ごすのは、思っている以上に消耗するものです。\n\n実際にご来院された方からは、\n\n「あんなに悩んでいたのに、なぜもっと早く来なかったんだろう」\n\nという言葉をよくいただきます。\n\nクーポンの期限もあと少しです。"),
                     "今すぐ予約する →",
                     booking_url or "https://example.com/booking"
                 )},
                {"stepOrder": 5, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "flex",
                 "messageContent": _fb(
                     R("{{name}}さん、こんにちは。\n\n「行きたいとは思っているけれど、なんとなく先延ばし…」\n\nそういう方、実はとても多いです。最初の一歩が一番難しいと思いますが、ご来院いただいた方のほぼ全員が「来てよかった」とおっしゃっています。"),
                     "今すぐ予約する →",
                     booking_url or "https://example.com/booking"
                 )},
                {"stepOrder": 6, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "flex",
                 "messageContent": _fb(
                     R("{{name}}さん、こんにちは。\n\nクーポンの期限が明日までとなりました。\n\nもし予定が合わない日があれば、お気軽に相談してください。日程の調整もできます。"),
                     "今すぐ予約する →",
                     booking_url or "https://example.com/booking"
                 )},
                {"stepOrder": 7, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "flex",
                 "messageContent": _fb(
                     R("{{name}}さん、こんにちは。\n\nお送りしていたクーポン、実は本日が最終日です。\n\n「行こうと思っていたけど、まだで…」という方、今日がラストチャンスです。"),
                     "今すぐ予約する →",
                     booking_url or "https://example.com/booking"
                 )},
                {"stepOrder": 8, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "flex",
                 "messageContent": _fb(
                     R("{{name}}さん、こんにちは。\n\n少し時間が経ちましたが、改めてご案内させてください。\n\n体のお悩みは、放置するほど改善に時間がかかるケースが多いです。早めにご来院いただくほど、回復も早くなります。"),
                     "今すぐ予約する →",
                     booking_url or "https://example.com/booking"
                 )},
            ],
        },
        # ─── シナリオC｜初来院チェックイン ────────────────────────────
        {
            "name": f"シナリオC｜初来院チェックイン【{shop_name}】",
            "triggerType": "tag_added",
            "triggerTagName": tag_checkin,
            "steps": [
                {"stepOrder": 1, "delayMinutes": 0, "deliveryHour": None, "messageType": "text",
                 "messageContent": R("{{name}}さん、本日はご来院ありがとうございます！\n\n施術をより効果的にするために、簡単な問診票にご回答をお願いします。\n受付にお声がけいただく前に、ご回答いただけると助かります。")},
                {"stepOrder": 2, "delayMinutes": 0, "deliveryHour": None, "messageType": "flex",
                 "messageContent": _flex_button("問診票に回答する →", form_url or "https://example.com/form")},
                {"stepOrder": 3, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、本日はご来院いただきありがとうございました。\n\nお体の調子はいかがでしょうか？\n\n施術を受けての感想を、ぜひ聞かせてください。\nご回答いただいた方全員に、次回来院時に使えるクーポンをプレゼントしています。")},
                {"stepOrder": 4, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "flex",
                 "messageContent": _flex_button("感想フォームに回答して次回クーポンを受け取る →", form_url or "https://example.com/form"),
                 "conditionType": "tag_not_exists", "conditionValue": "__REVIEW_COUPON_TAG__", "nextStepOnFalse": 5},
                {"stepOrder": 5, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、こんにちは。\n昨日ご案内した感想フォーム、まだでしたらこちらからどうぞ。\n\nご回答いただいた方全員に、次回来院クーポンをお届けしています。"),
                 "conditionType": "tag_not_exists", "conditionValue": "__REVIEW_COUPON_TAG__", "nextStepOnFalse": 6},
                {"stepOrder": 6, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "flex",
                 "messageContent": _flex_button("感想フォームはこちら →", form_url or "https://example.com/form"),
                 "conditionType": "tag_not_exists", "conditionValue": "__REVIEW_COUPON_TAG__", "nextStepOnFalse": 7},
                {"stepOrder": 7, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、こんにちは。\nご来院から3日が経ちました。お体の調子はいかがでしょうか？\n\n施術の効果を長持ちさせるために、自宅でできるケアをご紹介します。\n\n【簡単セルフケア】\n・肩をゆっくり後ろに大きく回す（10回）\n・首を左右にゆっくり倒して10秒キープ（各1回）\n・仰向けで膝を抱えて、腰をやさしくストレッチ（30秒）\n\n無理のない範囲で、毎日続けてみてください。")},
                {"stepOrder": 8, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、その後お体の調子はいかがですか？\n\nご来院から5日が経ちました。変化を感じていただけていれば嬉しいですし、「なんか戻ってきた気がする」という場合もぜひ教えてください。\n\nどんな小さなことでも、お気軽にこちらのLINEへご連絡ください。")},
                {"stepOrder": 9, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、一つ大切なことをお伝えさせてください。\n\n「痛みが引いた＝治った」ではない、という話です。\n\n体の歪みや筋肉の緊張は、日常の姿勢や動作のクセによって少しずつ元に戻ろうとします。\n\n特に初回施術後の2〜3週間は、体が新しい状態に定着しようとしている大切な時期です。\nこの時期に定期的なケアを続けることで、改善の効果がずっと持続しやすくなります。")},
                {"stepOrder": 10, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、こんにちは。\n\nご来院から2週間が経ちました。\n\n{{name}}さんの体の状態から見ると、2〜3週間以内に一度ご来院いただくと施術の効果がより定着しやすくなります。")},
                {"stepOrder": 11, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "flex",
                 "messageContent": _flex_button("今すぐ予約する →", booking_url or "https://example.com/booking")},
            ],
        },
        # ─── シナリオC-分岐A｜口コミ候補（星4〜5） ─────────────────
        {
            "name": f"シナリオC-分岐A｜口コミ候補（星4〜5）【{shop_name}】",
            "triggerType": "tag_added",
            "triggerTagName": f"{shop_name}_高評価",
            "steps": [
                {"stepOrder": 1, "delayMinutes": 0, "deliveryHour": None, "messageType": "text",
                 "messageContent": R("{{name}}さん、嬉しいお声をありがとうございます。\n\nお約束の次回来院クーポンをお届けします。")},
                {"stepOrder": 2, "delayMinutes": 0, "deliveryHour": None, "messageType": "flex",
                 "messageContent": frc},
                {"stepOrder": 3, "delayMinutes": 0, "deliveryHour": None, "messageType": "text",
                 "messageContent": R("一つお願いがあります。\n\n先ほどフォームに入力していただいた内容を、そのままGoogleにもコピーして貼り付けていただけますか？\n\n新たに文章を考える必要はありません。貼り付けるだけなので10秒ほどで完了します。")},
                {"stepOrder": 4, "delayMinutes": 0, "deliveryHour": None, "messageType": "flex",
                 "messageContent": _flex_button("Googleの口コミを投稿する →", review_url or "https://maps.google.com", color="#E65100")},
            ],
        },
        # ─── シナリオC-分岐B｜改善フィードバック（星1〜3） ──────────
        {
            "name": f"シナリオC-分岐B｜改善フィードバック（星1〜3）【{shop_name}】",
            "triggerType": "tag_added",
            "triggerTagName": f"{shop_name}_低評価",
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
        {
            "name": f"シナリオD｜既存顧客チェックイン【{shop_name}】",
            "triggerType": "tag_added",
            "triggerTagName": tag_existing,
            "steps": [
                {"stepOrder": 1, "delayMinutes": 0, "deliveryHour": None, "messageType": "text",
                 "messageContent": R("{{name}}さん、本日もご来院ありがとうございます！\n\nまたお会いできて嬉しいです。今日もしっかり整えていきましょう。")},
                {"stepOrder": 2, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、本日もご来院いただきありがとうございました。\n\nお体の調子はいかがでしょうか？\n\n同じようなお悩みを抱えて、どこに行けばいいか迷っている方の参考に、{{name}}さんの体験を口コミで教えていただけませんか？\n\nご回答いただいた方全員に、次回来院クーポンをお届けしています。"),
                 "conditionType": "tag_not_exists", "conditionValue": "__REVIEW_COUPON_TAG__", "nextStepOnFalse": 3},
                {"stepOrder": 3, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "flex",
                 "messageContent": _flex_button("感想フォームに回答して次回クーポンを受け取る →", form_url or "https://example.com/form"),
                 "conditionType": "tag_not_exists", "conditionValue": "__REVIEW_COUPON_TAG__", "nextStepOnFalse": 4},
                {"stepOrder": 4, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、こんにちは。\n\n昨日ご案内した感想フォーム、まだでしたらこちらからどうぞ。\n\n{{name}}さんの声が、誰かの背中を押すかもしれません。"),
                 "conditionType": "tag_not_exists", "conditionValue": "__REVIEW_COUPON_TAG__", "nextStepOnFalse": 5},
                {"stepOrder": 5, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "flex",
                 "messageContent": _flex_button("感想フォームはこちら →", form_url or "https://example.com/form"),
                 "conditionType": "tag_not_exists", "conditionValue": "__REVIEW_COUPON_TAG__", "nextStepOnFalse": 6},
                {"stepOrder": 6, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、こんにちは。\nご来院から3日が経ちました。お体の調子はいかがでしょうか？\n\n自宅でできる簡単なケアをご紹介します。\n\n・肩をゆっくり後ろに大きく回す（10回）\n・首を左右にゆっくり倒して10秒キープ（各1回）\n・仰向けで膝を抱えて、腰をやさしくストレッチ（30秒）\n\n何かあればいつでもご連絡ください。")},
                {"stepOrder": 7, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、その後お体の調子はいかがですか？\n\nご来院から5日が経ちました。気になることがあれば、いつでもこちらのLINEへご連絡ください。")},
                {"stepOrder": 8, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、一つ大切なことをお伝えさせてください。\n\n体の歪みや筋肉の緊張は、日常の姿勢や動作のクセによって少しずつ元に戻ろうとします。\n\n「調子が良いときこそ来院する」習慣が、長期的に体を良い状態に保つ一番の近道です。")},
                {"stepOrder": 9, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、こんにちは。\n\nご来院から2週間が経ちました。\n\n定期的なケアのタイミングとして、そろそろ一度ご来院いただくのがベストな時期です。")},
                {"stepOrder": 10, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "flex",
                 "messageContent": _flex_button("今すぐ予約する →", booking_url or "https://example.com/booking")},
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
        "lp":       f"{shop_name}_LP経由",
        "checkin":  f"{shop_name}_初来院",
        "existing": f"{shop_name}_既存顧客",
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
    templates = _scenario_templates(
        shop_name=shop_name,
        owner_name=owner_name,
        booking_url=booking_url,
        survey_url=survey_url,
        review_url=review_url,
        form_url=form_url,
        tag_lp=tag_names["lp"],
        tag_checkin=tag_names["checkin"],
        tag_existing=tag_names["existing"],
        coupon_name=coupon_name,
        coupon_discount=coupon_discount,
        revisit_coupon_name=revisit_coupon_name,
        revisit_coupon_discount=revisit_coupon_discount,
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

        # triggerTagName → triggerTagId 解決
        trigger_tag_id = None
        for k, name in tag_names.items():
            if name == tmpl.get("triggerTagName"):
                trigger_tag_id = tag_ids[k]
                break
        # 専用タグ以外（アンケート回答済み / 高評価 / 低評価）はIDなしで作成
        # (後から手動設定 or 自動連携)

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

    # LP経由QR
    lp_ref_code = f"lp-{slug}"
    lp_route_id = _ensure_entry_route(lp_ref_code, f"LP経由_{shop_name}", tag_ids["lp"])
    lp_qr_url   = f"{harness_url}/auth/line?ref={lp_ref_code}&account={line_account_id}"

    # 来院チェックインQR
    checkin_ref_code = f"checkin-{slug}"
    checkin_route_id = _ensure_entry_route(checkin_ref_code, f"来院チェックイン_{shop_name}", tag_ids["checkin"])
    checkin_qr_url   = f"{harness_url}/auth/line?ref={checkin_ref_code}&account={line_account_id}"

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
