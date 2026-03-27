"""ヒアリングシートをもとにLPのライティングを生成するモジュール"""
import os
import json
import anthropic
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

WRITING_GUIDELINES_PATH = Path(__file__).parent.parent / "writing-guidelines.md"


def _load_writing_guidelines() -> str:
    if WRITING_GUIDELINES_PATH.exists():
        return WRITING_GUIDELINES_PATH.read_text(encoding="utf-8")
    return ""


SYSTEM_PROMPT = """あなたはローカル店舗（整体院・サロン・飲食店）専門のLP（ランディングページ）コピーライターです。
Web集客コンサルとして多くの店舗のLPを手がけてきた実績があります。

【役割】
ヒアリングシートの情報をもとに、集客効果の高いLPのライティングを生成します。
読んだ人が「これは自分のための店だ」と感じ、LINEに登録したくなるコピーを書いてください。

【トーンの指針】
- ビジネスライクで誠実な文体を基本とする
- 過度にカジュアルな口語や砕けた表現は避ける
- 信頼感・専門性・実績を前面に出す
- 「です・ます」調で統一し、丁寧かつ簡潔に
- 感情に訴えつつも、落ち着いた説得力のある表現を心がける"""


def generate_lp_copy(hearing: dict) -> dict:
    """
    ヒアリングシートをもとにLPの各セクションのコピーを生成する。

    Returns:
        各セクションのコピーを含むdict
    """
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    guidelines = _load_writing_guidelines()

    selected_catchcopy = hearing.get("selected_catchcopy", "")
    catchcopy_instruction = (
        f'※ catch_copyは必ず「{selected_catchcopy}」を使用してください。変更不可。'
        if selected_catchcopy else ""
    )

    prompt = f"""以下のヒアリングシートをもとに、LP（ランディングページ）の各セクションのコピーを生成してください。
{catchcopy_instruction}

【ヒアリングシート】
{json.dumps(hearing, ensure_ascii=False, indent=2)}

【ライティングガイドライン】
{guidelines}

【出力形式】
以下のJSON形式で出力してください。JSONのみ出力し、前後の説明文は不要です。

{{
  "catch_copy": "メインキャッチコピー（20〜30文字。ターゲットの悩みを直撃する一言）",
  "sub_copy": "サブキャッチコピー（30〜50文字。キャッチコピーを補足する文）",
  "pain_section": {{
    "headline": "「こんな悩みありませんか？」セクションの見出し",
    "items": ["悩み1（体験談調で）", "悩み2", "悩み3", "悩み4", "悩み5"]
  }},
  "empathy_text": "共感・問いかけの文章（100〜150文字。読者の気持ちを代弁する）",
  "solution_section": {{
    "headline": "解決策・サービス紹介セクションの見出し",
    "body": "サービスの説明文（200〜300文字。強みと解決できることを具体的に）",
    "points": [
      {{"title": "理由1の見出し", "body": "説明文（40〜60文字）"}},
      {{"title": "理由2の見出し", "body": "説明文（40〜60文字）"}},
      {{"title": "理由3の見出し", "body": "説明文（40〜60文字）"}},
      {{"title": "理由4の見出し", "body": "説明文（40〜60文字）"}},
      {{"title": "理由5の見出し", "body": "説明文（40〜60文字）"}}
    ]
  }},
  "achievements_section": {{
    "headline": "実績・数字セクションの見出し",
    "items": ["実績1（数字を使って具体的に）", "実績2", "実績3"]
  }},
  "testimonials_section": {{
    "headline": "お客様の声セクションの見出し",
    "items": [
      {{"name": "属性", "comment": "コメント（ヒアリング情報をもとに自然な口語体で。testimonials_aiがtrueの場合は3件AIで作成）"}},
      {{"name": "属性", "comment": "コメント"}},
      {{"name": "属性", "comment": "コメント（testimonials_aiがtrueの場合のみ3件目）"}}
    ]
  }},
  "menu_section": {{
    "headline": "料金・メニューセクションの見出し",
    "lead": "メニュー紹介のリード文（60〜80文字）"
  }},
  "faq_section": {{
    "headline": "よくある質問セクションの見出し"
  }},
  "cta_section": {{
    "headline": "CTAセクションのキャッチコピー（20〜30文字）",
    "body": "行動を後押しする文章（80〜120文字。今すぐLINEに登録したくなるような）",
    "button_text": "ボタンテキスト（10文字以内）",
    "note": "ボタン下の補足テキスト（30〜40文字。安心感を与える一言）"
  }}
}}"""

    import time
    for attempt in range(3):
        try:
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            break
        except anthropic.APIStatusError as e:
            if e.status_code == 529 and attempt < 2:
                time.sleep(10 * (attempt + 1))
                continue
            raise

    raw = message.content[0].text.strip()

    # JSONブロックの抽出
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()

    return json.loads(raw)
