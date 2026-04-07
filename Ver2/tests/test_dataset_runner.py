import asyncio
import json
from pathlib import Path

from app.analyzer import publicize_result
from app.dataset_runner import build_prediction_record, load_dataset, run_dataset
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
        "model_used": "heuristic+gemini-evidence+gemini-style",
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


def test_run_dataset_preserves_order_and_limits_concurrency(monkeypatch) -> None:
    active = {"count": 0}
    max_active = {"count": 0}
    cases = [{"id": f"case-{index}", "title": f"ケース{index}", "expected": {}} for index in range(12)]

    async def fake_analyze_case(case, settings):
        active["count"] += 1
        max_active["count"] = max(max_active["count"], active["count"])
        await asyncio.sleep(0.01)
        active["count"] -= 1
        return make_result(), [], False, None

    monkeypatch.setattr("app.dataset_runner.load_dataset", lambda path: {"cases": cases})
    monkeypatch.setattr("app.dataset_runner.analyze_case", fake_analyze_case)

    bundle = asyncio.run(run_dataset(Path("dummy.json"), use_gemini=True))

    assert [record["id"] for record in bundle["records"]] == [case["id"] for case in cases]
    assert max_active["count"] <= 8


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
