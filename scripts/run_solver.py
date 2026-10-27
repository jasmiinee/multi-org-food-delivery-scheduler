"""Run the CP-SAT solver on the worked example and all benchmark instances.

From the project root, run:
    .venv-solver/bin/python scripts/run_solver_model.py

Choose another output directory to keep results from separate model versions:
    .venv-solver/bin/python scripts/run_solver_model.py --output-dir outputs/cpsat_v2
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INSTANCE_DIRS = (
    PROJECT_ROOT / "instances" / "example",
    PROJECT_ROOT / "instances" / "benchmark" / "easy",
    PROJECT_ROOT / "instances" / "benchmark" / "medium",
    PROJECT_ROOT / "instances" / "benchmark" / "hard",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/solver"),
        help="Directory for per-instance JSON results and error logs",
    )
    parser.add_argument("--time-limit", type=float, default=60.0)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    output_dir = args.output_dir
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    instances = sorted(
        path
        for directory in INSTANCE_DIRS
        for path in directory.glob("*.json")
        if not path.name.endswith(".witness.json")
    )
    if not instances:
        print("No instance JSON files found.", file=sys.stderr)
        return 1

    failures = 0
    for instance_path in instances:
        name = instance_path.stem
        result_path = output_dir / f"{name}.json"
        error_path = output_dir / f"{name}.stderr.log"
        command = [
            sys.executable,
            "-m",
            "solver.csp_solver",
            str(instance_path.relative_to(PROJECT_ROOT)),
            "--time-limit",
            str(args.time_limit),
            "--workers",
            str(args.workers),
        ]

        print(f"Solving {instance_path.relative_to(PROJECT_ROOT)} ...", flush=True)
        with result_path.open("w", encoding="utf-8") as stdout, error_path.open(
            "w", encoding="utf-8"
        ) as stderr:
            completed = subprocess.run(
                command,
                cwd=PROJECT_ROOT,
                stdout=stdout,
                stderr=stderr,
                text=True,
                check=False,
            )

        if completed.returncode == 0:
            error_path.unlink(missing_ok=True)
            print(f"  Saved {result_path.relative_to(PROJECT_ROOT)}")
        else:
            failures += 1
            print(
                f"  Failed (exit {completed.returncode}); see "
                f"{error_path.relative_to(PROJECT_ROOT)}"
            )
            if result_path.stat().st_size == 0:
                result_path.unlink()

    print(f"Finished: {len(instances) - failures}/{len(instances)} succeeded.")
    print(f"Results folder: {output_dir}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
