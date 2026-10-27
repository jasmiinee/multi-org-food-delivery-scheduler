"""CP-SAT solver for the project's JSON food-delivery instances.

Usage:
    python -m solver.csp_solver instances/benchmark/easy/easy_001.json

Install dependencies with: pip install -r requirements.txt
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from ortools.sat.python import cp_model

from models import IndependentSchedule, InputFirstInstance, Instance, Schedule


def _clock(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _run(model: cp_model.CpModel, expression: Any, *, maximize: bool,
         seconds: float, workers: int, log: bool = False):
    """Optimize one objective and return its incumbent value and proof status."""
    model.ClearObjective()
    (model.Maximize if maximize else model.Minimize)(expression)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = seconds
    solver.parameters.num_search_workers = workers
    solver.parameters.log_search_progress = log
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return solver, status, None
    return solver, status, int(round(solver.ObjectiveValue()))


def _build(instance: Instance | InputFirstInstance):
    is_v2 = isinstance(instance, InputFirstInstance)
    p = instance.parameters
    orgs = {x.id: x for x in instance.organisations}
    households = {x.id: x for x in instance.households}
    requests = {x.id: x for x in instance.requests}
    vehicles = {x.id: x for x in instance.vehicles}
    volunteers = {x.id: x for x in instance.volunteers}
    shifts = {
        (org.id, shift.id): shift
        for org in instance.organisations
        for shift in org.shifts
    }

    def travel(a: str, b: str) -> int:
        try:
            return instance.travel_times[a][b]
        except KeyError as exc:
            raise ValueError(f"Missing travel time from {a!r} to {b!r}") from exc

    # Fail early on inconsistent references rather than silently building a
    # different scheduling problem.
    for v in vehicles.values():
        if v.organisation not in orgs or v.driver_id not in volunteers:
            raise ValueError(f"Vehicle {v.id} has an unknown organisation or driver")
        d = volunteers[v.driver_id]
        if d.role != "driver" or d.vehicle_id != v.id or d.organisation != v.organisation:
            raise ValueError(f"Vehicle {v.id} does not match its assigned driver")
        if (d.organisation, d.shift_id) not in shifts:
            raise ValueError(f"Driver {d.id} refers to an unknown shift")
    for r in requests.values():
        if r.organisation not in orgs or r.household not in households:
            raise ValueError(f"Request {r.id} has an unknown organisation or household")
        if r.window_start > r.window_end:
            raise ValueError(f"Request {r.id} has a reversed service window")
    for a in volunteers.values():
        if a.role == "assistant" and (a.organisation, a.shift_id) not in shifts:
            raise ValueError(f"Assistant {a.id} refers to an unknown shift")

    model = cp_model.CpModel()
    assign: dict[tuple[str, str], cp_model.IntVar] = {}
    fulfilled = {r: model.NewBoolVar(f"fulfilled_{r}") for r in requests}
    for r, rd in requests.items():
        eligible = [v for v, vd in vehicles.items() if vd.organisation == rd.organisation]
        for v in eligible:
            assign[r, v] = model.NewBoolVar(f"assign_{r}_{v}")
        model.Add(sum(assign[r, v] for v in eligible) == fulfilled[r])

    used = {v: model.NewBoolVar(f"used_{v}") for v in vehicles}
    assistants = [a.id for a in volunteers.values() if a.role == "assistant"]
    ride = {
        (a, v): model.NewBoolVar(f"ride_{a}_{v}")
        for a in assistants for v, vd in vehicles.items()
        if volunteers[a].organisation == vd.organisation
    }

    served = {h: model.NewBoolVar(f"served_{h}") for h in households}
    for h in households:
        alternatives = [fulfilled[r.id] for r in requests.values() if r.household == h]
        if is_v2:
            # V2 counts a household once even when multiple organisations
            # fulfill separate requests for that household.
            for request_fulfilled in alternatives:
                model.Add(request_fulfilled <= served[h])
            model.Add(served[h] <= sum(alternatives))
        else:
            # V1 treats duplicate requests as alternatives: at most one wins.
            model.Add(sum(alternatives) == served[h])

    service_start = {
        r: model.NewIntVar(rd.window_start, rd.window_end, f"start_{r}")
        for r, rd in requests.items()
    }
    departure = {v: model.NewIntVar(0, 1439, f"depart_{v}") for v in vehicles}
    return_time = {v: model.NewIntVar(0, 2879, f"return_{v}") for v in vehicles}
    travel_terms = []
    service = p.service_minutes
    loading = p.loading_minutes

    for v, vd in vehicles.items():
        own_requests = [r for r in requests if (r, v) in assign]
        model.Add(sum(assign[r, v] for r in own_requests) >= 1).OnlyEnforceIf(used[v])
        model.Add(sum(assign[r, v] for r in own_requests) == 0).OnlyEnforceIf(used[v].Not())
        for r in own_requests:
            model.AddImplication(assign[r, v], used[v])

        # A circuit gives each used vehicle one depot-rooted route. Self arcs
        # exclude requests not assigned to this vehicle; the depot loop means
        # that an unused vehicle has no route.
        arcs = [(0, 0, used[v].Not())]
        node = {r: i + 1 for i, r in enumerate(own_requests)}
        depot = vd.home_depot
        for r in own_requests:
            i = node[r]
            arcs.append((i, i, assign[r, v].Not()))
            first = model.NewBoolVar(f"first_{v}_{r}")
            arcs.append((0, i, first))
            t = travel(depot, requests[r].household)
            model.Add(service_start[r] >= departure[v] + t).OnlyEnforceIf(first)
            travel_terms.append(t * first)

            last = model.NewBoolVar(f"last_{v}_{r}")
            arcs.append((i, 0, last))
            t = travel(requests[r].household, depot)
            model.Add(return_time[v] >= service_start[r] + service + t).OnlyEnforceIf(last)
            travel_terms.append(t * last)

            for r2 in own_requests:
                if r == r2:
                    continue
                nxt = model.NewBoolVar(f"next_{v}_{r}_{r2}")
                arcs.append((i, node[r2], nxt))
                t = travel(requests[r].household, requests[r2].household)
                model.Add(service_start[r2] >= service_start[r] + service + t).OnlyEnforceIf(nxt)
                travel_terms.append(t * nxt)
        model.AddCircuit(arcs)

        model.Add(sum(requests[r].ambient_crates * assign[r, v] for r in own_requests)
                  <= vd.ambient_capacity)
        model.Add(sum(requests[r].chilled_crates * assign[r, v] for r in own_requests)
                  <= vd.chilled_capacity)

        driver = volunteers[vd.driver_id]
        driver_shift = shifts[driver.organisation, driver.shift_id]
        model.Add(departure[v] - loading >= driver_shift.start).OnlyEnforceIf(used[v])
        model.Add(return_time[v] <= driver_shift.end).OnlyEnforceIf(used[v])
        # Schedule times serialize as HH:MM (00:00 through 23:59).
        model.Add(return_time[v] <= 1439).OnlyEnforceIf(used[v])

        riders = [ride[a, v] for a in assistants if (a, v) in ride]
        model.Add(1 + sum(riders) <= vd.seats)
        for a in assistants:
            if (a, v) not in ride:
                continue
            model.AddImplication(ride[a, v], used[v])
            assistant = volunteers[a]
            shift = shifts[assistant.organisation, assistant.shift_id]
            model.Add(departure[v] - loading >= shift.start).OnlyEnforceIf(ride[a, v])
            model.Add(return_time[v] <= shift.end).OnlyEnforceIf(ride[a, v])

        if not driver.trained:
            trained_riders = [ride[a, v] for a in assistants
                              if (a, v) in ride and volunteers[a].trained]
            for r in own_requests:
                if households[requests[r].household].needs_trained_volunteer:
                    model.Add(sum(trained_riders) >= 1).OnlyEnforceIf(assign[r, v])

    for a in assistants:
        vars_for_assistant = [ride[a, v] for v in vehicles if (a, v) in ride]
        model.Add(sum(vars_for_assistant) <= 1)

    # The input contract has a list of duplicate groups; the served equality
    # above also enforces at-most-one request for every household.
    known_duplicate_requests = set()
    for group in instance.duplicate_households:
        group_requests = group.request_ids if is_v2 else group.competing_requests
        for r in group_requests:
            if r not in requests or requests[r].household != group.household:
                raise ValueError(f"Invalid duplicate group for request {r}")
            known_duplicate_requests.add(r)

    served_count = sum(served.values())
    priority = sum(households[h].priority * served[h] for h in households)
    travel_expr = sum(travel_terms)
    max_leg = max((max(row.values(), default=0)
                   for row in instance.travel_times.values()), default=0)
    travel_bound = max(1, len(vehicles) * max_leg * (len(requests) + 1))
    total_travel = model.NewIntVar(0, travel_bound, "total_travel")
    model.Add(total_travel == travel_expr)
    return {
        "model": model, "instance": instance, "orgs": orgs, "households": households,
        "requests": requests, "vehicles": vehicles, "volunteers": volunteers,
        "is_v2": is_v2,
        "shifts": shifts, "assign": assign, "fulfilled": fulfilled, "served": served,
        "used": used, "ride": ride, "service_start": service_start,
        "departure": departure, "return_time": return_time,
        "served_count": served_count, "priority": priority,
        "total_travel": total_travel,
    }


def _extract(ctx, solver, status: str) -> Schedule | IndependentSchedule:
    instance = ctx["instance"]
    requests, vehicles = ctx["requests"], ctx["vehicles"]
    assignments: dict[str, str] = {}
    out_vehicles = []
    total_travel = 0
    for v, vd in vehicles.items():
        if not solver.Value(ctx["used"][v]):
            continue
        selected = [r for r in requests if (r, v) in ctx["assign"]
                    and solver.Value(ctx["assign"][r, v])]
        selected.sort(key=lambda r: solver.Value(ctx["service_start"][r]))
        for r in selected:
            assignments[r] = v
        stops = []
        previous = vd.home_depot
        for r in selected:
            req = requests[r]
            total_travel += instance.travel_times[previous][req.household]
            previous = req.household
            stops.append({"request": r, "household": req.household,
                          "service_start": _clock(solver.Value(ctx["service_start"][r]))})
        return_leg = instance.travel_times[previous][vd.home_depot]
        total_travel += return_leg
        earliest_return = (solver.Value(ctx["service_start"][selected[-1]])
                           + instance.parameters.service_minutes + return_leg)
        out_vehicles.append({
            "vehicle": v, "driver": vd.driver_id,
            "assistants": [a for a in ctx["volunteers"] if (a, v) in ctx["ride"]
                           and solver.Value(ctx["ride"][a, v])],
            "loading_start": _clock(solver.Value(ctx["departure"][v]) - instance.parameters.loading_minutes),
            "departure": _clock(solver.Value(ctx["departure"][v])),
            "route": stops,
            "return": _clock(earliest_return),
        })

    by_household: dict[str, list[str]] = defaultdict(list)
    for r, req in requests.items():
        by_household[req.household].append(r)
    request_status = []
    unserved_households = []
    for h, alternatives in by_household.items():
        winners = [r for r in alternatives if r in assignments]
        if ctx["is_v2"]:
            for r in alternatives:
                if r in assignments:
                    request_status.append({"request": r, "status": "fulfilled",
                                           "vehicle": assignments[r]})
                else:
                    request_status.append({
                        "request": r,
                        "status": "unserved",
                        "reason": _unserved_reason(ctx, h, [r]),
                    })
        else:
            winner = winners[0] if winners else None
            for r in alternatives:
                if r == winner:
                    request_status.append({"request": r, "status": "fulfilled",
                                           "vehicle": assignments[r]})
                elif winner:
                    request_status.append({"request": r, "status": "covered_by_alternative",
                                           "covered_by": winner})
                else:
                    request_status.append({"request": r, "status": "unserved"})
        if not winners:
            unserved_households.append({
                "household": h,
                "reason": _unserved_reason(ctx, h, alternatives),
            })

    count = len(out_vehicles)
    objective = {
        "households_served": sum(1 for h in ctx["households"]
                                  if any(r in assignments for r in by_household[h])),
        "priority_weight": sum(ctx["households"][h].priority for h in by_household
                                if any(r in assignments for r in by_household[h])),
        "mean_travel_minutes": round(total_travel / count, 2) if count else 0,
        "vehicles_used": count,
    }
    if ctx["is_v2"]:
        objective["requests_fulfilled"] = len(assignments)
    payload = {
        "status": status,
        "objective": objective,
        "vehicles": out_vehicles,
        "request_status": request_status,
        "unserved_households": unserved_households,
    }
    if ctx["is_v2"]:
        return IndependentSchedule.model_validate(payload)
    return Schedule.model_validate(payload)


def _unserved_reason(ctx, household: str, alternatives: list[str]) -> str:
    reqs, vehicles = ctx["requests"], ctx["vehicles"]
    for r in alternatives:
        req = reqs[r]
        possible = [v for v in vehicles.values() if v.organisation == req.organisation]
        if not any(v.ambient_capacity >= req.ambient_crates
                   and v.chilled_capacity >= req.chilled_crates for v in possible):
            return "No vehicle in the organisation has enough capacity for an alternative request."
    return "No feasible route was found within vehicle, shift, window, and volunteer constraints."


def solve(instance: Instance | InputFirstInstance, *, time_limit: float = 60.0,
          workers: int = 8, log: bool = False) -> Schedule | IndependentSchedule:
    """Solve v1 or v2 lexicographically using its corresponding objective.

    For each possible nonzero fleet size, mean travel minimization is equivalent
    to total travel minimization. Candidate ratios are compared as exact integer
    fractions, avoiding rounding in the optimization decision.
    """
    ctx = _build(instance)
    model = ctx["model"]
    all_optimal = True

    stages = [(ctx["served_count"], True), (ctx["priority"], True)]
    if ctx["is_v2"]:
        stages.append((sum(ctx["fulfilled"].values()), True))
    for expr, maximize in stages:
        solver, status, value = _run(model, expr, maximize=maximize,
                                     seconds=time_limit, workers=workers, log=log)
        if value is None:
            raise RuntimeError(f"CP-SAT found no solution (status={solver.StatusName(status)})")
        all_optimal &= status == cp_model.OPTIMAL
        model.Add(expr == value)

    best = None
    fleet_limit = len(ctx["vehicles"])
    for count in range(1, fleet_limit + 1):
        candidate_model = model.Clone()
        candidate_used = [candidate_model.GetBoolVarFromProtoIndex(v.Index())
                          for v in ctx["used"].values()]
        candidate_model.Add(sum(candidate_used) == count)
        travel_var = candidate_model.GetIntVarFromProtoIndex(ctx["total_travel"].Index())
        solver, status, total = _run(candidate_model, travel_var, maximize=False,
                                     seconds=time_limit, workers=workers, log=log)
        if total is None:
            if status == cp_model.UNKNOWN:
                all_optimal = False
            continue
        all_optimal &= status == cp_model.OPTIMAL
        # Minimize vehicle ID only after fixing travel for this fleet size.
        candidate_model.Add(travel_var == total)
        id_expr = sum((i + 1) * candidate_model.GetBoolVarFromProtoIndex(ctx["used"][v].Index())
                      for i, v in enumerate(ctx["vehicles"]))
        solver, id_status, id_cost = _run(candidate_model, id_expr, maximize=False,
                                          seconds=time_limit, workers=workers, log=log)
        if id_cost is None:
            all_optimal = False
            continue
        all_optimal &= id_status == cp_model.OPTIMAL
        record = (total, count, id_cost, solver, candidate_model)
        if best is None or total * best[1] < best[0] * count or (
            total * best[1] == best[0] * count and (count, id_cost) < (best[1], best[2])
        ):
            best = record

    if best is None:
        # Valid instances may still have a zero-service solution. Find a model
        # with every vehicle disabled and return that valid empty schedule.
        empty_model = model.Clone()
        for v in ctx["used"]:
            empty_model.Add(empty_model.GetBoolVarFromProtoIndex(ctx["used"][v].Index()) == 0)
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = time_limit
        solver.parameters.num_search_workers = workers
        result = solver.Solve(empty_model)
        if result not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise RuntimeError(f"CP-SAT found no solution (status={solver.StatusName(result)})")
        # Map cloned-model values through the same variable indices.
        class CloneSolver:
            def Value(self, variable):
                return solver.Value(empty_model.GetIntVarFromProtoIndex(variable.Index()))
        return _extract(ctx, CloneSolver(), "optimal" if all_optimal else "feasible")

    best_total, count, id_cost, _, winning_model = best
    winning_model.Add(
        winning_model.GetIntVarFromProtoIndex(ctx["total_travel"].Index()) == best_total
    )
    winning_model.Add(sum(winning_model.GetIntVarFromProtoIndex(v.Index())
                          for v in ctx["used"].values()) == count)
    winning_model.Add(sum((i + 1) * winning_model.GetIntVarFromProtoIndex(ctx["used"][v].Index())
                          for i, v in enumerate(ctx["vehicles"])) == id_cost)
    # Re-solve with the tie-break fixed so the extracted assignment belongs to
    # the selected cloned model. Use corresponding cloned variables in extract.
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = workers
    solver.parameters.log_search_progress = log
    final_status = solver.Solve(winning_model)
    if final_status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"CP-SAT final solve failed (status={solver.StatusName(final_status)})")

    # _extract uses original variable handles, so wrap values from the clone by
    # their stable proto indices.
    class CloneSolver:
        def Value(self, variable):
            return solver.Value(winning_model.GetIntVarFromProtoIndex(variable.Index()))

    all_optimal &= final_status == cp_model.OPTIMAL
    return _extract(ctx, CloneSolver(), "optimal" if all_optimal else "feasible")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("instance", type=Path, help="Path to an instance JSON file")
    parser.add_argument("--time-limit", type=float, default=60.0)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--log", action="store_true")
    args = parser.parse_args()

    raw_instance = json.loads(args.instance.read_text(encoding="utf-8"))
    if raw_instance.get("metadata", {}).get("protocol_version") == "v2":
        instance = InputFirstInstance.model_validate(raw_instance)
    else:
        instance = Instance.model_validate(raw_instance)
    result = solve(instance, time_limit=args.time_limit, workers=args.workers, log=args.log)
    print(result.model_dump_json(indent=2, by_alias=True))


if __name__ == "__main__":
    main()
