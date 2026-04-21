"""判定ロジックの中心。

まずローカルのルールで一次判定を作り、Gemini の根拠確認が使える場合は
その結果を重ねて、最後に画面/API向けの `AnalysisResult` に整えます。
"""

import asyncio
import difflib
import json
import re
import time
from typing import Any
from urllib.parse import quote_plus, urlparse

import httpx

from .config import Settings
from .evidence_search import build_evidence_overview
from .models import (
    AnalysisResult,
    AnalysisSignal,
    EvidenceClaimReview,
    ResolvedPage,
    RetrievedUrl,
    ScoreCalculation,
    ScoreCalculationStep,
    SourceSnapshot,
    StyleOverview,
    StyleSignal,
    TimingOverview,
    TimingStage,
    VerificationLink,
)

ABSOLUTE_PATTERNS = [
    "絶対",
    "100%",
    "必ず",
    "完全に",
    "隠蔽",
    "断言する",
    "確実に",
]
# ここから下の *_PATTERNS / *_HINTS は、文章の危険サインや補正条件を拾う辞書です。
# 判定ロジックは「点数」だけでなく、これらの語句を理由説明にも使います。
EMOTIONAL_PATTERNS = [
    "衝撃",
    "今すぐ",
    "拡散希望",
    "ヤバい",
    "大変なこと",
    "知らないと危険",
    "許せない",
]
CONSPIRACY_PATTERNS = [
    "マスコミは報じない",
    "政府が隠している",
    "ディープステート",
    "利権",
    "捏造",
    "洗脳",
    "真実は消される",
]
OPINION_PATTERNS = [
    "コラム",
    "論説",
    "オピニオン",
    "ブログ",
    "私見",
    "感想",
    "エッセイ",
]
HIGH_RISK_DOMAINS = {
    "医療": ["ワクチン", "副作用", "感染", "治療", "薬", "病院", "医師", "医療"],
    "災害": ["地震", "津波", "避難", "台風", "噴火", "災害", "警報"],
    "政治": ["選挙", "知事", "政党", "不正", "国会", "移民", "政治", "都知事"],
    "金融": ["投資", "NISA", "株価", "仮想通貨", "利回り", "金利", "金融"],
}
SOURCE_HINTS = [
    "http://",
    "https://",
    "出典",
    "参考",
    "ソース",
    "報告書",
    "論文",
    "統計",
    "調査",
    "プレスリリース",
    "公式発表",
    "一次ソース",
]
OFFICIAL_ENTITY_HINTS = [
    "厚生労働省",
    "総務省",
    "気象庁",
    "内閣府",
    "金融庁",
    "警察庁",
    "大学",
    "研究所",
    "裁判所",
]
OFFICIAL_SITE_HINTS = OFFICIAL_ENTITY_HINTS + [
    "政府広報",
    "教育委員会",
    "消防庁",
    "日本銀行",
]
OFFICIAL_HOST_SUFFIXES = (
    "go.jp",
    "lg.jp",
    "ac.jp",
    "gov",
    "gov.jp",
)
OFFICIAL_HOSTNAMES = {
    "www.boj.or.jp",
    "boj.or.jp",
    "www.niid.go.jp",
    "niid.go.jp",
    "kokkai.ndl.go.jp",
    "www.gov-online.go.jp",
    "gov-online.go.jp",
}
FACT_CHECK_HOSTNAMES = {
    "www.factcheckcenter.jp",
    "factcheckcenter.jp",
    "www.factcheck.org",
    "factcheck.org",
    "www.snopes.com",
    "snopes.com",
}
FACT_CHECK_HINTS = [
    "ファクトチェック",
    "fact check",
    "fact-check",
]
REPORT_BACKED_ACCURATE_HINTS = [
    "日本ファクトチェックセンター",
    "factcheckcenter",
    "ファクトチェック",
    "infact",
    "インファクト",
    "litmus",
    "リトマス",
    "公式アカウント",
    "公式サイト",
    "公式faq",
    "公式faqによると",
    "公式youtube",
    "e-stat",
    "政府統計",
    "会計検査院",
    "文部科学省",
    "財務省",
    "学術論文",
    "主要報道機関",
    "複数の報道機関",
    "複数の主要報道機関",
    "公式見解",
]
REPORT_BACKED_CAUTION_HINTS = [
    "区別する必要",
    "一部異な",
    "別物",
    "直近",
    "評価",
    "解釈",
    "無駄遣い",
]
PARTIAL_INACCURACY_HINTS = [
    "主張は不正確",
    "という主張は不正確",
    "一部誤り",
    "一部誤って",
    "ではなく",
    "オリジナルは",
    "着色",
]
MOSTLY_ACCURATE_NUANCE_HINTS = [
    "概ね整合しているが",
    "概ね整合しますが",
    "わずかな差異",
    "やや控えめ",
    "わずかに異なります",
]
PARTIAL_SUPPORT_HINTS = [
    "概ね整合",
    "一致する",
    "一致しています",
    "確認できた",
    "確認できる",
    "であることは",
    "存在する",
    "数字自体は",
]
PARTIAL_CORRECTION_HINTS = [
    "ただし",
    "しかし",
    "が、",
    "ではない",
    "誤り",
    "異なる",
    "不正確",
    "公開年は",
    "名称は",
    "一次ソースは確認できない",
]
COUNTEREVIDENCE_DETAIL_CORRECTION_HINTS = [
    "ではありません",
    "ではない",
    "異なる",
    "異なります",
    "確認できません",
    "確認できない",
    "確認されていません",
    "確認されていない",
    "だけでなく",
    "もいます",
    "もいる",
    "同じく",
    "他にも",
]
COUNTEREVIDENCE_MINOR_NUMERIC_DETAIL_SIGNAL_HINTS = [
    "部分は事実と異なります",
    "とされています",
    "リリースされた",
]
COUNTEREVIDENCE_MINOR_NUMERIC_DETAIL_UNITS = ("年", "月", "日", "回", "倍", "本")
COUNTEREVIDENCE_SCOPE_CLAIM_HINTS = [
    "みんな",
    "すべて",
    "全て",
    "全部",
    "同学年",
]
COUNTEREVIDENCE_SCOPE_REASON_HINTS = [
    "だけでなく",
    "もいます",
    "もいる",
    "同じく",
    "他にも",
    "幅広い地域",
]
COUNTEREVIDENCE_MATERIAL_CLAIM_HINTS = [
    "二人とも",
    "両方",
    "いずれも",
    "両作品",
]
COUNTEREVIDENCE_MATERIAL_REASON_HINTS = [
    "主張とは逆",
    "取り違え",
    "入れ替わ",
]
COUNTEREVIDENCE_MATERIAL_ROLE_HINTS = [
    "監督",
    "プロデューサー",
]
STRONG_FALSE_CONSPIRACY_HINTS = ["陰謀論", "科学的根拠がなく", "科学的根拠はなく", "繰り返し否定"]
STRONG_FALSE_NONEXISTENT_LAW_HINTS = ["制定されていません", "存在しません", "存在せず"]
STRONG_FALSE_FAKE_QUOTE_HINTS = ["事実はなく", "事実はない", "原文の解釈も誤っている", "誤訳"]
STRONG_FALSE_FAKE_QUOTE_ABSENCE_HINTS = [
    "確認できませんでした",
    "確認されていません",
    "確認されておらず",
    "報道は確認できない",
    "報道や公的発表は確認できません",
    "発表や報道はなく",
]
STRONG_FALSE_FAKE_QUOTE_MISATTRIBUTION_HINTS = ["誤情報", "誤りである", "誤りです", "紐づくものではありません", "まとめサイト"]
STRONG_FALSE_FAKE_QUOTE_CONTEXT_HINTS = [
    "受けての発言ではありません",
    "受けてのものではありません",
    "受けたものではない",
    "とは無関係",
    "古い引用",
    "別の時期",
    "主張の前提が誤って",
    "異なる文脈",
    "本件とは異なる文脈",
]
STRONG_FALSE_FAKE_IMAGE_HINTS = ["加工された", "意図的に加工", "フェイク画像", "生成ai", "ディープフェイク", "合成", "捏造"]
STRONG_FALSE_GEOCENTRISM_REASON_HINTS = ["天動説", "地動説", "公転", "科学的に確立", "確立されています"]
STRONG_FALSE_5G_COVID_NO_SCIENCE_HINTS = [
    "科学的根拠がなく",
    "科学的根拠はなく",
    "科学的根拠がない",
    "科学的根拠は全くありません",
    "科学的知見や実験確認例は全くなく",
    "明確に否定",
]
STRONG_FALSE_VACCINE_CANCER_REASON_HINTS = ["因果関係", "主張は誤り", "認めたという主張は誤り"]
STRONG_FALSE_VACCINE_CANCER_AUTHORITY_HINTS = ["ファイザー社", "厚生労働省", "国立がん研究センター"]
STRONG_FALSE_VACCINE_CANCER_NO_BASIS_HINTS = ["根拠はない", "根拠がない", "誘発する根拠はない", "科学的根拠はない"]
STRONG_FALSE_VACCINE_CANCER_DISCLAIMER_HINTS = [
    "関連性を示す発表や報道もありません",
    "関連性は説明していない",
    "関連性は確認されていません",
]
STRONG_FALSE_BIRTHER_REASON_HINTS = ["出生証明書", "ハワイ州ホノルル", "バーサー運動", "陰謀論"]
STRONG_FALSE_BIRTHER_BIRTHPLACE_HINTS = ["ハワイ州ホノルル", "ハワイ州", "アメリカ合衆国"]
STRONG_FALSE_BIRTHER_CONFIRMATION_HINTS = ["確認されています", "確認されている", "複数の信頼できる情報源", "出生証明書"]
STRONG_FALSE_VACCINE_AUTISM_RETRACTION_HINTS = [
    "論文",
    "撤回",
    "データ不正",
    "データ改ざん",
    "データ捏造",
    "不正なデータ",
    "不正行為",
]
STRONG_FALSE_VACCINE_AUTISM_EPIDEMIOLOGY_HINTS = ["大規模な疫学研究", "多数の疫学研究", "大規模疫学研究"]
STRONG_FALSE_VACCINE_AUTISM_NO_LINK_HINTS = [
    "関連性は確認されていません",
    "関連性を示す証拠はありません",
    "関連性はない",
    "関連性は否定されている",
    "因果関係がない",
    "因果関係を否定",
    "関連性は認められていません",
    "科学的証拠はなく",
]
STRONG_FALSE_NICKNAME_REASON_HINTS = ["愛称", "広く知られています", "見当たりません", "見つかりません", "ではありません"]
STRONG_FALSE_RECORDHOLDER_CLAIM_HINTS = ["最多受賞者", "最初の受賞者", "第1回の受賞者"]
STRONG_FALSE_RECORDHOLDER_REASON_HINTS = ["最多受賞者は", "最初の受賞者は", "第1回の受賞者は", "記念すべき第1回の受賞者は"]
STRONG_FALSE_RECORDHOLDER_CONCLUSION_HINTS = ["ではありません", "である", "であり", "です", "受賞していません"]
STRONG_FALSE_IDENTITY_NEGATION_CLAIM_HINTS = ["同一人物でない", "同一人物ではない", "別人である", "別人だ"]
STRONG_FALSE_IDENTITY_NEGATION_REASON_HINTS = ["同一人物である", "同一人物です", "仮の姿", "正体", "本名は"]
STRONG_FALSE_IDENTITY_NEGATION_SUPPORT_HINTS = ["公式", "公式情報", "明記", "主人公", "毒薬"]
STRONG_FALSE_JAPAN_NORTHERNMOST_CLAIM_HINTS = ["日本の最北端"]
STRONG_FALSE_JAPAN_NORTHERNMOST_REASON_HINTS = ["最北端は", "択捉島", "宗谷岬"]
STRONG_FALSE_JAPAN_NORTHERNMOST_REASON_CONCLUSION_HINTS = ["ではない", "主張は誤り"]
STRONG_FALSE_HISTORICAL_HOAX_CLAIM_HINTS = ["朝鮮人", "井戸", "毒"]
STRONG_FALSE_HISTORICAL_HOAX_REASON_HINTS = ["流言", "デマ", "誤り", "警視庁", "内閣府", "公的資料", "複数の資料"]
STRONG_FALSE_MOON_LANDING_HOAX_CLAIM_HINTS = ["アポロ", "月面着陸", "捏造"]
STRONG_FALSE_MOON_LANDING_HOAX_REASON_HINTS = [
    "かぐや",
    "ルナリコネッサンスオービター",
    "高解像度画像",
    "レーザー反射鏡",
    "月探査機",
    "ソビエト連邦",
    "独立して監視",
    "陰謀論",
]
STRONG_FALSE_MOON_LANDING_HOAX_VARIATION_HINTS = [
    "旗の揺れ",
    "旗がなびいて",
    "星の不在",
    "星が写っていない",
    "科学的に反証",
    "40万人",
    "証言は出ていない",
    "証言がない",
]
STRONG_FALSE_SAIGO_BOSHIN_FALSE_CLAIM_HINTS = ["西郷隆盛", "戊辰戦争", "戦死"]
STRONG_FALSE_SAIGO_BOSHIN_FALSE_REASON_HINTS = ["戦死したのは", "西南戦争", "参謀"]
STRONG_FALSE_SAIGO_SEINAN_VICTORY_CLAIM_HINTS = ["西郷隆盛", "西南戦争", "勝利"]
STRONG_FALSE_SAIGO_SEINAN_VICTORY_REASON_HINTS = ["明治政府軍", "新政府軍", "敗北", "自刃", "最期を遂げ"]
ATOMIC_FALSE_COMPLEXITY_HINTS = ["だが", "が、", "しかし", "ため", "ので", "もあり", "また", "かつ", "一方"]
CORRECTION_PATTERNS = [
    "は誤り",
    "はデマ",
    "誤情報",
    "デマ",
    "否定",
    "訂正",
    "反証",
    "ファクトチェック",
    "検証",
    "misinformation",
    "false",
]
PRIMARY_SOURCE_PATTERNS = [
    "報道発表",
    "報道発表資料",
    "プレスリリース",
    "公式発表",
    "一次ソース",
    "調査結果",
    "統計",
]
GEMINI_RETRYABLE_STATUS_CODES = {
    408,
    429,
    500,
    502,
    503,
    504,
}
GEMINI_MAX_RETRIES = 2
GEMINI_RETRY_DELAY_SECONDS = 1.2
ALLOWED_LABELS = {
    "出典不明",
    "誇張表現が強い",
    "既知のデマ類型に類似",
    "信頼できる一次ソース未確認",
    "反証情報あり",
    "判定不能",
}
EVIDENCE_VERDICTS = {
    "反証あり",
    "一次ソース未確認",
    "判定不能",
    "概ね整合",
    "要追加確認",
}
EVIDENCE_LABEL_HINTS = {
    "反証あり": ["反証情報あり"],
    "一次ソース未確認": ["信頼できる一次ソース未確認"],
    "判定不能": ["判定不能"],
    "要追加確認": ["判定不能"],
    "概ね整合": [],
}
URL_RETRIEVAL_STATUS_LABELS = {
    "URL_RETRIEVAL_STATUS_SUCCESS": "取得成功",
    "URL_RETRIEVAL_STATUS_UNSPECIFIED": "状態不明",
    "URL_RETRIEVAL_STATUS_ERROR": "取得失敗",
    "URL_RETRIEVAL_STATUS_PAYWALL": "有料・会員制",
    "URL_RETRIEVAL_STATUS_UNSAFE": "安全判定で除外",
    "URL_RETRIEVAL_STATUS_NOT_FOUND": "URL未検出",
    "URL_RETRIEVAL_STATUS_UNSUPPORTED": "非対応URL",
}
FACT_CHECK_LINKS = [
    VerificationLink(title="日本ファクトチェックセンター", url="https://www.factcheckcenter.jp/", kind="ファクトチェック記事"),
    VerificationLink(title="Google Fact Check Explorer", url="https://toolbox.google.com/factcheck/explorer", kind="ファクトチェック記事"),
]
DOMAIN_LINKS: dict[str, list[VerificationLink]] = {
    "医療": [
        VerificationLink(title="厚生労働省", url="https://www.mhlw.go.jp/", kind="公的機関"),
        VerificationLink(title="国立感染症研究所", url="https://www.niid.go.jp/niid/ja/", kind="公的機関"),
        VerificationLink(title="NHKニュース", url="https://www3.nhk.or.jp/news/", kind="報道機関"),
    ],
    "災害": [
        VerificationLink(title="気象庁", url="https://www.jma.go.jp/jma/index.html", kind="公的機関"),
        VerificationLink(title="内閣府防災情報", url="https://www.bousai.go.jp/", kind="公的機関"),
        VerificationLink(title="NHKニュース", url="https://www3.nhk.or.jp/news/", kind="報道機関"),
    ],
    "政治": [
        VerificationLink(title="総務省", url="https://www.soumu.go.jp/", kind="公的機関"),
        VerificationLink(title="国会会議録検索システム", url="https://kokkai.ndl.go.jp/", kind="公的機関"),
        VerificationLink(title="Reuters Japan", url="https://jp.reuters.com/", kind="報道機関"),
    ],
    "金融": [
        VerificationLink(title="金融庁", url="https://www.fsa.go.jp/", kind="公的機関"),
        VerificationLink(title="日本銀行", url="https://www.boj.or.jp/", kind="公的機関"),
        VerificationLink(title="Reuters Japan", url="https://jp.reuters.com/", kind="報道機関"),
    ],
    "一般": [
        VerificationLink(title="政府広報オンライン", url="https://www.gov-online.go.jp/", kind="公的機関"),
        VerificationLink(title="NHKニュース", url="https://www3.nhk.or.jp/news/", kind="報道機関"),
        VerificationLink(title="Reuters Japan", url="https://jp.reuters.com/", kind="報道機関"),
    ],
}
PUBLIC_VERDICT_KEYS = {
    "正確": "water",
    "ほぼ正確": "green",
    "判断保留": "yellow",
    "不正確": "orange",
    "誤り": "red",
}
PUBLIC_VERDICT_BANDS: dict[str, tuple[int, int] | None] = {
    "正確": (0, 20),
    "ほぼ正確": (21, 40),
    "判断保留": (41, 60),
    "不正確": (61, 80),
    "誤り": (81, 100),
}
PUBLIC_VERDICT_HINTS = {
    "正確": ["一次ソースと整合"],
    "ほぼ正確": ["大筋で整合"],
    "判断保留": ["追加確認が必要"],
    "不正確": ["文脈不足に注意"],
    "誤り": ["反証根拠あり"],
}
STYLE_RELEVANT_SIGNAL_TITLES = {
    "強い見出し",
    "感情誘導",
    "陰謀論テンプレ",
    "見出し先行",
    "意見文の可能性",
    "本文が短い",
}
STYLE_SEVERITIES = {"高", "中", "低"}
COUNTEREVIDENCE_HOLD_CONFIDENCE_FLOOR = 40
COUNTEREVIDENCE_SOURCE_GAP_INACCURATE_RISK_FLOOR = 70
COUNTEREVIDENCE_SOURCE_GAP_INACCURATE_CONFIDENCE_FLOOR = 50
COUNTEREVIDENCE_SOURCE_GAP_FALSE_RISK_FLOOR = 88
COUNTEREVIDENCE_SOURCE_GAP_FALSE_CONFIDENCE_FLOOR = 51
COUNTEREVIDENCE_ERROR_RISK_FLOOR = 78
COUNTEREVIDENCE_ERROR_CONFIDENCE_FLOOR = 50
CLAIM_MODE_MAX_CHARS = 280
CLAIM_MODE_MAX_PARAGRAPHS = 2
PRIMARY_REVIEW_RISK_WEIGHT = 0.35
PRIMARY_REVIEW_CONFIDENCE_WEIGHT = 0.3
PRIMARY_REVIEW_RISK_DELTA_CAP = 12
PRIMARY_REVIEW_CONFIDENCE_DELTA_CAP = 10


def elapsed_ms(started_at: float) -> int:
    return max(int(round((time.perf_counter() - started_at) * 1000)), 0)


def merge_timing_overview(base: TimingOverview | None, extra_stages: list[TimingStage]) -> TimingOverview | None:
    stages: list[TimingStage] = []
    if base:
        stages.extend(base.stages)
    stages.extend(extra_stages)
    if not stages:
        return None
    return TimingOverview(total_ms=sum(stage.duration_ms for stage in stages), stages=stages)


def clamp(value: int, lower: int = 0, upper: int = 100) -> int:
    return max(lower, min(upper, value))


def normalize_analysis_mode(value: Any) -> str:
    mode = str(value or "").strip().lower()
    return "claim" if mode == "claim" else "article"


def is_claim_mode(page: Any) -> bool:
    if isinstance(page, dict):
        analysis_mode = normalize_analysis_mode(page.get("analysis_mode"))
        input_source = str(page.get("input_source") or "").strip()
        source_url = str(page.get("source_url") or "").strip()
        extracted_chars = int(page.get("extracted_chars") or 0)
        paragraph_count = int(page.get("paragraph_count") or 0)
        has_author = bool(page.get("has_author"))
        has_published_at = bool(page.get("has_published_at"))
        reference_link_count = int(page.get("reference_link_count") or 0)
    else:
        analysis_mode = normalize_analysis_mode(getattr(page, "analysis_mode", None))
        input_source = str(getattr(page, "input_source", "") or "").strip()
        source_url = str(getattr(page, "source_url", "") or "").strip()
        extracted_chars = int(getattr(page, "extracted_chars", 0) or 0)
        paragraph_count = int(getattr(page, "paragraph_count", 0) or 0)
        has_author = bool(getattr(page, "has_author", False))
        has_published_at = bool(getattr(page, "has_published_at", False))
        reference_link_count = int(getattr(page, "reference_link_count", 0) or 0)

    if analysis_mode == "claim":
        return True
    return (
        input_source in {"manual_text", "test_fixture"}
        and not source_url
        and not has_author
        and not has_published_at
        and reference_link_count == 0
        and extracted_chars <= CLAIM_MODE_MAX_CHARS
        and paragraph_count <= CLAIM_MODE_MAX_PARAGRAPHS
    )


def format_signed(value: int) -> str:
    return f"+{value}" if value > 0 else str(value)


def label_for_score(score: int) -> str:
    if score >= 75:
        return "高リスク"
    if score >= 45:
        return "要確認"
    return "低リスク"


def public_verdict_key(verdict: str) -> str:
    return PUBLIC_VERDICT_KEYS.get(verdict, "hold")


def public_attention_score(verdict: str, score: int | None) -> int | None:
    if score is None:
        return None
    band = PUBLIC_VERDICT_BANDS.get(verdict)
    if not band:
        return None
    lower, upper = band
    return max(lower, min(upper, score))


def public_attention_display(score: int | None) -> str:
    return "?%" if score is None else f"{score}%"


def public_verdict_display(verdict: str) -> str:
    mapping = {
        "正確": "正確",
        "ほぼ正確": "ほぼ正確",
        "判断保留": "判断保留",
        "不正確": "不正確",
        "誤り": "誤り",
    }
    return mapping.get(verdict, verdict)


def public_attention_band_display(verdict: str) -> str:
    mapping = {
        "正確": "0〜20%",
        "ほぼ正確": "21〜40%",
        "判断保留": "41〜60%",
        "不正確": "61〜80%",
        "誤り": "81〜100%",
    }
    return mapping.get(verdict, "?%")


def style_key_for_score(score: int | None) -> str:
    if score is None:
        return "gray"
    if score <= 40:
        return "gray"
    if score <= 60:
        return "yellow"
    if score <= 80:
        return "orange"
    return "red"


def style_score_display(score: int | None) -> str:
    return "?%" if score is None else f"{score}%"


def style_label_for_score(score: int | None) -> str:
    if score is None:
        return "未評価"
    if score <= 20:
        return "強い注意サインは目立たない"
    if score <= 40:
        return "注意サインは比較的少ない"
    if score <= 60:
        return "中立からやや注意寄り"
    if score <= 80:
        return "煽りや断定に注意"
    return "煽りや断定がかなり強い"


def confidence_bucket(score: int) -> str:
    if score >= 70:
        return "高め"
    if score >= 45:
        return "中程度"
    return "低め"


def normalize_link_item(item: Any, fallback_kind: str = "確認リンク") -> VerificationLink | None:
    if isinstance(item, VerificationLink):
        return item
    if not isinstance(item, dict):
        return None
    url = str(item.get("url") or "").strip()
    title = str(item.get("title") or url).strip()
    kind = str(item.get("kind") or fallback_kind).strip() or fallback_kind
    if not url:
        return None
    return VerificationLink(title=title or url, url=url, kind=kind)


def dedupe_links(links: list[VerificationLink], limit: int = 8) -> list[VerificationLink]:
    deduped: list[VerificationLink] = []
    seen_urls: set[str] = set()
    for link in links:
        if link.url in seen_urls:
            continue
        seen_urls.add(link.url)
        deduped.append(link)
        if len(deduped) >= limit:
            break
    return deduped


def has_unsettled_future_prediction_claim(claim_reviews: list[dict[str, Any]]) -> bool:
    future_time_markers = ("近い将来", "将来的に", "将来", "今後", "いずれ", "やがて")
    future_deadline_markers = ("までに", "以内", "前後", "ごろ", "頃", "ころ")
    future_modal_suffixes = ("だろう", "でしょう")
    future_outcome_markers = (
        "現れない",
        "現れる",
        "獲得する",
        "加盟する",
        "加入する",
        "改正する",
        "改憲する",
        "侵攻する",
        "起こる",
        "続ける",
    )
    uncertainty_markers = (
        "政治的目標",
        "目指して",
        "目指す",
        "国民投票",
        "承認が必要",
        "確定していない",
        "予定はありません",
        "具体的な動き",
        "確認されていません",
        "情報はありません",
        "公式発表",
        "見通し",
        "可能性",
        "推測",
        "見解",
        "議論",
        "予測",
        "断定できない",
        "現時点",
        "破られにくい",
        "評価",
    )
    for review in claim_reviews:
        claim = str(review.get("claim") or "").strip()
        reason = str(review.get("reason") or "").strip()
        if not claim:
            continue
        normalized_claim = claim.rstrip("。！？!?")
        year_matches = [int(year) for year in re.findall(r"(\d{4})年", normalized_claim)]
        has_future_year_deadline = any(year > time.localtime().tm_year for year in year_matches) and any(
            marker in normalized_claim for marker in future_deadline_markers
        )
        has_future_form = (
            any(marker in normalized_claim for marker in future_time_markers)
            or normalized_claim.endswith(future_modal_suffixes)
            or has_future_year_deadline
        )
        if not has_future_form:
            continue
        if any(marker in normalized_claim for marker in future_outcome_markers):
            return True
        if not reason:
            continue
        if any(marker in reason for marker in uncertainty_markers):
            return True
    return False


def has_disputed_historical_existence_claim(claim_reviews: list[dict[str, Any]]) -> bool:
    debate_markers = (
        "議論が続いている",
        "議論が続いており",
        "議論している",
        "議論されており",
        "歴史家の間では",
        "通説では",
        "伝説上の人物",
        "伝説上の英雄",
        "伝説的な要素が強い",
        "民間伝承",
        "創作",
        "明確な歴史的根拠は確認されていません",
        "確固たる証拠はない",
        "証拠は確立されていない",
        "裏付けられていません",
    )
    for review in claim_reviews:
        claim = str(review.get("claim") or "").strip()
        reason = str(review.get("reason") or "").strip()
        if "実在" not in claim or not reason:
            continue
        if any(marker in reason for marker in debate_markers):
            return True
    return False


def has_disputed_historical_identity_or_role_claim(claim_reviews: list[dict[str, Any]]) -> bool:
    claim_markers = ("女城主",)
    reason_markers = ("同一性", "史料が少ない", "断定を控えるべき")
    for review in claim_reviews:
        claim = str(review.get("claim") or "").strip()
        reason = str(review.get("reason") or "").strip()
        if not reason or not any(marker in claim for marker in claim_markers):
            continue
        if all(marker in reason for marker in reason_markers):
            return True
    return False


def has_disputed_authenticity_claim(claim_reviews: list[dict[str, Any]]) -> bool:
    claim_markers = ("本当に", "本物", "真正", "遺体を包んだ")
    debate_markers = ("異論", "議論", "一部", "別の研究", "研究も存在", "信頼性への異論")
    consensus_markers = ("主流の科学的見解", "主流の見解", "年代測定", "中世起源", "中世の布", "科学的に結論")
    relic_claim_markers = ("聖骸布",)
    relic_reason_markers = ("放射性炭素年代測定", "年代測定", "中世の布", "中世起源", "1260年", "1390年")
    for review in claim_reviews:
        claim = str(review.get("claim") or "").strip()
        reason = str(review.get("reason") or "").strip()
        if not reason:
            continue
        if any(marker in claim for marker in relic_claim_markers) and any(marker in reason for marker in relic_reason_markers):
            return True
        if not any(marker in claim for marker in claim_markers):
            continue
        if any(marker in reason for marker in debate_markers) and any(marker in reason for marker in consensus_markers):
            return True
    return False


def derive_public_verdict(
    risk_score: int,
    confidence_score: int,
    labels: list[str],
    source_profile: dict[str, Any],
    evidence_overview: dict[str, Any],
    claim_mode: bool = False,
) -> str:
    """内部スコアと根拠確認結果から、利用者に見せる5区分ラベルを決める。"""
    overall_verdict = str(evidence_overview.get("assessment_status") or "").strip()
    grounding_sources = evidence_overview.get("grounding_sources") or []
    claim_reviews = evidence_overview.get("claim_reviews") or []
    correction_article = bool(source_profile.get("correction_article"))
    official_source = bool(source_profile.get("official_source"))
    fact_check_source = bool(source_profile.get("fact_check_source"))
    trusted_source = bool(source_profile.get("trusted_source"))
    indeterminate = "判定不能" in labels
    source_gap = "信頼できる一次ソース未確認" in labels or "出典不明" in labels
    needs_extra_check = "追加確認が必要" in labels
    context_gap = "文脈不足に注意" in labels
    evidence_missing = not overall_verdict
    trusted_grounding_sources = count_trusted_grounding_sources(grounding_sources)
    official_grounding_sources = count_official_grounding_sources(grounding_sources)
    grounding_source_count = count_grounding_sources(grounding_sources)
    positive_claim_reviews = sum(
        1
        for review in claim_reviews
        if normalize_evidence_verdict(review.get("verdict")) == "概ね整合"
    )
    counterevidence_claim_reviews = sum(
        1
        for review in claim_reviews
        if normalize_evidence_verdict(review.get("verdict")) == "反証あり"
    )
    report_backed_claim_reviews = count_report_backed_positive_claim_reviews(claim_reviews)
    claim_review_caution = has_report_backed_claim_review_caution(claim_reviews)
    claim_review_partial_inaccuracy = has_positive_claim_review_partial_inaccuracy(claim_reviews)
    claim_review_nuance = has_positive_claim_review_nuance(claim_reviews)
    claim_review_name_correction = has_positive_claim_review_name_correction(claim_reviews)
    claim_review_death_manner_correction = has_positive_claim_review_death_manner_correction(claim_reviews)
    counterevidence_name_correction = has_counterevidence_name_correction(claim_reviews)
    counterevidence_death_manner_correction = has_counterevidence_death_manner_correction(claim_reviews)
    counterevidence_minor_detail_correction = has_counterevidence_minor_detail_correction(claim_reviews)
    strong_false_counterevidence = has_strong_false_counterevidence(claim_reviews)
    partially_supported_counterevidence = has_partially_supported_counterevidence(claim_reviews)
    unsettled_future_prediction = has_unsettled_future_prediction_claim(claim_reviews)
    disputed_historical_existence = has_disputed_historical_existence_claim(claim_reviews)
    disputed_historical_identity_or_role = has_disputed_historical_identity_or_role_claim(claim_reviews)
    disputed_authenticity = has_disputed_authenticity_claim(claim_reviews)

    if claim_mode:
        if disputed_historical_existence:
            return "判断保留"
        if disputed_historical_identity_or_role:
            return "判断保留"
        if disputed_authenticity:
            return "判断保留"
        if unsettled_future_prediction:
            return "判断保留"
        if overall_verdict == "概ね整合":
            if counterevidence_claim_reviews >= 1 and positive_claim_reviews == 0:
                return "不正確"
            if (
                claim_review_partial_inaccuracy
                or claim_review_nuance
                or claim_review_name_correction
                or claim_review_death_manner_correction
            ):
                return "ほぼ正確"
            if positive_claim_reviews >= 1 or official_grounding_sources >= 1 or trusted_grounding_sources >= 1:
                return "正確" if confidence_score >= 45 else "ほぼ正確"
            return "ほぼ正確"
        if overall_verdict == "反証あり":
            if (counterevidence_name_correction or counterevidence_death_manner_correction) and (
                positive_claim_reviews >= 1 or partially_supported_counterevidence
            ):
                return "ほぼ正確"
            if counterevidence_minor_detail_correction and confidence_score >= 48 and risk_score < 60:
                return "ほぼ正確"
            if strong_false_counterevidence and confidence_score >= 58:
                return "誤り"
            return "誤り" if risk_score >= 60 and confidence_score >= 40 else "不正確"
        if overall_verdict in {"一次ソース未確認", "判定不能", "要追加確認"}:
            return "判断保留"
        if evidence_missing:
            if "反証情報あり" in labels and risk_score >= 75 and confidence_score >= 45:
                return "不正確"
            return "判断保留"

    if overall_verdict == "反証あり":
        if official_source:
            return "正確" if risk_score <= 25 and confidence_score >= 60 else "ほぼ正確"
        if (counterevidence_name_correction or counterevidence_death_manner_correction) and (
            positive_claim_reviews >= 1 or partially_supported_counterevidence
        ):
            return "ほぼ正確"
        if counterevidence_minor_detail_correction and confidence_score >= 48:
            return "ほぼ正確"
        if correction_article or fact_check_source or trusted_source:
            return "ほぼ正確"
        if confidence_score < COUNTEREVIDENCE_HOLD_CONFIDENCE_FLOOR:
            return "判断保留"
        if source_gap or indeterminate:
            if (
                not indeterminate
                and not needs_extra_check
                and context_gap
                and risk_score >= COUNTEREVIDENCE_SOURCE_GAP_FALSE_RISK_FLOOR
                and confidence_score >= COUNTEREVIDENCE_SOURCE_GAP_FALSE_CONFIDENCE_FLOOR
            ):
                return "誤り"
            return (
                "不正確"
                if risk_score >= COUNTEREVIDENCE_SOURCE_GAP_INACCURATE_RISK_FLOOR
                and confidence_score >= COUNTEREVIDENCE_SOURCE_GAP_INACCURATE_CONFIDENCE_FLOOR
                else "判断保留"
            )
        if (
            risk_score >= COUNTEREVIDENCE_ERROR_RISK_FLOOR
            and confidence_score >= COUNTEREVIDENCE_ERROR_CONFIDENCE_FLOOR
        ):
            return "誤り"
        return "不正確"
    if overall_verdict == "概ね整合":
        if (
            claim_review_partial_inaccuracy
            or claim_review_nuance
            or claim_review_name_correction
            or claim_review_death_manner_correction
        ):
            return "ほぼ正確"
        if official_source and confidence_score >= 60 and risk_score <= 25:
            return "正確"
        if (
            official_grounding_sources >= 1
            and positive_claim_reviews >= 1
            and confidence_score >= 40
            and risk_score <= 70
            and not indeterminate
            and not needs_extra_check
        ):
            return "正確"
        if (
            trusted_grounding_sources >= 2
            and positive_claim_reviews >= 1
            and confidence_score >= 40
            and not indeterminate
            and not needs_extra_check
        ):
            return "正確"
        if (
            report_backed_claim_reviews >= 1
            and confidence_score >= 44
            and not indeterminate
            and not needs_extra_check
            and not claim_review_caution
        ):
            return "正確"
        if (
            grounding_source_count >= 3
            and positive_claim_reviews >= 1
            and confidence_score >= 45
            and risk_score <= 68
            and not indeterminate
            and not needs_extra_check
            and not claim_review_caution
        ):
            return "正確"
        return "ほぼ正確"
    if overall_verdict == "一次ソース未確認":
        return "判断保留"
    if overall_verdict == "判定不能":
        return "判断保留"
    if overall_verdict == "要追加確認":
        if partially_supported_counterevidence and confidence_score >= 39:
            return "ほぼ正確"
        return "不正確" if risk_score >= 61 else "判断保留"

    if evidence_missing and fact_check_source and risk_score <= 46 and confidence_score >= 58:
        return "ほぼ正確"
    if evidence_missing and not trusted_source and not correction_article:
        if risk_score >= 80 and source_gap and confidence_score <= 50:
            return "誤り"
        if risk_score >= 46 and confidence_score < 60:
            return "不正確"
        if risk_score <= 45 and confidence_score >= 70 and not source_gap and not indeterminate:
            return "ほぼ正確"
        if risk_score <= 40 and confidence_score < 70:
            return "判断保留"

    if "判定不能" in labels and confidence_score < 45:
        return "判断保留"
    if "信頼できる一次ソース未確認" in labels and confidence_score < 55 and risk_score < 75:
        return "判断保留"
    if official_source and confidence_score >= 55 and risk_score <= 30:
        return "正確"
    if fact_check_source and confidence_score >= 50 and risk_score <= 40:
        return "ほぼ正確"
    if risk_score <= 20:
        return "ほぼ正確"
    if risk_score <= 40:
        return "ほぼ正確"
    if risk_score <= 60:
        return "判断保留"
    if risk_score <= 80:
        return "不正確"
    return "誤り"


def build_public_supplement(verdict: str) -> str:
    if verdict == "正確":
        return "発信元や日付を確認しつつ、重要な数字は一次ソースで追うとさらに安心です。"
    if verdict == "ほぼ正確":
        return "大筋は整合していても、細部や最新更新の有無は確認してください。"
    if verdict == "判断保留":
        return "一部材料はありますが、断定に足る公開根拠がまだ十分ではありません。"
    if verdict == "不正確":
        return "見出しだけで拡散せず、一次ソースや主要報道で主要主張を確認してください。"
    if verdict == "誤り":
        return "強い断定を広める前に、公的機関や主要報道による反証有無を確認してください。"
    return "公開根拠が不足しているため、追加の一次情報や主要報道が出るまで断定は控えるのが安全です。"


def build_public_summary(
    payload: dict[str, Any],
    public_verdict: str,
    page: ResolvedPage,
    source_profile: dict[str, Any],
) -> str:
    evidence_summary = str(payload.get("evidence_overview", {}).get("assessment_summary") or "").strip()
    if evidence_summary:
        return evidence_summary
    if source_profile.get("claim_mode"):
        if public_verdict == "正確":
            return "この主張は、公開情報と大きな齟齬が見えにくく、現時点では正確と見ました。"
        if public_verdict == "ほぼ正確":
            return "この主張は大筋では整合しそうですが、細部や前提条件は追加確認の余地があります。"
        if public_verdict == "判断保留":
            return "この主張は、真偽を断定するにはまだ公開根拠が十分ではありません。"
        if public_verdict == "不正確":
            return "この主張は、一部に事実を含んでいても表現や前提にズレがありそうです。"
        if public_verdict == "誤り":
            return "この主張は、外部根拠による反証が強く、誤りと見ました。"
        return "この主張は、現時点で信頼できる裏付けを十分に確認できず、判断保留として扱いました。"
    if public_verdict == "正確":
        if source_profile.get("official_source"):
            return f"{page.site_name} の内容は、公的な一次ソースとして確認しやすく、現時点では正確と見ました。"
        if source_profile.get("fact_check_source"):
            return f"{page.site_name} の内容は、ファクトチェック記事として整合が取りやすく、現時点では正確と見ました。"
        return f"{page.site_name} の内容は、公開情報と大きな齟齬が見えにくく、現時点では正確と見ました。"
    if public_verdict == "ほぼ正確":
        return f"{page.site_name} の内容は大筋では整合しそうですが、細部や前提条件は追加確認の余地があります。"
    if public_verdict == "判断保留":
        return f"{page.site_name} の内容は一部の材料はありますが、真偽を断定するにはまだ公開根拠が十分ではありません。"
    if public_verdict == "不正確":
        return f"{page.site_name} の内容は、一部事実を含んでいても、文脈不足や表現の強さで誤解を招くおそれがあります。"
    if public_verdict == "誤り":
        return f"{page.site_name} の内容は、反証や出典不足が目立ち、誤りと見ました。"
    return f"{page.site_name} の内容は、現時点で信頼できる裏付けを十分に確認できず、判断保留として扱いました。"


def build_public_status(
    public_verdict: str,
    confidence_score: int,
    model_used: str,
    internal_status: str = "",
    style_overview: dict[str, Any] | None = None,
) -> str:
    style_score = normalize_style_score((style_overview or {}).get("score"))
    if internal_status == "要人手確認" or (style_score is not None and style_score >= 80):
        return "人による確認推奨"
    if public_verdict == "判断保留" or confidence_score < 45:
        return "人による確認推奨"
    if model_used in {"heuristic", "heuristic-fallback"}:
        return "ローカル暫定判定"
    return "自動判定"


def build_public_evidence_sources(page: ResolvedPage, payload: dict[str, Any]) -> list[VerificationLink]:
    evidence_overview = payload.get("evidence_overview", {})
    links: list[VerificationLink] = []
    for raw_link in evidence_overview.get("grounding_sources", []):
        link = normalize_link_item(raw_link, fallback_kind="Gemini参照ソース")
        if link:
            links.append(link)
    if page.source_url:
        links.append(VerificationLink(title=f"入力元: {page.site_name}", url=page.source_url, kind="入力元"))
    if not links:
        for raw_link in evidence_overview.get("links", [])[:3]:
            link = normalize_link_item(raw_link, fallback_kind="確認候補")
            if link:
                links.append(link)
    return dedupe_links(links, limit=8)


def build_public_verification_links(page: ResolvedPage, payload: dict[str, Any]) -> list[VerificationLink]:
    links: list[VerificationLink] = []
    for raw_link in payload.get("verification_links", []):
        link = normalize_link_item(raw_link)
        if link:
            links.append(link)
    for raw_link in payload.get("evidence_overview", {}).get("links", []):
        link = normalize_link_item(raw_link, fallback_kind="確認候補")
        if link:
            links.append(link)
    if page.source_url:
        links.append(VerificationLink(title="元ページを開く", url=page.source_url, kind="入力元"))
    return dedupe_links(links, limit=10)


def build_score_calculation(payload: dict[str, Any], public_verdict: str, attention_score: int | None) -> ScoreCalculation:
    steps: list[ScoreCalculationStep] = []
    heuristic_base_score = payload.get("heuristic_base_score")
    heuristic_signal_total = payload.get("heuristic_signal_total")
    heuristic_raw_score = payload.get("heuristic_raw_score")
    heuristic_risk_score = payload.get("heuristic_risk_score")
    primary_review_risk_score = payload.get("primary_review_risk_score")
    final_risk_score = int(payload.get("risk_score") or 0)
    evidence_delta = int(payload.get("evidence_risk_delta") or 0)
    attention_band_display = str(payload.get("attention_band_display") or "")

    if isinstance(heuristic_base_score, int) and isinstance(heuristic_signal_total, int) and isinstance(heuristic_raw_score, int):
        steps.append(
            ScoreCalculationStep(
                label="ローカル一次判定",
                expression=f"{heuristic_base_score} {format_signed(heuristic_signal_total)}",
                result=f"{heuristic_raw_score}点",
                note="見出し・出典・透明性などのローカル要因を足し引きした値です。",
            )
        )

    if isinstance(heuristic_risk_score, int) and heuristic_raw_score != heuristic_risk_score:
        steps.append(
            ScoreCalculationStep(
                label="0〜100に丸めた内部リスク点",
                expression=f"clamp({heuristic_raw_score})",
                result=f"{heuristic_risk_score}%",
                note="0未満や100超えにならないように丸めています。",
            )
        )

    seed_for_evidence = heuristic_risk_score
    if isinstance(primary_review_risk_score, int) and isinstance(heuristic_risk_score, int):
        steps.append(
            ScoreCalculationStep(
                label="Gemini一次判定で補正",
                expression=f"{heuristic_risk_score}% -> {primary_review_risk_score}%",
                result=f"{primary_review_risk_score}%",
                note="Ver3 では Gemini の一次判定案を弱く混ぜて内部リスク点を補正します。",
            )
        )
        seed_for_evidence = primary_review_risk_score

    if isinstance(seed_for_evidence, int):
        steps.append(
            ScoreCalculationStep(
                label="外部根拠比較の補正",
                expression=f"{seed_for_evidence}% {format_signed(evidence_delta)}",
                result=f"{final_risk_score}%",
                note="Gemini の外部根拠比較で増減した内部リスク点です。",
            )
        )

    if attention_score is not None:
        if attention_score != final_risk_score:
            steps.append(
                ScoreCalculationStep(
                    label="表示用の要注意度",
                    expression=f"{final_risk_score}% -> {attention_score}%",
                    result=f"{attention_score}%",
                    note=f"判定「{public_verdict}」の表示帯 {attention_band_display} に収まるように表示しています。",
                )
            )
        else:
            steps.append(
                ScoreCalculationStep(
                    label="最終要注意度",
                    expression=f"{final_risk_score}%",
                    result=f"{attention_score}%",
                )
            )

    return ScoreCalculation(attention_steps=steps)


def publicize_result(page: ResolvedPage, payload: dict[str, Any], source_profile: dict[str, Any]) -> AnalysisResult:
    risk_score = int(payload.get("risk_score") or 0)
    confidence_score = clamp(int(payload.get("confidence_score") or 0))
    labels = [str(label).strip() for label in payload.get("labels", []) if str(label).strip()]
    evidence_overview = dict(payload.get("evidence_overview") or {})
    signal_breakdown = payload.get("signal_breakdown", [])
    fallback_style_overview = build_fallback_style_overview(signal_breakdown).model_dump()
    style_overview = dict(payload.get("style_overview") or fallback_style_overview)
    claim_mode = bool(source_profile.get("claim_mode")) or is_claim_mode(page)
    effective_source_profile = {**source_profile, "claim_mode": claim_mode}
    public_verdict = derive_public_verdict(
        risk_score,
        confidence_score,
        labels,
        effective_source_profile,
        evidence_overview,
        claim_mode=claim_mode,
    )
    attention_score = public_attention_score(public_verdict, risk_score)
    merged_labels = list(dict.fromkeys(labels + PUBLIC_VERDICT_HINTS.get(public_verdict, [])))[:4]
    if claim_mode and public_verdict != "判断保留":
        merged_labels = [
            label
            for label in merged_labels
            if label not in {"判定不能", "出典不明", "信頼できる一次ソース未確認"}
        ][:4]
    attention_band_display = public_attention_band_display(public_verdict)
    score_calculation = build_score_calculation(
        {**payload, "attention_band_display": attention_band_display},
        public_verdict,
        attention_score,
    )
    return AnalysisResult(
        verdict=public_verdict,
        verdict_key=public_verdict_key(public_verdict),
        verdict_display=public_verdict_display(public_verdict),
        attention_score=attention_score,
        attention_display=public_attention_display(attention_score),
        attention_band_display=attention_band_display,
        risk_score=risk_score,
        caution_level=public_verdict,
        confidence=confidence_bucket(confidence_score),
        confidence_label=confidence_bucket(confidence_score),
        confidence_score=confidence_score,
        status=build_public_status(
            public_verdict,
            confidence_score,
            str(payload.get("model_used") or ""),
            str(payload.get("status") or ""),
            style_overview,
        ),
        summary=build_public_summary(payload, public_verdict, page, effective_source_profile),
        reasons=[str(reason).strip() for reason in payload.get("reasons", []) if str(reason).strip()][:3],
        supplement=build_public_supplement(public_verdict),
        labels=merged_labels,
        domain=str(payload.get("domain") or "一般"),
        evidence_sources=build_public_evidence_sources(page, payload),
        verification_links=build_public_verification_links(page, payload),
        model_used=str(payload.get("model_used") or "heuristic"),
        source_snapshot=build_source_snapshot(page),
        signal_breakdown=signal_breakdown,
        evidence_overview=evidence_overview,
        style_overview=style_overview,
        score_calculation=score_calculation,
    )


def detect_domain(text: str) -> str:
    for domain, keywords in HIGH_RISK_DOMAINS.items():
        if any(keyword in text for keyword in keywords):
            return domain
    return "一般"


def match_patterns(text: str, patterns: list[str]) -> list[str]:
    return [pattern for pattern in patterns if pattern in text]


def count_source_hints(text: str) -> int:
    lowered = text.lower()
    return sum(1 for hint in SOURCE_HINTS if hint.lower() in lowered)


def normalize_hostname(url: str | None) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    return (parsed.hostname or "").lower()


def hostname_matches(hostname: str, domains: set[str]) -> bool:
    return any(hostname == domain or hostname.endswith(f".{domain}") for domain in domains)


def build_source_profile(page: ResolvedPage, text: str, source_hint_count: int) -> dict[str, Any]:
    claim_mode = is_claim_mode(page)
    hostname = normalize_hostname(page.source_url)
    site_text = f"{page.site_name}\n{page.title}"
    combined_text = f"{site_text}\n{text[:1800]}"
    lowered_text = combined_text.lower()

    official_source = (
        hostname_matches(hostname, OFFICIAL_HOSTNAMES)
        or any(hostname == suffix or hostname.endswith(f".{suffix}") for suffix in OFFICIAL_HOST_SUFFIXES)
        or any(hint in site_text for hint in OFFICIAL_SITE_HINTS)
    )
    fact_check_source = hostname_matches(hostname, FACT_CHECK_HOSTNAMES) or any(
        hint in lowered_text for hint in FACT_CHECK_HINTS
    )
    correction_context = any(pattern.lower() in lowered_text for pattern in CORRECTION_PATTERNS)
    primary_source_context = official_source or any(pattern in combined_text for pattern in PRIMARY_SOURCE_PATTERNS)
    correction_article = correction_context and (
        fact_check_source
        or official_source
        or page.reference_link_count >= 1
        or source_hint_count >= 1
        or page.has_author
        or page.has_published_at
    )
    trusted_source = official_source or fact_check_source

    return {
        "hostname": hostname,
        "claim_mode": claim_mode,
        "official_source": official_source,
        "fact_check_source": fact_check_source,
        "trusted_source": trusted_source,
        "primary_source_context": primary_source_context,
        "correction_context": correction_context,
        "correction_article": correction_article,
    }


def build_source_snapshot(page: ResolvedPage) -> SourceSnapshot:
    return SourceSnapshot(
        title=page.title,
        site_name=page.site_name,
        source_url=page.source_url,
        input_source=page.input_source,
        analysis_mode="claim" if is_claim_mode(page) else "article",
        extraction_note=page.extraction_note,
        analysis_date=page.analysis_date,
        analysis_datetime=page.analysis_datetime,
        analysis_timezone=page.analysis_timezone,
        policy_check_status=page.policy_check_status,
        policy_check_note=page.policy_check_note,
        policy_check_url=page.policy_check_url,
        policy_checked_urls=page.policy_checked_urls,
        text_preview=page.text_preview,
        extracted_chars=page.extracted_chars,
        has_author=page.has_author,
        has_published_at=page.has_published_at,
        author_name=page.author_name,
        published_at=page.published_at,
        reference_link_count=page.reference_link_count,
        paragraph_count=page.paragraph_count,
        heading_count=page.heading_count,
        extraction_score=page.extraction_score,
    )


def style_severity_for_delta(score_delta: int) -> str:
    if score_delta >= 12:
        return "高"
    if score_delta >= 6:
        return "中"
    return "低"


def build_style_fallback_summary(score: int, relevant_signals: list[AnalysisSignal]) -> str:
    if not relevant_signals:
        return "ローカル補助判定では、本文の書き振りに強い注意サインは目立ちませんでした。"
    top_signal = max(relevant_signals, key=lambda signal: signal.score_delta)
    if score <= 40:
        return f"ローカル補助判定では、「{top_signal.title}」はあるものの、全体として強い注意サインは多くありません。"
    if score <= 60:
        return f"ローカル補助判定では、「{top_signal.title}」があり、書き振りは中立からやや注意寄りです。"
    if score <= 80:
        return f"ローカル補助判定では、「{top_signal.title}」が目立ち、煽りや断定に注意が必要です。"
    return f"ローカル補助判定では、「{top_signal.title}」が強く、煽りや断定がかなり強い書き振りです。"


def build_fallback_style_overview(signals: list[AnalysisSignal]) -> StyleOverview:
    relevant_signals = [signal for signal in signals if signal.title in STYLE_RELEVANT_SIGNAL_TITLES and signal.score_delta > 0]
    positive_total = sum(signal.score_delta for signal in relevant_signals)
    coverage_bonus = min(len(relevant_signals) * 5, 20)
    intensity_bonus = min(sum(max(signal.score_delta - 4, 0) for signal in relevant_signals), 28)
    style_score = clamp(12 + min(positive_total, 40) + coverage_bonus + intensity_bonus // 2)
    style_signals = [
        StyleSignal(
            title=signal.title,
            severity=style_severity_for_delta(signal.score_delta),
            detail=signal.detail,
        )
        for signal in sorted(relevant_signals, key=lambda item: item.score_delta, reverse=True)[:4]
    ]
    highlights = [signal.title for signal in style_signals]
    return StyleOverview(
        status="ローカル補助",
        summary=build_style_fallback_summary(style_score, relevant_signals),
        score=style_score,
        score_display=style_score_display(style_score),
        label=style_label_for_score(style_score),
        key=style_key_for_score(style_score),
        note="Gemini の書き振り評価がない場合に使う補助表示です。",
        model="local-style-fallback",
        highlights=highlights,
        signals=style_signals,
    )


def base_verification_links(domain: str, source_url: str | None) -> list[VerificationLink]:
    links = list(DOMAIN_LINKS.get(domain, DOMAIN_LINKS["一般"])) + FACT_CHECK_LINKS
    if source_url:
        links.append(VerificationLink(title="元ページを開く", url=source_url, kind="確認リンク"))
    return links


def add_signal(signals: list[AnalysisSignal], title: str, score_delta: int, detail: str) -> None:
    tone = "補足"
    if score_delta > 0:
        tone = "リスク上昇"
    elif score_delta < 0:
        tone = "リスク低下"
    signals.append(
        AnalysisSignal(
            title=title,
            score_delta=score_delta,
            tone=tone,
            detail=detail,
        )
    )


def build_reason_list(signals: list[AnalysisSignal]) -> list[str]:
    ordered = sorted(signals, key=lambda item: (abs(item.score_delta), item.score_delta), reverse=True)
    return list(dict.fromkeys(signal.detail for signal in ordered))[:4]


def merge_policy_reason(page: ResolvedPage, reasons: list[str]) -> list[str]:
    deduped = [reason for reason in dict.fromkeys(reasons) if reason]
    return deduped[:4]


def heuristic_analysis(page: ResolvedPage) -> dict[str, Any]:
    """外部AIに聞く前に、文章特徴とメタ情報だけで一次判定を作る。"""
    text = f"{page.title}\n{page.analysis_text}"
    body = page.analysis_text
    signals: list[AnalysisSignal] = []
    labels: list[str] = []
    domain = detect_domain(text)
    score = 42

    title_absolute_hits = match_patterns(page.title, ABSOLUTE_PATTERNS + EMOTIONAL_PATTERNS)
    body_emotional_hits = match_patterns(body, EMOTIONAL_PATTERNS)
    body_conspiracy_hits = match_patterns(text, CONSPIRACY_PATTERNS)
    opinion_hits = match_patterns(text, OPINION_PATTERNS)
    source_hint_count = count_source_hints(text)
    source_profile = build_source_profile(page, text, source_hint_count)
    official_entity_hits = match_patterns(text, OFFICIAL_ENTITY_HINTS)
    numeric_claims = bool(re.search(r"\d", body))
    title_is_loud = bool(title_absolute_hits or page.title.count("!") >= 1 or page.title.count("！") >= 1)
    short_body = len(body) < 500
    claim_mode = is_claim_mode(page)
    strong_transparency = page.has_author and page.has_published_at and page.reference_link_count >= 1
    medium_transparency = (page.has_author or page.has_published_at) and page.reference_link_count >= 1
    official_source = bool(source_profile["official_source"])
    fact_check_source = bool(source_profile["fact_check_source"])
    trusted_source = bool(source_profile["trusted_source"])
    correction_article = bool(source_profile["correction_article"])

    if domain != "一般":
        domain_risk = 12
        if official_source:
            domain_risk = 4
        elif fact_check_source:
            domain_risk = 6
        elif correction_article:
            domain_risk = 8
        score += domain_risk
        add_signal(signals, "高影響領域", domain_risk, f"{domain}領域の主張で、誤りがあった場合の社会的影響が大きい内容です。")

    if official_source:
        score -= 18
        add_signal(signals, "公的な一次ソース", -18, "URLやサイト名から、公的機関が直接出している一次ソースと判断できるページです。")
    elif fact_check_source:
        score -= 16
        add_signal(signals, "ファクトチェック記事", -16, "誤情報を検証するためのファクトチェック記事と判断でき、本文自体の誤警報は抑えます。")
    elif correction_article:
        score -= 8
        add_signal(signals, "訂正・検証文脈", -8, "本文は誤情報そのものではなく、誤情報の訂正や検証を目的としている可能性があります。")

    if title_is_loud:
        score += 10
        labels.append("誇張表現が強い")
        add_signal(signals, "強い見出し", 10, "見出しに断定や強い煽りがあり、過信を招く可能性があります。")

    if body_emotional_hits or body.count("!") >= 2 or body.count("！") >= 2:
        score += 8
        if "誇張表現が強い" not in labels:
            labels.append("誇張表現が強い")
        add_signal(signals, "感情誘導", 8, "本文に感情を強く揺さぶる語や煽り表現が見られます。")

    if body_conspiracy_hits:
        score += 18
        labels.append("既知のデマ類型に類似")
        add_signal(signals, "陰謀論テンプレ", 18, "陰謀論テンプレートに近い表現が含まれています。")

    if source_hint_count == 0 and page.reference_link_count == 0:
        if official_source:
            score -= 8
            add_signal(signals, "一次ソースそのもの", -8, "外部リンクがなくても、元ページ自体が公的機関の一次ソースとして機能しています。")
        elif fact_check_source:
            score += 2
            add_signal(signals, "出典抽出が限定的", 2, "ファクトチェック記事ですが、抽出本文内では出典導線を十分に確認できませんでした。")
        elif not claim_mode:
            score += 14
            labels.append("出典不明")
            add_signal(signals, "出典の手がかり不足", 14, "本文内に出典語や引用リンクが見当たらず、確認の足がかりが弱いです。")
    elif page.reference_link_count >= 2 or source_hint_count >= 2:
        source_bonus = -14 if trusted_source or correction_article else -12
        score += source_bonus
        add_signal(signals, "引用リンクあり", source_bonus, "引用リンクや出典語があり、一次ソースを追いやすい構成です。")

    if not page.has_author and not page.has_published_at:
        if official_source:
            add_signal(signals, "組織発信ページ", 0, "著者名や公開日時の明示は限定的ですが、組織名とURLから発信主体は追跡できます。")
        elif fact_check_source:
            if not claim_mode:
                score += 2
                if "信頼できる一次ソース未確認" not in labels and page.reference_link_count == 0 and source_hint_count == 0:
                    labels.append("信頼できる一次ソース未確認")
                add_signal(signals, "出所情報が一部不足", 2, "検証記事ですが、著者名や公開日時の明示は限定的でした。")
        elif not claim_mode:
            score += 8
            if "信頼できる一次ソース未確認" not in labels:
                labels.append("信頼できる一次ソース未確認")
            add_signal(signals, "出所情報が薄い", 8, "著者名や公開日時の情報が薄く、出所確認がしにくいページです。")
    elif strong_transparency:
        transparency_bonus = -12 if trusted_source or correction_article else -10
        score += transparency_bonus
        add_signal(signals, "出所情報が明確", transparency_bonus, "著者名・公開日時・引用リンクが揃っており、透明性は比較的高めです。")
    elif medium_transparency:
        transparency_bonus = -8 if trusted_source or correction_article else -6
        score += transparency_bonus
        add_signal(signals, "出所情報あり", transparency_bonus, "著者名または公開日時と引用リンクがあり、確認材料があります。")

    if numeric_claims and source_hint_count == 0 and page.reference_link_count == 0:
        if official_source:
            score -= 6
            add_signal(signals, "数字の一次ソース", -6, "数字や統計を含みますが、元ページ自体が公的機関の一次ソースです。")
        elif not claim_mode:
            score += 8
            labels.append("信頼できる一次ソース未確認")
            add_signal(signals, "数字の裏付け不足", 8, "数字や統計らしき記述がありますが、対応する出典が見当たりません。")
    elif numeric_claims and page.reference_link_count >= 1:
        score -= 4
        add_signal(signals, "数字に確認導線あり", -4, "数字を含む主張に対して、少なくとも確認できるリンクが付いています。")

    if official_entity_hits and page.reference_link_count >= 1:
        official_hint_bonus = -8 if correction_article or fact_check_source else -4
        score += official_hint_bonus
        add_signal(signals, "一次ソース候補への言及", official_hint_bonus, "公的機関や研究機関への言及があり、追加確認の起点を持てます。")

    if title_is_loud and source_hint_count == 0 and page.reference_link_count == 0:
        score += 6
        add_signal(signals, "見出し先行", 6, "見出しは強い一方で、本文の根拠提示が弱く、タイトル先行に見えます。")

    if any(word in text for word in ["誤り", "デマ", "否定", "反論", "訂正", "誤情報"]):
        labels.append("反証情報あり")
        if correction_article:
            rebuttal_delta = -10 if fact_check_source or page.reference_link_count >= 1 else -4
            score += rebuttal_delta
            add_signal(signals, "反証・訂正文脈", rebuttal_delta, "否定や訂正の語がありますが、本文は誤情報の是正や検証を主目的としている可能性があります。")
        else:
            score += 7
            add_signal(signals, "反証ワードあり", 7, "本文中に否定・訂正・反証を示す語があり、文脈確認が必要です。")

    if opinion_hits:
        score += 4
        add_signal(signals, "意見文の可能性", 4, "コラムや私見のような表現があり、事実と意見が混ざる可能性があります。")

    if short_body and not claim_mode:
        short_body_delta = 2 if trusted_source or correction_article else 4
        score += short_body_delta
        add_signal(signals, "本文が短い", short_body_delta, "抽出本文が短く、前後文脈を十分に確認できません。")

    if page.policy_check_note:
        add_signal(signals, "規約確認結果", 0, f"規約確認結果: {page.policy_check_note}")

    confidence_score = 30 + page.extraction_score // 2
    if page.reference_link_count >= 1:
        confidence_score += 8
    if page.reference_link_count >= 3:
        confidence_score += 4
    if page.has_author:
        confidence_score += 5
    if page.has_published_at:
        confidence_score += 5
    if source_hint_count >= 2:
        confidence_score += 5
    if short_body and not claim_mode:
        confidence_score -= 12
    if page.input_source == "manual_text":
        confidence_score -= 5
    if len(body) > 1800:
        confidence_score += 5
    if official_source:
        confidence_score += 12
    elif fact_check_source:
        confidence_score += 10
    elif correction_article and page.reference_link_count >= 1:
        confidence_score += 4
    if not trusted_source and source_hint_count == 0 and page.reference_link_count == 0 and not claim_mode:
        confidence_score -= 6
    if official_source and source_hint_count == 0 and page.reference_link_count == 0:
        confidence_score += 6

    risk_score = clamp(score)
    confidence_score = clamp(confidence_score)
    confidence = "モデルの確信度" if confidence_score >= 45 else "判定不能"
    status = "自動判定"
    if confidence_score < 50 or opinion_hits or page.extraction_score < 45:
        status = "要人手確認"

    if not labels and (risk_score >= 45 or confidence_score < 45):
        labels.append("判定不能")

    transparency_text = "比較的あります" if strong_transparency or trusted_source else "限定的です"
    source_text = ""
    if official_source:
        source_text = " 公的な一次ソースとして扱っています。"
    elif fact_check_source:
        source_text = " ファクトチェック記事として扱っています。"
    elif correction_article:
        source_text = " 訂正・検証記事の可能性を加味しています。"
    summary = (
        f"{page.site_name} のページを {domain} 領域として判定しました。"
        f" 出所情報は {transparency_text}。見出しの強さと出典の厚みを中心に見ています。"
        f"{source_text}"
    )
    evidence_overview = build_evidence_overview(page, domain)
    style_overview = build_fallback_style_overview(signals)

    return {
        "heuristic_base_score": 42,
        "heuristic_signal_total": score - 42,
        "heuristic_raw_score": score,
        "heuristic_risk_score": risk_score,
        "evidence_risk_delta": 0,
        "risk_score": risk_score,
        "confidence": confidence,
        "confidence_score": confidence_score,
        "status": status,
        "summary": summary,
        "labels": list(dict.fromkeys(labels))[:4],
        "reasons": merge_policy_reason(page, build_reason_list(signals)),
        "domain": domain,
        "verification_links": base_verification_links(domain, page.source_url),
        "caution_level": label_for_score(risk_score),
        "model_used": "heuristic",
        "source_snapshot": build_source_snapshot(page),
        "signal_breakdown": signals,
        "evidence_overview": evidence_overview.model_dump(),
        "style_overview": style_overview.model_dump(),
        "source_profile": source_profile,
    }


def build_prompt(page: ResolvedPage, seed: dict[str, Any], settings: Settings) -> str:
    """Gemini に渡すプロンプトを作る。ローカル一次判定もヒントとして入れる。"""
    source_snapshot = seed["source_snapshot"].model_dump()
    evidence_overview = seed["evidence_overview"]
    evidence_links = evidence_overview.get("links", [])
    source_profile = {key: value for key, value in seed.get("source_profile", {}).items() if key != "hostname"}
    prompt_seed = {
        "local_domain": seed["domain"],
        "local_labels": seed["labels"],
        "local_reasons": seed["reasons"],
        "source_profile": source_profile,
        "source_snapshot": source_snapshot,
        "evidence_claims": evidence_overview.get("claims", []),
        "evidence_links": evidence_links,
    }
    style_task_text = ""
    style_review_schema = ""
    if settings.gemini_style_review_enabled:
        style_task_text = (
            "2. 本文の書き振りだけを見て、煽り・断定・感情誘導・文脈不足の強さを採点する\n"
            "真偽と書き振りは混同しないでください。書き振りが落ち着いていても真実とは限らず、"
            "書き振りが強くても即座に虚偽とは限りません。"
        )
        style_review_schema = """
  "style_review": {
    "style_score": 0から100の整数,
    "summary": "120字以内の要約",
    "highlights": ["書き振り上の注目点1", "書き振り上の注目点2"] を最大4件,
    "signals": [
      {
        "title": "煽り表現" のような短い項目名,
        "severity": "高" または "中" または "低",
        "detail": "書き振り上の短い理由"
      }
    ]
  }
""".rstrip()

    claim_mode = is_claim_mode(page)
    mode_instruction = ""
    mode_label = "短文claim評価" if claim_mode else "記事評価"
    metadata_guidance = "一次ソースが見当たらない場合は無理に断定せず、「一次ソース未確認」または「判定不能」にしてください。"
    if claim_mode:
        mode_instruction = (
            "今回の入力は記事本文ではなく短文の主張です。入力に URL・著者名・公開日時・引用リンクが無いこと自体は通常なので、"
            "それだけで「出典不明」や「信頼できる一次ソース未確認」を付けないでください。"
            "主張そのものが公開情報と整合するかを優先し、外部検索しても真偽判断に足る根拠が見つからない場合に限って"
            "「一次ソース未確認」または「判定不能」を使ってください。"
            "発言引用を含む主張では、引用句そのもの、話者、発言時期、元の文脈が一致しているかを必ず確認し、"
            "必要なら引用の一部をそのまま検索して英語原文や過去発言も確認してください。"
        )
        metadata_guidance = (
            "短文claim評価では、入力メタデータ不足だけで「一次ソース未確認」や「判定不能」にしないでください。"
            "外部検索しても主張の真偽判断に足る根拠が見つからない場合に限って使ってください。"
        )

    return f"""
あなたは日本語のニュース検証支援AIです。
役割は次の1つ{("と補助評価1つ" if settings.gemini_style_review_enabled else "")}を厳密に分けて実行することです。
1. 本文から抽出した主張候補を外部根拠と照合して整理する
{style_task_text}
{mode_instruction}
必要に応じて google_search と url_context を使い、公開ウェブ上の一次ソース、公的機関、主要報道機関、ファクトチェック記事を優先して確認してください。
{metadata_guidance}
相対表現の「今日」「昨日」「明日」は、下記の判定日時を基準に解釈してください。
出力は次のJSONだけにしてください。Markdownや説明文は不要です。
{{
  "overall_verdict": "反証あり" または "一次ソース未確認" または "判定不能" または "概ね整合" または "要追加確認",
  "overall_summary": "120字以内の要約",
  "claim_reviews": [
    {{
      "claim": "確認した主張",
      "verdict": "反証あり" または "一次ソース未確認" または "判定不能" または "概ね整合" または "要追加確認",
      "reason": "外部根拠ベースの短い理由"
    }}
  ],
  "labels": ["反証情報あり", "信頼できる一次ソース未確認", "判定不能"] から適切なものを最大4件,
  "reasons": ["外部根拠の要点1", "外部根拠の要点2", "外部根拠の要点3"] のように最大4件,
  "suggested_queries": ["確認用検索語1", "確認用検索語2", "確認用検索語3"]{"," if style_review_schema else ""}
{style_review_schema}
}}

対象URL: {page.source_url or "未入力"}
ページ名: {page.title}
サイト名: {page.site_name}
判定日: {page.analysis_date or "未設定"}
判定日時: {page.analysis_datetime or "未設定"}
判定タイムゾーン: {page.analysis_timezone or "未設定"}
解析モード: {mode_label}

著者名: {page.author_name or "未取得"}
公開日時: {page.published_at or "未取得"}
引用リンク数: {page.reference_link_count}
抽出品質: {page.extraction_score}/100
規約確認状態: {page.policy_check_status or "未実施"}
規約確認メモ: {page.policy_check_note or "未実施"}

確認対象の本文抜粋:
\"\"\"
{page.analysis_text[:2400]}
\"\"\"

ローカルで抽出した確認対象の主張候補:
{json.dumps(evidence_overview.get("claims", []), ensure_ascii=False)}

事前に作った確認導線:
{json.dumps(evidence_links, ensure_ascii=False)}

ローカル一次判定の補助情報:
{json.dumps(prompt_seed, ensure_ascii=False)}
""".strip()


def extract_json_block(raw_text: str) -> dict[str, Any]:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Gemini response did not contain JSON")
    return json.loads(cleaned[start : end + 1])


def get_dict_value(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload[key]
    return None


def parse_grounding_queries(candidate: dict[str, Any]) -> list[str]:
    metadata = get_dict_value(candidate, "groundingMetadata", "grounding_metadata") or {}
    raw_queries = get_dict_value(metadata, "webSearchQueries", "web_search_queries") or []
    queries = [str(query).strip() for query in raw_queries if str(query).strip()]
    return list(dict.fromkeys(queries))[:6]


def parse_grounding_sources(candidate: dict[str, Any]) -> list[VerificationLink]:
    metadata = get_dict_value(candidate, "groundingMetadata", "grounding_metadata") or {}
    chunks = get_dict_value(metadata, "groundingChunks", "grounding_chunks") or []
    sources: list[VerificationLink] = []
    seen_urls: set[str] = set()

    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        web_source = chunk.get("web")
        if not isinstance(web_source, dict):
            continue
        url = str(web_source.get("uri") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        title = str(web_source.get("title") or url).strip()
        sources.append(VerificationLink(title=title, url=url, kind="Gemini参照ソース"))
        if len(sources) >= 8:
            break
    return sources


def normalize_retrieval_status(value: Any) -> str:
    raw_status = str(value or "").strip()
    if not raw_status:
        return "状態不明"
    return URL_RETRIEVAL_STATUS_LABELS.get(raw_status, raw_status.replace("URL_RETRIEVAL_STATUS_", "").replace("_", " ").title())


def parse_retrieved_urls(candidate: dict[str, Any]) -> list[RetrievedUrl]:
    metadata = get_dict_value(candidate, "urlContextMetadata", "url_context_metadata") or {}
    url_metadata = get_dict_value(metadata, "urlMetadata", "url_metadata") or []
    retrieved: list[RetrievedUrl] = []
    seen_urls: set[str] = set()

    for entry in url_metadata:
        if not isinstance(entry, dict):
            continue
        url = str(get_dict_value(entry, "retrievedUrl", "retrieved_url", "url") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        status = normalize_retrieval_status(get_dict_value(entry, "urlRetrievalStatus", "url_retrieval_status", "status"))
        retrieved.append(RetrievedUrl(url=url, status=status))
        if len(retrieved) >= 8:
            break
    return retrieved


def normalize_style_severity(value: Any) -> str:
    severity = str(value or "").strip()
    if severity in STYLE_SEVERITIES:
        return severity
    if "高" in severity or "strong" in severity.lower():
        return "高"
    if "中" in severity or "medium" in severity.lower():
        return "中"
    return "低"


def normalize_style_score(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        score = int(float(value))
    except (TypeError, ValueError):
        return None
    return clamp(score)


def normalize_style_signals(raw_signals: Any) -> list[StyleSignal]:
    if not isinstance(raw_signals, list):
        return []
    normalized: list[StyleSignal] = []
    seen_titles: set[str] = set()
    for item in raw_signals:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        detail = str(item.get("detail") or "").strip()
        if not title or not detail or title in seen_titles:
            continue
        seen_titles.add(title)
        normalized.append(
            StyleSignal(
                title=title,
                severity=normalize_style_severity(item.get("severity")),
                detail=detail,
            )
        )
        if len(normalized) >= 4:
            break
    return normalized


def build_style_summary(score: int | None, raw_summary: Any, signals: list[StyleSignal]) -> str:
    summary = str(raw_summary or "").strip()
    if summary:
        return summary
    if signals:
        top_signal = signals[0]
        return f"Gemini は「{top_signal.title}」を主な書き振り要因として挙げました。"
    if score is None:
        return "Gemini は本文の書き振りを十分に整理できませんでした。"
    return f"Gemini は本文の書き振りを {style_label_for_score(score)} と見ました。"


def sanitize_highlights(raw_highlights: Any) -> list[str]:
    if not isinstance(raw_highlights, list):
        return []
    highlights = [str(item).strip() for item in raw_highlights if str(item).strip()]
    return list(dict.fromkeys(highlights))[:4]


def normalize_primary_domain(value: Any) -> str | None:
    domain = str(value or "").strip()
    if domain in DOMAIN_LINKS:
        return domain
    return None


def normalize_primary_score(value: Any, fallback: int) -> int:
    try:
        return clamp(int(float(value)))
    except (TypeError, ValueError):
        return clamp(fallback)


def blend_primary_score(seed_score: int, primary_score: int, weight: float, delta_cap: int) -> int:
    delta = primary_score - seed_score
    weighted_delta = int(round(delta * weight))
    bounded_delta = max(-delta_cap, min(delta_cap, weighted_delta))
    return clamp(seed_score + bounded_delta)


def apply_gemini_primary_review(seed: dict[str, Any], llm_output: dict[str, Any]) -> dict[str, Any]:
    source_profile = seed.get("source_profile", {}) if isinstance(seed, dict) else {}
    if bool(source_profile.get("claim_mode")):
        return seed

    raw_primary_review = llm_output.get("primary_review") if isinstance(llm_output, dict) else None
    if not isinstance(raw_primary_review, dict):
        return seed

    seed_risk_score = int(seed["risk_score"])
    seed_confidence_score = int(seed["confidence_score"])
    raw_risk_score = normalize_primary_score(raw_primary_review.get("risk_score"), seed_risk_score)
    raw_confidence_score = normalize_primary_score(raw_primary_review.get("confidence_score"), seed_confidence_score)
    risk_score = blend_primary_score(
        seed_risk_score,
        raw_risk_score,
        PRIMARY_REVIEW_RISK_WEIGHT,
        PRIMARY_REVIEW_RISK_DELTA_CAP,
    )
    confidence_score = blend_primary_score(
        seed_confidence_score,
        raw_confidence_score,
        PRIMARY_REVIEW_CONFIDENCE_WEIGHT,
        PRIMARY_REVIEW_CONFIDENCE_DELTA_CAP,
    )
    domain = normalize_primary_domain(raw_primary_review.get("domain")) or str(seed["domain"])
    summary = str(raw_primary_review.get("summary") or "").strip() or str(seed["summary"])

    raw_labels = raw_primary_review.get("labels")
    primary_labels = []
    if isinstance(raw_labels, list):
        primary_labels = [str(label).strip() for label in raw_labels if str(label).strip() in ALLOWED_LABELS]

    raw_reasons = raw_primary_review.get("reasons")
    primary_reasons = []
    if isinstance(raw_reasons, list):
        primary_reasons = [str(reason).strip() for reason in raw_reasons if str(reason).strip()]

    merged = dict(seed)
    merged.update(
        {
            "primary_review_raw_risk_score": raw_risk_score,
            "primary_review_risk_score": risk_score,
            "risk_score": risk_score,
            "confidence": "モデルの確信度" if confidence_score >= 45 else "判定不能",
            "confidence_score": confidence_score,
            "status": "Gemini一次判定",
            "summary": summary,
            "labels": list(dict.fromkeys(primary_labels + seed["labels"]))[:4] if primary_labels else seed["labels"],
            "reasons": list(dict.fromkeys(primary_reasons + seed["reasons"]))[:4] if primary_reasons else seed["reasons"],
            "domain": domain,
            "caution_level": label_for_score(risk_score),
        }
    )
    return merged


def extract_text_parts(parts: Any) -> list[str]:
    if not isinstance(parts, list):
        return []

    texts: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        text = str(part.get("text") or "").strip()
        if text:
            texts.append(text)
    return texts


def extract_content_text(content: Any) -> str:
    if isinstance(content, dict):
        text_parts = extract_text_parts(content.get("parts"))
        if text_parts:
            return "\n".join(text_parts)
        for key in ("text", "output_text"):
            text = str(content.get(key) or "").strip()
            if text:
                return text
        return ""

    if isinstance(content, list):
        text_parts = extract_text_parts(content)
        if text_parts:
            return "\n".join(text_parts)

    return ""


def extract_candidate_text(candidate: dict[str, Any]) -> str:
    content = candidate.get("content")
    text = extract_content_text(content)
    if text:
        return text

    for key in ("text", "output_text"):
        value = str(candidate.get(key) or "").strip()
        if value:
            return value

    raise KeyError("Candidate text not found")


def select_candidate_with_text(data: dict[str, Any]) -> tuple[dict[str, Any], str]:
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise KeyError("Candidates not found")

    last_error: Exception | None = None
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        try:
            return candidate, extract_candidate_text(candidate)
        except KeyError as exc:
            last_error = exc
            continue

    if last_error:
        raise last_error
    raise KeyError("Candidate text not found")


def format_gemini_error(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        try:
            payload = exc.response.json()
        except json.JSONDecodeError:
            payload = {}
        error_detail = payload.get("error") if isinstance(payload, dict) else {}
        message = str(error_detail.get("message") or "").strip()
        if message:
            return f"Gemini API error {status_code}: {message}"
        return f"Gemini API error {status_code}"
    if isinstance(exc, httpx.HTTPError):
        detail = str(exc).strip() or exc.__class__.__name__
        return f"Gemini HTTP error: {detail}"
    if isinstance(exc, (KeyError, ValueError, TypeError, json.JSONDecodeError)):
        return f"Gemini response parse error: {exc}"
    return f"Gemini error: {exc}"


def is_retryable_gemini_error(exc: Exception) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in GEMINI_RETRYABLE_STATUS_CODES
    return False


async def post_gemini_request(endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    timeout = httpx.Timeout(connect=15.0, read=70.0, write=20.0, pool=20.0)
    last_error: Exception | None = None

    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(GEMINI_MAX_RETRIES + 1):
            try:
                response = await client.post(endpoint, json=payload)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt >= GEMINI_MAX_RETRIES or not is_retryable_gemini_error(exc):
                    raise
                await asyncio.sleep(GEMINI_RETRY_DELAY_SECONDS * (attempt + 1))

    if last_error:
        raise last_error
    raise RuntimeError("Gemini request did not complete")


async def run_gemini_preflight(settings: Settings) -> None:
    if not settings.gemini_api_key:
        return

    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent?key={settings.gemini_api_key}"
    )
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": "接続確認です。外部検索や URL 参照は行わず、OK とだけ返してください。"
                    }
                ]
            }
        ],
        "tools": [
            {"google_search": {}},
            {"url_context": {}},
        ],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 8,
        },
    }

    try:
        await post_gemini_request(endpoint, payload)
    except httpx.HTTPError as exc:
        raise RuntimeError(format_gemini_error(exc)) from exc


async def gemini_analysis(page: ResolvedPage, settings: Settings, seed: dict[str, Any]) -> dict[str, Any] | None:
    """Gemini に根拠確認を依頼し、JSONとして扱える形で返す。"""
    if not settings.gemini_api_key:
        return None

    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent?key={settings.gemini_api_key}"
    )
    payload = {
        "contents": [{"parts": [{"text": build_prompt(page, seed, settings)}]}],
        "tools": [
            {"google_search": {}},
            {"url_context": {}},
        ],
        "generationConfig": {
            "temperature": 0.1,
        },
    }

    try:
        data = await post_gemini_request(endpoint, payload)
        candidate, raw_text = select_candidate_with_text(data)
        return {
            "output": extract_json_block(raw_text),
            "grounding_queries": parse_grounding_queries(candidate),
            "grounding_sources": [source.model_dump() for source in parse_grounding_sources(candidate)],
            "retrieved_urls": [item.model_dump() for item in parse_retrieved_urls(candidate)],
        }
    except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError, TypeError) as exc:
        return {
            "output": None,
            "grounding_queries": [],
            "grounding_sources": [],
            "retrieved_urls": [],
            "error": format_gemini_error(exc),
        }


def build_search_link(query: str) -> VerificationLink:
    return VerificationLink(
        title=f"検索: {query}",
        url=f"https://www.google.com/search?q={quote_plus(query)}",
        kind="確認リンク",
    )


def merge_links(domain: str, suggested_queries: list[str] | None, source_url: str | None) -> list[VerificationLink]:
    links = base_verification_links(domain, source_url)
    if suggested_queries:
        for query in suggested_queries[:3]:
            if query:
                links.append(build_search_link(query))
    return links


def normalize_evidence_verdict(value: Any) -> str:
    verdict = str(value or "").strip()
    if verdict in EVIDENCE_VERDICTS:
        return verdict
    if "反証" in verdict or "否定" in verdict:
        return "反証あり"
    if "一次" in verdict and ("未確認" in verdict or "不足" in verdict):
        return "一次ソース未確認"
    if "整合" in verdict or "支持" in verdict or "裏付けあり" in verdict:
        return "概ね整合"
    if "追加" in verdict or "要確認" in verdict:
        return "要追加確認"
    return "判定不能"


def normalize_claim_reviews(raw_reviews: Any, fallback_claims: list[str]) -> list[EvidenceClaimReview]:
    if not isinstance(raw_reviews, list):
        return []

    claim_reviews: list[EvidenceClaimReview] = []
    seen_claims: set[str] = set()
    for index, item in enumerate(raw_reviews):
        if not isinstance(item, dict):
            continue
        claim = str(item.get("claim") or "").strip()
        if not claim and index < len(fallback_claims):
            claim = fallback_claims[index]
        if not claim or claim in seen_claims:
            continue
        seen_claims.add(claim)
        verdict = normalize_evidence_verdict(item.get("verdict"))
        reason = str(item.get("reason") or "").strip() or "外部根拠を十分に特定できず、追加確認が必要です。"
        claim_reviews.append(EvidenceClaimReview(claim=claim, verdict=verdict, reason=reason))
        if len(claim_reviews) >= 4:
            break
    return claim_reviews


def derive_overall_verdict(raw_verdict: Any, claim_reviews: list[EvidenceClaimReview]) -> str:
    normalized = normalize_evidence_verdict(raw_verdict)
    if normalized != "判定不能" or not claim_reviews:
        return normalized

    priority = {
        "反証あり": 5,
        "一次ソース未確認": 4,
        "要追加確認": 3,
        "概ね整合": 2,
        "判定不能": 1,
    }
    return max(claim_reviews, key=lambda review: priority.get(review.verdict, 0)).verdict


def sanitize_queries(raw_queries: Any) -> list[str]:
    if not isinstance(raw_queries, list):
        return []
    queries = [str(query).strip() for query in raw_queries if str(query).strip()]
    return list(dict.fromkeys(queries))[:3]


def build_evidence_reasons(raw_reasons: Any, claim_reviews: list[EvidenceClaimReview]) -> list[str]:
    reasons: list[str] = []
    if isinstance(raw_reasons, list):
        reasons.extend(str(reason).strip() for reason in raw_reasons if str(reason).strip())
    if not reasons:
        reasons.extend(review.reason for review in claim_reviews)
    return list(dict.fromkeys(reasons))[:4]


def build_evidence_labels(raw_labels: Any, overall_verdict: str) -> list[str]:
    labels: list[str] = []
    if isinstance(raw_labels, list):
        labels.extend(str(label).strip() for label in raw_labels if str(label).strip() in ALLOWED_LABELS)
    labels.extend(EVIDENCE_LABEL_HINTS.get(overall_verdict, []))
    return list(dict.fromkeys(labels))[:4]


def build_evidence_summary(raw_summary: Any, overall_verdict: str, claim_reviews: list[EvidenceClaimReview]) -> str:
    summary = str(raw_summary or "").strip()
    if summary:
        return summary
    if claim_reviews:
        first_review = claim_reviews[0]
        return f"外部根拠比較では「{first_review.claim}」を {first_review.verdict} と整理しました。"
    return f"外部根拠比較では {overall_verdict} と整理しましたが、参照材料は限定的です。"


def determine_evidence_status(
    has_llm_output: bool,
    grounding_sources: list[dict[str, Any]],
    retrieved_urls: list[dict[str, Any]],
    claim_reviews: list[EvidenceClaimReview],
    error_note: str | None = None,
) -> str:
    if error_note:
        return "Gemini比較失敗"
    if not has_llm_output:
        return "探索リンク生成済み"
    if grounding_sources or retrieved_urls:
        return "Gemini外部根拠比較済み"
    if claim_reviews:
        return "Gemini外部根拠比較済み(参照元限定)"
    return "Gemini比較失敗"


def merge_evidence_overview(seed: dict[str, Any], llm_bundle: dict[str, Any] | None, settings: Settings) -> dict[str, Any]:
    overview = dict(seed["evidence_overview"])

    if not llm_bundle:
        return overview

    llm_output = llm_bundle.get("output") if isinstance(llm_bundle.get("output"), dict) else {}
    error_note = str(llm_bundle.get("error") or "").strip() or None
    fallback_claims = overview.get("claims", [])
    claim_reviews = normalize_claim_reviews(llm_output.get("claim_reviews"), fallback_claims)
    overall_verdict = derive_overall_verdict(llm_output.get("overall_verdict"), claim_reviews)
    grounding_queries = llm_bundle.get("grounding_queries") or []
    grounding_sources = llm_bundle.get("grounding_sources") or []
    retrieved_urls = llm_bundle.get("retrieved_urls") or []

    overview["status"] = determine_evidence_status(bool(llm_output), grounding_sources, retrieved_urls, claim_reviews, error_note)
    overview["assessment_status"] = None if error_note and not llm_output else overall_verdict
    overview["assessment_summary"] = (
        None if error_note and not llm_output else build_evidence_summary(llm_output.get("overall_summary"), overall_verdict, claim_reviews)
    )
    overview["assessment_note"] = error_note
    overview["assessment_model"] = f"{settings.gemini_model} + google_search/url_context"
    overview["claim_reviews"] = [review.model_dump() for review in claim_reviews]
    overview["grounding_queries"] = grounding_queries
    overview["grounding_sources"] = grounding_sources
    overview["retrieved_urls"] = retrieved_urls
    return overview


def merge_style_overview(seed: dict[str, Any], llm_bundle: dict[str, Any] | None, settings: Settings) -> dict[str, Any]:
    overview = dict(seed.get("style_overview") or build_fallback_style_overview(seed["signal_breakdown"]).model_dump())

    if not settings.gemini_style_review_enabled:
        overview["status"] = "ローカル補助判定"
        overview["note"] = "Gemini の書き振り評価は無効です。ローカル補助表示のみを使っています。"
        overview["model"] = "local-style-fallback"
        return overview

    if not llm_bundle:
        return overview

    llm_output = llm_bundle.get("output") if isinstance(llm_bundle.get("output"), dict) else {}
    error_note = str(llm_bundle.get("error") or "").strip() or None
    raw_style_review = llm_output.get("style_review") if isinstance(llm_output, dict) else None

    if isinstance(raw_style_review, dict):
        style_score = normalize_style_score(raw_style_review.get("style_score"))
        style_signals = normalize_style_signals(raw_style_review.get("signals"))
        style_summary = build_style_summary(style_score, raw_style_review.get("summary"), style_signals)
        overview.update(
            {
                "status": "Gemini書き振り評価済み",
                "summary": style_summary,
                "score": style_score,
                "score_display": style_score_display(style_score),
                "label": style_label_for_score(style_score),
                "key": style_key_for_score(style_score),
                "note": error_note,
                "model": f"{settings.gemini_model} text-style-review",
                "highlights": sanitize_highlights(raw_style_review.get("highlights")),
                "signals": [signal.model_dump() for signal in style_signals],
            }
        )
        return overview

    if error_note:
        overview["status"] = "Gemini評価失敗"
        overview["note"] = error_note
        overview["model"] = f"{settings.gemini_model} text-style-review"
        return overview

    overview["status"] = "Gemini返却不完全"
    overview["note"] = "書き振り評価が Gemini の返答に含まれていませんでした。"
    overview["model"] = f"{settings.gemini_model} text-style-review"
    return overview


def count_trusted_grounding_sources(grounding_sources: list[dict[str, Any]]) -> int:
    trusted_count = 0
    for source in grounding_sources:
        if not isinstance(source, dict):
            continue
        hostname = normalize_hostname(str(source.get("url") or "").strip())
        title = str(source.get("title") or "").strip()
        title_hostname = normalize_hostname(title)
        lowered_title = title.lower()
        if hostname_matches(hostname, OFFICIAL_HOSTNAMES) or any(
            hostname == suffix or hostname.endswith(f".{suffix}") for suffix in OFFICIAL_HOST_SUFFIXES
        ) or hostname_matches(title_hostname, OFFICIAL_HOSTNAMES) or any(
            title_hostname == suffix or title_hostname.endswith(f".{suffix}") for suffix in OFFICIAL_HOST_SUFFIXES
        ) or hostname_matches(lowered_title, OFFICIAL_HOSTNAMES) or any(
            lowered_title == suffix or lowered_title.endswith(f".{suffix}") for suffix in OFFICIAL_HOST_SUFFIXES
        ):
            trusted_count += 1
            continue
        if (
            hostname_matches(hostname, FACT_CHECK_HOSTNAMES)
            or hostname_matches(title_hostname, FACT_CHECK_HOSTNAMES)
            or hostname_matches(lowered_title, FACT_CHECK_HOSTNAMES)
            or any(hint in lowered_title for hint in FACT_CHECK_HINTS)
        ):
            trusted_count += 1
    return trusted_count


def count_official_grounding_sources(grounding_sources: list[dict[str, Any]]) -> int:
    official_count = 0
    for source in grounding_sources:
        if not isinstance(source, dict):
            continue
        hostname = normalize_hostname(str(source.get("url") or "").strip())
        title = str(source.get("title") or "").strip()
        title_hostname = normalize_hostname(title)
        lowered_title = title.lower()
        if (
            hostname_matches(hostname, OFFICIAL_HOSTNAMES)
            or any(hostname == suffix or hostname.endswith(f".{suffix}") for suffix in OFFICIAL_HOST_SUFFIXES)
            or hostname_matches(title_hostname, OFFICIAL_HOSTNAMES)
            or any(title_hostname == suffix or title_hostname.endswith(f".{suffix}") for suffix in OFFICIAL_HOST_SUFFIXES)
            or hostname_matches(lowered_title, OFFICIAL_HOSTNAMES)
            or any(lowered_title == suffix or lowered_title.endswith(f".{suffix}") for suffix in OFFICIAL_HOST_SUFFIXES)
        ):
            official_count += 1
    return official_count


def count_grounding_sources(grounding_sources: list[dict[str, Any]]) -> int:
    return sum(
        1
        for source in grounding_sources
        if isinstance(source, dict) and (str(source.get("title") or "").strip() or str(source.get("url") or "").strip())
    )


def count_report_backed_positive_claim_reviews(claim_reviews: list[dict[str, Any]]) -> int:
    supported_count = 0
    for review in claim_reviews:
        if not isinstance(review, dict):
            continue
        if normalize_evidence_verdict(review.get("verdict")) != "概ね整合":
            continue
        hint_text = f"{review.get('claim') or ''} {review.get('reason') or ''}".strip().lower()
        if any(hint in hint_text for hint in REPORT_BACKED_CAUTION_HINTS):
            continue
        if any(hint in hint_text for hint in REPORT_BACKED_ACCURATE_HINTS):
            supported_count += 1
    return supported_count


def has_report_backed_claim_review_caution(claim_reviews: list[dict[str, Any]]) -> bool:
    for review in claim_reviews:
        if not isinstance(review, dict):
            continue
        if normalize_evidence_verdict(review.get("verdict")) != "概ね整合":
            continue
        hint_text = f"{review.get('claim') or ''} {review.get('reason') or ''}".strip().lower()
        if any(hint in hint_text for hint in REPORT_BACKED_CAUTION_HINTS):
            return True
    return False


def has_positive_claim_review_partial_inaccuracy(claim_reviews: list[dict[str, Any]]) -> bool:
    for review in claim_reviews:
        if not isinstance(review, dict):
            continue
        if normalize_evidence_verdict(review.get("verdict")) != "概ね整合":
            continue
        hint_text = f"{review.get('claim') or ''} {review.get('reason') or ''}".strip().lower()
        if any(hint in hint_text for hint in PARTIAL_INACCURACY_HINTS):
            return True
    return False


def has_positive_claim_review_nuance(claim_reviews: list[dict[str, Any]]) -> bool:
    for review in claim_reviews:
        if not isinstance(review, dict):
            continue
        if normalize_evidence_verdict(review.get("verdict")) != "概ね整合":
            continue
        claim_text = str(review.get("claim") or "").strip()
        reason_text = str(review.get("reason") or "").strip()
        hint_text = f"{claim_text} {reason_text}".strip().lower()
        if any(hint in hint_text for hint in MOSTLY_ACCURATE_NUANCE_HINTS):
            return True
        if re.search(r"\d", claim_text) and re.search(r"\d", reason_text):
            if any(hint in reason_text for hint in ("上回っています", "下回っています", "記述されているため")):
                return True
            if "複数の記事で" in reason_text and "記述されている" in reason_text:
                return True
        if any(hint in claim_text for hint in ("移った", "移行した", "移行した。")) and "その後" in reason_text:
            if any(hint in reason_text for hint in ("王政復古の大号令", "を経て")):
                return True
        if any(hint in claim_text for hint in ("作った", "作成した")):
            if "修正を加えて制定" in reason_text or ("修正を加え" in reason_text and "強い影響下" in reason_text):
                return True
    return False


def has_positive_claim_review_name_correction(claim_reviews: list[dict[str, Any]]) -> bool:
    katakana_pattern = re.compile(r"[ァ-ヶー]{3,}")
    name_like_pattern = re.compile(r"[一-龥々ァ-ヶーA-Za-z0-9]{2,}")
    stop_tokens = {
        "日本",
        "出身",
        "存在",
        "映像",
        "カラー",
        "オリジナル",
        "白黒",
        "現在",
        "主張",
        "確認",
        "情報源",
        "ボーカリスト",
        "シンガーソングライター",
    }
    generic_suffixes = ("ロボット", "条例", "制度")
    honorific_suffixes = ("選手", "氏", "さん", "容疑者", "議員", "首相", "大統領", "知事", "監督", "投手", "教授")
    non_name_hints = (
        "日本人",
        "最初",
        "史上",
        "シーズン",
        "本塁打",
        "盗塁",
        "歌詞",
        "報道機関",
        "メジャーリーグ",
        "メジャーリーガー",
        "デビュー",
        "プレー",
        "集団",
        "生贄",
    )

    def normalize_name_token(token: str) -> str:
        normalized = token.strip("「」『』()（）")
        for suffix in honorific_suffixes:
            if normalized.endswith(suffix) and len(normalized) - len(suffix) >= 2:
                normalized = normalized[: -len(suffix)]
                break
        return normalized

    def normalized_name_tokens(text: str) -> set[str]:
        tokens = set()
        for token in katakana_pattern.findall(text):
            normalized = normalize_name_token(token)
            if len(normalized) >= 3 and not re.search(r"\d", normalized) and not any(
                hint in normalized for hint in non_name_hints
            ):
                tokens.add(normalized)
        for token in name_like_pattern.findall(text):
            normalized = normalize_name_token(token)
            if len(normalized) < 3:
                continue
            if normalized in stop_tokens:
                continue
            if re.search(r"\d", normalized):
                continue
            if any(normalized.endswith(suffix) for suffix in generic_suffixes):
                continue
            if any(hint in normalized for hint in non_name_hints):
                continue
            if re.fullmatch(r"[A-Za-z0-9]+", normalized):
                continue
            tokens.add(normalized)
        return tokens

    for review in claim_reviews:
        if not isinstance(review, dict):
            continue
        if normalize_evidence_verdict(review.get("verdict")) != "概ね整合":
            continue
        claim_text = str(review.get("claim") or "").strip()
        reason_text = str(review.get("reason") or "").strip()
        if not claim_text or not reason_text:
            continue
        claim_tokens = normalized_name_tokens(claim_text)
        reason_tokens = normalized_name_tokens(reason_text)
        for token in claim_tokens:
            if token in reason_tokens:
                continue
            for candidate in reason_tokens:
                if candidate == token:
                    continue
                similarity = difflib.SequenceMatcher(None, token, candidate).ratio()
                shares_edge = (
                    token[:2] == candidate[:2]
                    or token[-2:] == candidate[-2:]
                    or token in candidate
                    or candidate in token
                )
                if similarity >= 0.55 and shares_edge:
                    return True
    return False


def has_positive_claim_review_death_manner_correction(claim_reviews: list[dict[str, Any]]) -> bool:
    claim_hints = ("殺された", "殺害された", "暗殺された", "討たれた")
    reason_hints = ("自害", "自刃", "切腹")

    for review in claim_reviews:
        if not isinstance(review, dict):
            continue
        if normalize_evidence_verdict(review.get("verdict")) != "概ね整合":
            continue
        claim_text = str(review.get("claim") or "").strip()
        reason_text = str(review.get("reason") or "").strip()
        if not claim_text or not reason_text:
            continue
        if any(hint in claim_text for hint in claim_hints) and any(hint in reason_text for hint in reason_hints):
            return True
    return False


def has_counterevidence_name_correction(claim_reviews: list[dict[str, Any]]) -> bool:
    normalized_reviews = [
        {**review, "verdict": "概ね整合"}
        for review in claim_reviews
        if (
            isinstance(review, dict)
            and normalize_evidence_verdict(review.get("verdict")) == "反証あり"
            and not is_material_counterevidence_review(review)
            and any(
                hint in str(review.get("reason") or "")
                for hint in ("名称は", "表記", "正しくは", "綴り", "ではない", "ではありません", "は誤り")
            )
        )
    ]
    return has_positive_claim_review_name_correction(normalized_reviews)


def has_counterevidence_death_manner_correction(claim_reviews: list[dict[str, Any]]) -> bool:
    normalized_reviews = [
        {**review, "verdict": "概ね整合"}
        for review in claim_reviews
        if isinstance(review, dict) and normalize_evidence_verdict(review.get("verdict")) == "反証あり"
    ]
    return has_positive_claim_review_death_manner_correction(normalized_reviews)


def is_material_counterevidence_review(review: dict[str, Any]) -> bool:
    claim_text = str(review.get("claim") or "").strip()
    reason_text = str(review.get("reason") or "").strip()
    if not claim_text or not reason_text:
        return False
    if any(hint in claim_text for hint in COUNTEREVIDENCE_MATERIAL_CLAIM_HINTS):
        return True
    if any(hint in reason_text for hint in COUNTEREVIDENCE_MATERIAL_REASON_HINTS):
        return True
    role_hits = sum(1 for hint in COUNTEREVIDENCE_MATERIAL_ROLE_HINTS if hint in reason_text)
    if role_hits >= 2:
        return True
    correction_hits = sum(reason_text.count(hint) for hint in COUNTEREVIDENCE_DETAIL_CORRECTION_HINTS)
    if correction_hits >= 2 and "また" in reason_text:
        return True
    return False


def normalized_char_ngram_recall(source_text: str, target_text: str, *, n: int = 2) -> float:
    normalized_source = re.sub(r"[\s\d０-９、。・「」（）()『』]+", "", source_text)
    normalized_target = re.sub(r"[\s\d０-９、。・「」（）()『』]+", "", target_text)
    if len(normalized_source) < n or len(normalized_target) < n:
        return 0.0
    source_ngrams = {normalized_source[i : i + n] for i in range(len(normalized_source) - n + 1)}
    target_ngrams = {normalized_target[i : i + n] for i in range(len(normalized_target) - n + 1)}
    if not source_ngrams:
        return 0.0
    return len(source_ngrams & target_ngrams) / len(source_ngrams)


def has_minor_numeric_detail_signal(reason_text: str) -> bool:
    return any(hint in reason_text for hint in COUNTEREVIDENCE_DETAIL_CORRECTION_HINTS) or any(
        hint in reason_text for hint in COUNTEREVIDENCE_MINOR_NUMERIC_DETAIL_SIGNAL_HINTS
    )


def has_close_numeric_detail_gap(claim_text: str, reason_text: str) -> bool:
    claim_values = [float(value) for value in re.findall(r"\d+(?:\.\d+)?", claim_text)]
    reason_values = [float(value) for value in re.findall(r"\d+(?:\.\d+)?", reason_text)]
    if not claim_values or not reason_values:
        return False
    for claim_value in claim_values:
        for reason_value in reason_values:
            if abs(claim_value - reason_value) < 1e-9:
                continue
            diff = abs(claim_value - reason_value)
            larger = max(abs(claim_value), abs(reason_value))
            if diff <= 1:
                return True
            if larger >= 10 and diff <= 2:
                return True
            if larger and diff / larger <= 0.08:
                return True
    return False


def has_counterevidence_minor_numeric_detail(claim_reviews: list[dict[str, Any]]) -> bool:
    for review in claim_reviews:
        if not isinstance(review, dict):
            continue
        if normalize_evidence_verdict(review.get("verdict")) not in {"反証あり", "要追加確認"}:
            continue
        claim_text = str(review.get("claim") or "").strip()
        reason_text = str(review.get("reason") or "").strip()
        if not claim_text or not reason_text:
            continue
        sentence_breaks = sum(claim_text.rstrip("。！？!?").count(separator) for separator in ("。", "！", "!", "？", "?"))
        if sentence_breaks > 1:
            continue
        if any(marker in claim_text for marker in ("だが", "しかし", "ため", "ので")):
            continue
        if claim_text.count("、") >= 2:
            continue
        if is_material_counterevidence_review(review):
            continue
        if not re.search(r"\d", claim_text) or not re.search(r"\d", reason_text):
            continue
        if not any(unit in claim_text for unit in COUNTEREVIDENCE_MINOR_NUMERIC_DETAIL_UNITS):
            continue
        if not any(unit in reason_text for unit in COUNTEREVIDENCE_MINOR_NUMERIC_DETAIL_UNITS):
            continue
        claim_numbers = set(re.findall(r"\d+(?:\.\d+)?", claim_text))
        reason_numbers = set(re.findall(r"\d+(?:\.\d+)?", reason_text))
        if not claim_numbers or not reason_numbers or claim_numbers == reason_numbers:
            continue
        if not has_minor_numeric_detail_signal(reason_text):
            continue
        if not has_close_numeric_detail_gap(claim_text, reason_text):
            continue
        normalized_claim = re.sub(r"[\s\d０-９、。・「」（）()]+", "", claim_text)
        normalized_reason = re.sub(r"[\s\d０-９、。・「」（）()]+", "", reason_text)
        if difflib.SequenceMatcher(None, normalized_claim, normalized_reason).ratio() >= 0.3 or normalized_char_ngram_recall(
            claim_text, reason_text
        ) >= 0.55:
            return True
    return False


def has_counterevidence_minor_scope_correction(claim_reviews: list[dict[str, Any]]) -> bool:
    for review in claim_reviews:
        if not isinstance(review, dict):
            continue
        if normalize_evidence_verdict(review.get("verdict")) not in {"反証あり", "要追加確認"}:
            continue
        claim_text = str(review.get("claim") or "").strip()
        reason_text = str(review.get("reason") or "").strip()
        if not claim_text or not reason_text:
            continue
        if is_material_counterevidence_review(review):
            continue
        claim_has_scope = any(hint in claim_text for hint in COUNTEREVIDENCE_SCOPE_CLAIM_HINTS)
        reason_has_scope = any(hint in reason_text for hint in COUNTEREVIDENCE_SCOPE_REASON_HINTS)
        if claim_has_scope and reason_has_scope:
            return True
    return False


def has_counterevidence_minor_detail_correction(claim_reviews: list[dict[str, Any]]) -> bool:
    return has_counterevidence_minor_numeric_detail(claim_reviews) or has_counterevidence_minor_scope_correction(
        claim_reviews
    )


def has_strong_false_counterevidence(claim_reviews: list[dict[str, Any]]) -> bool:
    for review in claim_reviews:
        if not isinstance(review, dict):
            continue
        if normalize_evidence_verdict(review.get("verdict")) != "反証あり":
            continue
        claim_text = str(review.get("claim") or "").strip()
        claim_text_lower = claim_text.lower()
        reason_text = str(review.get("reason") or "").strip()
        reason_text_lower = reason_text.lower()
        if not claim_text or not reason_text:
            continue
        if "ため" in claim_text:
            continue
        has_compound_structure = "、" in claim_text or any(hint in claim_text for hint in ATOMIC_FALSE_COMPLEXITY_HINTS)
        is_conspiracy_false = "ケムトレイル" in claim_text and any(
            hint in reason_text_lower for hint in STRONG_FALSE_CONSPIRACY_HINTS
        )
        is_nonexistent_law_false = ("法" in claim_text or "法律" in claim_text) and any(
            hint in reason_text for hint in STRONG_FALSE_NONEXISTENT_LAW_HINTS
        )
        has_fake_quote_absence = any(hint in reason_text for hint in STRONG_FALSE_FAKE_QUOTE_ABSENCE_HINTS)
        has_fake_quote_misattribution = any(hint in reason_text for hint in STRONG_FALSE_FAKE_QUOTE_MISATTRIBUTION_HINTS)
        has_fake_quote_context_shift = (
            any(hint in reason_text for hint in STRONG_FALSE_FAKE_QUOTE_CONTEXT_HINTS)
            and (
                (
                    ("発言" in reason_text or "引用" in reason_text)
                    and (re.search(r"\d{4}年", reason_text) or any(hint in reason_text for hint in ("選挙集会", "当時", "過去")))
                )
                or "文脈" in reason_text
            )
        )
        is_fake_quote_false = ("発言" in claim_text or "「" in claim_text) and (
            any(hint in reason_text for hint in STRONG_FALSE_FAKE_QUOTE_HINTS)
            or (has_fake_quote_absence and (has_fake_quote_misattribution or has_fake_quote_context_shift))
            or has_fake_quote_context_shift
        )
        is_fake_image_false = any(hint in reason_text for hint in ("画像", "写真")) and any(
            hint in reason_text_lower for hint in STRONG_FALSE_FAKE_IMAGE_HINTS
        )
        is_geocentrism_false = (
            "地球" in claim_text
            and "宇宙の中心" in claim_text
            and "太陽" in claim_text
            and any(hint in reason_text for hint in STRONG_FALSE_GEOCENTRISM_REASON_HINTS[:2])
            and any(hint in reason_text for hint in STRONG_FALSE_GEOCENTRISM_REASON_HINTS[2:])
        )
        has_5g_authoritative_denial = (
            "世界保健機関" in reason_text
            or "who" in reason_text_lower
            or "公的機関" in reason_text
            or "ファクトチェック機関" in reason_text
        )
        has_5g_transmission_denial = any(
            hint in reason_text_lower for hint in ("電波", "モバイルネットワーク", "移動せず", "移動できず")
        )
        has_5g_generation_denial = any(hint in reason_text for hint in ("生成しない", "生成することはない", "広めない"))
        has_5g_counterexample = any(
            hint in reason_text_lower for hint in ("5gがない", "5gネットワークがない", "導入されていない地域")
        )
        has_5g_no_causation = any(
            hint in reason_text_lower
            for hint in ("因果関係がない", "関連がない", "関連性がない", "科学的な因果関係がない")
        )
        has_5g_no_science = any(hint in reason_text for hint in STRONG_FALSE_5G_COVID_NO_SCIENCE_HINTS)
        is_5g_covid_false = (
            "5g" in claim_text_lower
            and ("新型コロナ" in claim_text or "コロナ" in claim_text)
            and has_5g_authoritative_denial
            and (has_5g_transmission_denial or has_5g_no_causation or has_5g_no_science or has_5g_generation_denial)
            and (has_5g_counterexample or has_5g_no_causation or has_5g_no_science or has_5g_generation_denial)
        )
        has_vaccine_cancer_authority = any(hint in reason_text for hint in STRONG_FALSE_VACCINE_CANCER_AUTHORITY_HINTS)
        has_vaccine_cancer_no_basis = any(hint in reason_text for hint in STRONG_FALSE_VACCINE_CANCER_NO_BASIS_HINTS)
        is_vaccine_cancer_false = (
            "ワクチン" in claim_text
            and any(hint in claim_text for hint in ("がん", "癌", "ガン"))
            and (
                (
                    STRONG_FALSE_VACCINE_CANCER_REASON_HINTS[0] in reason_text
                    and any(hint in reason_text for hint in STRONG_FALSE_VACCINE_CANCER_REASON_HINTS[1:])
                    and any(hint in reason_text for hint in STRONG_FALSE_VACCINE_CANCER_DISCLAIMER_HINTS)
                )
                or (
                    ("因果関係" in reason_text or has_vaccine_cancer_no_basis)
                    and has_vaccine_cancer_authority
                )
            )
        )
        has_birther_birthplace = any(hint in reason_text for hint in STRONG_FALSE_BIRTHER_BIRTHPLACE_HINTS)
        has_birther_confirmation = any(hint in reason_text for hint in STRONG_FALSE_BIRTHER_CONFIRMATION_HINTS)
        is_birther_false = (
            ("オバマ" in claim_text or "バラク・オバマ" in claim_text)
            and any(hint in claim_text for hint in ("アメリカ生まれではない", "米国生まれではない"))
            and (
                (
                    any(hint in reason_text for hint in STRONG_FALSE_BIRTHER_REASON_HINTS[:2])
                    and any(hint in reason_text for hint in STRONG_FALSE_BIRTHER_REASON_HINTS[2:])
                )
                or (has_birther_birthplace and has_birther_confirmation)
            )
        )
        is_vaccine_autism_false = (
            "mmr" in claim_text_lower
            and "自閉症" in claim_text
            and all(hint in reason_text for hint in STRONG_FALSE_VACCINE_AUTISM_RETRACTION_HINTS[:2])
            and any(hint in reason_text for hint in STRONG_FALSE_VACCINE_AUTISM_RETRACTION_HINTS[2:])
            and any(hint in reason_text for hint in STRONG_FALSE_VACCINE_AUTISM_NO_LINK_HINTS)
            and (
                any(hint in reason_text for hint in STRONG_FALSE_VACCINE_AUTISM_EPIDEMIOLOGY_HINTS)
                or any(hint in reason_text for hint in ("医師免許", "剥奪"))
            )
        )
        is_nickname_false = (
            not has_compound_structure
            and ("とは" in claim_text or "愛称" in claim_text)
            and "愛称" in reason_text
            and any(hint in reason_text for hint in STRONG_FALSE_NICKNAME_REASON_HINTS[1:])
        )
        is_recordholder_false = (
            not has_compound_structure
            and any(hint in claim_text for hint in STRONG_FALSE_RECORDHOLDER_CLAIM_HINTS)
            and any(hint in reason_text for hint in STRONG_FALSE_RECORDHOLDER_REASON_HINTS)
            and any(hint in reason_text for hint in STRONG_FALSE_RECORDHOLDER_CONCLUSION_HINTS)
        )
        is_identity_negation_false = (
            not has_compound_structure
            and any(hint in claim_text for hint in STRONG_FALSE_IDENTITY_NEGATION_CLAIM_HINTS)
            and any(hint in reason_text for hint in STRONG_FALSE_IDENTITY_NEGATION_REASON_HINTS)
            and any(hint in reason_text for hint in STRONG_FALSE_IDENTITY_NEGATION_SUPPORT_HINTS)
        )
        is_japan_northernmost_false = (
            not has_compound_structure
            and any(hint in claim_text for hint in STRONG_FALSE_JAPAN_NORTHERNMOST_CLAIM_HINTS)
            and all(hint in reason_text for hint in STRONG_FALSE_JAPAN_NORTHERNMOST_REASON_HINTS)
            and any(hint in reason_text for hint in STRONG_FALSE_JAPAN_NORTHERNMOST_REASON_CONCLUSION_HINTS)
        )
        is_historical_hoax_false = (
            all(hint in claim_text for hint in STRONG_FALSE_HISTORICAL_HOAX_CLAIM_HINTS)
            and any(hint in reason_text for hint in STRONG_FALSE_HISTORICAL_HOAX_REASON_HINTS[:3])
            and any(hint in reason_text for hint in STRONG_FALSE_HISTORICAL_HOAX_REASON_HINTS[3:])
        )
        has_moon_landing_physical_evidence = any(
            hint in reason_text for hint in ("かぐや", "ルナリコネッサンスオービター", "高解像度画像", "レーザー反射鏡", "月探査機")
        )
        has_moon_landing_independent_confirmation = any(
            hint in reason_text for hint in ("ソビエト連邦", "独立して監視", "独立した検証", "陰謀論")
        )
        has_moon_landing_variation_explanation = any(
            hint in reason_text for hint in ("旗の揺れ", "旗がなびいて", "星の不在", "星が写っていない", "科学的に反証", "科学的に説明")
        )
        has_moon_landing_coverup_absence = any(
            hint in reason_text for hint in ("40万人", "証言は出ていない", "証言がない", "多数の関係者")
        )
        is_moon_landing_hoax_false = (
            all(hint in claim_text for hint in STRONG_FALSE_MOON_LANDING_HOAX_CLAIM_HINTS)
            and (
                (has_moon_landing_physical_evidence and has_moon_landing_independent_confirmation)
                or (has_moon_landing_variation_explanation and has_moon_landing_coverup_absence)
            )
        )
        is_saigo_boshin_false = (
            not has_compound_structure
            and all(hint in claim_text for hint in STRONG_FALSE_SAIGO_BOSHIN_FALSE_CLAIM_HINTS)
            and all(hint in reason_text for hint in STRONG_FALSE_SAIGO_BOSHIN_FALSE_REASON_HINTS)
        )
        has_saigo_seinan_government_victory = any(hint in reason_text for hint in ("明治政府軍", "新政府軍"))
        has_saigo_seinan_defeat = "敗北" in reason_text
        has_saigo_seinan_end = any(hint in reason_text for hint in ("自刃", "最期を遂げ"))
        is_saigo_seinan_victory_false = (
            not has_compound_structure
            and all(hint in claim_text for hint in STRONG_FALSE_SAIGO_SEINAN_VICTORY_CLAIM_HINTS)
            and has_saigo_seinan_government_victory
            and has_saigo_seinan_defeat
            and has_saigo_seinan_end
        )
        if (
            is_conspiracy_false
            or is_nonexistent_law_false
            or is_fake_quote_false
            or is_fake_image_false
            or is_geocentrism_false
            or is_5g_covid_false
            or is_vaccine_cancer_false
            or is_birther_false
            or is_vaccine_autism_false
            or is_nickname_false
            or is_recordholder_false
            or is_identity_negation_false
            or is_japan_northernmost_false
            or is_historical_hoax_false
            or is_moon_landing_hoax_false
            or is_saigo_boshin_false
            or is_saigo_seinan_victory_false
        ):
            return True
    return False


def has_partially_supported_counterevidence(claim_reviews: list[dict[str, Any]]) -> bool:
    for review in claim_reviews:
        if not isinstance(review, dict):
            continue
        if normalize_evidence_verdict(review.get("verdict")) not in {"反証あり", "要追加確認"}:
            continue
        hint_text = f"{review.get('claim') or ''} {review.get('reason') or ''}".strip().lower()
        has_support = any(hint in hint_text for hint in PARTIAL_SUPPORT_HINTS)
        has_correction = any(hint in hint_text for hint in PARTIAL_CORRECTION_HINTS)
        if has_support and has_correction:
            return True
    return False


def score_adjustments_from_evidence(
    overall_verdict: str,
    claim_reviews: list[EvidenceClaimReview],
    grounding_sources: list[dict[str, Any]],
    retrieved_urls: list[dict[str, Any]],
    source_profile: dict[str, Any],
) -> tuple[int, int]:
    """Gemini の根拠確認結果を、リスク点と確信度の増減に変換する。"""
    risk_delta = 0
    confidence_delta = 0
    correction_article = bool(source_profile.get("correction_article"))
    official_source = bool(source_profile.get("official_source"))
    trusted_grounding_sources = count_trusted_grounding_sources(grounding_sources)

    if correction_article:
        verdict_risk = {
            "反証あり": -8,
            "一次ソース未確認": 2,
            "要追加確認": 1,
            "判定不能": 0,
            "概ね整合": -4,
        }
        verdict_confidence = {
            "反証あり": 6,
            "一次ソース未確認": 1,
            "要追加確認": 0,
            "判定不能": -6,
            "概ね整合": 5,
        }
    else:
        verdict_risk = {
            "反証あり": 7,
            "一次ソース未確認": 6,
            "要追加確認": 3,
            "判定不能": 0,
            "概ね整合": -5,
        }
        verdict_confidence = {
            "反証あり": 4,
            "一次ソース未確認": 3,
            "要追加確認": 1,
            "判定不能": -6,
            "概ね整合": 6,
        }

    risk_delta += verdict_risk.get(overall_verdict, 0)
    confidence_delta += verdict_confidence.get(overall_verdict, 0)

    for review in claim_reviews:
        if review.verdict == "反証あり":
            if correction_article:
                risk_delta -= 4
                confidence_delta += 1
            else:
                risk_delta += 5
                confidence_delta += 1
        elif review.verdict == "一次ソース未確認":
            risk_delta += 4
        elif review.verdict == "要追加確認":
            risk_delta += 2
        elif review.verdict == "概ね整合":
            risk_delta -= 2 if correction_article else 3
            confidence_delta += 1

    if grounding_sources:
        confidence_delta += min(len(grounding_sources), 4)
    if retrieved_urls:
        confidence_delta += 2
    if not grounding_sources and not retrieved_urls:
        confidence_delta -= 4
    if trusted_grounding_sources:
        risk_delta -= min(trusted_grounding_sources * 2, 6)
        confidence_delta += min(trusted_grounding_sources, 3)
    if official_source and overall_verdict == "概ね整合":
        risk_delta -= 3
        confidence_delta += 2

    return max(-15, min(risk_delta, 22)), max(-15, min(confidence_delta, 15))


def merge_result_labels(
    seed_labels: list[str],
    evidence_labels: list[str],
    overall_verdict: str = "",
    claim_mode: bool = False,
) -> list[str]:
    cleaned_evidence_labels = list(evidence_labels)
    cleaned_seed_labels = list(seed_labels)
    if overall_verdict in {"概ね整合", "反証あり"}:
        cleaned_evidence_labels = [label for label in cleaned_evidence_labels if label != "判定不能"]
    if evidence_labels or overall_verdict in {"概ね整合", "反証あり"}:
        cleaned_seed_labels = [label for label in cleaned_seed_labels if label != "判定不能"]
    if claim_mode:
        cleaned_evidence_labels = [
            label
            for label in cleaned_evidence_labels
            if label not in {"出典不明", "信頼できる一次ソース未確認"}
        ]
        cleaned_seed_labels = [
            label
            for label in cleaned_seed_labels
            if label not in {"出典不明", "信頼できる一次ソース未確認"}
        ]
    merged = list(dict.fromkeys(cleaned_evidence_labels + cleaned_seed_labels))
    return merged[:4] if merged else ["判定不能"]


def merge_result_reasons(page: ResolvedPage, seed_reasons: list[str], evidence_reasons: list[str]) -> list[str]:
    merged = list(dict.fromkeys(evidence_reasons + seed_reasons))
    return merge_policy_reason(page, merged)


def build_result_summary(seed_summary: str, evidence_overview: dict[str, Any]) -> str:
    evidence_summary = str(evidence_overview.get("assessment_summary") or "").strip()
    if evidence_summary:
        return evidence_summary
    return seed_summary


def build_result_status(
    seed_status: str,
    overall_verdict: str,
    confidence_score: int,
    source_profile: dict[str, Any],
    style_overview: dict[str, Any] | None = None,
) -> str:
    style_score = normalize_style_score((style_overview or {}).get("score"))
    if style_score is not None and style_score >= 80:
        return "要人手確認"
    correction_article = bool(source_profile.get("correction_article"))
    if overall_verdict == "反証あり":
        if correction_article and confidence_score >= 55:
            return "自動判定"
        return "要人手確認"
    if overall_verdict in {"一次ソース未確認", "判定不能", "要追加確認"}:
        return "要人手確認"
    if overall_verdict == "概ね整合" and confidence_score >= 55:
        return "自動判定"
    return seed_status


def build_model_used(style_overview: dict[str, Any], has_llm_output: bool, has_primary_review: bool) -> str:
    if not has_llm_output:
        return "heuristic-fallback"
    base = "gemini-primary" if has_primary_review else "heuristic"
    if str(style_overview.get("status") or "") == "Gemini書き振り評価済み":
        return f"{base}+gemini-evidence+gemini-style"
    return f"{base}+gemini-evidence"


def combine_result(page: ResolvedPage, seed: dict[str, Any], llm_bundle: dict[str, Any] | None, settings: Settings) -> AnalysisResult:
    """ローカル一次判定と Gemini 結果を合成して最終判定を作る。"""
    result_seed = {key: value for key, value in seed.items() if key != "source_profile"}

    if not llm_bundle:
        return publicize_result(page, result_seed, seed.get("source_profile", {}))

    llm_output = llm_bundle.get("output") if isinstance(llm_bundle.get("output"), dict) else {}
    evidence_overview = merge_evidence_overview(seed, llm_bundle, settings)
    style_overview = merge_style_overview(seed, llm_bundle, settings)
    if not llm_output:
        fallback_seed = dict(result_seed)
        fallback_seed["model_used"] = "heuristic-fallback"
        fallback_seed["evidence_overview"] = evidence_overview
        fallback_seed["style_overview"] = style_overview
        return publicize_result(page, fallback_seed, seed.get("source_profile", {}))

    effective_seed = apply_gemini_primary_review(seed, llm_output)
    primary_review_used = effective_seed is not seed

    claim_reviews = normalize_claim_reviews(llm_output.get("claim_reviews"), evidence_overview.get("claims", []))
    overall_verdict = evidence_overview.get("assessment_status") or derive_overall_verdict(llm_output.get("overall_verdict"), claim_reviews)
    evidence_labels = build_evidence_labels(llm_output.get("labels"), overall_verdict)
    evidence_reasons = build_evidence_reasons(llm_output.get("reasons"), claim_reviews)
    suggested_queries = sanitize_queries(llm_output.get("suggested_queries"))

    risk_delta, confidence_delta = score_adjustments_from_evidence(
        overall_verdict,
        claim_reviews,
        evidence_overview.get("grounding_sources", []),
        evidence_overview.get("retrieved_urls", []),
        effective_seed.get("source_profile", {}),
    )
    risk_score = clamp(effective_seed["risk_score"] + risk_delta)
    confidence_score = clamp(effective_seed["confidence_score"] + confidence_delta)
    status = build_result_status(
        effective_seed["status"],
        overall_verdict,
        confidence_score,
        effective_seed.get("source_profile", {}),
        style_overview,
    )
    summary = build_result_summary(effective_seed["summary"], evidence_overview)
    labels = merge_result_labels(
        effective_seed["labels"],
        evidence_labels,
        overall_verdict=overall_verdict,
        claim_mode=bool(effective_seed.get("source_profile", {}).get("claim_mode")) or is_claim_mode(page),
    )
    reasons = merge_result_reasons(page, effective_seed["reasons"], evidence_reasons)

    internal_payload = dict(
        heuristic_base_score=seed.get("heuristic_base_score"),
        heuristic_signal_total=seed.get("heuristic_signal_total"),
        heuristic_raw_score=seed.get("heuristic_raw_score"),
        heuristic_risk_score=seed.get("heuristic_risk_score", seed["risk_score"]),
        primary_review_risk_score=effective_seed.get("primary_review_risk_score"),
        evidence_risk_delta=risk_delta,
        risk_score=risk_score,
        confidence="モデルの確信度" if confidence_score >= 45 else "判定不能",
        confidence_score=confidence_score,
        status=status,
        summary=summary,
        labels=labels,
        reasons=reasons,
        domain=effective_seed["domain"],
        verification_links=merge_links(effective_seed["domain"], suggested_queries, page.source_url),
        caution_level=label_for_score(risk_score),
        model_used=build_model_used(style_overview, True, primary_review_used),
        source_snapshot=build_source_snapshot(page),
        signal_breakdown=effective_seed["signal_breakdown"],
        evidence_overview=evidence_overview,
        style_overview=style_overview,
    )
    return publicize_result(page, internal_payload, effective_seed.get("source_profile", {}))


async def analyze_page(page: ResolvedPage, settings: Settings) -> AnalysisResult:
    """1ページ分の判定を実行する最上位関数。main.py と dataset_runner.py から呼ばれる。"""
    analysis_stages: list[TimingStage] = []

    heuristic_started_at = time.perf_counter()
    seed = heuristic_analysis(page)
    analysis_stages.append(
        TimingStage(
            key="heuristic_analysis",
            label="ローカル一次判定",
            duration_ms=elapsed_ms(heuristic_started_at),
            note="本文の特徴量から一次スコアを作成しました。",
        )
    )

    gemini_started_at = time.perf_counter()
    llm_bundle = await gemini_analysis(page, settings, seed)
    gemini_note = (
        "外部根拠比較と書き振り評価を実行しました。"
        if settings.gemini_style_review_enabled
        else "外部根拠比較を実行しました。書き振り評価はローカル補助表示です。"
    )
    if not settings.gemini_api_key:
        gemini_note = "Gemini API 未設定のため未実行です。"
    elif llm_bundle and llm_bundle.get("error"):
        gemini_note = str(llm_bundle.get("error"))
    analysis_stages.append(
        TimingStage(
            key="gemini_analysis",
            label="Gemini比較",
            duration_ms=elapsed_ms(gemini_started_at),
            note=gemini_note,
        )
    )

    combine_started_at = time.perf_counter()
    result = combine_result(page, seed, llm_bundle, settings)
    analysis_stages.append(
        TimingStage(
            key="result_combine",
            label="結果統合",
            duration_ms=elapsed_ms(combine_started_at),
            note="公開表示用の判定結果に整形しました。",
        )
    )
    timing_overview = merge_timing_overview(page.timing_overview, analysis_stages)
    return result.model_copy(update={"timing_overview": timing_overview})
