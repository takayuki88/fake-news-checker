import re
from urllib.parse import quote_plus

from .models import EvidenceOverview, ResolvedPage, VerificationLink

CLAIM_SPLIT_PATTERN = re.compile(r"(?<=[。.!?！？])\s+|\n+")
NOISE_PHRASES = [
    "ログイン",
    "会員登録",
    "続きを読む",
    "シェア",
    "コメント",
]
DOMAIN_KEYWORDS = {
    "医療": ["ワクチン", "副作用", "感染", "治療", "薬", "病院", "医師", "医療"],
    "災害": ["地震", "津波", "避難", "台風", "噴火", "災害", "警報"],
    "政治": ["選挙", "知事", "政党", "不正", "国会", "移民", "政治", "都知事"],
    "金融": ["投資", "NISA", "株価", "仮想通貨", "利回り", "金利", "金融"],
    "一般": ["発表", "報告", "問題", "調査", "主張"],
}
ASSERTIVE_PATTERNS = [
    "と発表",
    "と主張",
    "という",
    "判明",
    "確実",
    "絶対",
    "100%",
    "隠蔽",
    "デマ",
]
EVIDENCE_SOURCE_CATALOG: dict[str, list[tuple[str, str, str]]] = {
    "医療": [
        ("公的機関", "厚生労働省", "mhlw.go.jp"),
        ("公的機関", "国立感染症研究所", "niid.go.jp"),
        ("報道機関", "NHKニュース", "www3.nhk.or.jp"),
        ("ファクトチェック記事", "日本ファクトチェックセンター", "factcheckcenter.jp"),
    ],
    "災害": [
        ("公的機関", "気象庁", "jma.go.jp"),
        ("公的機関", "内閣府防災情報", "bousai.go.jp"),
        ("報道機関", "NHKニュース", "www3.nhk.or.jp"),
        ("ファクトチェック記事", "日本ファクトチェックセンター", "factcheckcenter.jp"),
    ],
    "政治": [
        ("公的機関", "総務省", "soumu.go.jp"),
        ("公的機関", "国会会議録検索システム", "kokkai.ndl.go.jp"),
        ("報道機関", "Reuters Japan", "jp.reuters.com"),
        ("ファクトチェック記事", "日本ファクトチェックセンター", "factcheckcenter.jp"),
    ],
    "金融": [
        ("公的機関", "金融庁", "fsa.go.jp"),
        ("公的機関", "日本銀行", "boj.or.jp"),
        ("報道機関", "Reuters Japan", "jp.reuters.com"),
        ("ファクトチェック記事", "日本ファクトチェックセンター", "factcheckcenter.jp"),
    ],
    "一般": [
        ("公的機関", "政府広報オンライン", "gov-online.go.jp"),
        ("報道機関", "NHKニュース", "www3.nhk.or.jp"),
        ("報道機関", "Reuters Japan", "jp.reuters.com"),
        ("ファクトチェック記事", "日本ファクトチェックセンター", "factcheckcenter.jp"),
    ],
}
MAX_CLAIMS = 3
MAX_LINKS = 8


def normalize_whitespace(value: str) -> str:
    return " ".join(value.replace("\u3000", " ").split())


def trim_claim(value: str, max_chars: int = 90) -> str:
    cleaned = normalize_whitespace(value).strip(" 。.!?！？")
    return cleaned[:max_chars].strip()


def split_sentences(text: str) -> list[str]:
    raw_parts = CLAIM_SPLIT_PATTERN.split(text)
    sentences = [trim_claim(part) for part in raw_parts]
    return [sentence for sentence in sentences if sentence]


def looks_like_noise(text: str) -> bool:
    if len(text) < 18:
        return True
    lowered = text.lower()
    if lowered.startswith("http://") or lowered.startswith("https://"):
        return True
    if looks_like_case_slug(text):
        return True
    return any(phrase in text for phrase in NOISE_PHRASES)


def looks_like_case_slug(text: str) -> bool:
    cleaned = normalize_whitespace(text)
    if len(cleaned) < 20 or " " in cleaned:
        return False
    if any(char in cleaned for char in "。、「」『』（）()"):
        return False
    hyphen_like_count = cleaned.count("-") + cleaned.count("_")
    if hyphen_like_count < 2:
        return False
    ascii_ratio = sum(1 for char in cleaned if ord(char) < 128) / max(len(cleaned), 1)
    return ascii_ratio >= 0.9


def score_claim(text: str, domain: str) -> int:
    keywords = DOMAIN_KEYWORDS.get(domain, DOMAIN_KEYWORDS["一般"])
    score = 0
    if any(keyword in text for keyword in keywords):
        score += 4
    if any(pattern in text for pattern in ASSERTIVE_PATTERNS):
        score += 3
    if re.search(r"\d", text):
        score += 2
    if 24 <= len(text) <= 100:
        score += 2
    elif len(text) > 100:
        score += 1
    if "?" in text or "？" in text:
        score -= 1
    return score


def dedupe_claims(claims: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for claim in claims:
        key = re.sub(r"\s+", "", claim)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(claim)
    return deduped


def extract_claim_candidates(page: ResolvedPage, domain: str) -> list[str]:
    candidates: list[tuple[int, str]] = []
    title_claim = trim_claim(page.title)
    if title_claim and not looks_like_noise(title_claim):
        candidates.append((score_claim(title_claim, domain) + 3, title_claim))

    for sentence in split_sentences(page.analysis_text):
        if looks_like_noise(sentence):
            continue
        score = score_claim(sentence, domain)
        if score < 2:
            continue
        candidates.append((score, sentence))

    ordered = [text for _, text in sorted(candidates, key=lambda item: (item[0], len(item[1])), reverse=True)]
    deduped = dedupe_claims(ordered)
    if deduped:
        return deduped[:MAX_CLAIMS]

    fallback = trim_claim(page.text_preview or page.analysis_text[:80])
    return [fallback] if fallback else []


def build_google_site_search_url(site_scope: str, claim: str) -> str:
    query = f"site:{site_scope} {claim}"
    return f"https://www.google.com/search?q={quote_plus(query)}"


def build_google_fact_search_url(claim: str) -> str:
    query = f"{claim} fact check"
    return f"https://www.google.com/search?q={quote_plus(query)}"


def shorten_for_label(claim: str, max_chars: int = 34) -> str:
    if len(claim) <= max_chars:
        return claim
    return claim[: max_chars - 1].rstrip() + "…"


def build_evidence_links(claims: list[str], domain: str) -> list[VerificationLink]:
    source_catalog = EVIDENCE_SOURCE_CATALOG.get(domain, EVIDENCE_SOURCE_CATALOG["一般"])
    links: list[VerificationLink] = []

    for claim in claims:
        claim_label = shorten_for_label(claim)
        for kind, source_name, site_scope in source_catalog:
            title = f"{source_name} で確認: {claim_label}"
            links.append(
                VerificationLink(
                    title=title,
                    url=build_google_site_search_url(site_scope, claim),
                    kind=f"外部根拠探索/{kind}",
                )
            )
            if len(links) >= MAX_LINKS:
                return links

    if claims and len(links) < MAX_LINKS:
        for claim in claims[:2]:
            links.append(
                VerificationLink(
                    title=f"ファクトチェック横断検索: {shorten_for_label(claim)}",
                    url=build_google_fact_search_url(claim),
                    kind="外部根拠探索/ファクトチェック記事",
                )
            )
            if len(links) >= MAX_LINKS:
                break
    return links[:MAX_LINKS]


def build_evidence_summary(claims: list[str], links: list[VerificationLink]) -> str:
    if not claims:
        return "本文から確認すべき主張候補を十分に絞れなかったため、一般的な確認導線のみ表示します。"
    return (
        f"確認すべき主張候補を {len(claims)} 件抽出し、"
        f"公的機関・報道機関・ファクトチェック向けに {len(links)} 件の探索リンクを作成しました。"
    )


def build_evidence_overview(page: ResolvedPage, domain: str) -> EvidenceOverview:
    claims = extract_claim_candidates(page, domain)
    links = build_evidence_links(claims, domain)
    status = "探索リンク生成済み" if links else "探索リンク限定"
    return EvidenceOverview(
        status=status,
        summary=build_evidence_summary(claims, links),
        claims=claims,
        links=links,
    )
