"""データセットをまとめて判定するための補助コード。"""

import json
import re
from pathlib import Path
from typing import Any

from .analyzer import analyze_page
from .config import Settings
from .content_extractor import resolve_page_input
from .models import AnalysisResult, ResolvedPage
from .time_utils import build_analysis_timestamp_fields

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATASET_PATH = ROOT_DIR / "testdata" / "article_dataset.json"
REAL_DATASET_PATH = ROOT_DIR / "testdata" / "real_article_dataset.json"
URL_PATTERN = re.compile(r"https?://[^\s)>\"]+")


def is_gemini_quota_skip(result: AnalysisResult, use_gemini: bool) -> bool:
    if not use_gemini or result.model_used != "heuristic-fallback":
        return False
    note = (result.evidence_overview.assessment_note or "").lower()
    quota_markers = [
        "quota exceeded",
        "resource_exhausted",
        "free_tier_requests",
        "rate limit",
    ]
    return any(marker in note for marker in quota_markers)


def load_dataset(path: Path) -> dict[str, Any]:
    """データセットJSONを読み込む。"""
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def select_cases(dataset: dict[str, Any], case_filter: str | None = None) -> list[dict[str, Any]]:
    all_cases = dataset.get("cases", [])
    return [case for case in all_cases if not case_filter or case["id"] == case_filter]


def build_settings(use_gemini: bool) -> Settings:
    """Geminiを使う/使わない設定を作る。"""
    return Settings() if use_gemini else Settings(gemini_api_key="")


def build_preview(text: str, max_chars: int = 320) -> str:
    return text.replace("\n", " ")[:max_chars].strip()


def count_reference_links(text: str) -> int:
    return len(dict.fromkeys(URL_PATTERN.findall(text)))


def estimate_paragraph_count(text: str) -> int:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return max(len(lines), 1)


def build_fixture_page(case: dict[str, Any], settings: Settings) -> ResolvedPage:
    """データセット1行を、通常のURL/本文入力と同じ `ResolvedPage` 形式にする。"""
    overrides = case.get("snapshot_overrides", {})
    text = str(case["analysis_text"]).strip()
    timestamp_fields = build_analysis_timestamp_fields(settings)

    author_name = overrides.get("author_name")
    published_at = overrides.get("published_at")
    has_author = bool(overrides.get("has_author", bool(author_name)))
    has_published_at = bool(overrides.get("has_published_at", bool(published_at)))

    return ResolvedPage(
        title=str(case["title"]).strip(),
        site_name=str(case.get("site_name") or "fixture.local").strip(),
        source_url=case.get("source_url"),
        input_source="test_fixture",
        extraction_note=str(case.get("purpose") or "テスト用記事セット").strip(),
        analysis_date=timestamp_fields["analysis_date"],
        analysis_datetime=timestamp_fields["analysis_datetime"],
        analysis_timezone=timestamp_fields["analysis_timezone"],
        policy_check_status=None,
        policy_check_note=None,
        policy_check_url=None,
        policy_checked_urls=[],
        text_preview=build_preview(text),
        extracted_chars=len(text),
        has_author=has_author,
        has_published_at=has_published_at,
        author_name=author_name,
        published_at=published_at,
        reference_link_count=int(overrides.get("reference_link_count", count_reference_links(text))),
        paragraph_count=int(overrides.get("paragraph_count", estimate_paragraph_count(text))),
        heading_count=int(overrides.get("heading_count", 1)),
        extraction_score=int(overrides.get("extraction_score", 60)),
        analysis_text=text,
    )


async def resolve_case_page(case: dict[str, Any], settings: Settings) -> tuple[ResolvedPage | None, str | None]:
    if case.get("analysis_text"):
        return build_fixture_page(case, settings), None

    page_url = str(case.get("page_url") or case.get("source_url") or "").strip()
    if page_url:
        return await resolve_page_input(None, page_url, settings)

    return None, "analysis_text または page_url が必要です。"


async def analyze_case(
    case: dict[str, Any],
    settings: Settings,
) -> tuple[AnalysisResult | None, list[str], bool, str | None]:
    """データセット1件を解析し、期待値との簡易チェック結果も返す。"""
    page, error = await resolve_case_page(case, settings)
    if error or not page:
        return None, [error or "ページを解決できませんでした。"], False, error

    result = await analyze_page(page, settings)
    failures = evaluate_result(case, result, bool(settings.gemini_api_key))
    quota_skipped = is_gemini_quota_skip(result, bool(settings.gemini_api_key))
    return result, failures, quota_skipped, None


def evaluate_result(case: dict[str, Any], result: AnalysisResult, use_gemini: bool) -> list[str]:
    """1件分の判定結果が期待値に合っているかを確認する。"""
    expected = case.get("expected", {})
    failures: list[str] = []

    if use_gemini and result.model_used != "heuristic+gemini-text" and not is_gemini_quota_skip(result, use_gemini):
        note = result.evidence_overview.assessment_note or "Gemini text review did not complete."
        failures.append(f"gemini fallback: {note}")

    expected_domain = expected.get("domain")
    if expected_domain and result.domain != expected_domain:
        failures.append(f"domain expected={expected_domain} actual={result.domain}")

    expected_caution_level = expected.get("caution_level")
    if expected_caution_level and result.caution_level != expected_caution_level:
        failures.append(f"caution_level expected={expected_caution_level} actual={result.caution_level}")

    expected_status = expected.get("status")
    if expected_status and result.status != expected_status:
        failures.append(f"status expected={expected_status} actual={result.status}")

    risk_min = expected.get("risk_min")
    risk_max = expected.get("risk_max")
    if isinstance(risk_min, int) and result.risk_score < risk_min:
        failures.append(f"risk_score expected>={risk_min} actual={result.risk_score}")
    if isinstance(risk_max, int) and result.risk_score > risk_max:
        failures.append(f"risk_score expected<={risk_max} actual={result.risk_score}")

    required_labels = expected.get("required_labels", [])
    for label in required_labels:
        if label not in result.labels:
            failures.append(f"missing label: {label}")

    min_claims = expected.get("min_claims")
    if isinstance(min_claims, int) and len(result.evidence_overview.claims) < min_claims:
        failures.append(
            f"evidence claims expected>={min_claims} actual={len(result.evidence_overview.claims)}"
        )

    return failures
