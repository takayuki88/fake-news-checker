"""判定ロジックの中心。

まずローカルのルールで一次判定を作り、Gemini の根拠確認が使える場合は
その結果を重ねて、最後に画面/API向けの `AnalysisResult` に整えます。
"""

import asyncio
import json
import re
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
    SourceSnapshot,
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
    "信頼性が高い": "water",
    "おおむね正確": "green",
    "判断保留": "yellow",
    "誤解を招く可能性が高い": "orange",
    "フェイクの可能性が高い": "red",
    "未確認": "gray",
}
PUBLIC_VERDICT_BANDS: dict[str, tuple[int, int] | None] = {
    "信頼性が高い": (0, 20),
    "おおむね正確": (21, 40),
    "判断保留": (41, 60),
    "誤解を招く可能性が高い": (61, 80),
    "フェイクの可能性が高い": (81, 100),
    "未確認": None,
}
PUBLIC_VERDICT_HINTS = {
    "信頼性が高い": ["一次ソースと整合"],
    "おおむね正確": ["大筋で整合"],
    "判断保留": ["追加確認が必要"],
    "誤解を招く可能性が高い": ["文脈不足に注意"],
    "フェイクの可能性が高い": ["反証根拠あり"],
    "未確認": ["未確認"],
}


def clamp(value: int, lower: int = 0, upper: int = 100) -> int:
    return max(lower, min(upper, value))


def label_for_score(score: int) -> str:
    if score >= 75:
        return "高リスク"
    if score >= 45:
        return "要確認"
    return "低リスク"


def public_verdict_key(verdict: str) -> str:
    return PUBLIC_VERDICT_KEYS.get(verdict, "hold")


def public_attention_score(verdict: str, score: int | None) -> int | None:
    if verdict == "未確認":
        return None
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
        "信頼性が高い": "信頼できる",
        "おおむね正確": "おおむね正確",
        "判断保留": "どちらとも言えない",
        "誤解を招く可能性が高い": "注意が必要",
        "フェイクの可能性が高い": "高確率でフェイク",
        "未確認": "未確認",
    }
    return mapping.get(verdict, verdict)


def public_attention_band_display(verdict: str) -> str:
    mapping = {
        "信頼性が高い": "0〜20%",
        "おおむね正確": "21〜40%",
        "判断保留": "41〜60%",
        "誤解を招く可能性が高い": "61〜80%",
        "フェイクの可能性が高い": "81〜100%",
        "未確認": "?%",
    }
    return mapping.get(verdict, "?%")


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


def derive_public_verdict(
    risk_score: int,
    confidence_score: int,
    labels: list[str],
    source_profile: dict[str, Any],
    evidence_overview: dict[str, Any],
) -> str:
    """内部スコアと根拠確認結果から、利用者に見せる5区分ラベルを決める。"""
    overall_verdict = str(evidence_overview.get("assessment_status") or "").strip()
    correction_article = bool(source_profile.get("correction_article"))
    trusted_source = bool(source_profile.get("trusted_source"))

    if overall_verdict == "反証あり":
        if correction_article or trusted_source:
            return "信頼性が高い" if risk_score <= 30 else "おおむね正確"
        return "フェイクの可能性が高い"
    if overall_verdict == "概ね整合":
        if trusted_source or confidence_score >= 70 or risk_score <= 20:
            return "信頼性が高い"
        return "おおむね正確"
    if overall_verdict == "一次ソース未確認":
        return "未確認"
    if overall_verdict == "判定不能":
        return "未確認" if confidence_score < 45 else "判断保留"
    if overall_verdict == "要追加確認":
        return "誤解を招く可能性が高い" if risk_score >= 61 else "判断保留"

    if "判定不能" in labels and confidence_score < 45:
        return "未確認"
    if "信頼できる一次ソース未確認" in labels and confidence_score < 55 and risk_score < 75:
        return "未確認"
    if trusted_source and confidence_score >= 55 and risk_score <= 30:
        return "信頼性が高い"
    if risk_score <= 20:
        return "信頼性が高い"
    if risk_score <= 40:
        return "おおむね正確"
    if risk_score <= 60:
        return "判断保留"
    if risk_score <= 80:
        return "誤解を招く可能性が高い"
    return "フェイクの可能性が高い"


def build_public_supplement(verdict: str) -> str:
    if verdict == "信頼性が高い":
        return "発信元や日付を確認しつつ、重要な数字は一次ソースで追うとさらに安心です。"
    if verdict == "おおむね正確":
        return "大筋は整合していても、細部や最新更新の有無は確認してください。"
    if verdict == "判断保留":
        return "一部材料はありますが、断定に足る公開根拠がまだ十分ではありません。"
    if verdict == "誤解を招く可能性が高い":
        return "見出しだけで拡散せず、一次ソースや主要報道で主要主張を確認してください。"
    if verdict == "フェイクの可能性が高い":
        return "強い断定を広める前に、公的機関や主要報道による反証有無を確認してください。"
    return "追加の一次情報や主要報道が出るまで、断定や拡散は控えるのが安全です。"


def build_public_summary(
    payload: dict[str, Any],
    public_verdict: str,
    page: ResolvedPage,
    source_profile: dict[str, Any],
) -> str:
    evidence_summary = str(payload.get("evidence_overview", {}).get("assessment_summary") or "").strip()
    if evidence_summary:
        return evidence_summary
    if public_verdict == "信頼性が高い":
        if source_profile.get("official_source"):
            return f"{page.site_name} の内容は、公的な一次ソースとして確認しやすく、現時点では信頼性が高いと見ました。"
        if source_profile.get("fact_check_source"):
            return f"{page.site_name} の内容は、ファクトチェック記事として整合が取りやすく、現時点では信頼性が高いと見ました。"
        return f"{page.site_name} の内容は、公開情報と大きな齟齬が見えにくく、現時点では信頼性が高いと見ました。"
    if public_verdict == "おおむね正確":
        return f"{page.site_name} の内容は大筋では整合しそうですが、細部や前提条件は追加確認の余地があります。"
    if public_verdict == "判断保留":
        return f"{page.site_name} の内容は一部の材料はありますが、真偽を断定するにはまだ公開根拠が十分ではありません。"
    if public_verdict == "誤解を招く可能性が高い":
        return f"{page.site_name} の内容は、一部事実を含んでいても、文脈不足や表現の強さで誤解を招くおそれがあります。"
    if public_verdict == "フェイクの可能性が高い":
        return f"{page.site_name} の内容は、反証や出典不足が目立ち、フェイクの可能性が高いと見ました。"
    return f"{page.site_name} の内容は、現時点で信頼できる裏付けを十分に確認できず、未確認として扱いました。"


def build_public_status(public_verdict: str, confidence_score: int, model_used: str) -> str:
    if public_verdict in {"判断保留", "未確認"} or confidence_score < 45:
        return "要確認"
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


def publicize_result(page: ResolvedPage, payload: dict[str, Any], source_profile: dict[str, Any]) -> AnalysisResult:
    risk_score = int(payload.get("risk_score") or 0)
    confidence_score = clamp(int(payload.get("confidence_score") or 0))
    labels = [str(label).strip() for label in payload.get("labels", []) if str(label).strip()]
    evidence_overview = dict(payload.get("evidence_overview") or {})
    public_verdict = derive_public_verdict(risk_score, confidence_score, labels, source_profile, evidence_overview)
    attention_score = public_attention_score(public_verdict, risk_score)
    merged_labels = list(dict.fromkeys(labels + PUBLIC_VERDICT_HINTS.get(public_verdict, [])))[:4]
    return AnalysisResult(
        verdict=public_verdict,
        verdict_key=public_verdict_key(public_verdict),
        verdict_display=public_verdict_display(public_verdict),
        attention_score=attention_score,
        attention_display=public_attention_display(attention_score),
        attention_band_display=public_attention_band_display(public_verdict),
        risk_score=attention_score,
        caution_level=public_verdict,
        confidence=confidence_bucket(confidence_score),
        confidence_label=confidence_bucket(confidence_score),
        confidence_score=confidence_score,
        status=build_public_status(public_verdict, confidence_score, str(payload.get("model_used") or "")),
        summary=build_public_summary(payload, public_verdict, page, source_profile),
        reasons=[str(reason).strip() for reason in payload.get("reasons", []) if str(reason).strip()][:3],
        supplement=build_public_supplement(public_verdict),
        labels=merged_labels,
        domain=str(payload.get("domain") or "一般"),
        evidence_sources=build_public_evidence_sources(page, payload),
        verification_links=build_public_verification_links(page, payload),
        model_used=str(payload.get("model_used") or "heuristic"),
        source_snapshot=build_source_snapshot(page),
        signal_breakdown=payload.get("signal_breakdown", []),
        evidence_overview=evidence_overview,
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
        else:
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
            score += 2
            if "信頼できる一次ソース未確認" not in labels and page.reference_link_count == 0 and source_hint_count == 0:
                labels.append("信頼できる一次ソース未確認")
            add_signal(signals, "出所情報が一部不足", 2, "検証記事ですが、著者名や公開日時の明示は限定的でした。")
        else:
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
        else:
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

    if short_body:
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
    if short_body:
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

    return {
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
        "source_profile": source_profile,
    }


def build_prompt(page: ResolvedPage, seed: dict[str, Any]) -> str:
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

    return f"""
あなたは日本語の外部根拠比較専用AIです。
役割は、入力本文そのものを文体で採点することではなく、本文から抽出した主張候補を外部根拠と照合して整理することです。
本文の煽り表現・誇張・陰謀論テンプレは別ロジックで評価済みなので、ここでは外部根拠を優先してください。
必要に応じて google_search と url_context を使い、公開ウェブ上の一次ソース、公的機関、主要報道機関、ファクトチェック記事を優先して確認してください。
一次ソースが見当たらない場合は無理に断定せず、「一次ソース未確認」または「判定不能」にしてください。
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
  "suggested_queries": ["確認用検索語1", "確認用検索語2", "確認用検索語3"]
}}

対象URL: {page.source_url or "未入力"}
ページ名: {page.title}
サイト名: {page.site_name}
判定日: {page.analysis_date or "未設定"}
判定日時: {page.analysis_datetime or "未設定"}
判定タイムゾーン: {page.analysis_timezone or "未設定"}

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


async def gemini_analysis(page: ResolvedPage, settings: Settings, seed: dict[str, Any]) -> dict[str, Any] | None:
    """Gemini に根拠確認を依頼し、JSONとして扱える形で返す。"""
    if not settings.gemini_api_key:
        return None

    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent?key={settings.gemini_api_key}"
    )
    payload = {
        "contents": [{"parts": [{"text": build_prompt(page, seed)}]}],
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


def count_trusted_grounding_sources(grounding_sources: list[dict[str, Any]]) -> int:
    trusted_count = 0
    for source in grounding_sources:
        if not isinstance(source, dict):
            continue
        hostname = normalize_hostname(str(source.get("url") or "").strip())
        title = str(source.get("title") or "").strip()
        if hostname_matches(hostname, OFFICIAL_HOSTNAMES) or any(
            hostname == suffix or hostname.endswith(f".{suffix}") for suffix in OFFICIAL_HOST_SUFFIXES
        ):
            trusted_count += 1
            continue
        lowered_title = title.lower()
        if hostname_matches(hostname, FACT_CHECK_HOSTNAMES) or any(hint in lowered_title for hint in FACT_CHECK_HINTS):
            trusted_count += 1
    return trusted_count


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
            "反証あり": 10,
            "一次ソース未確認": 6,
            "要追加確認": 3,
            "判定不能": 0,
            "概ね整合": -5,
        }
        verdict_confidence = {
            "反証あり": 5,
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
                risk_delta += 8
                confidence_delta += 2
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


def merge_result_labels(seed_labels: list[str], evidence_labels: list[str]) -> list[str]:
    cleaned_seed_labels = seed_labels
    if evidence_labels:
        cleaned_seed_labels = [label for label in seed_labels if label != "判定不能"]
    merged = list(dict.fromkeys(evidence_labels + cleaned_seed_labels))
    return merged[:4] if merged else ["判定不能"]


def merge_result_reasons(page: ResolvedPage, seed_reasons: list[str], evidence_reasons: list[str]) -> list[str]:
    merged = list(dict.fromkeys(evidence_reasons + seed_reasons))
    return merge_policy_reason(page, merged)


def build_result_summary(seed_summary: str, evidence_overview: dict[str, Any]) -> str:
    evidence_summary = str(evidence_overview.get("assessment_summary") or "").strip()
    if evidence_summary:
        return evidence_summary
    return seed_summary


def build_result_status(seed_status: str, overall_verdict: str, confidence_score: int, source_profile: dict[str, Any]) -> str:
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


def combine_result(page: ResolvedPage, seed: dict[str, Any], llm_bundle: dict[str, Any] | None, settings: Settings) -> AnalysisResult:
    """ローカル一次判定と Gemini 結果を合成して最終判定を作る。"""
    result_seed = {key: value for key, value in seed.items() if key != "source_profile"}

    if not llm_bundle:
        return publicize_result(page, result_seed, seed.get("source_profile", {}))

    llm_output = llm_bundle.get("output") if isinstance(llm_bundle.get("output"), dict) else {}
    evidence_overview = merge_evidence_overview(seed, llm_bundle, settings)
    if not llm_output:
        fallback_seed = dict(result_seed)
        fallback_seed["model_used"] = "heuristic-fallback"
        fallback_seed["evidence_overview"] = evidence_overview
        return publicize_result(page, fallback_seed, seed.get("source_profile", {}))

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
        seed.get("source_profile", {}),
    )
    risk_score = clamp(seed["risk_score"] + risk_delta)
    confidence_score = clamp(seed["confidence_score"] + confidence_delta)
    status = build_result_status(seed["status"], overall_verdict, confidence_score, seed.get("source_profile", {}))
    summary = build_result_summary(seed["summary"], evidence_overview)
    labels = merge_result_labels(seed["labels"], evidence_labels)
    reasons = merge_result_reasons(page, seed["reasons"], evidence_reasons)

    internal_payload = dict(
        risk_score=risk_score,
        confidence="モデルの確信度" if confidence_score >= 45 else "判定不能",
        confidence_score=confidence_score,
        status=status,
        summary=summary,
        labels=labels,
        reasons=reasons,
        domain=seed["domain"],
        verification_links=merge_links(seed["domain"], suggested_queries, page.source_url),
        caution_level=label_for_score(risk_score),
        model_used="heuristic+gemini-evidence",
        source_snapshot=build_source_snapshot(page),
        signal_breakdown=seed["signal_breakdown"],
        evidence_overview=evidence_overview,
    )
    return publicize_result(page, internal_payload, seed.get("source_profile", {}))


async def analyze_page(page: ResolvedPage, settings: Settings) -> AnalysisResult:
    """1ページ分の判定を実行する最上位関数。main.py と dataset_runner.py から呼ばれる。"""
    seed = heuristic_analysis(page)
    llm_bundle = await gemini_analysis(page, settings, seed)
    return combine_result(page, seed, llm_bundle, settings)
