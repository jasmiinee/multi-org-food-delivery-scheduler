# Multi-Organisation Daily Food Delivery Coordination

This project compares two ways of solving a daily delivery scheduling problem from the same natural-language requirements:

- **Direct LLM:** GPT-6 produces a complete schedule from the description.
- **LLM-to-solver:** an LLM converts the description into structured instance JSON, which the local Python system validates and passes to the OR-Tools CP-SAT solver.

Both approaches use the same delivery requirements, travel times, constraints and objective order. Their schedules must be independently checked before comparing solution quality.

## Workflow

```text
Natural-language scheduling instance
                 |
        +--------+--------+
        |                 |
   Direct LLM       LLM interpretation
        |                 |
 Candidate schedule   Instance JSON
        |                 |
        |           Input validation
        |                 |
        |           CP-SAT scheduling
        |                 |
        +--------+--------+
                 |
     Independent schedule validation
                 |
      Feasibility and objective comparison
```

The model interactions take place outside the local solver, using the ChatGPT website. The Python solver reads JSON; it does not interpret the natural-language text itself.

## Scheduling rules

The formulation uses a closed-world assumption: the supplied facts and stated constraints define the scheduling problem. Use the explicit travel-time table and resource data rather than adding assumptions about geography or operations.

- Every request may be fulfilled at most once, using its own organisation's vehicle, volunteers and depot.
- Requests from different organisations for the same household are independent deliveries. Both should be fulfilled when jointly feasible under the objective order. Each retains its own items, delivery window and service duration.
- A household counts as served when at least one of its requests is fulfilled. Its household count and priority weight are counted once.
- Every request must appear in `request_status`, either `fulfilled` with an assigned vehicle or `unserved` with a reason. Another organisation's delivery does not change an unfulfilled request's status.
- Each used vehicle makes one trip starting and ending at its home depot. Its designated driver uses that vehicle; each assistant may join at most one vehicle from their organisation.
- Seats include the driver. The complete trip, from loading through return, must fit every assigned team member's shift.
- Ambient and chilled crate capacities are checked separately over all requests assigned to a vehicle.
- Each delivery to a household requiring trained assistance must have a trained driver or assistant on that delivery's vehicle.
- Delivery windows constrain service-start times. Early arrival and waiting are permitted. Travel, loading and service durations must be included in the timetable.
- The supplied instances use five minutes of loading and ten minutes of service per fulfilled request. The structured parameters record these durations.

## Objective order

Schedules are compared lexicographically, preserving each earlier objective before improving the next:

1. Maximise distinct households served.
2. Maximise their total priority weight, counted once per household.
3. Maximise fulfilled requests, including additional deliveries to households already served.
4. Minimise mean travel minutes per used vehicle.
5. Minimise vehicles used, followed by a vehicle-ID tie-break.

Mean travel is total depot-to-stop, inter-stop and return-to-depot travel divided by the number of used vehicles. Loading, waiting and service are excluded. The mean is zero when no vehicle is used.

Because the denominator is the number of used vehicles, minimising mean travel can favour splitting deliveries across more vehicles. Fleet size is minimised only after the earlier objectives are tied.

## Dataset

The dataset contains **24 natural-language scheduling instances**: five easy, five medium and fourteen hard. The instances were constructed through manual scenario design and Python scripting, varying household demand, vehicle availability, volunteer qualifications and delivery windows. All input requirements were specified before solving, without deriving them from a pre-existing feasible schedule.

Each description follows a consistent structure covering organisations, shifts, households, volunteers, vehicles, requests and travel times. A corresponding JSON file records the same facts for input validation and solver execution. Difficulty varies through instance size, geographical spread, window tightness and resource scarcity; the labels describe intended challenge levels rather than proving computational difficulty.

Travel times are integer-minute values, obtained from rounded-up Euclidean distances between synthetic coordinates or directly specified values. They are recorded explicitly in complete symmetric tables and used consistently by both approaches and the independent validator.

| Level | Cases | Input filename stems |
|---|---:|---|
| Easy | 5 | `input_easy_001` to `input_easy_005` |
| Medium | 5 | `input_medium_001` to `input_medium_005` |
| Hard | 14 | `hard_001` to `hard_014` |

For every case, the `.txt` file is the natural-language input and the matching `.json` file is its structured representation. Give the direct LLM the text and output requirements, without supplying the instance JSON or solver schedules.

## Directory guide

The following paths are relevant to the current experiment:

```text
models.py                         Pydantic models for inputs and schedules
requirements.txt                  Pydantic and OR-Tools dependencies
schemas/                          Machine-readable instance and schedule contracts
instances/input_first/
  easy/                           Five paired JSON/text instances
  medium/                         Five paired JSON/text instances
  hard/                           Fourteen paired JSON/text instances
prompts/prompt.txt                Direct instructions, output schema and an embedded instance
solver/csp_solver.py              CP-SAT model, staged optimisation and schedule extraction
scripts/check_schedule_shape.py   Schedule parsing and structural checking helpers
generator/                       Text rendering utilities and instance-construction scripts
analysis/
  analyse_direct_results.py       Aggregation of runs with metadata and validator results
  error_taxonomy.csv              Constraint-violation categories
outputs/
  gpt6/
  solver/                          Saved direct-model responses, grouped by case
```

The active input and output contracts are [the instance schema](schemas/instance_v2.schema.json) and [the schedule schema](schemas/schedule_v2.schema.json). These links identify the exact files used for independent-request scheduling.

Direct responses use folders such as `outputs/gpt6/easy_1/easy_1.json`, `outputs/gpt6/medium_1/medium_1.json` and `outputs/gpt6/hard_1/hard_1.json`. Match each response to its input by difficulty and case number.

## Setup

Use Python 3.11 with the pinned OR-Tools dependency. Run the following from the project root:

```text
python -m venv .venv
```

Activate the environment in Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Or in Git Bash on Windows:

```bash
source .venv/Scripts/activate
```

Then install the dependencies:

```text
python -m pip install -r requirements.txt
```

## Approach 1: Direct LLM scheduling

1. Open a new ChatGPT conversation for the case.
2. Use the scheduling instructions and required output schema from `prompts/prompt.txt`. Replace everything after its `INSTANCE:` heading with the complete text of the chosen instance; the file already contains one instance.
3. Ask the model to construct the schedule directly, following the objective order and returning one JSON object. The direct-solving instructions prohibit external optimisers and tools.
4. Save the response in the matching `outputs/gpt6/` case folder. Preserve unsuccessful responses as part of the experiment rather than silently replacing them.
5. Check the JSON structure, then submit the schedule and its matching input to the independent validator.

The response must have these top-level fields:

| Field | Contents |
|---|---|
| `status` | `candidate` for a direct model response pending validation |
| `objective` | Household count, priority weight, fulfilled-request count, mean travel and vehicles used |
| `vehicles` | Assigned teams, loading and departure times, ordered stops, service-start times and depot return |
| `request_status` | Exactly one entry for every request, with its assignment or omission reason |
| `unserved_households` | Households for which no request was fulfilled, with reasons |

Schedule times use `HH:MM`. Mean travel is reported to two decimal places. A model's reported objectives must be recomputed from its actual schedule.

## Approach 2: LLM-to-solver translation

Provide the natural-language description and the instance schema to the LLM. Ask it to preserve identifiers, organisations, resources, item quantities, qualifications, shifts, windows and travel times, and return instance JSON rather than a schedule. Clock times are represented as minutes from midnight, such as `09:00` becoming `540`. Expand a symmetric travel table into both directions and include zero diagonal entries.

The translation may use an LLM-generated parsing script. Check the extracted representation against the source text: structural validity alone does not establish that every fact was translated correctly. Resolve missing or contradictory facts before scheduling rather than inventing values.

Run the solver on one structured instance:

```text
python -m solver.csp_solver instances/input_first/easy/input_easy_001.json --time-limit 60 --workers 8
```

For a hard case:

```text
python -m solver.csp_solver instances/input_first/hard/hard_001.json --time-limit 60 --workers 8
```

The solver validates the input model, creates assignment, route, timing and resource constraints, and optimises the objectives in stages. It prints the resulting schedule JSON to standard output. The time limit applies to each optimisation call; a complete case can involve several calls.

To save a result using Git Bash, choose a new output filename:

```bash
mkdir -p outputs/solver_runs
python -m solver.csp_solver instances/input_first/easy/input_easy_001.json --time-limit 60 --workers 8 > outputs/solver_runs/easy_1.json
```

Shell redirection replaces an existing file of the same name. A `feasible` result is an incumbent without a complete optimality proof; an `optimal` result indicates that the solver established the required objective stages. A timeout or failure to find a schedule does not establish infeasibility.

## Validation and evaluation

Structural checks and scheduling checks serve different purposes. For a saved direct response, this command checks the current Pydantic schedule contract:

```text
python -c "from pathlib import Path; from models import IndependentSchedule; IndependentSchedule.model_validate_json(Path('outputs/gpt6/easy_1/easy_1.json').read_text(encoding='utf-8')); print('Schedule structure is valid.')"
```

The JSON must contain the response object itself, without surrounding Markdown fences. This check does not establish scheduling feasibility.

The independent validator must check entity references, organisation ownership, repeated requests, capacities, seating, volunteer assignments, trained assistance, timing, shifts and request-status consistency. It must also recompute distinct households served, their priority weight, fulfilled requests, mean travel and fleet size. Apply the same checks to both approaches.

Compare objective values using the stated hierarchy only after feasibility has been established. Lower travel in an invalid schedule is not evidence of a better solution.

`analysis/analyse_direct_results.py` expects per-run `run.json` metadata and optional `validation.json` results. It does not directly discover the bare response files in `outputs/gpt6/`. Any results aggregation must match the saved response layout and retain the independent validator's outcomes.

For reproducible experiments, record the model used, run date, exact prompt, raw response, attempt count, solver settings and validation results. Keep the same input facts and evaluation rules across both approaches.
