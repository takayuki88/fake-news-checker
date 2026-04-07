import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

from .analyzer import analyze_page, run_gemini_preflight
from .config import Settings
from .content_extractor import resolve_page_input
from .evaluation import build_evaluation_report, format_report_text
from .models import AnalysisResult, ResolvedPage
from .time_utils import build_analysis_timestamp_fields

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATASET_PATH = ROOT_DIR / "testdata" / "article_dataset.json"
REAL_DATASET_PATH = ROOT_DIR / "testdata" / "real_article_dataset.json"
URL_PATTERN = re.compile(r"https?://[^\s)>\"]+")
MAX_CONCURRENT_CASES = 4
MAX_CONCURRENT_GEMINI_CASES = 8
CASE_MAX_ATTEMPTS = 2


class GeminiPreflightError(RuntimeError):
    pass


def format_gemini_preflight_error(detail: str) -> str:
    normalized_detail = detail.strip() or "Gemini preflight did not complete."
    lowered_detail = normalized_detail.lower()
    hints = [
        ".env の GEMINI_API_KEY と GEMINI_MODEL を確認してください。",
        "Gemini を使わず続ける場合は --no-gemini を付けて実行してください。",
    ]
    if "all connection attempts failed" in lowered_detail or "http error" in lowered_detail:
        hints.insert(0, "ネットワーク接続、プロキシ、VPN、ファイアウォール設定を確認してください。")
    elif "api error 429" in lowered_detail or "quota" in lowered_detail or "resource_exhausted" in lowered_detail:
        hints.insert(0, "Gemini API の利用上限やレート制限に達していないか確認してください。")
    elif "api error 403" in lowered_detail or "api error 401" in lowered_detail:
        hints.insert(0, "API キーの権限や有効期限を確認してください。")

    hint_lines = "\n".join(f"- {hint}" for hint in hints)
    return (
        "Gemini preflight failed.\n"
        "dataset 実行前の接続確認で停止しました。\n"
        f"原因: {normalized_detail}\n"
        "確認ポイント:\n"
        f"{hint_lines}"
    )


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


def normalize_case_schema(case: dict[str, Any], dataset_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    expected = case.get("expected")
    if isinstance(expected, dict):
        return case

    expected_verdict = case.get("expected_verdict")
    expected_domain = case.get("expected_domain")
    if expected_verdict is None and expected_domain is None:
        return case

    dataset_name = ""
    if isinstance(dataset_meta, dict):
        dataset_name = str(dataset_meta.get("name") or "").strip()

    normalized = dict(case)
    normalized["title"] = str(case.get("title") or case.get("id") or "dataset case").strip()
    normalized["site_name"] = str(case.get("site_name") or dataset_name or "dataset_fixture").strip()
    normalized["source_url"] = case.get("source_url") or case.get("page_url")
    normalized["purpose"] = str(
        case.get("purpose") or "簡略スキーマの評価用データセットを内部形式に正規化したケース"
    ).strip()
    normalized["reference_urls"] = list(case.get("reference_urls") or [])
    normalized["snapshot_overrides"] = dict(case.get("snapshot_overrides") or {})
    normalized["source_verdict_label"] = str(
        case.get("source_verdict_label") or expected_verdict or ""
    ).strip()
    normalized["expected"] = {
        "verdict": expected_verdict,
        "domain": expected_domain,
    }
    return normalized


def normalize_dataset_schema(payload: dict[str, Any]) -> dict[str, Any]:
    dataset_meta = payload.get("meta")
    cases = payload.get("cases", [])
    if not isinstance(cases, list):
        return payload

    normalized_cases = [
        normalize_case_schema(case, dataset_meta)
        for case in cases
        if isinstance(case, dict)
    ]
    normalized_payload = dict(payload)
    normalized_payload["cases"] = normalized_cases
    return normalized_payload


def load_dataset(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("データセット JSON は {'cases': [...]} 形式で指定してください。")
    return normalize_dataset_schema(payload)


def select_cases(dataset: dict[str, Any], case_filter: str | None = None) -> list[dict[str, Any]]:
    all_cases = dataset.get("cases", [])
    return [case for case in all_cases if not case_filter or case["id"] == case_filter]


def build_settings(use_gemini: bool) -> Settings:
    return Settings() if use_gemini else Settings(gemini_api_key="")


def get_max_concurrent_cases(use_gemini: bool) -> int:
    return MAX_CONCURRENT_GEMINI_CASES if use_gemini else MAX_CONCURRENT_CASES


async def verify_gemini_preflight(use_gemini: bool, settings: Settings) -> str:
    if not use_gemini:
        return "disabled"
    if not settings.gemini_api_key:
        return "skipped-no-api-key"
    try:
        await run_gemini_preflight(settings)
    except RuntimeError as exc:
        raise GeminiPreflightError(format_gemini_preflight_error(str(exc))) from exc
    return "passed"


def build_preview(text: str, max_chars: int = 320) -> str:
    return text.replace("\n", " ")[:max_chars].strip()


def count_reference_links(text: str) -> int:
    return len(dict.fromkeys(URL_PATTERN.findall(text)))


def estimate_paragraph_count(text: str) -> int:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return max(len(lines), 1)


def build_fixture_page(case: dict[str, Any], settings: Settings) -> ResolvedPage:
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
    page, error = await resolve_case_page(case, settings)
    if error or not page:
        return None, [error or "ページを解決できませんでした。"], False, error

    result = await analyze_page(page, settings)
    failures = evaluate_result(case, result, bool(settings.gemini_api_key))
    quota_skipped = is_gemini_quota_skip(result, bool(settings.gemini_api_key))
    return result, failures, quota_skipped, None


def should_retry_case(
    failures: list[str],
    quota_skipped: bool,
    error: str | None,
    attempt_number: int,
    max_attempts: int,
) -> bool:
    if attempt_number >= max_attempts:
        return False
    if error:
        return True
    if quota_skipped:
        return False
    return any(failure.startswith("gemini fallback:") for failure in failures)


async def analyze_case_with_retry(
    case: dict[str, Any],
    settings: Settings,
    max_attempts: int = CASE_MAX_ATTEMPTS,
) -> tuple[AnalysisResult | None, list[str], bool, str | None]:
    attempt_number = 0
    while True:
        attempt_number += 1
        try:
            result, failures, quota_skipped, error = await analyze_case(case, settings)
        except Exception as exc:
            result = None
            failures = []
            quota_skipped = False
            error = f"{type(exc).__name__}: {exc}"

        if not should_retry_case(failures, quota_skipped, error, attempt_number, max_attempts):
            return result, failures, quota_skipped, error


async def run_case_task(
    index: int,
    case: dict[str, Any],
    settings: Settings,
    semaphore: asyncio.Semaphore,
) -> tuple[int, dict[str, Any]]:
    async with semaphore:
        result, failures, quota_skipped, error = await analyze_case_with_retry(case, settings)
    return index, build_prediction_record(case, result, failures, quota_skipped, error)


def evaluate_result(case: dict[str, Any], result: AnalysisResult, use_gemini: bool) -> list[str]:
    expected = case.get("expected", {})
    failures: list[str] = []

    valid_gemini_models = {
        "heuristic+gemini-evidence+gemini-style",
        "heuristic+gemini-evidence",
        "gemini-primary+gemini-evidence+gemini-style",
        "gemini-primary+gemini-evidence",
    }
    if use_gemini and result.model_used not in valid_gemini_models and not is_gemini_quota_skip(result, use_gemini):
        note = result.style_overview.note or result.evidence_overview.assessment_note or "Gemini dual review did not complete."
        failures.append(f"gemini fallback: {note}")

    expected_domain = expected.get("domain")
    if expected_domain and result.domain != expected_domain:
        failures.append(f"domain expected={expected_domain} actual={result.domain}")

    expected_verdict = expected.get("verdict")
    if expected_verdict and result.verdict != expected_verdict:
        failures.append(f"verdict expected={expected_verdict} actual={result.verdict}")

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


def resolve_dataset_path(dataset_path: Path | None, dataset_name: str | None) -> Path:
    if dataset_path:
        return dataset_path
    if dataset_name == "default":
        return DEFAULT_DATASET_PATH
    if dataset_name == "real":
        return REAL_DATASET_PATH
    if DEFAULT_DATASET_PATH.exists():
        return DEFAULT_DATASET_PATH
    raise ValueError("データセット JSON を指定してください。例: python -m app.dataset_runner .\\eval_cases.json")


def serialize_prediction(result: AnalysisResult | None) -> dict[str, Any]:
    if not result:
        return {}
    return {
        "verdict": result.verdict,
        "verdict_display": result.verdict_display,
        "status": result.status,
        "attention_score": result.attention_score,
        "attention_band_display": result.attention_band_display,
        "risk_score": result.risk_score,
        "confidence_score": result.confidence_score,
        "domain": result.domain,
        "labels": list(result.labels),
        "model_used": result.model_used,
        "timing_total_ms": result.timing_overview.total_ms if result.timing_overview else None,
    }


def build_prediction_record(
    case: dict[str, Any],
    result: AnalysisResult | None,
    failures: list[str],
    quota_skipped: bool,
    error: str | None,
) -> dict[str, Any]:
    record = {
        "id": str(case.get("id") or ""),
        "title": str(case.get("title") or "").strip(),
        "source_url": case.get("source_url") or case.get("page_url"),
        "expected": dict(case.get("expected") or {}),
        "predicted": serialize_prediction(result),
        "failures": list(failures),
        "quota_skipped": quota_skipped,
        "error": error,
    }
    if result:
        record["analysis_result"] = result.model_dump()
    return record


async def run_dataset(
    dataset_path: Path,
    use_gemini: bool,
    case_filter: str | None = None,
) -> dict[str, Any]:
    settings = build_settings(use_gemini)
    gemini_preflight = await verify_gemini_preflight(use_gemini, settings)
    dataset = load_dataset(dataset_path)
    cases = select_cases(dataset, case_filter)
    timestamp_fields = build_analysis_timestamp_fields(settings)
    records: list[dict[str, Any] | None] = [None] * len(cases)
    semaphore = asyncio.Semaphore(get_max_concurrent_cases(use_gemini))

    tasks = [
        asyncio.create_task(run_case_task(index, case, settings, semaphore))
        for index, case in enumerate(cases)
    ]
    for index, record in await asyncio.gather(*tasks):
        records[index] = record

    ordered_records = [record for record in records if record is not None]

    completed_count = sum(1 for record in ordered_records if record.get("predicted", {}).get("verdict"))
    error_count = sum(1 for record in ordered_records if record.get("error"))
    quota_skipped_count = sum(1 for record in ordered_records if record.get("quota_skipped"))
    failure_case_count = sum(1 for record in ordered_records if record.get("failures"))

    return {
        "meta": {
            "dataset_path": str(dataset_path),
            "use_gemini": use_gemini,
            "gemini_preflight": gemini_preflight,
            "case_filter": case_filter,
            "analysis_date": timestamp_fields["analysis_date"],
            "analysis_datetime": timestamp_fields["analysis_datetime"],
            "analysis_timezone": timestamp_fields["analysis_timezone"],
            "case_count": len(cases),
            "completed_count": completed_count,
            "error_count": error_count,
            "quota_skipped_count": quota_skipped_count,
            "failure_case_count": failure_case_count,
        },
        "records": ordered_records,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="データセットを解析して評価互換の予測 JSON を出力します。")
    parser.add_argument("dataset_json", nargs="?", type=Path, default=None, help="入力データセット JSON")
    parser.add_argument("--dataset", choices=["default", "real"], default=None, help="組み込みデータセットを使う")
    parser.add_argument("--case-id", default=None, help="単一ケース ID のみ実行")
    gemini_group = parser.add_mutually_exclusive_group()
    gemini_group.add_argument("--use-gemini", dest="use_gemini", action="store_true", help="Gemini を明示的に有効化")
    gemini_group.add_argument("--no-gemini", dest="use_gemini", action="store_false", help="Gemini を使わずローカル判定のみで実行")
    parser.set_defaults(use_gemini=True)
    parser.add_argument("--output-json", type=Path, default=None, help="予測 JSON の保存先")
    parser.add_argument("--print-evaluation", action="store_true", help="評価結果を標準出力にも表示")
    parser.add_argument("--evaluation-output", type=Path, default=None, help="評価結果 JSON の保存先")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dataset_path = resolve_dataset_path(args.dataset_json, args.dataset)
    try:
        prediction_bundle = asyncio.run(run_dataset(dataset_path, use_gemini=args.use_gemini, case_filter=args.case_id))
    except GeminiPreflightError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.output_json:
        args.output_json.write_text(json.dumps(prediction_bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        print(json.dumps(prediction_bundle, ensure_ascii=False, indent=2))

    if args.print_evaluation or args.evaluation_output:
        report = build_evaluation_report(
            prediction_bundle["records"],
            truth_key="expected.verdict",
            pred_key="predicted.verdict",
            id_key="id",
            skip_incomplete=True,
        )
        if args.print_evaluation:
            print()
            print(format_report_text(report))
        if args.evaluation_output:
            args.evaluation_output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
