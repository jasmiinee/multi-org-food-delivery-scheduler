"""Run direct scheduling trials with the Codex CLI and a ChatGPT sign-in."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.check_schedule_shape import extract_json, schema_errors


DISABLED_FEATURES = (
    "shell_tool", "apps", "plugins", "memories", "multi_agent", "skill_search",
    "hooks", "browser_use", "computer_use", "image_generation", "view_image",
)
NON_TOOL_ITEMS = {"agent_message", "reasoning", "plan", "error"}


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def discover_instances(directory: Path) -> list[Path]:
    levels = {"easy": 0, "medium": 1, "hard": 2}
    return sorted(directory.rglob("*.txt"), key=lambda p: (levels.get(p.parent.name, 3), str(p)))


def run_trial(
    instance_path: Path, output_dir: Path, *, codex_path: str, model: str,
    reasoning_effort: str = "medium", timeout: float = 600, dry_run: bool = False,
    cli_version: str | None = None,
) -> dict[str, Any]:
    prompt = (ROOT / "prompts/direct_v1.txt").read_text(encoding="utf-8")
    schema = json.loads((ROOT / "schemas/schedule.schema.json").read_text(encoding="utf-8"))
    instance_text = instance_path.read_text(encoding="utf-8")
    effective_prompt = (
        prompt + "\n\nUse only the supplied problem text. Do not call tools or read files."
        + "\n\nREQUIRED JSON SCHEMA:\n" + json.dumps(schema, separators=(",", ":"))
        + "\n\nINSTANCE:\n" + instance_text
    )
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{instance_path.stem}_{timestamp}_{uuid.uuid4().hex[:8]}"
    run_dir = (output_dir / run_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    raw_path = run_dir / "raw_response.txt"
    command = [
        codex_path, "exec", "--ignore-user-config", "--ephemeral",
        "--skip-git-repo-check", "--sandbox", "read-only", "--json", "--color", "never",
        "--model", model, "-c", f'model_reasoning_effort="{reasoning_effort}"',
        "-c", 'forced_login_method="chatgpt"', "-c", 'web_search="disabled"',
        "-c", "project_doc_max_bytes=0", "-c", "memories.use_memories=false",
        "-c", "memories.generate_memories=false",
    ]
    for feature in DISABLED_FEATURES:
        command.extend(["--disable", feature])
    command.extend(["--output-last-message", str(raw_path), "-"])
    record: dict[str, Any] = {
        "run_id": run_id, "instance": instance_path.stem, "model": model,
        "provider": "codex_cli", "authentication": "chatgpt",
        "temperature": None, "reasoning_effort": reasoning_effort,
        "timestamp_utc": timestamp, "cli_version": cli_version,
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "effective_prompt_sha256": hashlib.sha256(effective_prompt.encode()).hexdigest(),
        "command": command, "working_directory": "empty temporary directory",
        "dry_run": dry_run, "schema_enforced_by_cli": False,
        "parsed_successfully": False, "schema_valid": False,
        "direct_protocol_valid": False,
    }
    (run_dir / "prompt.txt").write_text(effective_prompt, encoding="utf-8")
    write_json(run_dir / "request.json", record)
    if dry_run:
        write_json(run_dir / "run.json", record)
        print(f"{instance_path.stem}: dry-run request saved to {run_dir}", flush=True)
        return record

    started = time.monotonic()
    execution_error = None
    return_code = None
    with tempfile.TemporaryDirectory(prefix="cs3263_codex_input_") as isolated:
        with (run_dir / "events.jsonl").open("w", encoding="utf-8") as events_file:
            with (run_dir / "stderr.txt").open("w", encoding="utf-8") as stderr_file:
                try:
                    result = subprocess.run(
                        command, input=effective_prompt, text=True, encoding="utf-8",
                        cwd=isolated, stdout=events_file, stderr=stderr_file,
                        timeout=timeout, check=False,
                    )
                    return_code = result.returncode
                except (OSError, subprocess.TimeoutExpired) as error:
                    execution_error = str(error)

    tool_items = []
    diagnostic_items = []
    event_errors = []
    turn_completed = False
    usage = None
    thread_id = None
    for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            event_errors.append("Invalid JSON event")
            continue
        if event.get("type") == "thread.started":
            thread_id = event.get("thread_id")
        elif event.get("type") == "turn.completed":
            turn_completed = True
            usage = event.get("usage")
        elif event.get("type") in {"error", "turn.failed"}:
            event_errors.append(event)
        if event.get("type", "").startswith("item."):
            item = event.get("item", {})
            if item.get("type") == "error":
                diagnostic_items.append(item)
            if item.get("type") not in NON_TOOL_ITEMS:
                tool_items.append(item)

    record.update(
        cli_exit_code=return_code, execution_error=execution_error,
        elapsed_seconds=round(time.monotonic() - started, 2), thread_id=thread_id,
        usage=usage, turn_completed=turn_completed, tool_use_detected=bool(tool_items),
        tool_items=tool_items, diagnostic_items=diagnostic_items, event_errors=event_errors,
        direct_protocol_valid=(
            return_code == 0 and turn_completed and not tool_items and not event_errors
        ),
    )
    if raw_path.exists():
        raw = raw_path.read_text(encoding="utf-8")
        try:
            parsed, fence_removed = extract_json(raw)
            write_json(run_dir / "parsed.json", parsed)
            errors = schema_errors(parsed)
            record.update(
                parsed_successfully=True, schema_valid=not errors,
                markdown_fence_removed=fence_removed, schema_errors=errors,
            )
        except (json.JSONDecodeError, ValueError) as error:
            record["parse_error"] = str(error)
    else:
        record["parse_error"] = "Codex did not produce a final response file"
    write_json(run_dir / "run.json", record)
    print(
        f"{instance_path.stem}: parsed={record['parsed_successfully']}, "
        f"schema_valid={record['schema_valid']}, "
        f"direct_protocol_valid={record['direct_protocol_valid']}; {run_dir}",
        flush=True,
    )
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--instance-text", type=Path)
    source.add_argument("--instances-dir", type=Path)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/codex")
    parser.add_argument("--model", required=True, help="Codex model ID available to your sign-in")
    parser.add_argument("--reasoning-effort", default="medium", choices=("low", "medium", "high", "xhigh", "max"))
    parser.add_argument("--codex", default="codex", help="Codex executable name or full path")
    parser.add_argument("--timeout", type=float, default=600, help="Maximum seconds per instance")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    instances = [args.instance_text] if args.instance_text else discover_instances(args.instances_dir)
    if not instances or any(not p.is_file() for p in instances):
        parser.error("No readable instance text files found")
    codex_path = shutil.which(args.codex)
    if not codex_path and not args.dry_run:
        parser.error("Codex CLI was not found. Install it or supply --codex PATH, then run codex login.")
    version = None
    if not args.dry_run:
        try:
            version_result = subprocess.run(
                [codex_path, "--version"], capture_output=True, text=True,
                encoding="utf-8", timeout=15, check=True,
            )
            version = version_result.stdout.strip()
        except (OSError, subprocess.SubprocessError) as error:
            parser.error(f"Cannot start Codex: {error}")
    failed = False
    for instance in instances:
        print(f"Starting {instance.stem}...", flush=True)
        record = run_trial(
            instance, args.output_dir, codex_path=codex_path or args.codex,
            model=args.model, reasoning_effort=args.reasoning_effort,
            timeout=args.timeout, dry_run=args.dry_run, cli_version=version,
        )
        if not args.dry_run:
            failed |= not (record["schema_valid"] and record["direct_protocol_valid"])
            if record["cli_exit_code"] != 0:
                print("Stopped after a CLI failure; inspect the saved stderr.txt and events.jsonl.", flush=True)
                break
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
