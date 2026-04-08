import json
import os
from pathlib import Path

from app.model_compare import (
    build_summary_markdown,
    export_comparison_csv,
    run_model_comparison,
    sanitize_model_id,
    sort_summary_entries,
)


def test_sanitize_model_id_replaces_unsafe_characters() -> None:
    assert sanitize_model_id(" gpt/5.4 mini ") == "gpt-5.4-mini"


def test_sort_summary_entries_prefers_macro_f1_then_accuracy() -> None:
    entries = [
        {"model": "b", "status": "completed", "metrics": {"macro_f1": 0.4, "accuracy": 0.6, "false_recall": 0.1}},
        {"model": "a", "status": "completed", "metrics": {"macro_f1": 0.5, "accuracy": 0.5, "false_recall": 0.2}},
        {"model": "err", "status": "error", "error": "boom"},
    ]

    sorted_entries = sort_summary_entries(entries)

    assert [entry["model"] for entry in sorted_entries] == ["a", "b", "err"]


def test_build_summary_markdown_includes_table_rows() -> None:
    markdown = build_summary_markdown(
        dataset_path=Path("sample.json"),
        use_gemini=True,
        case_filter=None,
        entries=[
            {
                "model": "gpt-5-mini",
                "status": "completed",
                "metrics": {
                    "accuracy": 0.4,
                    "macro_f1": 0.3,
                    "false_recall": 0.2,
                    "false_precision": 0.1,
                    "mismatch_count": 12,
                },
            }
        ],
    )

    assert "| 1 | `gpt-5-mini` | completed | 0.4000 | 0.3000 | 0.2000 | 0.1000 | 12 |" in markdown


def test_export_comparison_csv_filters_to_prediction_records(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset.json"
    csv_path = tmp_path / "out.csv"
    dataset_path.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "case-1",
                        "expected_verdict": "誤り",
                        "expected_domain": "一般",
                        "analysis_text": "本文1",
                    },
                    {
                        "id": "case-2",
                        "expected_verdict": "正確",
                        "expected_domain": "一般",
                        "analysis_text": "本文2",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    export_comparison_csv(
        {
            "records": [
                {
                    "id": "case-2",
                    "expected": {"verdict": "正確", "domain": "一般"},
                    "predicted": {"verdict": "正確", "attention_score": 18},
                }
            ]
        },
        dataset_path,
        csv_path,
    )

    content = csv_path.read_text(encoding="utf-8-sig")
    assert "case-2" in content
    assert "case-1" not in content


def test_run_model_comparison_restores_environment_and_writes_summary(tmp_path: Path, monkeypatch) -> None:
    original_model = "baseline-model"
    os.environ["OPENAI_PRIMARY_MODEL"] = original_model
    seen_models: list[str] = []

    async def fake_run_dataset(dataset_path, use_gemini, case_filter=None):
        seen_models.append(os.environ["OPENAI_PRIMARY_MODEL"])
        return {
            "meta": {
                "dataset_path": str(dataset_path),
                "use_gemini": use_gemini,
                "case_filter": case_filter,
                "analysis_date": "2026-04-09",
                "analysis_datetime": "2026-04-09 10:00:00 JST",
                "analysis_timezone": "Asia/Tokyo",
                "case_count": 1,
                "completed_count": 1,
                "error_count": 0,
                "quota_skipped_count": 0,
                "failure_case_count": 0,
                "gemini_preflight": "disabled",
            },
            "records": [
                {
                    "id": "case-1",
                    "expected": {"verdict": "誤り", "domain": "一般"},
                    "predicted": {"verdict": "誤り", "attention_score": 80},
                }
            ],
        }

    monkeypatch.setattr("app.model_compare.run_dataset", fake_run_dataset)
    monkeypatch.setattr(
        "app.model_compare.load_dataset",
        lambda path: {
            "cases": [
                {
                    "id": "case-1",
                    "expected_verdict": "誤り",
                    "expected_domain": "一般",
                    "analysis_text": "本文",
                }
            ]
        },
    )

    summary = run_model_comparison(
        dataset_path=Path("dummy.json"),
        models=["gpt-4.1-mini", "gpt-5-mini"],
        use_gemini=False,
        case_filter=None,
        output_root=tmp_path,
    )

    assert seen_models == ["gpt-4.1-mini", "gpt-5-mini"]
    assert os.environ["OPENAI_PRIMARY_MODEL"] == original_model
    assert summary["results"][0]["model"] == "gpt-4.1-mini"
    assert (tmp_path / "summary.json").exists()
    assert (tmp_path / "summary.md").exists()
