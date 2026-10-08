#!/usr/bin/env python3
"""Create manuscript-ready k-IM charts for the fair k-submodular draft.

This script is intentionally self-contained. It reads one normalized result
CSV for a selected dataset and does not import code or data from another draft.

The pipeline preserves the source draft's layout: a shared legend, separate
objective/query/memory figures, a compact three-panel figure, a PDF bundle, a
summary CSV, and a provenance manifest. Each source contains one run per
algorithm and budget, so no run-to-run confidence bands are drawn.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter, LogLocator, MaxNLocator


SCRIPT_DIR = Path(__file__).resolve().parent
ARTIFACT_ROOT = SCRIPT_DIR.parent
DEFAULT_INPUT_DIR = ARTIFACT_ROOT / "results"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR
DEFAULT_BUDGETS = (9, 12, 15, 18, 21, 24, 27, 30)

# Colors and open markers remain stable across both datasets and all metrics.
ALGORITHMS = (
    ("Fair-Greedy", "Fair-Greedy", "#1f77b4", "o"),
    ("Fair-Threshold", "Fair-Threshold", "#d62728", "D"),
    ("OPFSA", "OPFSA", "#2ca02c", "s"),
    ("MPFSA", "MPFSA", "#9467bd", "^"),
)
DATASET_FILES = {
    "email": ("Email-Eu-core", "run_details.csv"),
    "grqc": ("ca-GrQc", "grqc/run_details.csv"),
}
METRICS = (
    ("objective", "objective", r"Objective $f(\mathbf{x})$", "linear"),
    ("queries", "queries", "Number of queries", "log"),
    ("memory", "peak_memory_mb", "Peak memory (MB)", "log"),
)
REQUIRED_FIELDS = {
    "dataset", "algorithm", "access_model", "B", "objective", "evaluation_se",
    "queries", "peak_memory_mb",
}


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"{path}: expected at least one data row")
    missing = REQUIRED_FIELDS - set(rows[0])
    if missing:
        raise ValueError(f"{path}: missing columns {sorted(missing)}")
    return rows


def finite_number(row: dict[str, str], column: str, path: Path) -> float:
    try:
        value = float(row[column])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"{path}: invalid {column} value {row.get(column)!r}") from error
    if not math.isfinite(value):
        raise ValueError(f"{path}: non-finite {column} value {value}")
    return value


def load_results(input_dir: Path, dataset_key: str, budgets: tuple[int, ...]):
    if dataset_key not in DATASET_FILES:
        raise ValueError(f"unknown dataset key: {dataset_key}")
    dataset_name, relative_input = DATASET_FILES[dataset_key]
    path = input_dir / relative_input
    if not path.is_file():
        raise FileNotFoundError(path)

    records: dict[str, dict[int, dict[str, float]]] = {
        algorithm: {} for algorithm, *_ in ALGORITHMS
    }
    source_files: dict[str, dict[int, str]] = {
        algorithm: {} for algorithm, *_ in ALGORITHMS
    }
    rows = read_rows(path)
    for row in rows:
        if row["dataset"] != dataset_name:
            raise ValueError(
                f"{path}: expected dataset {dataset_name!r}, found {row['dataset']!r}"
            )
        algorithm = row["algorithm"]
        if algorithm not in records:
            raise ValueError(f"{path}: unexpected algorithm {algorithm!r}")
        budget = int(row["B"])
        if budget in records[algorithm]:
            raise ValueError(f"duplicate {algorithm} row for B={budget}")
        record = {
            column: finite_number(row, column, path)
            for _, column, _, _ in METRICS
        }
        record["evaluation_se"] = finite_number(row, "evaluation_se", path)
        records[algorithm][budget] = record
        source_files[algorithm][budget] = str(path)

    for algorithm, *_ in ALGORITHMS:
        missing = sorted(set(budgets) - set(records[algorithm]))
        if missing:
            raise ValueError(f"{algorithm}: missing requested budgets {missing}")

    return dataset_name, records, source_files


def compact_number(value: float, _position: int | None = None) -> str:
    for scale, suffix in ((1.0e9, "B"), (1.0e6, "M"), (1.0e3, "K")):
        if abs(value) >= scale:
            return f"{value / scale:.1f}".rstrip("0").rstrip(".") + suffix
    if abs(value) >= 100.0:
        return f"{value:.0f}"
    if abs(value) >= 1.0:
        return f"{value:.1f}".rstrip("0").rstrip(".")
    if value == 0.0:
        return "0"
    if abs(value) >= 0.01:
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return f"{value:.1e}"


def finish_axis(axis, ylabel: str, budgets: tuple[int, ...], scale: str) -> None:
    axis.set_xlabel("Budget $B$", fontsize=28.0, labelpad=8)
    axis.set_ylabel(ylabel, fontsize=28.0, labelpad=9)
    axis.set_xticks(budgets)
    axis.set_xticklabels([str(B) for B in budgets])
    axis.tick_params(axis="both", labelsize=22.0, pad=5)
    if scale == "log":
        axis.set_yscale("log")
        axis.yaxis.set_major_locator(LogLocator(base=10, numticks=6))
    else:
        axis.yaxis.set_major_locator(MaxNLocator(nbins=6))
    axis.yaxis.set_major_formatter(FuncFormatter(compact_number))
    axis.grid(True, which="major", alpha=0.28)
    axis.margins(x=0.05, y=0.12)
    if scale != "log":
        axis.set_ylim(bottom=0)


def draw_metric(axis, records, budgets: tuple[int, ...], metric_column: str,
                ylabel: str, scale: str) -> None:
    for algorithm, label, color, marker in ALGORITHMS:
        values = [records[algorithm][B][metric_column] for B in budgets]
        axis.plot(
            budgets,
            values,
            color=color,
            marker=marker,
            markerfacecolor="none",
            markeredgewidth=1.5,
            markersize=24.0,
            linewidth=1.8,
            label=label,
        )
    finish_axis(axis, ylabel, budgets, scale)


def legend_figure() -> plt.Figure:
    # The legend is exported with a tight bounding box so it is narrower than
    # the fixed-size metric pages without clipping the large labels.
    figure = plt.figure(figsize=(11.5, 1.2))
    handles = [
        Line2D(
            [0], [0], color=color, marker=marker, markerfacecolor="none",
            markeredgewidth=1.5, markersize=27.0, linewidth=1.8, label=label,
        )
        for _, label, color, marker in ALGORITHMS
    ]
    figure.legend(
        handles=handles,
        loc="center",
        ncol=len(handles),
        frameon=False,
        fontsize=23.0,
        handlelength=1.6,
        columnspacing=1.0,
    )
    return figure


def metric_figure(records, budgets: tuple[int, ...], metric, compact: bool) -> plt.Figure:
    _name, metric_column, ylabel, scale = metric
    if compact:
        figure, axes = plt.subplots(1, 3, figsize=(24.0, 7.0), squeeze=False)
        for axis, selected_metric in zip(axes[0], METRICS):
            draw_metric(axis, records, budgets, selected_metric[1], selected_metric[2], selected_metric[3])
        handles = [
            Line2D(
                [0], [0], color=color, marker=marker, markerfacecolor="none",
                markeredgewidth=1.5, markersize=24.0, linewidth=1.8, label=label,
            )
            for _, label, color, marker in ALGORITHMS
        ]
        figure.legend(handles=handles, loc="upper center", ncol=4,
                      frameon=False, fontsize=23.0, handlelength=2.0,
                      columnspacing=1.8)
        figure.subplots_adjust(left=0.16, right=0.995, bottom=0.22,
                               top=0.69, wspace=0.55)
        return figure

    figure, axis = plt.subplots(1, 1, figsize=(11.5, 7.2))
    draw_metric(axis, records, budgets, metric_column, ylabel, scale)
    figure.subplots_adjust(left=0.18, right=0.98, bottom=0.19, top=0.95)
    return figure


def write_summary(path: Path, dataset_name: str, records, budgets: tuple[int, ...]) -> None:
    fields = [
        "dataset", "metric", "algorithm", "B", "value", "evaluation_se",
        "uncertainty",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for metric_name, metric_column, _, _ in METRICS:
            for algorithm, *_ in ALGORITHMS:
                for budget in budgets:
                    value = records[algorithm][budget][metric_column]
                    writer.writerow({
                        "dataset": dataset_name,
                        "metric": metric_name,
                        "algorithm": algorithm,
                        "B": budget,
                        "value": f"{value:.9f}",
                        "evaluation_se": (
                            f"{records[algorithm][budget]['evaluation_se']:.9f}"
                            if metric_name == "objective" else ""
                        ),
                        "uncertainty": (
                            "evaluation_bank_se"
                            if metric_name == "objective" else "single_run"
                        ),
                    })


def relative_path(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dataset", choices=sorted(DATASET_FILES), default="email")
    parser.add_argument("--budgets", nargs="+", type=int,
                        default=list(DEFAULT_BUDGETS))
    parser.add_argument("--prefix", default="email",
                        help="Prefix for generated chart artifacts")
    args = parser.parse_args()

    budgets = tuple(dict.fromkeys(args.budgets))
    if not budgets or any(B <= 0 for B in budgets):
        raise SystemExit("--budgets must contain positive integers")
    args.outdir.mkdir(parents=True, exist_ok=True)
    dataset_name, records, source_files = load_results(
        args.input_dir, args.dataset, budgets
    )

    legend_path = args.outdir / f"{args.prefix}_legend.png"
    legend = legend_figure()
    legend.savefig(legend_path, dpi=300, bbox_inches="tight", transparent=True)
    plt.close(legend)

    summary_path = args.outdir / f"{args.prefix}_plot_summary.csv"
    write_summary(summary_path, dataset_name, records, budgets)

    pdf_path = args.outdir / f"{args.prefix}.pdf"
    with PdfPages(pdf_path) as pdf:
        legend = legend_figure()
        pdf.savefig(legend, bbox_inches="tight", transparent=True)
        plt.close(legend)
        for metric in METRICS:
            figure = metric_figure(records, budgets, metric, compact=False)
            pdf.savefig(figure, transparent=True)
            figure.savefig(
                args.outdir / f"{args.prefix}_{metric[0]}.png",
                dpi=300,
                transparent=True,
            )
            plt.close(figure)

    panel = metric_figure(records, budgets, METRICS[0], compact=True)
    panel_path = args.outdir / f"{args.prefix}_panel.png"
    panel.savefig(panel_path, dpi=300, transparent=True)
    plt.close(panel)

    manifest = {
        "pipeline": "standalone fair k-IM chart pipeline",
        "dataset_key": args.dataset,
        "dataset": dataset_name,
        "input_dir": relative_path(args.input_dir, ARTIFACT_ROOT),
        "budgets": list(budgets),
        "algorithms": [algorithm for algorithm, *_ in ALGORITHMS],
        "metrics": [name for name, _, _, _ in METRICS],
        "excluded_metric": "runtime_seconds",
        "uncertainty": (
            "one deterministic run per algorithm and B; objective evaluation-SE "
            "is retained in summary but no run-to-run bands are drawn"
        ),
        "query_definition": "value-oracle calls; not multiplied by decision MC",
        "memory_definition": "algorithm-phase Python-traced peak; not full process RSS",
        "access_models": {
            algorithm: "offline" if algorithm in {"Fair-Greedy", "Fair-Threshold"}
            else "one-pass-fixed-order" if algorithm == "OPFSA"
            else "replayable-fixed-order"
            for algorithm, *_ in ALGORITHMS
        },
        "layout": "shared legend plus objective, queries, and memory panels",
        "source_files": {
            algorithm: {
                str(K): relative_path(Path(path), ARTIFACT_ROOT)
                for K, path in by_K.items()
                if K in budgets
            }
            for algorithm, by_K in source_files.items()
        },
    }
    manifest_path = args.outdir / f"{args.prefix}_plot_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Created {pdf_path}")
    print(f"Created {panel_path}")
    print(f"Wrote {summary_path}")


if __name__ == "__main__":
    main()
