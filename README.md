# Multi-Organisation Daily Food Delivery Coordination

## Scope decision

This version retains separate ambient and chilled vehicle capacities. A request with chilled crates must use a vehicle whose chilled capacity is large enough. It deliberately **does not implement a separate 45-minute chilled-delivery time limit**.

Two experimental protocols are preserved. **V1** (`instances/benchmark/`, `prompts/direct_v1.txt`) treats duplicate requests as alternatives and uses witness-first generation. **V2** (`instances/input_first/`, `prompts/direct_v2.txt`) samples inputs before any scheduling and allows both organisations to fulfil their own request. V2 maximizes distinct households, then their priority weight, then fulfilled requests, before minimizing mean travel and vehicles. Each household and its priority count once. Unfulfilled requests remain unserved rather than covered by another organisation. Both protocols keep the separate chilled-delivery time limit disabled.

This bundle uses `mean_travel_minutes`, defined as the sum of all depot and inter-stop travel legs divided by the number of used vehicles. Loading, waiting and service time are excluded. If no vehicle is used, the mean is defined as 0. The worked schedule has 101 total travel minutes across 3 used vehicles, so its reported mean is 33.67 minutes.

Because a per-vehicle mean can decrease when work is split across more vehicles, it may favour a larger fleet. The current objective follows the proposal: minimize mean travel first, then minimize vehicles used only when the means are tied.

## Comparison being supported

Both experimental methods receive the same natural-language instance.

- **Direct method:** the frontier model produces a final schedule JSON without an optimization solver.
- **Tool-assisted method:** the frontier model translates the description into a formal specification; the other workstream passes that specification to a CP-SAT solver.

## Directory guide

```text
models.py                        Shared Python instance and schedule models
requirements.txt                 Python dependencies (Pydantic)
schemas/                         Separate V1 and V2 input/output contracts
generator/                       Legacy witness-first and new input-first generators; NL renderer
instances/
  example/                       Worked proposal input: JSON and natural language
  benchmark/
    easy/                        Five easy cases
    medium/                      Five medium cases
    hard/                        Five legacy hard cases
  input_first/                   V2 guide and generation manifest
    hard/                        Ten input-first JSON/NL pairs; no witnesses
prompts/direct_v1.txt             Legacy alternatives policy
prompts/direct_v2.txt             Independent-request policy and request-count objective
scripts/
  run_codex_model.py              Codex trials with explicit --protocol v1 or v2
  check_schedule_shape.py         JSON parsing helpers and structural checks
examples/                        Worked candidate schedule used by the tests
analysis/
  error_taxonomy.csv             Shared validation violation codes
  analyse_direct_results.py      Summarizes independently validated direct runs
outputs/codex/                   Preserved V1 experiment artifacts
  summary.csv                    Per-instance results and preliminary checks
  summary.json                   Aggregate counts for the completed batch
  <instance>_<timestamp>_<id>/    One directory per trial; contains:
    parsed.json                  Parsed candidate schedule
    raw_response.txt             Original model response
    prompt.txt                   Exact text supplied to Codex
    request.json, run.json        Invocation settings and completion metadata
    events.jsonl, stderr.txt      Codex event stream and diagnostics
    preliminary_validation.json  Preliminary checks from the completed batch
outputs/codex_v2/                V2 trials, created when the new experiment is run
tests/                           Input-first, protocol and legacy-compatibility tests
.venv/                           Local Python environment (ignored by Git)
```

## Setup

Use Python 3.11 or later.

```bash
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
```

On Windows PowerShell, activate with:

```powershell
.venv\Scripts\Activate.ps1
```

## Generate input-first hard cases (V2)

Ten new cases are in `instances/input_first/hard/`, each with JSON and natural-language text. The generator samples resource limits, geography, requests and windows without constructing schedules, invoking a solver, filtering by feasibility or saving witnesses. All cases are structurally valid hard candidates with serviceability still unclassified.

See [the V2 case guide and next steps](instances/input_first/README.md) for the ten challenge profiles, the changes from the attached proposal, and the solver/validator handoff. This protocol intentionally overrides the proposal's alternative-request rule and witness-first construction; the 45-minute chilled limit remains disabled by user instruction.

Generate another set in a fresh directory:

```bash
python -m generator.generate_input_first --output-dir instances/input_first_extra --seed 424242 --per-profile 3
```

Use `--protocol v2` for these inputs. V1 remains the default for the earlier benchmark. The runner rejects mismatched protocol/input combinations.

## Generate legacy benchmark instances (V1)

The generator builds a feasible witness schedule first and derives time windows and capacities around it. The witness is saved separately and must never be shown to the direct model.

The included benchmark contains five instances at each level. Instances numbered `005` are deliberately partially serviceable: one non-duplicate household has ambient demand greater than every vehicle capacity in its organisation. This tests whether a method can maximize service and explain a necessary omission instead of inventing an invalid delivery.

| Level | Organisations | Households | Duplicates | Main difficulty controls |
|---|---:|---:|---:|---|
| Easy | 2 | 6–8 | 1 | 40-minute window margin, 60-minute shift slack, four-crate route-capacity slack |
| Medium | 2–3 | 12–15 | 2–3 | 20-minute window margin, 25-minute shift slack, two-crate route-capacity slack, one refrigerated route and one trained assistant per organisation |
| Hard | 3 | 20–25 | 4–5 | 8-minute window margin, 5-minute shift slack, exact route capacities, one refrigerated route and one trained assistant per organisation, refrigerated alternative duplicates |

```bash
python -m generator.generate_instances \
  --output-dir instances/benchmark \
  --per-level 5 \
  --seed 4248 \
  --impossible-every 5
```

This creates paired files such as:

```text
instances/benchmark/easy/easy_001.json
instances/benchmark/easy/easy_001.txt
instances/benchmark/easy/easy_001.witness.json
```

The JSON is the source of truth. The text file is the equivalent natural-language model input. The witness demonstrates one valid schedule (including justified omissions in partially serviceable cases); it is not guaranteed optimal.

## Render an existing instance

```bash
python -m generator.render_natural_language \
  instances/example/final_proposal_example.json \
  --output instances/example/final_proposal_example.txt
```

## Run with Codex (no API key)

For the new input-first cases, use the V2 prompt and schema explicitly:

```bash
python scripts/run_codex_model.py --instances-dir instances/input_first/hard --protocol v2 --model gpt-6.1-sol --output-dir outputs/codex_v2
```

Add `--dry-run` to inspect requests without model calls. Complete the V2 solver/validator checks described in the case guide before interpreting model results. The examples below remain available for the legacy V1 benchmark.

Use `scripts/run_codex_model.py` to run the direct method through Codex CLI with your ChatGPT sign-in. Codex availability and usage limits depend on your ChatGPT access.

On Windows, the runner checks PATH and then automatically finds the Codex executable bundled with the VS Code or VS Code Insiders extension. You can run the Python commands below even when Git Bash cannot find a bare `codex` command. It uses your existing ChatGPT sign-in.

For a standalone CLI installed on PATH, check it and sign in if needed:

```bash
codex --version
codex login
codex login status
```

In Git Bash on Windows, activate the existing environment with `source .venv/Scripts/activate`. From the project root, generate a schedule for one instance:

```bash
python scripts/run_codex_model.py --instance-text instances/benchmark/easy/easy_001.txt --model gpt-6.1-sol --output-dir outputs/codex
```

Generate one candidate for every benchmark instance:

```bash
python scripts/run_codex_model.py --instances-dir instances/benchmark --model gpt-6.1-sol --output-dir outputs/codex
```

Use a Codex model available to your sign-in. The example model matches the model configured when this workflow was added. Reasoning effort defaults to `medium`; pin another supported value with `--reasoning-effort`. Each instance has a 600-second limit, adjustable with `--timeout`. Add `--dry-run` to save prompts without invoking Codex. To choose a specific executable, supply its full path with `--codex "C:/path/to/codex.exe"`. An invalid explicit override produces an error instead of selecting a different installation.

Every trial starts a new ephemeral session in an empty temporary working directory. It sends only the natural-language instance, the direct prompt, output schema and an instruction to avoid tools. User configuration, inherited project guidance, memories, shell execution, web search, apps and other tool features are disabled for these trials. The runner uses your existing ChatGPT sign-in.

Each output directory contains `prompt.txt`, `request.json`, `events.jsonl`, `stderr.txt`, `raw_response.txt`, `run.json`, and `parsed.json` when parsing succeeds. The runner records CLI version, model, reasoning effort, usage and process failures. A completed trial with no observed tool events has `direct_protocol_valid: true`. Any observed tool use disqualifies it as a direct trial. Parsing and schema checks do not establish scheduling feasibility or optimality.

Use the same model and reasoning settings in the eventual tool-assisted method. Describe these results as a Codex-based direct baseline in the report, since Codex adds its own agent instructions around the project prompt.

## Check an output's shape

This checks only JSON structure, not scheduling feasibility. Add `--protocol v2` for a V2 candidate:

```bash
python scripts/check_schedule_shape.py examples/direct_candidate_example.json
```

## Summarize results

The saved `outputs/codex/summary.csv` and `summary.json` describe the completed batch and its preliminary checks. The analysis command below produces final results after an independent validator adds `validation.json` to each run directory. Preliminary checks do not establish travel optimality.

```bash
python analysis/analyse_direct_results.py \
  --runs outputs/codex \
  --output analysis/direct_results.csv
```

## Fair experimental protocol

- Use the same model version for the direct and tool-assisted methods.
- Give both methods the same natural-language instances.
- Use the same supported sampling and reasoning settings for both methods and record all decoding settings. Omit temperature for models that do not support it.
- Run the same number of repetitions for each method and difficulty level.
- Keep all raw outputs, including parse failures.
- Do not expose structured JSON or witness schedules to the direct model.
- Report parse rate, feasible-schedule rate, households served, priority score, mean-travel gap and violation categories.

