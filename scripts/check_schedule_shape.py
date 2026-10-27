"""Check that a candidate schedule is valid JSON and matches the shared schema."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from models import IndependentSchedule, Schedule


DEFAULT_SCHEMA = ROOT / "schemas" / "schedule.schema.json"


def extract_json(text: str) -> tuple[dict[str, Any], bool]:
    stripped = text.strip()
    fence_removed = False
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        stripped = fenced.group(1).strip()
        fence_removed = True
    value = json.loads(stripped)
    if not isinstance(value, dict):
        raise ValueError("The model response must be one JSON object")
    return value, fence_removed


def schema_errors(value: dict[str, Any], *, protocol: str = "v1") -> list[str]:
    try:
        model = {"v1": Schedule, "v2": IndependentSchedule}[protocol]
        model.model_validate(value)
        return []
    except ValidationError as error:
        return [item["msg"] for item in error.errors()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("schedule", type=Path)
    parser.add_argument("--schema", type=Path)
    parser.add_argument("--protocol", choices=("v1", "v2"), default="v1")
    args = parser.parse_args()

    schedule = json.loads(args.schedule.read_text(encoding="utf-8"))
    schema_path = args.schema or (ROOT / "schemas" / ("schedule_v2.schema.json" if args.protocol == "v2" else "schedule.schema.json"))
    json.loads(schema_path.read_text(encoding="utf-8"))
    try:
        model = IndependentSchedule if args.protocol == "v2" else Schedule
        model.model_validate(schedule)
    except ValidationError as error:
        print(error)
        raise SystemExit(1)
    print("Schedule JSON matches the shared schema.")


if __name__ == "__main__":
    main()

