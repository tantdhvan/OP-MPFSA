#!/usr/bin/env python3
"""Validate the frozen fair k-IM result CSVs without rerunning experiments."""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path


DEFAULT_RESULTS_DIR = Path(__file__).resolve().parent / "results"
ALGORITHMS = {
    "Fair-Greedy": "offline",
    "Fair-Threshold": "offline",
    "OPFSA": "one-pass-fixed-order",
    "MPFSA": "replayable-fixed-order",
}
BUDGETS = {9, 12, 15, 18, 21, 24, 27, 30}
EXPECTED = {
    "email": {
        "dataset": "Email-Eu-core",
        "n": 1005,
        "m": 25571,
        "topology": "directed",
        "relative_path": Path("run_details.csv"),
    },
    "grqc": {
        "dataset": "ca-GrQc",
        "n": 5242,
        "m": 28980,
        "topology": "undirected-expanded",
        "relative_path": Path("grqc") / "run_details.csv",
    },
}
REQUIRED_FIELDS = {
    "dataset", "n", "m", "topology", "algorithm", "access_model", "B", "k",
    "lower", "upper", "objective", "evaluation_se", "queries", "passes",
    "runtime_seconds", "peak_memory_mb", "support_size", "label_counts",
    "decision_MC", "evaluation_MC", "seed",
}


def add_error(errors: list[str], message: str) -> None:
    errors.append(message)


def finite_float(value: str, field: str, row_number: int, errors: list[str]) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        add_error(errors, f"row {row_number}: {field} is not numeric: {value!r}")
        return math.nan
    if not math.isfinite(parsed):
        add_error(errors, f"row {row_number}: {field} is not finite: {value!r}")
    return parsed


def validate_dataset(results_dir: Path, key: str) -> list[str]:
    spec = EXPECTED[key]
    path = results_dir / spec["relative_path"]
    errors: list[str] = []
    if not path.is_file():
        return [f"{key}: missing {path}"]

    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or [])
        missing = REQUIRED_FIELDS - fields
        if missing:
            add_error(errors, f"{key}: missing columns {sorted(missing)}")
        rows = list(reader)

    if len(rows) != 32:
        add_error(errors, f"{key}: expected 32 rows, found {len(rows)}")
    seen: set[tuple[str, int]] = set()
    for row_number, row in enumerate(rows, 2):
        algorithm = row.get("algorithm", "")
        try:
            budget = int(row.get("B", ""))
        except ValueError:
            budget = -1
            add_error(errors, f"{key} row {row_number}: invalid budget {row.get('B')!r}")

        identity = (algorithm, budget)
        if identity in seen:
            add_error(errors, f"{key} row {row_number}: duplicate {identity}")
        seen.add(identity)
        if row.get("dataset") != spec["dataset"]:
            add_error(errors, f"{key} row {row_number}: wrong dataset")
        if row.get("topology") != spec["topology"]:
            add_error(errors, f"{key} row {row_number}: wrong topology")
        for field, expected in (("n", spec["n"]), ("m", spec["m"]), ("k", 3),
                                ("decision_MC", 100), ("evaluation_MC", 1000),
                                ("seed", 42)):
            try:
                actual = int(row.get(field, ""))
            except ValueError:
                actual = None
            if actual != expected:
                add_error(errors, f"{key} row {row_number}: {field}={actual!r}, expected {expected}")
        if algorithm not in ALGORITHMS:
            add_error(errors, f"{key} row {row_number}: unknown algorithm {algorithm!r}")
        elif row.get("access_model") != ALGORITHMS[algorithm]:
            add_error(errors, f"{key} row {row_number}: wrong access_model for {algorithm}")
        if budget not in BUDGETS:
            add_error(errors, f"{key} row {row_number}: unexpected budget {budget}")
        if row.get("lower") != "3;3;3" or row.get("upper") != "10;10;10":
            add_error(errors, f"{key} row {row_number}: quota metadata mismatch")

        try:
            label_counts = [int(value) for value in row.get("label_counts", "").split(";")]
        except ValueError:
            label_counts = []
            add_error(errors, f"{key} row {row_number}: invalid label_counts")
        if len(label_counts) != 3 or any(value < 3 or value > 10 for value in label_counts):
            add_error(errors, f"{key} row {row_number}: label_counts outside [3,10]")
        try:
            support_size = int(row.get("support_size", ""))
        except ValueError:
            support_size = -1
        if support_size != budget:
            add_error(errors, f"{key} row {row_number}: support_size={support_size}, B={budget}")

        queries = finite_float(row.get("queries", ""), "queries", row_number, errors)
        if math.isfinite(queries) and (queries < 0 or not queries.is_integer()):
            add_error(errors, f"{key} row {row_number}: queries must be a nonnegative integer")
        expected_passes = {"Fair-Greedy": str(budget), "Fair-Threshold": "NA", "OPFSA": "1"}.get(algorithm)
        passes = row.get("passes")
        if expected_passes is not None and passes != expected_passes:
            add_error(errors, f"{key} row {row_number}: passes={passes!r}, expected {expected_passes!r}")
        if algorithm == "MPFSA":
            try:
                if int(passes) < 1:
                    raise ValueError
            except (TypeError, ValueError):
                add_error(errors, f"{key} row {row_number}: MPFSA passes must be a positive integer")

        objective = finite_float(row.get("objective", ""), "objective", row_number, errors)
        if math.isfinite(objective) and objective < 0:
            add_error(errors, f"{key} row {row_number}: objective must be nonnegative")
        for field in ("evaluation_se", "runtime_seconds", "peak_memory_mb"):
            value = finite_float(row.get(field, ""), field, row_number, errors)
            if math.isfinite(value) and value < 0:
                add_error(errors, f"{key} row {row_number}: {field} must be nonnegative")

    expected_keys = {(algorithm, budget) for algorithm in ALGORITHMS for budget in BUDGETS}
    if seen != expected_keys:
        add_error(errors, f"{key}: algorithm-budget grid does not match the expected 4 x 8 grid")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--dataset", choices=["email", "grqc", "all"], default="all")
    args = parser.parse_args()
    keys = ["email", "grqc"] if args.dataset == "all" else [args.dataset]
    errors = [error for key in keys for error in validate_dataset(args.results_dir, key)]
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    for key in keys:
        print(f"PASS: {key} result file has a valid 4 x 8 algorithm-budget grid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
