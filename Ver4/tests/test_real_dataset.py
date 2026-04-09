from collections import Counter

from app.dataset_runner import (
    REAL_DATASET_PATH,
    build_fixture_page,
    build_settings,
    evaluate_result,
    load_dataset,
    normalize_case_schema,
)
from app.evidence_search import extract_claim_candidates
from app.models import AnalysisResult, EvidenceOverview, SourceSnapshot, StyleOverview


def make_result(verdict: str) -> AnalysisResult:
    return AnalysisResult(
        verdict=verdict,
        verdict_key="gray",
        verdict_display=verdict,
        attention_score=50,
        attention_display="50%",
        attention_band_display="41〜60%",
        risk_score=50,
        caution_level=verdict,
        confidence="中程度",
        confidence_label="中程度",
        confidence_score=60,
        status="自動判定",
        summary="test",
        reasons=["test"],
        supplement=None,
        labels=[],
        domain="一般",
        evidence_sources=[],
        verification_links=[],
        model_used="heuristic",
        source_snapshot=SourceSnapshot(
            title="t",
            site_name="s",
            input_source="test_fixture",
            extraction_note="note",
            text_preview="preview",
            extracted_chars=20,
        ),
        signal_breakdown=[],
        evidence_overview=EvidenceOverview(status="ok", summary="ok", links=[]),
        style_overview=StyleOverview(
            status="ok",
            summary="ok",
            score=10,
            score_display="10%",
            label="強い注意サインは目立たない",
            key="gray",
        ),
        timing_overview=None,
    )


def test_real_dataset_exists_and_has_cases() -> None:
    dataset = load_dataset(REAL_DATASET_PATH)
    assert REAL_DATASET_PATH.exists()
    assert len(dataset["cases"]) == 100
    labels = Counter(case["expected"]["verdict"] for case in dataset["cases"])
    assert labels == Counter(
        {
            "正確": 20,
            "ほぼ正確": 20,
            "判断保留": 20,
            "不正確": 20,
            "誤り": 20,
        }
    )
    assert any("5区分" in note for note in dataset["meta"]["notes"])
    assert any("analysis_text の中心命題" in note for note in dataset["meta"]["notes"])


def test_evaluate_result_checks_expected_verdict() -> None:
    case = {"expected": {"verdict": "誤り"}}
    failures = evaluate_result(case, make_result("不正確"), use_gemini=False)
    assert "verdict expected=誤り actual=不正確" in failures


def test_normalize_case_schema_supports_simplified_expected_fields() -> None:
    case = normalize_case_schema(
        {
            "id": "case-1",
            "expected_verdict": "判断保留",
            "analysis_text": "判定材料が不足している。",
            "expected_domain": "一般",
        },
        {"name": "real_article_dataset_v2"},
    )

    assert case["title"] == "判定材料が不足している。"
    assert case["site_name"] == "real_article_dataset_v2"
    assert case["expected"]["verdict"] == "判断保留"
    assert case["expected"]["domain"] == "一般"


def test_extract_claim_candidates_skips_dataset_case_slug_titles() -> None:
    case = normalize_case_schema(
        {
            "id": "positive-accurate-17-toyota-city-japan-name",
            "expected_verdict": "正確",
            "expected_domain": "一般",
            "analysis_mode": "claim",
            "claim_text": "日本の豊田市は、自動車メーカーであるトヨタ自動車にちなんで名付けられた。",
            "analysis_text": "日本の豊田市は、自動車メーカーであるトヨタ自動車にちなんで名付けられた。",
        },
        {"name": "real_article_dataset_v2"},
    )

    page = build_fixture_page(case, build_settings(False))
    claims = extract_claim_candidates(page, case["expected"]["domain"])

    assert claims == ["日本の豊田市は、自動車メーカーであるトヨタ自動車にちなんで名付けられた"]
