"""
LINE Harness シナリオ自動生成モジュール

LP設定完了後に以下を自動生成:
1. タグ3本 (新規LP経由 / 初来院 / 既存顧客)
2. シナリオ6本 + 全ステップ
3. 専用エントリールート (QRコード用)
"""
import re
import httpx

# ─── テンプレート置換 ─────────────────────────────────────────────
def _replace(text: str, shop_name: str, owner_name: str, booking_url: str,
             survey_url: str, review_url: str, form_url: str) -> str:
    return (text
        .replace("【院名】", shop_name)
        .replace("【院長名】", owner_name)
        .replace("【予約URL】", booking_url or "（予約URLを設定してください）")
        .replace("【アンケートURL】", survey_url or "（アンケートURLを設定してください）")
        .replace("【GoogleマップURL】", review_url or "（GoogleマップURLを設定してください）")
        .replace("【LINEフォームURL】", form_url or "（フォームURLを設定してください）")
    )


# ─── シナリオテンプレート ─────────────────────────────────────────
def _scenario_templates(shop_name: str, owner_name: str, booking_url: str,
                        survey_url: str, review_url: str, form_url: str,
                        tag_lp: str, tag_checkin: str, tag_existing: str,
                        review_coupon_tag_id: str = "") -> list[dict]:
    """6本のシナリオ定義を返す"""
    R = lambda t: _replace(t, shop_name, owner_name, booking_url, survey_url, review_url, form_url)

    return [
        {
            "name": f"シナリオA｜新規LP経由（アンケート前）【{shop_name}】",
            "triggerType": "tag_added",
            "triggerTagName": tag_lp,
            "steps": [
                {"stepOrder": 1, "delayMinutes": 0, "deliveryHour": None, "messageType": "text",
                 "messageContent": R("{{name}}さん、はじめまして。\n【院名】の【院長名】です。\n\nLINEへのご登録、ありがとうございます。\n\nこのLINEでは、お体のお悩みに役立つ情報や、来院された方限定のお得な情報をお届けしています。\n\nまず最初に、1つお願いがあります。\nよりお役に立てる情報をお届けするために、簡単なアンケートにご協力ください。\n\n所要時間は1〜2分ほどです。\n\n▼アンケートはこちら\n【アンケートURL】\n\nご回答いただいた方には、初回来院時に使えるクーポンをプレゼントしています。\nぜひご回答いただけると嬉しいです。")},
                {"stepOrder": 2, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、こんにちは。\n【院名】の【院長名】です。\n\n昨日ご案内したアンケート、まだご回答いただけていない場合はこちらからどうぞ。\n\n▼アンケートはこちら（所要1〜2分）\n【アンケートURL】\n\nご回答いただくと、初回来院時に使えるクーポンをお受け取りいただけます。\n\nご予約もお気軽にどうぞ。\n▼ご予約はこちら\n【予約URL】")},
                {"stepOrder": 3, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、こんにちは。\n【院名】の【院長名】です。\n\nクーポンのご案内、もう少し時間がかかっていますか？\n\nアンケートにご回答いただくと、すぐにクーポンをお届けします。\n\n▼アンケートはこちら\n【アンケートURL】\n\n「まずは一度来てみたい」という方は、アンケートなしでもご予約いただけます。\n\n▼ご予約はこちら\n【予約URL】")},
                {"stepOrder": 4, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、こんにちは。\n【院名】の【院長名】です。\n\n今日は少し、お体のことをお伝えさせてください。\n\n肩こりや腰痛は、「痛みがないから大丈夫」ではなく、気づかないうちに積み重なっているケースがほとんどです。\n\n特にデスクワークや立ち仕事が多い方は、定期的なケアを習慣にするだけで、体の変わり方が全然違ってきます。\n\n気になることがあれば、いつでもこちらのLINEにメッセージをください。\n\nまたお役に立てる情報があればご連絡しますね。")},
            ],
        },
        {
            "name": f"シナリオB｜アンケート回答後【{shop_name}】",
            "triggerType": "tag_added",
            "triggerTagName": f"{shop_name}_アンケート回答済み",
            "steps": [
                {"stepOrder": 1, "delayMinutes": 0, "deliveryHour": None, "messageType": "text",
                 "messageContent": R("{{name}}さん、アンケートへのご回答ありがとうございます。\n\nさっそくですが、初回来院時に使えるクーポンをお届けします。\n\n▼初回限定クーポン\n（クーポン内容をご確認ください）\n\nこの機会にぜひ一度、体の状態を診させてください。\n\n▼ご予約はこちら\n【予約URL】\n\nご不明な点があればいつでもご連絡ください。\nお会いできるのを楽しみにしています。")},
                {"stepOrder": 2, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、こんにちは。\n【院名】の【院長名】です。\n\n一つ質問させてください。\n最近、こんなことはありませんか？\n\n・朝起きたとき、体が重い\n・夕方になると肩や首がパンパンになる\n・マッサージに行っても、しばらくするとまた戻る\n\nこれらは「疲れているから」ではなく、体のバランスが崩れているサインです。\n\n【院名】では、根本から体を整えるアプローチを大切にしています。\n「何度通っても変わらない」とお感じの方ほど、変化を実感していただいています。\n\n▼まずは一度、体験してみませんか？\n【予約URL】")},
                {"stepOrder": 3, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、こんにちは。\n\n体のお悩みを抱えたまま毎日を過ごすのは、思っている以上に消耗するものです。\n\n実際にご来院された方からは、\n\n「あんなに悩んでいたのに、なぜもっと早く来なかったんだろう」\n\nという言葉をよくいただきます。\n\nクーポンの期限もあと少しです。\nこの機会に、ぜひご自身の体に時間を使ってみてください。\n\n▼ご予約はこちら\n【予約URL】")},
                {"stepOrder": 4, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、こんにちは。\n\n「行きたいとは思っているけれど、なんとなく先延ばし…」\n\nそういう方、実はとても多いです。\n最初の一歩が一番難しいと思いますが、ご来院いただいた方のほぼ全員が「来てよかった」とおっしゃっています。\n\n▼ご予約はこちら\n【予約URL】")},
                {"stepOrder": 5, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、こんにちは。\n\nクーポンの期限が明日までとなりました。\n\nもし予定が合わない日があれば、お気軽に相談してください。\n日程の調整もできます。\n\n▼ご予約・お問い合わせ\n【予約URL】\n\nご来院、お待ちしています。")},
                {"stepOrder": 6, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、こんにちは。\n\nお送りしていたクーポン、実は本日が最終日です。\n\n「行こうと思っていたけど、まだで…」という方、今日がラストチャンスです。\n\n▼ご予約はこちら\n【予約URL】\n\nご来院、お待ちしています。")},
                {"stepOrder": 7, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、こんにちは。\n\n少し時間が経ちましたが、改めてご案内させてください。\n\n体のお悩みは、放置するほど改善に時間がかかるケースが多いです。\n早めにご来院いただくほど、回復も早くなります。\n\n▼ご予約はこちら\n【予約URL】")},
                {"stepOrder": 8, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、こんにちは。\n\n今回のご案内はこちらで一区切りとなります。\n\n「気になっているけれどタイミングが合わなかった」という方のために、いつでもご予約をお受けしています。\n\n▼ご予約はこちら\n【予約URL】\n\n体のことで何かあれば、いつでもご相談ください。")},
            ],
        },
        {
            "name": f"シナリオC｜初来院チェックイン【{shop_name}】",
            "triggerType": "tag_added",
            "triggerTagName": tag_checkin,
            "steps": [
                {"stepOrder": 1, "delayMinutes": 0, "deliveryHour": None, "messageType": "text",
                 "messageContent": R("{{name}}さん、本日はご来院ありがとうございます。\n\n施術をより効果的にするために、簡単な問診票にご回答をお願いします。\n\n▼問診票はこちら（所要3〜5分）\n（問診フォームURLを設定してください）\n\n受付にお声がけいただく前に、ご回答いただけると助かります。")},
                {"stepOrder": 2, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、本日はご来院いただきありがとうございました。\n\nお体の調子はいかがでしょうか？\n\n施術を受けての感想を、ぜひ聞かせてください。\nご回答いただいた方全員に、次回来院時に使えるクーポンをプレゼントしています。\n\n▼感想フォームはこちら（1分ほどで入力できます）\n【LINEフォームURL】\n\nよろしくお願いします。")},
                {"stepOrder": 3, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、こんにちは。\n昨日はご来院いただきありがとうございました。\n\n昨日ご案内した感想フォーム、まだでしたらこちらからどうぞ。\n\nご回答いただいた方全員に、次回来院クーポンをお届けしています。\n\n▼感想フォームはこちら\n【LINEフォームURL】")},
                {"stepOrder": 4, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、こんにちは。\nご来院から3日が経ちました。お体の調子はいかがでしょうか？\n\n施術の効果を長持ちさせるために、自宅でできるケアをご紹介します。\n\n【簡単セルフケア】\n・肩をゆっくり後ろに大きく回す（10回）\n・首を左右にゆっくり倒して10秒キープ（各1回）\n・仰向けで膝を抱えて、腰をやさしくストレッチ（30秒）\n\n無理のない範囲で、毎日続けてみてください。")},
                {"stepOrder": 5, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、その後お体の調子はいかがですか？\n\nご来院から5日が経ちました。\n変化を感じていただけていれば嬉しいですし、「なんか戻ってきた気がする」という場合もぜひ教えてください。\n\nどんな小さなことでも、お気軽にこちらのLINEへご連絡ください。")},
                {"stepOrder": 6, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、こんにちは。\n\nご来院から1週間ほどが経ちました。\nその後、お体はいかがでしょうか？\n\n何かお気になりの点があれば、いつでもご相談ください。")},
                {"stepOrder": 7, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、一つ大切なことをお伝えさせてください。\n\n「痛みが引いた＝治った」ではない、という話です。\n\n体の歪みや筋肉の緊張は、日常の姿勢や動作のクセによって少しずつ元に戻ろうとします。\n\n特に初回施術後の2〜3週間は、体が新しい状態に定着しようとしている大切な時期です。\nこの時期に定期的なケアを続けることで、改善の効果がずっと持続しやすくなります。\n\n{{name}}さんの体が、しっかりと良い方向に定着していくことを願っています。")},
                {"stepOrder": 8, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、こんにちは。\n\n少し時間が経ちましたが、「また行きたいな」と思っていただけているなら嬉しいです。\n\nご予約はいつでもお気軽にどうぞ。\n\n▼ご予約はこちら\n【予約URL】")},
                {"stepOrder": 9, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、こんにちは。\n\nご来院から2週間が経ちました。\n\n{{name}}さんの体の状態から見ると、2〜3週間以内に一度ご来院いただくと施術の効果がより定着しやすくなります。\n\n▼ご予約はこちら\n【予約URL】\n\nご不明な点があればいつでもご連絡ください。")},
                {"stepOrder": 10, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、こんにちは。\n\n「行こうと思っているんだけど、なかなか時間が…」という方、とても多いです。\n\nでも、体のケアは後回しにするほど、回復に時間がかかるようになります。\n\n▼ご予約はこちら\n【予約URL】")},
                {"stepOrder": 11, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、こんにちは。\n\nしばらくご連絡していましたが、一度区切りのご挨拶をさせてください。\n\n何かお体のことで気になることがあれば、いつでもこちらのLINEにご連絡ください。\n「また来ようかな」と思ったときに、いつでもお待ちしています。\n\n▼ご予約はこちら\n【予約URL】")},
            ],
        },
        {
            "name": f"シナリオC-分岐A｜口コミ候補（星4〜5）【{shop_name}】",
            "triggerType": "tag_added",
            "triggerTagName": f"{shop_name}_高評価",
            "steps": [
                {"stepOrder": 1, "delayMinutes": 0, "deliveryHour": None, "messageType": "text",
                 "messageContent": R("{{name}}さん、嬉しいお声をありがとうございます。\n\nクーポンはこちらです。次回ご来院時にお使いください。\n\n（次回来院クーポンの内容を設定してください）\n\n---\n\n一つお願いがあります。\n\n先ほどフォームに入力していただいた内容を、そのままGoogleにもコピーして貼り付けていただけませんか。\n\n新たに文章を考える必要はありません。貼り付けるだけなので10秒ほどで完了します。\n\n▼Googleの口コミはこちら\n【GoogleマップURL】\n\nよろしくお願いします。")},
            ],
        },
        {
            "name": f"シナリオC-分岐B｜改善フィードバック（星1〜3）【{shop_name}】",
            "triggerType": "tag_added",
            "triggerTagName": f"{shop_name}_低評価",
            "steps": [
                {"stepOrder": 1, "delayMinutes": 0, "deliveryHour": None, "messageType": "text",
                 "messageContent": R("{{name}}さん、正直なご意見をありがとうございます。\n\nクーポンはこちらです。次回ご来院時にお使いください。\n\n（次回来院クーポンの内容を設定してください）\n\n---\n\nご期待に沿えなかった点があったようで、大変申し訳ありません。\n\nもし差し支えなければ、気になった点をこのLINEに直接メッセージいただけますか。\nいただいたご意見は、施術の改善に活かしてまいります。")},
            ],
        },
        {
            "name": f"シナリオD｜既存顧客チェックイン【{shop_name}】",
            "triggerType": "tag_added",
            "triggerTagName": tag_existing,
            "steps": [
                {"stepOrder": 1, "delayMinutes": 0, "deliveryHour": None, "messageType": "text",
                 "messageContent": R("{{name}}さん、本日もご来院ありがとうございます。\n\nまたお会いできて嬉しいです。\n今日もしっかり整えていきましょう。\n\n施術中、お体のことで何か気になることがあれば遠慮なくおっしゃってください。")},
                {"stepOrder": 2, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、本日もご来院いただきありがとうございました。\n\nお体の調子はいかがでしょうか？\n\n同じようなお悩みを抱えて、どこに行けばいいか迷っている方の参考に、{{name}}さんの体験を口コミで教えていただけませんか？\n\nご回答いただいた方全員に、次回来院クーポンをお届けしています。\n\n▼感想フォームはこちら（1分ほどで入力できます）\n【LINEフォームURL】"),
                 "conditionType": "tag_not_exists", "conditionValue": "__REVIEW_COUPON_TAG__", "nextStepOnFalse": 3},
                {"stepOrder": 3, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、こんにちは。\n\n昨日ご案内した感想フォーム、まだでしたらこちらからどうぞ。\n\n▼感想フォームはこちら\n【LINEフォームURL】\n\n{{name}}さんの声が、誰かの背中を押すかもしれません。"),
                 "conditionType": "tag_not_exists", "conditionValue": "__REVIEW_COUPON_TAG__", "nextStepOnFalse": 4},
                {"stepOrder": 4, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、こんにちは。\nご来院から3日が経ちました。お体の調子はいかがでしょうか？\n\n自宅でできる簡単なケアをご紹介します。\n\n・肩をゆっくり後ろに大きく回す（10回）\n・首を左右にゆっくり倒して10秒キープ（各1回）\n・仰向けで膝を抱えて、腰をやさしくストレッチ（30秒）\n\n何かあればいつでもご連絡ください。")},
                {"stepOrder": 5, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、その後お体の調子はいかがですか？\n\nご来院から5日が経ちました。\n気になることがあれば、いつでもこちらのLINEへご連絡ください。")},
                {"stepOrder": 6, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、こんにちは。\n\nご来院から1週間ほどが経ちました。\nその後、お体はいかがでしょうか？\n\n気になることがあれば、いつでもご相談ください。")},
                {"stepOrder": 7, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、一つ大切なことをお伝えさせてください。\n\n体の歪みや筋肉の緊張は、日常の姿勢や動作のクセによって少しずつ元に戻ろうとします。\n\n「調子が良いときこそ来院する」習慣が、長期的に体を良い状態に保つ一番の近道です。\n\n何かあれば、いつでもご連絡ください。")},
                {"stepOrder": 8, "delayMinutes": 1440, "deliveryHour": 20, "messageType": "text",
                 "messageContent": R("{{name}}さん、こんにちは。\n\nご来院から2週間が経ちました。\n\n定期的なケアのタイミングとして、そろそろ一度ご来院いただくのがベストな時期です。\n\n▼ご予約はこちら\n【予約URL】\n\nまたお会いできるのを楽しみにしています。")},
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

    # ── タグ作成 ────────────────────────────────────────────────────
    tag_ids = {}
    for key, name in tag_names.items():
        res = httpx.post(
            f"{harness_url}/api/tags",
            headers=headers,
            json={"name": name, "lineAccountId": line_account_id},
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
    )

    # ── シナリオ + ステップ作成 ─────────────────────────────────────
    scenario_ids = {}
    for tmpl in templates:
        # triggerTagName → triggerTagId 解決
        trigger_tag_id = None
        for k, name in tag_names.items():
            if name == tmpl["triggerTagName"]:
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

    # ── 専用エントリールート（QR）作成 ─────────────────────────────
    ref_code = f"lp-{slug}"
    er_res = httpx.post(
        f"{harness_url}/api/entry-routes",
        headers=headers,
        json={
            "refCode":      ref_code,
            "name":         f"LP経由_{shop_name}",
            "tagId":        tag_ids["lp"],
            "lineAccountId": line_account_id,
            "redirectUrl":  None,
        },
        timeout=15,
    )
    if not er_res.is_success:
        raise RuntimeError(f"エントリールート作成失敗: {er_res.text}")

    entry_route = er_res.json()["data"]

    # QRコードURL: /auth/line?ref=REF&account=ACCOUNT_ID
    qr_url = f"{harness_url}/auth/line?ref={ref_code}&account={line_account_id}"

    return {
        "qr_url":         qr_url,
        "entry_route_id": entry_route["id"],
        "ref_code":       ref_code,
        "scenario_ids":   scenario_ids,
        "tag_ids":        tag_ids,
    }
