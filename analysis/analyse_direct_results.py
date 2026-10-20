"""Summarize direct-model runs after independent validation."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


FIELDS = [
    "run_id",
    "instance",
    "model",
    "temperature",
    "parsed_successfully",
    "schema_valid",
    "feasible",
    "optimal",
    "households_served",
    "priority_weight",
    "mean_travel_minutes",
    "violation_codes",
]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rows: list[dict[str, Any]] = []
    violations: Counter[str] = Counter()
    for run_file in sorted(args.runs.rglob("run.json")):
        run = load_json(run_file)
        validation_file = run_file.parent / "validation.json"
        validation = load_json(validation_file) if validation_file.exists() else {}
        codes = [item["code"] for item in validation.get("violations", []) if "code" in item]
        violations.update(codes)
        objective = validation.get("recomputed_objective", {})
        rows.append(
            {
                "run_id": run.get("run_id", run_file.parent.name),
                "instance": run.get("instance", ""),
                "model": run.get("model", ""),
                "temperature": run.get("temperature", ""),
                "parsed_successfully": run.get("parsed_successfully", False),
                "schema_valid": run.get("schema_valid", False),
                "feasible": validation.get("valid", "NOT_VALIDATED"),
                "optimal": validation.get("optimal", "NOT_VALIDATED"),
                "households_served": objective.get("households_served", ""),
                "priority_weight": objective.get("priority_weight", ""),
                "mean_travel_minutes": objective.get("mean_travel_minutes", ""),
                "violation_codes": ";".join(codes),
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    parsed = sum(str(row["parsed_successfully"]).lower() == "true" for row in rows)
    feasible = sum(str(row["feasible"]).lower() == "true" for row in rows)
    print(f"Runs: {len(rows)}")
    print(f"Parsed successfully: {parsed}/{len(rows)}")
    print(f"Feasible after validation: {feasible}/{len(rows)}")
    if violations:
        print("Violation counts:")
        for code, count in violations.most_common():
            print(f"  {code}: {count}")
    print(f"CSV written to {args.output}")


if __name__ == "__main__":
    main()

