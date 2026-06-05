import argparse
import json
from pathlib import Path
from typing import Any

VERSION_LABEL = "Ver3"


def load_report(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        report = json.load(handle)

    required_top_level = {"meta", "multiclass", "binary_fake_positive"}
    missing = sorted(required_top_level - set(report))
    if missing:
        raise ValueError(f"評価 JSON に必要なキーが不足しています: {', '.join(missing)}")
    return report


def resolve_output_dir(input_json: Path, output_dir: Path | None) -> Path:
    if output_dir:
        return output_dir
    return input_json.parent / f"{input_json.stem}_plots"


def ensure_plotting_modules() -> tuple[Any, Any]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
        import seaborn as sns
    except ImportError as exc:
        raise SystemExit(
            "matplotlib と seaborn が必要です。"
            " `pip install -r requirements.txt` を実行してから再実行してください。"
        ) from exc
    return plt, sns, font_manager


def pick_preferred_font(font_manager: Any) -> str:
    available_fonts = {font.name for font in font_manager.fontManager.ttflist}
    preferred_fonts = [
        "Yu Gothic",
        "Meiryo",
        "MS Gothic",
        "IPAexGothic",
    ]
    for font_name in preferred_fonts:
        if font_name in available_fonts:
            return font_name
    return "sans-serif"


def configure_plot_style(plt: Any, sns: Any, font_manager: Any) -> str:
    sns.set_theme(style="whitegrid")
    preferred_font = pick_preferred_font(font_manager)
    plt.rcParams["font.family"] = preferred_font
    plt.rcParams["font.sans-serif"] = [preferred_font]
    plt.rcParams["font.monospace"] = [preferred_font]
    plt.rcParams["axes.unicode_minus"] = False
    return preferred_font


def annotate_bars(ax: Any, values: list[float]) -> None:
    for index, value in enumerate(values):
        ax.text(index, value + 0.015, f"{value:.3f}", ha="center", va="bottom", fontsize=9)


def place_confusion_matrix_labels_on_top(ax: Any) -> None:
    ax.xaxis.tick_top()
    ax.xaxis.set_label_position("top")
    ax.tick_params(axis="x", top=True, labeltop=True, bottom=False, labelbottom=False)


def save_confusion_matrix(report: dict[str, Any], output_path: Path, plt: Any, sns: Any) -> None:
    multi = report["multiclass"]
    labels = multi["labels"]
    matrix = multi["confusion_matrix"]

    fig, ax = plt.subplots(figsize=(8, 6))
    sns.heatmap(
        matrix,
        annot=True,
        fmt="d",
        cmap="Blues",
        xticklabels=labels,
        yticklabels=labels,
        cbar=True,
        ax=ax,
    )
    ax.set_title(f"{VERSION_LABEL} Confusion Matrix")
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Truth")
    place_confusion_matrix_labels_on_top(ax)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def save_per_class_metrics(report: dict[str, Any], output_path: Path, plt: Any) -> None:
    multi = report["multiclass"]
    labels = multi["labels"]
    per_class = multi["per_class"]

    precisions = [per_class[label]["precision"] for label in labels]
    recalls = [per_class[label]["recall"] for label in labels]
    f1s = [per_class[label]["f1"] for label in labels]

    x_positions = list(range(len(labels)))
    width = 0.24

    fig, ax = plt.subplots(figsize=(11, 6))
    ax.bar([x - width for x in x_positions], precisions, width=width, label="Precision", color="#4C78A8")
    ax.bar(x_positions, recalls, width=width, label="Recall", color="#F58518")
    ax.bar([x + width for x in x_positions], f1s, width=width, label="F1", color="#54A24B")

    ax.set_xticks(x_positions)
    ax.set_xticklabels(labels, rotation=15)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Score")
    ax.set_title(f"{VERSION_LABEL} Per-class Metrics")
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def save_summary_metrics(report: dict[str, Any], output_path: Path, plt: Any) -> None:
    multi = report["multiclass"]
    binary = report["binary_fake_positive"]

    summary_labels = [
        "Accuracy",
        "Macro F1",
        "Weighted F1",
        "Binary Precision",
        "Binary Recall",
        "Binary F1",
    ]
    summary_values = [
        multi["accuracy"],
        multi["macro_avg"]["f1"],
        multi["weighted_avg"]["f1"],
        binary["precision"],
        binary["recall"],
        binary["f1"],
    ]
    colors = ["#4C78A8", "#72B7B2", "#54A24B", "#F58518", "#E45756", "#B279A2"]

    fig, ax = plt.subplots(figsize=(9, 6))
    ax.bar(summary_labels, summary_values, color=colors)
    ax.set_ylim(0, 1.05)
    ax.set_title(f"{VERSION_LABEL} Summary Metrics")
    ax.tick_params(axis="x", rotation=20)
    annotate_bars(ax, summary_values)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def save_evaluation_overview(report: dict[str, Any], output_path: Path, plt: Any) -> None:
    meta = report["meta"]
    multi = report["multiclass"]
    binary = report["binary_fake_positive"]

    overview_lines = [
        f"{VERSION_LABEL} Evaluation Overview",
        f"sample_count: {meta['sample_count']}",
        f"skipped_count: {meta['skipped_count']}",
        f"mismatches: {len(report.get('mismatches', []))}",
        f"positive_label: {binary['positive_label']}",
        f"positive_support: {binary['support']}",
        "",
        "Macro Avg",
        f"precision={multi['macro_avg']['precision']:.4f}",
        f"recall={multi['macro_avg']['recall']:.4f}",
        f"f1={multi['macro_avg']['f1']:.4f}",
        "",
        "Weighted Avg",
        f"precision={multi['weighted_avg']['precision']:.4f}",
        f"recall={multi['weighted_avg']['recall']:.4f}",
        f"f1={multi['weighted_avg']['f1']:.4f}",
    ]

    fig, ax = plt.subplots(figsize=(4.5, 5.5))
    ax.axis("off")
    ax.text(
        0.02,
        0.98,
        "\n".join(overview_lines),
        va="top",
        ha="left",
        fontsize=12,
    )
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def save_summary_dashboard(report: dict[str, Any], output_path: Path, plt: Any, sns: Any) -> None:
    meta = report["meta"]
    multi = report["multiclass"]
    binary = report["binary_fake_positive"]
    labels = multi["labels"]
    matrix = multi["confusion_matrix"]

    summary_labels = [
        "Accuracy",
        "Macro F1",
        "Weighted F1",
        "Binary Precision",
        "Binary Recall",
        "Binary F1",
    ]
    summary_values = [
        multi["accuracy"],
        multi["macro_avg"]["f1"],
        multi["weighted_avg"]["f1"],
        binary["precision"],
        binary["recall"],
        binary["f1"],
    ]

    per_class = multi["per_class"]
    precisions = [per_class[label]["precision"] for label in labels]
    recalls = [per_class[label]["recall"] for label in labels]
    f1s = [per_class[label]["f1"] for label in labels]
    x_positions = list(range(len(labels)))
    width = 0.24

    fig, axes = plt.subplots(2, 2, figsize=(16, 10))

    sns.heatmap(
        matrix,
        annot=True,
        fmt="d",
        cmap="Blues",
        xticklabels=labels,
        yticklabels=labels,
        cbar=True,
        ax=axes[0, 0],
    )
    axes[0, 0].set_title(f"{VERSION_LABEL} Confusion Matrix")
    axes[0, 0].set_xlabel("Predicted")
    axes[0, 0].set_ylabel("Truth")
    place_confusion_matrix_labels_on_top(axes[0, 0])

    axes[0, 1].bar(summary_labels, summary_values, color=["#4C78A8", "#72B7B2", "#54A24B", "#F58518", "#E45756", "#B279A2"])
    axes[0, 1].set_ylim(0, 1.05)
    axes[0, 1].set_title(f"{VERSION_LABEL} Summary Metrics")
    axes[0, 1].tick_params(axis="x", rotation=20)
    annotate_bars(axes[0, 1], summary_values)

    axes[1, 0].bar([x - width for x in x_positions], precisions, width=width, label="Precision", color="#4C78A8")
    axes[1, 0].bar(x_positions, recalls, width=width, label="Recall", color="#F58518")
    axes[1, 0].bar([x + width for x in x_positions], f1s, width=width, label="F1", color="#54A24B")
    axes[1, 0].set_xticks(x_positions)
    axes[1, 0].set_xticklabels(labels, rotation=15)
    axes[1, 0].set_ylim(0, 1.05)
    axes[1, 0].set_ylabel("Score")
    axes[1, 0].set_title(f"{VERSION_LABEL} Per-class Metrics")
    axes[1, 0].legend()

    axes[1, 1].axis("off")
    overview_lines = [
        f"{VERSION_LABEL} Evaluation Overview",
        f"sample_count: {meta['sample_count']}",
        f"skipped_count: {meta['skipped_count']}",
        f"mismatches: {len(report.get('mismatches', []))}",
        f"positive_label: {binary['positive_label']}",
        f"positive_support: {binary['support']}",
        "",
        "Macro Avg",
        f"precision={multi['macro_avg']['precision']:.4f}",
        f"recall={multi['macro_avg']['recall']:.4f}",
        f"f1={multi['macro_avg']['f1']:.4f}",
        "",
        "Weighted Avg",
        f"precision={multi['weighted_avg']['precision']:.4f}",
        f"recall={multi['weighted_avg']['recall']:.4f}",
        f"f1={multi['weighted_avg']['f1']:.4f}",
    ]
    axes[1, 1].text(
        0.02,
        0.98,
        "\n".join(overview_lines),
        va="top",
        ha="left",
        fontsize=11,
    )

    fig.suptitle(f"{VERSION_LABEL} Fake News Checker Evaluation Dashboard", fontsize=16)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="評価 JSON を画像で可視化します。")
    parser.add_argument("input_json", type=Path, help="app.evaluation の出力 JSON")
    parser.add_argument("--output-dir", type=Path, default=None, help="画像の保存先ディレクトリ")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = load_report(args.input_json)
    output_dir = resolve_output_dir(args.input_json, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    plt, sns, font_manager = ensure_plotting_modules()
    preferred_font = configure_plot_style(plt, sns, font_manager)

    dashboard_path = output_dir / "evaluation_dashboard.png"
    confusion_path = output_dir / "confusion_matrix.png"
    per_class_path = output_dir / "per_class_metrics.png"
    summary_metrics_path = output_dir / "summary_metrics.png"
    overview_path = output_dir / "evaluation_overview.png"

    save_summary_dashboard(report, dashboard_path, plt, sns)
    save_confusion_matrix(report, confusion_path, plt, sns)
    save_per_class_metrics(report, per_class_path, plt)
    save_summary_metrics(report, summary_metrics_path, plt)
    save_evaluation_overview(report, overview_path, plt)

    print(f"font: {preferred_font}")
    print(f"saved: {dashboard_path}")
    print(f"saved: {confusion_path}")
    print(f"saved: {per_class_path}")
    print(f"saved: {summary_metrics_path}")
    print(f"saved: {overview_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
