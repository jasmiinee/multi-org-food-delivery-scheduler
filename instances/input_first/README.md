# Input-first candidates (protocol v2)

The hard/ folder contains fourteen JSON/text pairs named hard_001 through hard_014. The first four are user-authored cases moved from instances/v2.1/hard/. The remaining ten are generated input-first cases. There are no witness files.

The ten generated hard cases have three organisations and nine vehicles. The four user-authored cases have 12 vehicles and 28-30 households. The feasibility of complete household coverage, complete request coverage and the optimal objective values has not been solved. "Hard" describes the intended challenge profile; solver-based calibration is still required.

## Easy and medium cases

Five fresh easy cases and five fresh medium cases are saved in easy/ and medium/, with one JSON input and one equivalent natural-language text file per case. These use the same v2 independent-request constraints and objective order as hard/. They are sampled directly from input profiles and are not conversions of the v1 witness-based cases.

| Level | IDs | Households | Requests | Organisations / vehicles | Intended difficulty controls |
|---|---|---:|---:|---|---|
| Easy | input_easy_001 through input_easy_005 | 6-8 | 7-10 | 2 / 4 | Compact geography, 90-120 minute windows, long shifts, larger capacities and more trained drivers |
| Medium | input_medium_001 through input_medium_005 | 12-15 | 14-18 | 2-3 / 4-6 | 20-60 minute windows, early/day shifts, smaller capacities and competing chilled/training requirements |

The new cases use base seed 20261029. The actual seed is base seed + 100000 for easy or + 200000 for medium, then + 1000 per profile index. Repetitions add their zero-based repetition index. Per-level provenance and counts are recorded in generation_manifest_easy.json and generation_manifest_medium.json. generation_manifest.json records the ten generated hard cases in cases, the four user-authored cases in manual_cases, and a complete old-to-new ID mapping.

Recreate the easy and medium batches in a fresh directory:

    python -m generator.generate_input_first --output-dir instances/input_first_copy --difficulty easy medium --seed 20261029

The generator defaults to hard when --difficulty is omitted, preserving the original hard generation command. Multiple levels can be selected with --difficulty easy medium hard. Five profiles exist at each of easy and medium, while hard has ten. --per-profile controls repetitions for each selected profile.

Easy and medium are intended difficulty levels, not solver-certified labels. Complete household/request coverage and optimal schedules remain unchecked; no witness files or schedules are generated. Use --protocol v2 for every level. A batch run over instances/input_first/ now includes all twenty-four text instances.

## Hard cases

| Instance | Previous location / ID | Households | Requests | Duplicate households |
|---|---|---:|---:|---:|
| hard_001 | v2.1/hard/hard_1, input_hard_101 | 28 | 44 | 15 |
| hard_002 | v2.1/hard/hard_2, input_hard_102 | 28 | 44 | 15 |
| hard_003 | v2.1/hard/hard_3, input_hard_103 | 28 | 44 | 16 |
| hard_004 | v2.1/hard/hard_4, input_hard_104 | 30 | 44 | 14 |

The original generated input_hard_001 through input_hard_010 became hard_005 through hard_014, respectively. JSON metadata IDs and text headers match filenames. Historical experiment outputs retain their original identifiers.

The generator now names hard outputs hard_005 onward by default, reserving 001-004 for the user-authored cases. --start-number can select another range. Generation in a fresh directory recreates only the ten synthetic hard cases, not the four user-authored ones.

| Instance | Households | Requests | Duplicate households | Intended pressure |
|---|---:|---:|---:|---|
| hard_005 | 22 | 27 | 5 | Mixed resource and time-window constraints |
| hard_006 | 24 | 29 | 5 | Windows of only 10-20 minutes |
| hard_007 | 23 | 28 | 5 | Untrained drivers competing for one trained assistant per organisation |
| hard_008 | 25 | 30 | 5 | Many chilled requests and limited refrigerated capacity |
| hard_009 | 24 | 29 | 5 | Staggered early, day and late shifts |
| hard_010 | 20 | 24 | 4 | Long depot-to-household travel and organisation restrictions |
| hard_011 | 25 | 30 | 5 | Aggregate ambient demand exceeding the fleet's capacity |
| hard_012 | 21 | 25 | 4 | A chilled delivery needing training, but an untrained refrigerated driver has no assistant seat |
| hard_013 | 22 | 27 | 5 | A trained assistant's shift ending before a specialised delivery window |
| hard_014 | 25 | 30 | 5 | Combined capacity, refrigeration, training and tight-window pressure |

Profile labels and this table are for benchmark authors. The text supplied to the model contains the input facts and rules, without these labels or any reference answer.

## Confirmed v2 policy

Every organisation's request is a separate delivery obligation. Two organisations may both deliver to the same household. Each must use its own depot, team, request items and request window. Neither delivery substitutes for the other.

The objective order is:

1. Maximize distinct households served.
2. Maximize their total priority weight, counted once per household.
3. Maximize fulfilled requests, including second deliveries to the same household.
4. Minimize mean travel per used vehicle.
5. Minimize vehicles used, then use vehicle ID as the deterministic tie-breaker.

"Both deliver if feasible" means jointly feasible under this objective order. A request being feasible on its own does not guarantee it can coexist with every other delivery. Serving a new household takes priority over a second delivery to a household already served.

The output adds requests_fulfilled. A household is served if any of its requests is fulfilled, and its priority is counted once. Each request is either fulfilled with a vehicle or unserved with a reason. Do not use covered_by_alternative. An unfulfilled request remains unserved even when another organisation serves its household. A household belongs in unserved_households only when none of its requests is fulfilled.

Service takes ten minutes per fulfilled request. The other organisation's trained volunteer cannot satisfy this delivery's training requirement. No additional household-level constraint prohibits overlapping service by different organisations.

The 45-minute chilled-delivery limit remains disabled, as explicitly requested. Chilled vehicle capacity remains mandatory.

## Relationship to the attached proposal

The reference is CS3263 Project Proposal (3).pdf.

- Page 3, assumption 15, and page 7, C1, define alternatives and prohibit multiple deliveries to one household. V2 intentionally replaces that rule with the confirmed independent-request policy.
- Pages 7-8 list the objectives. V2 adds fulfilled-request count after household count and priority, before travel.
- Page 3, assumption 17, and page 7, C10, require a 45-minute chilled-delivery limit. It stays disabled in this experiment by user instruction.
- Page 9 describes constructing a feasible schedule before deriving inputs. This generator replaces that process with input-first sampling.
- The remaining organisation, depot, vehicle, team, capacity, service-start-window and shift rules are retained.

The PDF has not been edited. Amend these passages in the formulation used for the report, solver and validator before presenting v2 as the agreed problem.

## How the inputs were created

The generator fixes shifts, vehicles, seats, capacities and volunteer qualifications before sampling requests. It samples household locations and creates a complete symmetric travel matrix. Requesting organisations, item quantities and clock-time windows are then sampled without reference to any departure, route or service time. Request IDs are shuffled so they do not reveal route order.

The seat-conflict and training-gap profiles directly specify an input-level constraint interaction. They are not derived by breaking an existing schedule. All sampled cases are retained; the generator never rejects a seed because an instance is inconvenient or infeasible. Structural validation checks the data format, not serviceability.

Regenerate the frozen set in a new directory:

    python -m generator.generate_input_first --output-dir instances/input_first_copy --seed 20261023

Generate thirty more candidates using new draws:

    python -m generator.generate_input_first --output-dir instances/input_first_extra --seed 424242 --per-profile 3

Existing files are protected against overwrite unless --overwrite is explicitly supplied.

## Next steps

1. Freeze the v2 formulation. Use independent requests, the confirmed objective order and no time-based cold-chain limit consistently. Keep the earlier v1 benchmark/results as a separate experiment.
2. Have Member 2 update the exact model. For binary fulfilled-request variables x_r and household variables y_h, enforce y_h >= x_r for every request of household h, and y_h <= sum(x_r for that household). Keep each request assigned to at most one vehicle; remove the old household-level at-most-one constraint. Optimize request count after household count and priority.
3. Solve the frozen inputs after generation. Record the optimal household count, priority weight, fulfilled-request count, travel objective, vehicles used, solver status, elapsed time and bounds. A timeout is unknown or a feasible incumbent with a gap, not proof of infeasibility. Distinguish impossible full household coverage from impossible full request coverage; an empty partial schedule is otherwise feasible.
4. Have Member 3 update the independent validator. Repeated household IDs on different organisations' deliveries are allowed; repeated request IDs are not. Recompute all three coverage metrics, per-request statuses, loads, training, seats, timing and full-trip shift compatibility. Missing a second request must not be treated as alternative coverage.
5. Inspect a dry-run request before making new model calls:

       python scripts/run_codex_model.py --instance-text instances/input_first/hard/hard_005.txt --protocol v2 --model gpt-6.1-sol --output-dir outputs/codex_v2 --dry-run

6. Freeze the prompt/model/settings and run the direct method and tool-assisted method on identical natural-language inputs. Start with two pilot cases, then use the same predetermined number of repetitions, such as three per case. Preserve all attempts and failures. Do not expose JSON input, challenge labels, solver answers or witnesses to the direct model.

       python scripts/run_codex_model.py --instances-dir instances/input_first/hard --protocol v2 --model gpt-6.1-sol --output-dir outputs/codex_v2

7. Score only after independent validation. Report parsing and schema rates, schedule feasibility, unique-household count, priority, fulfilled-request count, gaps to the exact reference, mean travel, vehicles used and violation categories. Calibrate difficulty from solver evidence and constraint interactions, not from size alone or by choosing only cases where the LLM failed.

The runner's protocol switch chooses the matching prompt and schedule contract and rejects mismatched v1/v2 input text. Its shape checks are not a v2 feasibility validator. The real trials and solver labels have intentionally not been produced as part of generating these examples.

## Checks

    python -m unittest discover -s tests -v

The tests cover structural consistency, seed reproducibility, resources staying fixed when demand changes, absence of schedule/witness construction, v2 status semantics and compatibility with the preserved v1 descriptions and outputs.
