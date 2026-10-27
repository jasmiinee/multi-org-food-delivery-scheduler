# Input-first hard candidates (protocol v2)

These ten synthetic cases were generated from resources, geography and requests without constructing a route or schedule. Each case has a structured JSON file and an equivalent natural-language text file in hard/. There are no witness files.

All cases have three organisations and nine vehicles. The feasibility of complete household coverage, complete request coverage and the optimal objective values has not been solved. "Hard" describes the intended challenge profile; solver-based calibration is still required.

| Instance | Households | Requests | Duplicate households | Intended pressure |
|---|---:|---:|---:|---|
| input_hard_001 | 22 | 27 | 5 | Mixed resource and time-window constraints |
| input_hard_002 | 24 | 29 | 5 | Windows of only 10-20 minutes |
| input_hard_003 | 23 | 28 | 5 | Untrained drivers competing for one trained assistant per organisation |
| input_hard_004 | 25 | 30 | 5 | Many chilled requests and limited refrigerated capacity |
| input_hard_005 | 24 | 29 | 5 | Staggered early, day and late shifts |
| input_hard_006 | 20 | 24 | 4 | Long depot-to-household travel and organisation restrictions |
| input_hard_007 | 25 | 30 | 5 | Aggregate ambient demand exceeding the fleet's capacity |
| input_hard_008 | 21 | 25 | 4 | A chilled delivery needing training, but an untrained refrigerated driver has no assistant seat |
| input_hard_009 | 22 | 27 | 5 | A trained assistant's shift ending before a specialised delivery window |
| input_hard_010 | 25 | 30 | 5 | Combined capacity, refrigeration, training and tight-window pressure |

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

       python scripts/run_codex_model.py --instance-text instances/input_first/hard/input_hard_001.txt --protocol v2 --model gpt-6.1-sol --output-dir outputs/codex_v2 --dry-run

6. Freeze the prompt/model/settings and run the direct method and tool-assisted method on identical natural-language inputs. Start with two pilot cases, then use the same predetermined number of repetitions, such as three per case. Preserve all attempts and failures. Do not expose JSON input, challenge labels, solver answers or witnesses to the direct model.

       python scripts/run_codex_model.py --instances-dir instances/input_first/hard --protocol v2 --model gpt-6.1-sol --output-dir outputs/codex_v2

7. Score only after independent validation. Report parsing and schema rates, schedule feasibility, unique-household count, priority, fulfilled-request count, gaps to the exact reference, mean travel, vehicles used and violation categories. Calibrate difficulty from solver evidence and constraint interactions, not from size alone or by choosing only cases where the LLM failed.

The runner's protocol switch chooses the matching prompt and schedule contract and rejects mismatched v1/v2 input text. Its shape checks are not a v2 feasibility validator. The real trials and solver labels have intentionally not been produced as part of generating these examples.

## Checks

    python -m unittest discover -s tests -v

The tests cover structural consistency, seed reproducibility, resources staying fixed when demand changes, absence of schedule/witness construction, v2 status semantics and compatibility with the preserved v1 descriptions and outputs.
