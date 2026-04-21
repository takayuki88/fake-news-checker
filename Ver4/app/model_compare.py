"""Ver4 で複数モデルの評価結果を比較するためのコマンドライン補助。"""

import argparse
import asyncio
import csv
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from .config import Settings
from .dataset_runner import ROOT_DIR, GeminiPreflightError, load_dataset, run_dataset
from .evaluation import build_evaluation_report
from .time_utils import get_current_app_datetime

DEFAULT_MODELS = ("gpt-4.1-mini", "gpt-5-mini", "gpt-5.4-mini")
SHARED_TESTDATA_DIR = ROOT_DIR.parent / "testdata" / "shared"


def sanitize_model_id(model_id: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z._-]+", "-", model_id.strip())
    return normalized.strip(".-") or "model"


def resolve_dataset_path(dataset_json: Path | None, dataset_name: str | None) -> Path:
    """指定された引数から、比較に使うデータセットパスを決める。"""
    if dataset_json:
        return dataset_json
    if dataset_name == "default":
        return SHARED_TESTDATA_DIR / "article_dataset.json"
    if dataset_name == "real":
        return SHARED_TESTDATA_DIR / "real_article_dataset.json"
    default_path = SHARED_TESTDATA_DIR / "article_dataset.json"
    if default_path.exists():
        return default_path
    raise ValueError("データセット JSON を指定してください。例: python -m app.model_compare --dataset real")


def build_comparison_output_dir(label: str | None = None) -> Path:
    timestamp = get_current_app_datetime(Settings()).strftime("%Y%m%d-%H%M%S")
    suffix = f"-{sanitize_model_id(label)}" if label else ""
    return ROOT_DIR / "evaluation_outputs" / "model_compare" / f"{timestamp}{suffix}"


def export_comparison_csv(
    prediction_bundle: dict[str, Any],
    dataset_path: Path,
    csv_path: Path,
) -> None:
    dataset = load_dataset(dataset_path)
    cases_by_id = {str(case.get("id") or ""): case for case in dataset.get("cases", [])}
    fieldnames = [
        "id",
        "expected_verdict",
        "analysis_text",
        "expected_domain",
        "predicted_verdict",
        "attention_score",
    ]
    rows: list[dict[str, str]] = []
    for record in prediction_bundle.get("records", []):
        case_id = str(record.get("id") or "")
        case = cases_by_id.get(case_id, {})
        expected = record.get("expected") or case.get("expected") or {}
        predicted = record.get("predicted") or {}
        attention_score = predicted.get("attention_score")
        rows.append(
            {
                "id": case_id,
                "expected_verdict": str(expected.get("verdict") or case.get("expected_verdict") or "").strip(),
                "analysis_text": str(case.get("analysis_text") or "").strip(),
                "expected_domain": str(expected.get("domain") or case.get("expected_domain") or "").strip(),
                "predicted_verdict": str(predicted.get("verdict") or "").strip(),
                "attention_score": "" if attention_score is None else str(int(round(float(attention_score)))),
            }
        )

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def save_model_outputs(
    *,
    prediction_bundle: dict[str, Any],
    report: dict[str, Any],
    dataset_path: Path,
    output_dir: Path,
) -> dict[str, Path]:
    """1モデル分の予測・評価・CSVを保存する。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "predictions_json": output_dir / "predictions.json",
        "evaluation_json": output_dir / "evaluation.json",
        "csv": output_dir / f"{dataset_path.stem}_with_predicted_verdict_attention_score.csv",
    }
    paths["predictions_json"].write_text(json.dumps(prediction_bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["evaluation_json"].write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    export_comparison_csv(prediction_bundle, dataset_path, paths["csv"])
    return paths


def build_summary_entry(
    *,
    model_id: str,
    prediction_bundle: dict[str, Any] | None,
    report: dict[str, Any] | None,
    output_dir: Path,
    error: str | None = None,
) -> dict[str, Any]:
    if error:
        return {
            "model": model_id,
            "output_dir": str(output_dir),
            "status": "error",
            "error": error,
        }

    assert prediction_bundle is not None
    assert report is not None
    multiclass = report["multiclass"]
    false_metrics = multiclass["per_class"]["誤り"]
    binary = report["binary_fake_positive"]
    return {
        "model": model_id,
        "output_dir": str(output_dir),
        "status": "completed",
        "meta": prediction_bundle["meta"],
        "metrics": {
            "accuracy": multiclass["accuracy"],
            "macro_f1": multiclass["macro_avg"]["f1"],
            "weighted_f1": multiclass["weighted_avg"]["f1"],
            "false_precision": false_metrics["precision"],
            "false_recall": false_metrics["recall"],
            "false_f1": false_metrics["f1"],
            "binary_false_precision": binary["precision"],
            "binary_false_recall": binary["recall"],
            "binary_false_f1": binary["f1"],
            "mismatch_count": len(report["mismatches"]),
        },
    }


def sort_summary_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def sort_key(entry: dict[str, Any]) -> tuple[Any, ...]:
        if entry.get("status") != "completed":
            return (1, 0, 0, 0, entry.get("model", ""))
        metrics = entry.get("metrics", {})
        return (
            0,
            -float(metrics.get("macro_f1", 0.0)),
            -float(metrics.get("accuracy", 0.0)),
            -float(metrics.get("false_recall", 0.0)),
            entry.get("model", ""),
        )

    return sorted(entries, key=sort_key)


def build_summary_markdown(
    *,
    dataset_path: Path,
    use_gemini: bool,
    case_filter: str | None,
    entries: list[dict[str, Any]],
) -> str:
    """モデル比較の概要を Markdown テーブルとして作る。"""
    lines = [
        "# OpenAI primary model comparison",
        "",
        f"- dataset: `{dataset_path}`",
        f"- use_gemini: `{use_gemini}`",
        f"- case_filter: `{case_filter or 'all'}`",
        "",
        "| rank | model | status | accuracy | macro_f1 | 誤り recall | 誤り precision | mismatches |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]

    ranked = sort_summary_entries(entries)
    rank = 0
    for entry in ranked:
        if entry.get("status") != "completed":
            lines.append(
                f"| - | `{entry['model']}` | error | - | - | - | - | - |"
            )
            continue
        rank += 1
        metrics = entry["metrics"]
        lines.append(
            "| "
            f"{rank} | `{entry['model']}` | completed | "
            f"{metrics['accuracy']:.4f} | {metrics['macro_f1']:.4f} | "
            f"{metrics['false_recall']:.4f} | {metrics['false_precision']:.4f} | "
            f"{metrics['mismatch_count']} |"
        )
    return "\n".join(lines) + "\n"


def run_model_comparison(
    *,
    dataset_path: Path,
    models: list[str],
    use_gemini: bool,
    case_filter: str | None,
    output_root: Path,
) -> dict[str, Any]:
    """指定モデルを順番に実行し、評価指標を比較用にまとめる。"""
    output_root.mkdir(parents=True, exist_ok=True)
    previous_model = os.environ.get("OPENAI_PRIMARY_MODEL")
    entries: list[dict[str, Any]] = []

    try:
        for model_id in models:
            model_dir = output_root / sanitize_model_id(model_id)
            print(f"[compare] running model={model_id}", file=sys.stderr)
            os.environ["OPENAI_PRIMARY_MODEL"] = model_id
            try:
                prediction_bundle = asyncio.run(run_dataset(dataset_path, use_gemini=use_gemini, case_filter=case_filter))
                report = build_evaluation_report(
                    prediction_bundle["records"],
                    truth_key="expected.verdict",
                    pred_key="predicted.verdict",
                    id_key="id",
                    skip_incomplete=True,
                )
                save_model_outputs(
                    prediction_bundle=prediction_bundle,
                    report=report,
                    dataset_path=dataset_path,
                    output_dir=model_dir,
                )
                entry = build_summary_entry(
                    model_id=model_id,
                    prediction_bundle=prediction_bundle,
                    report=report,
                    output_dir=model_dir,
                )
                print(
                    "[compare] "
                    f"model={model_id} accuracy={entry['metrics']['accuracy']:.4f} "
                    f"macro_f1={entry['metrics']['macro_f1']:.4f} "
                    f"false_recall={entry['metrics']['false_recall']:.4f}",
                    file=sys.stderr,
                )
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                model_dir.mkdir(parents=True, exist_ok=True)
                (model_dir / "error.txt").write_text(error, encoding="utf-8")
                entry = build_summary_entry(
                    model_id=model_id,
                    prediction_bundle=None,
                    report=None,
                    output_dir=model_dir,
                    error=error,
                )
                print(f"[compare] model={model_id} failed: {error}", file=sys.stderr)
            entries.append(entry)
    finally:
        if previous_model is None:
            os.environ.pop("OPENAI_PRIMARY_MODEL", None)
        else:
            os.environ["OPENAI_PRIMARY_MODEL"] = previous_model

    summary = {
        "meta": {
            "dataset_path": str(dataset_path),
            "use_gemini": use_gemini,
            "case_filter": case_filter,
            "models": models,
        },
        "results": sort_summary_entries(entries),
    }
    (output_root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_root / "summary.md").write_text(
        build_summary_markdown(
            dataset_path=dataset_path,
            use_gemini=use_gemini,
            case_filter=case_filter,
            entries=entries,
        ),
        encoding="utf-8",
    )
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OpenAI primary model を複数候補で比較します。")
    parser.add_argument("dataset_json", nargs="?", type=Path, default=None, help="入力データセット JSON")
    parser.add_argument("--dataset", choices=["default", "real"], default=None, help="組み込みデータセットを使う")
    parser.add_argument("--case-id", default=None, help="単一ケース ID のみ実行")
    gemini_group = parser.add_mutually_exclusive_group()
    gemini_group.add_argument("--use-gemini", dest="use_gemini", action="store_true", help="Gemini を明示的に有効化")
    gemini_group.add_argument("--no-gemini", dest="use_gemini", action="store_false", help="Gemini を使わずローカル判定のみで実行")
    parser.set_defaults(use_gemini=True)
    parser.add_argument(
        "--models",
        nargs="+",
        default=list(DEFAULT_MODELS),
        help="比較したい OPENAI_PRIMARY_MODEL の候補を空白区切りで指定",
    )
    parser.add_argument("--label", default=None, help="出力フォルダ名に付ける短いラベル")
    return parser.parse_args()


def main() -> int:
    """コマンドライン実行時の入口。"""
    args = parse_args()
    dataset_path = resolve_dataset_path(args.dataset_json, args.dataset)
    output_root = build_comparison_output_dir(args.label)
    try:
        summary = run_model_comparison(
            dataset_path=dataset_path,
            models=list(args.models),
            use_gemini=bool(args.use_gemini),
            case_filter=args.case_id,
            output_root=output_root,
        )
    except GeminiPreflightError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"saved comparison folder: {output_root}")
    print(f"summary json: {output_root / 'summary.json'}")
    print(f"summary md: {output_root / 'summary.md'}")
    completed = [entry for entry in summary["results"] if entry.get("status") == "completed"]
    if completed:
        best = completed[0]
        metrics = best["metrics"]
        print(
            "best model: "
            f"{best['model']} "
            f"(macro_f1={metrics['macro_f1']:.4f}, accuracy={metrics['accuracy']:.4f}, "
            f"false_recall={metrics['false_recall']:.4f})"
        )
    return 0 if len(completed) == len(summary["results"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
