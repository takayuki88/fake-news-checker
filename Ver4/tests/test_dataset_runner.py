import asyncio
import json
from pathlib import Path

from app.analyzer import publicize_result
from app.config import Settings
from app.dataset_runner import (
    GeminiPreflightError,
    analyze_case_with_retry,
    build_prediction_record,
    format_gemini_preflight_error,
    load_dataset,
    run_dataset,
    verify_gemini_preflight,
)
from app.models import ResolvedPage


def make_page() -> ResolvedPage:
    return ResolvedPage(
        title="検証用ページ",
        site_name="Example News",
        input_source="manual_text",
        extraction_note="manual input",
        text_preview="検証用の本文プレビューです。",
        extracted_chars=120,
        analysis_text="これは検証用の本文です。十分な長さがあり、解析対象として扱えます。",
    )


def make_result():
    page = make_page()
    payload = {
        "risk_score": 35,
        "confidence": "中程度",
        "confidence_score": 60,
        "status": "自動判定",
        "summary": "整合しています。",
        "labels": [],
        "reasons": ["テスト理由"],
        "domain": "一般",
        "verification_links": [],
        "caution_level": "ほぼ正確",
        "model_used": "gpt-primary+gemini-evidence",
        "signal_breakdown": [],
        "evidence_overview": {
            "status": "Gemini根拠比較済み",
            "summary": "外部根拠は大筋で整合しています。",
            "assessment_status": "概ね整合",
            "assessment_summary": "外部根拠は大筋で整合しています。",
            "links": [],
            "grounding_sources": [],
            "claim_reviews": [],
            "grounding_queries": [],
            "retrieved_urls": [],
        },
        "style_overview": {
            "status": "テスト用",
            "summary": "書き振り評価のテストです。",
            "score": 30,
            "score_display": "30%",
            "label": "注意サインは比較的少ない",
            "key": "gray",
            "note": None,
            "model": "test-style",
            "highlights": [],
            "signals": [],
        },
    }
    return publicize_result(page, payload, {})


def test_build_prediction_record_contains_evaluation_keys() -> None:
    case = {"id": "case-1", "title": "検証ケース", "expected": {"verdict": "ほぼ正確"}}
    record = build_prediction_record(case, make_result(), failures=[], quota_skipped=False, error=None)

    assert record["id"] == "case-1"
    assert record["expected"]["verdict"] == "ほぼ正確"
    assert record["predicted"]["verdict"] == "ほぼ正確"
    assert "analysis_result" in record


def test_analyze_case_with_retry_retries_after_exception(monkeypatch) -> None:
    attempts = {"count": 0}

    async def fake_analyze_case(case, settings):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("temporary failure")
        return make_result(), [], False, None

    monkeypatch.setattr("app.dataset_runner.analyze_case", fake_analyze_case)

    result, failures, quota_skipped, error = asyncio.run(
        analyze_case_with_retry({"id": "case-1"}, Settings(gemini_api_key=""), max_attempts=2)
    )

    assert attempts["count"] == 2
    assert result is not None
    assert failures == []
    assert quota_skipped is False
    assert error is None


def test_run_dataset_preserves_order_and_limits_concurrency(monkeypatch) -> None:
    active = {"count": 0}
    max_active = {"count": 0}
    cases = [{"id": f"case-{index}", "title": f"ケース{index}", "expected": {}} for index in range(6)]

    async def fake_analyze_case_with_retry(case, settings, max_attempts=2):
        active["count"] += 1
        max_active["count"] = max(max_active["count"], active["count"])
        await asyncio.sleep(0.01)
        active["count"] -= 1
        return make_result(), [], False, None

    monkeypatch.setattr("app.dataset_runner.load_dataset", lambda path: {"cases": cases})
    monkeypatch.setattr("app.dataset_runner.analyze_case_with_retry", fake_analyze_case_with_retry)

    bundle = asyncio.run(run_dataset(Path("dummy.json"), use_gemini=False))

    assert [record["id"] for record in bundle["records"]] == [case["id"] for case in cases]
    assert max_active["count"] <= 4
    assert bundle["meta"]["gemini_preflight"] == "disabled"


def test_verify_gemini_preflight_runs_once_when_enabled(monkeypatch) -> None:
    calls = {"count": 0}

    async def fake_run_gemini_preflight(settings):
        calls["count"] += 1

    monkeypatch.setattr("app.dataset_runner.run_gemini_preflight", fake_run_gemini_preflight)

    status = asyncio.run(verify_gemini_preflight(True, Settings(gemini_api_key="dummy-key")))

    assert status == "passed"
    assert calls["count"] == 1


def test_run_dataset_records_passed_gemini_preflight(monkeypatch) -> None:
    cases = [{"id": "case-1", "title": "ケース1", "expected": {}}]
    calls = {"count": 0}

    async def fake_run_gemini_preflight(settings):
        calls["count"] += 1

    async def fake_analyze_case_with_retry(case, settings, max_attempts=2):
        return make_result(), [], False, None

    monkeypatch.setattr("app.dataset_runner.load_dataset", lambda path: {"cases": cases})
    monkeypatch.setattr("app.dataset_runner.run_gemini_preflight", fake_run_gemini_preflight)
    monkeypatch.setattr("app.dataset_runner.analyze_case_with_retry", fake_analyze_case_with_retry)

    bundle = asyncio.run(run_dataset(Path("dummy.json"), use_gemini=True))

    assert bundle["meta"]["gemini_preflight"] == "passed"
    assert calls["count"] == 1


def test_format_gemini_preflight_error_for_connection_failure() -> None:
    message = format_gemini_preflight_error("Gemini HTTP error: All connection attempts failed")

    assert "Gemini preflight failed." in message
    assert "dataset 実行前の接続確認で停止しました。" in message
    assert "原因: Gemini HTTP error: All connection attempts failed" in message
    assert "ネットワーク接続、プロキシ、VPN、ファイアウォール設定を確認してください。" in message
    assert "--no-gemini" in message


def test_verify_gemini_preflight_raises_readable_error(monkeypatch) -> None:
    async def fake_run_gemini_preflight(settings):
        raise RuntimeError("Gemini API error 429: quota exceeded")

    monkeypatch.setattr("app.dataset_runner.run_gemini_preflight", fake_run_gemini_preflight)

    try:
        asyncio.run(verify_gemini_preflight(True, Settings(gemini_api_key="dummy-key")))
    except GeminiPreflightError as exc:
        message = str(exc)
    else:
        raise AssertionError("GeminiPreflightError was not raised")

    assert "Gemini preflight failed." in message
    assert "Gemini API の利用上限やレート制限に達していないか確認してください。" in message


def test_load_dataset_normalizes_simplified_schema() -> None:
    dataset_path = Path(__file__).resolve().parent / "_tmp_real_article_dataset_v2.json"
    try:
        dataset_path.write_text(
            json.dumps(
                {
                    "meta": {"name": "real_article_dataset_v2"},
                    "cases": [
                        {
                            "id": "case-1",
                            "expected_verdict": "誤り",
                            "analysis_text": "これは誤った主張です。",
                            "expected_domain": "一般",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        dataset = load_dataset(dataset_path)
        case = dataset["cases"][0]

        assert case["title"] == "case-1"
        assert case["site_name"] == "real_article_dataset_v2"
        assert case["expected"] == {"verdict": "誤り", "domain": "一般"}
        assert case["source_verdict_label"] == "誤り"
        assert case["reference_urls"] == []
    finally:
        dataset_path.unlink(missing_ok=True)
