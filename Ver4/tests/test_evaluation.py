from app.evaluation import build_evaluation_report, get_nested_value


def test_get_nested_value_reads_dotted_key() -> None:
    item = {"expected": {"verdict": "誤り"}}
    assert get_nested_value(item, "expected.verdict") == "誤り"
    assert get_nested_value(item, "expected.status") is None


def test_build_evaluation_report_for_five_class_metrics() -> None:
    records = [
        {"id": "1", "expected": {"verdict": "誤り"}, "predicted": {"verdict": "誤り"}},
        {"id": "2", "expected": {"verdict": "不正確"}, "predicted": {"verdict": "判断保留"}},
        {"id": "3", "expected": {"verdict": "正確"}, "predicted": {"verdict": "正確"}},
        {"id": "4", "expected": {"verdict": "判断保留"}, "predicted": {"verdict": "判断保留"}},
    ]

    report = build_evaluation_report(records, truth_key="expected.verdict", pred_key="predicted.verdict")

    assert report["meta"]["sample_count"] == 4
    assert report["multiclass"]["accuracy"] == 0.75
    assert report["binary_fake_positive"]["precision"] == 1.0
    assert report["binary_fake_positive"]["recall"] == 1.0
    assert len(report["mismatches"]) == 1
    assert report["mismatches"][0]["id"] == "2"


def test_build_evaluation_report_skips_incomplete_records_for_runner_output() -> None:
    records = [
        {"id": "1", "expected": {"verdict": "誤り"}, "predicted": {"verdict": "誤り"}},
        {"id": "2", "expected": {"verdict": "不正確"}, "error": "ページ取得失敗"},
    ]

    report = build_evaluation_report(
        records,
        truth_key="expected.verdict",
        pred_key="predicted.verdict",
        skip_incomplete=True,
    )

    assert report["meta"]["sample_count"] == 1
    assert report["meta"]["skipped_count"] == 1
    assert report["skipped_records"][0]["id"] == "2"
