import argparse
import json
from pathlib import Path
from typing import Any

from sklearn.metrics import accuracy_score, confusion_matrix, precision_recall_fscore_support

PUBLIC_VERDICTS = (
    "正確",
    "ほぼ正確",
    "判断保留",
    "不正確",
    "誤り",
)
FAKE_POSITIVE_LABEL = "誤り"


def get_nested_value(item: dict[str, Any], dotted_key: str) -> Any:
    current: Any = item
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def load_records(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict) and isinstance(payload.get("cases"), list):
        records = payload["cases"]
    elif isinstance(payload, dict) and isinstance(payload.get("records"), list):
        records = payload["records"]
    else:
        raise ValueError("JSON は list / {'cases': [...]} / {'records': [...]} のいずれかで指定してください。")

    if not all(isinstance(record, dict) for record in records):
        raise ValueError("各レコードは object である必要があります。")
    return records


def collect_labels(
    records: list[dict[str, Any]],
    truth_key: str,
    pred_key: str,
    id_key: str = "id",
) -> tuple[list[str], list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    return collect_labels_with_options(records, truth_key=truth_key, pred_key=pred_key, id_key=id_key, skip_incomplete=False)


def collect_labels_with_options(
    records: list[dict[str, Any]],
    truth_key: str,
    pred_key: str,
    id_key: str = "id",
    skip_incomplete: bool = False,
) -> tuple[list[str], list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    y_true: list[str] = []
    y_pred: list[str] = []
    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for index, record in enumerate(records):
        row_id = str(get_nested_value(record, id_key) or index + 1)
        truth = get_nested_value(record, truth_key)
        pred = get_nested_value(record, pred_key)

        if truth is None or pred is None:
            reason = f"truth_key='{truth_key}' または pred_key='{pred_key}' が見つかりません。"
            if skip_incomplete:
                skipped.append({"id": row_id, "reason": reason})
                continue
            raise ValueError(f"id={row_id}: {reason}")

        truth_label = str(truth).strip()
        pred_label = str(pred).strip()
        if truth_label not in PUBLIC_VERDICTS:
            reason = f"truth '{truth_label}' は5区分のいずれでもありません。"
            if skip_incomplete:
                skipped.append({"id": row_id, "reason": reason})
                continue
            raise ValueError(f"id={row_id}: {reason}")
        if pred_label not in PUBLIC_VERDICTS:
            reason = f"pred '{pred_label}' は5区分のいずれでもありません。"
            if skip_incomplete:
                skipped.append({"id": row_id, "reason": reason})
                continue
            raise ValueError(f"id={row_id}: {reason}")

        y_true.append(truth_label)
        y_pred.append(pred_label)
        rows.append({"id": row_id, "truth": truth_label, "pred": pred_label})

    if not rows:
        raise ValueError("評価対象レコードが 0 件です。")

    return y_true, y_pred, rows, skipped


def build_multiclass_metrics(y_true: list[str], y_pred: list[str]) -> dict[str, Any]:
    accuracy = accuracy_score(y_true, y_pred)
    precisions, recalls, f1s, supports = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=list(PUBLIC_VERDICTS),
        zero_division=0,
    )
    macro_precision, macro_recall, macro_f1, _ = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=list(PUBLIC_VERDICTS),
        average="macro",
        zero_division=0,
    )
    weighted_precision, weighted_recall, weighted_f1, _ = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=list(PUBLIC_VERDICTS),
        average="weighted",
        zero_division=0,
    )
    matrix = confusion_matrix(y_true, y_pred, labels=list(PUBLIC_VERDICTS))

    per_class = {}
    for label, precision, recall, f1, support in zip(PUBLIC_VERDICTS, precisions, recalls, f1s, supports):
        per_class[label] = {
            "precision": round(float(precision), 4),
            "recall": round(float(recall), 4),
            "f1": round(float(f1), 4),
            "support": int(support),
        }

    return {
        "accuracy": round(float(accuracy), 4),
        "macro_avg": {
            "precision": round(float(macro_precision), 4),
            "recall": round(float(macro_recall), 4),
            "f1": round(float(macro_f1), 4),
        },
        "weighted_avg": {
            "precision": round(float(weighted_precision), 4),
            "recall": round(float(weighted_recall), 4),
            "f1": round(float(weighted_f1), 4),
        },
        "per_class": per_class,
        "labels": list(PUBLIC_VERDICTS),
        "confusion_matrix": matrix.tolist(),
    }


def build_fake_binary_metrics(y_true: list[str], y_pred: list[str]) -> dict[str, Any]:
    y_true_binary = [label == FAKE_POSITIVE_LABEL for label in y_true]
    y_pred_binary = [label == FAKE_POSITIVE_LABEL for label in y_pred]
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true_binary,
        y_pred_binary,
        average="binary",
        zero_division=0,
    )
    return {
        "positive_label": FAKE_POSITIVE_LABEL,
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "f1": round(float(f1), 4),
        "support": int(sum(y_true_binary)) if support is None else int(support),
    }


def build_evaluation_report(
    records: list[dict[str, Any]],
    truth_key: str,
    pred_key: str,
    id_key: str = "id",
    skip_incomplete: bool = False,
) -> dict[str, Any]:
    y_true, y_pred, rows, skipped = collect_labels_with_options(
        records,
        truth_key=truth_key,
        pred_key=pred_key,
        id_key=id_key,
        skip_incomplete=skip_incomplete,
    )
    return {
        "meta": {
            "truth_key": truth_key,
            "pred_key": pred_key,
            "id_key": id_key,
            "sample_count": len(rows),
            "skipped_count": len(skipped),
        },
        "multiclass": build_multiclass_metrics(y_true, y_pred),
        "binary_fake_positive": build_fake_binary_metrics(y_true, y_pred),
        "mismatches": [row for row in rows if row["truth"] != row["pred"]],
        "skipped_records": skipped,
    }


def format_float(value: float) -> str:
    return f"{value:.4f}"


def format_report_text(report: dict[str, Any]) -> str:
    lines: list[str] = []
    meta = report["meta"]
    multi = report["multiclass"]
    binary = report["binary_fake_positive"]

    lines.append("5区分評価")
    lines.append(f"sample_count: {meta['sample_count']}")
    lines.append(f"skipped_count: {meta['skipped_count']}")
    lines.append(f"accuracy: {format_float(multi['accuracy'])}")
    lines.append(
        "macro_avg: "
        f"precision={format_float(multi['macro_avg']['precision'])} "
        f"recall={format_float(multi['macro_avg']['recall'])} "
        f"f1={format_float(multi['macro_avg']['f1'])}"
    )
    lines.append(
        "weighted_avg: "
        f"precision={format_float(multi['weighted_avg']['precision'])} "
        f"recall={format_float(multi['weighted_avg']['recall'])} "
        f"f1={format_float(multi['weighted_avg']['f1'])}"
    )
    lines.append("")
    lines.append("per_class:")
    for label in PUBLIC_VERDICTS:
        metrics = multi["per_class"][label]
        lines.append(
            f"- {label}: "
            f"precision={format_float(metrics['precision'])} "
            f"recall={format_float(metrics['recall'])} "
            f"f1={format_float(metrics['f1'])} "
            f"support={metrics['support']}"
        )
    lines.append("")
    lines.append(f"binary_fake_positive ({binary['positive_label']}):")
    lines.append(
        f"precision={format_float(binary['precision'])} "
        f"recall={format_float(binary['recall'])} "
        f"f1={format_float(binary['f1'])} "
        f"support={binary['support']}"
    )
    lines.append("")
    lines.append("confusion_matrix:")
    header = "truth\\pred," + ",".join(PUBLIC_VERDICTS)
    lines.append(header)
    for label, row in zip(PUBLIC_VERDICTS, multi["confusion_matrix"]):
        lines.append(label + "," + ",".join(str(value) for value in row))
    lines.append("")
    lines.append(f"mismatches: {len(report['mismatches'])}")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="5区分フェイクニュース判定の sklearn 評価")
    parser.add_argument("input_json", type=Path, help="評価用 JSON ファイル")
    parser.add_argument("--truth-key", default="expected.verdict", help="正解ラベルの dotted key")
    parser.add_argument("--pred-key", default="predicted.verdict", help="予測ラベルの dotted key")
    parser.add_argument("--id-key", default="id", help="ケース ID の dotted key")
    parser.add_argument("--strict", action="store_true", help="不完全レコードをスキップせずエラーにする")
    parser.add_argument("--output-json", type=Path, default=None, help="評価結果 JSON の保存先")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    records = load_records(args.input_json)
    report = build_evaluation_report(
        records,
        truth_key=args.truth_key,
        pred_key=args.pred_key,
        id_key=args.id_key,
        skip_incomplete=not args.strict,
    )
    print(format_report_text(report))
    if args.output_json:
        args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
