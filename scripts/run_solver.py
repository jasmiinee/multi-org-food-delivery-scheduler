"""Run the CP-SAT solver on v1 benchmarks and input-first v2 instances.

From the project root, run:
    .venv-solver/bin/python scripts/run_solver.py

V1 benchmark results go to outputs/solver/; v2 input-first results go to
outputs/solver_v2/. Override either directory with the corresponding option.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
V1_INSTANCE_ROOT = PROJECT_ROOT / "instances" / "benchmark"
V2_INSTANCE_ROOT = PROJECT_ROOT / "instances" / "input_first"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/solver"),
        help="Output directory for v1 benchmark results (default: outputs/solver)",
    )
    parser.add_argument(
        "--v2-output-dir",
        type=Path,
        default=Path("outputs/solver_v2"),
        help="Output directory for v2 input-first results (default: outputs/solver_v2)",
    )
    parser.add_argument("--time-limit", type=float, default=60.0)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    output_dirs = {"v1": args.output_dir, "v2": args.v2_output_dir}
    for protocol, path in output_dirs.items():
        if not path.is_absolute():
            output_dirs[protocol] = PROJECT_ROOT / path

    instances = [
        (path, "v1")
        for path in V1_INSTANCE_ROOT.rglob("*.json")
        if not path.name.endswith(".witness.json")
    ] + [
        (path, "v2")
        for path in V2_INSTANCE_ROOT.rglob("*.json")
        if not path.name.endswith(".witness.json")
        and path.name != "generation_manifest.json"
    ]
    instances.sort(key=lambda item: (item[1], str(item[0])))
    if not instances:
        print("No instance JSON files found.", file=sys.stderr)
        return 1

    failures = 0
    for instance_path, protocol in instances:
        output_dir = output_dirs[protocol]
        output_dir.mkdir(parents=True, exist_ok=True)
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
    print(f"V1 benchmark results: {output_dirs['v1']}")
    print(f"V2 input-first results: {output_dirs['v2']}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
