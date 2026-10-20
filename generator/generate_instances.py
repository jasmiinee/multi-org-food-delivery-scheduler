"""Generate reproducible easy, medium and hard food-delivery instances."""

from __future__ import annotations

import argparse
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .render_natural_language import hhmm, render_instance


GENERATOR_VERSION = "1.1.0-difficulty-calibrated"


@dataclass(frozen=True)
class DifficultySpec:
    organisations: tuple[int, int]
    households: tuple[int, int]
    duplicates: tuple[int, int]
    vehicles_per_org: int
    window_margin: int
    capacity_slack: int
    needs_trained_probability: float
    chilled_probability: float


SPECS = {
    "easy": DifficultySpec((2, 2), (6, 8), (1, 1), 2, 40, 4, 0.20, 0.20),
    "medium": DifficultySpec((2, 3), (12, 15), (2, 3), 2, 20, 2, 0.28, 0.28),
    "hard": DifficultySpec((3, 3), (20, 25), (4, 5), 3, 8, 0, 0.35, 0.35),
}


def _distance(left: tuple[int, int], right: tuple[int, int]) -> int:
    if left == right:
        return 0
    return max(5, int(round(math.dist(left, right))))


def _json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _minutes(value: str) -> int:
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


def make_instance(
    level: str,
    seed: int,
    instance_id: str,
    make_impossible: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if level not in SPECS:
        raise ValueError(f"Unknown difficulty: {level}")

    spec = SPECS[level]
    rng = random.Random(seed)
    organisation_count = rng.randint(*spec.organisations)
    household_count = rng.randint(*spec.households)
    duplicate_count = rng.randint(*spec.duplicates)

    organisations: list[dict[str, Any]] = []
    coordinates: dict[str, tuple[int, int]] = {}
    for index in range(organisation_count):
        org_id = f"O{index + 1}"
        depot = f"D{index + 1}"
        shift_start = 8 * 60 + index * 20
        shift_end = 18 * 60 - (organisation_count - index - 1) * 10
        organisations.append(
            {
                "id": org_id,
                "depot": depot,
                "shifts": [{"id": f"{org_id}_DAY", "start": shift_start, "end": shift_end}],
            }
        )
        coordinates[depot] = (10 + index * 35, 10 + (index % 2) * 30)

    households: list[dict[str, Any]] = []
    household_specs: dict[str, dict[str, Any]] = {}
    for index in range(household_count):
        household_id = f"H{index + 1}"
        needs_trained = rng.random() < spec.needs_trained_probability
        item = {
            "id": household_id,
            "needs_trained_volunteer": needs_trained,
            "priority": rng.randint(1, 3),
        }
        households.append(item)
        coordinates[household_id] = (rng.randint(5, 85), rng.randint(5, 70))
        household_specs[household_id] = {
            "primary_org_index": index % organisation_count,
            "ambient": rng.randint(1, 3),
            "chilled": rng.randint(1, 2) if rng.random() < spec.chilled_probability else 0,
        }

    # Medium and hard instances always contain a trained-and-chilled request for
    # every organisation. These requests share that organisation's first route,
    # making refrigerated capacity and its sole trained assistant scarce.
    if level in {"medium", "hard"}:
        household_by_id = {item["id"]: item for item in households}
        for org_index in range(organisation_count):
            household_id = next(
                item["id"]
                for item in households
                if household_specs[item["id"]]["primary_org_index"] == org_index
            )
            household_by_id[household_id]["needs_trained_volunteer"] = True
            household_specs[household_id]["chilled"] = max(
                1, household_specs[household_id]["chilled"]
            )

    locations = [item["depot"] for item in organisations] + [item["id"] for item in households]
    travel_times = {
        origin: {destination: _distance(coordinates[origin], coordinates[destination]) for destination in locations}
        for origin in locations
    }

    route_households: dict[str, list[str]] = {}
    org_vehicle_ids: dict[str, list[str]] = {}
    volunteers: list[dict[str, Any]] = []
    vehicle_shells: list[dict[str, Any]] = []
    vehicle_counter = 1

    for org_index, org in enumerate(organisations):
        vehicle_ids: list[str] = []
        for local_index in range(spec.vehicles_per_org):
            vehicle_id = f"V{vehicle_counter}"
            driver_id = f"Driver_{vehicle_counter}"
            vehicle_counter += 1
            vehicle_ids.append(vehicle_id)
            route_households[vehicle_id] = []
            volunteers.append(
                {
                    "id": driver_id,
                    "organisation": org["id"],
                    "role": "driver",
                    "shift_id": org["shifts"][0]["id"],
                    "trained": level == "easy" and local_index == 0,
                    "vehicle_id": vehicle_id,
                }
            )
            vehicle_shells.append(
                {
                    "id": vehicle_id,
                    "organisation": org["id"],
                    "home_depot": org["depot"],
                    "driver_id": driver_id,
                    "seats": 3 if level == "easy" else 2,
                    "ambient_capacity": 0,
                    "chilled_capacity": 0,
                }
            )

        org_vehicle_ids[org["id"]] = vehicle_ids
        volunteers.extend(
            [
                {
                    "id": f"{org['id']}_TrainedAssistant",
                    "organisation": org["id"],
                    "role": "assistant",
                    "shift_id": org["shifts"][0]["id"],
                    "trained": True,
                    "vehicle_id": None,
                },
                {
                    "id": f"{org['id']}_Assistant",
                    "organisation": org["id"],
                    "role": "assistant",
                    "shift_id": org["shifts"][0]["id"],
                    "trained": False,
                    "vehicle_id": None,
                },
            ]
        )

    regular_counters = {org["id"]: 0 for org in organisations}
    for household in households:
        household_id = household["id"]
        primary_org = organisations[household_specs[household_id]["primary_org_index"]]
        vehicle_ids = org_vehicle_ids[primary_org["id"]]
        if household["needs_trained_volunteer"] or household_specs[household_id]["chilled"] > 0:
            chosen_vehicle = vehicle_ids[0]
        else:
            chosen_vehicle = vehicle_ids[regular_counters[primary_org["id"]] % len(vehicle_ids)]
            regular_counters[primary_org["id"]] += 1
        route_households[chosen_vehicle].append(household_id)

    driver_by_vehicle = {
        volunteer["vehicle_id"]: volunteer
        for volunteer in volunteers
        if volunteer["role"] == "driver"
    }
    org_by_id = {org["id"]: org for org in organisations}
    vehicles_by_id = {vehicle["id"]: vehicle for vehicle in vehicle_shells}
    primary_request_for_household: dict[str, str] = {}
    requests: list[dict[str, Any]] = []
    witness_vehicles: list[dict[str, Any]] = []
    request_counter = 1

    for vehicle_id in sorted(route_households, key=lambda value: int(value[1:])):
        route = route_households[vehicle_id]
        vehicle = vehicles_by_id[vehicle_id]
        org = org_by_id[vehicle["organisation"]]
        shift = org["shifts"][0]
        depot = org["depot"]
        if not route:
            vehicle["ambient_capacity"] = max(1, spec.capacity_slack)
            vehicle["chilled_capacity"] = 0
            continue

        route.sort(key=lambda value: (coordinates[value][0], coordinates[value][1], value))
        departure = shift["start"] + 20
        current_time = departure
        previous_location = depot
        witness_stops: list[dict[str, Any]] = []
        route_ambient = 0
        route_chilled = 0
        route_travel = 0

        for household_id in route:
            household = next(item for item in households if item["id"] == household_id)
            values = household_specs[household_id]
            leg = travel_times[previous_location][household_id]
            route_travel += leg
            service_start = current_time + leg
            window_start = max(shift["start"], service_start - spec.window_margin)
            window_end = min(shift["end"], service_start + spec.window_margin)
            request_id = f"R{request_counter}"
            request_counter += 1
            primary_request_for_household[household_id] = request_id
            request = {
                "id": request_id,
                "organisation": org["id"],
                "household": household_id,
                "depot": depot,
                "ambient_crates": values["ambient"],
                "chilled_crates": values["chilled"],
                "window_start": window_start,
                "window_end": window_end,
            }
            requests.append(request)
            witness_stops.append(
                {"request": request_id, "household": household_id, "service_start": hhmm(service_start)}
            )
            route_ambient += values["ambient"]
            route_chilled += values["chilled"]
            current_time = service_start + 10
            previous_location = household_id

        return_leg = travel_times[previous_location][depot]
        route_travel += return_leg
        return_time = current_time + return_leg
        if return_time > shift["end"]:
            raise RuntimeError(f"Generated route exceeds shift for {vehicle_id}; retry with another seed")

        vehicle["ambient_capacity"] = route_ambient + spec.capacity_slack
        vehicle["chilled_capacity"] = route_chilled + spec.capacity_slack if route_chilled else 0
        needs_trained = any(
            next(item for item in households if item["id"] == household_id)["needs_trained_volunteer"]
            for household_id in route
        )
        driver = driver_by_vehicle[vehicle_id]
        assistants = []
        if needs_trained and not driver["trained"]:
            assistants = [f"{org['id']}_TrainedAssistant"]
        witness_vehicles.append(
            {
                "vehicle": vehicle_id,
                "driver": driver["id"],
                "assistants": assistants,
                "loading_start": hhmm(departure - 5),
                "departure": hhmm(departure),
                "route": witness_stops,
                "return": hhmm(return_time),
            }
        )

    duplicate_household_ids = rng.sample([item["id"] for item in households], duplicate_count)
    impossible_household_id: str | None = None
    impossible_request_id: str | None = None

    if make_impossible:
        duplicate_ids = set(duplicate_household_ids)
        candidate_trip = next(
            (
                trip
                for trip in sorted(witness_vehicles, key=lambda item: len(item["route"]), reverse=True)
                if len(trip["route"]) > 1
                and any(stop["household"] not in duplicate_ids for stop in reversed(trip["route"]))
            ),
            None,
        )
        if candidate_trip is None:
            candidate_trip = next(
                trip
                for trip in witness_vehicles
                if any(stop["household"] not in duplicate_ids for stop in reversed(trip["route"]))
            )

        removable_index = next(
            index
            for index in range(len(candidate_trip["route"]) - 1, -1, -1)
            if candidate_trip["route"][index]["household"] not in duplicate_ids
        )
        removed_stop = candidate_trip["route"].pop(removable_index)
        impossible_household_id = removed_stop["household"]
        impossible_request_id = removed_stop["request"]
        impossible_request = next(item for item in requests if item["id"] == impossible_request_id)
        impossible_request["ambient_crates"] = 1 + max(
            item["ambient_capacity"]
            for item in vehicle_shells
            if item["organisation"] == impossible_request["organisation"]
        )

        vehicle = vehicles_by_id[candidate_trip["vehicle"]]
        if candidate_trip["route"]:
            last_stop = candidate_trip["route"][-1]
            previous_location = last_stop["household"]
            current_time = _minutes(last_stop["service_start"]) + 10
        else:
            previous_location = vehicle["home_depot"]
            current_time = _minutes(candidate_trip["departure"])
        candidate_trip["return"] = hhmm(
            current_time + travel_times[previous_location][vehicle["home_depot"]]
        )
        if not candidate_trip["route"]:
            witness_vehicles.remove(candidate_trip)

    # Draw shifts around the known feasible work. Hard instances leave only five
    # minutes at either end, while easy instances retain substantial slack.
    shift_margin = {"easy": 60, "medium": 25, "hard": 5}[level]
    for org in organisations:
        vehicle_ids = set(org_vehicle_ids[org["id"]])
        org_trips = [trip for trip in witness_vehicles if trip["vehicle"] in vehicle_ids]
        if org_trips:
            org["shifts"][0]["start"] = min(
                _minutes(trip["loading_start"]) for trip in org_trips
            ) - shift_margin
            org["shifts"][0]["end"] = max(
                _minutes(trip["return"]) for trip in org_trips
            ) + shift_margin

    duplicate_households: list[dict[str, Any]] = []
    alternative_requests: list[dict[str, Any]] = []
    for household_id in duplicate_household_ids:
        primary_request_id = primary_request_for_household[household_id]
        primary_request = next(item for item in requests if item["id"] == primary_request_id)
        primary_org_index = next(
            index for index, item in enumerate(organisations) if item["id"] == primary_request["organisation"]
        )
        alternative_org = organisations[(primary_org_index + 1) % organisation_count]
        alternative_id = f"R{request_counter}"
        request_counter += 1
        shift = alternative_org["shifts"][0]
        centre = (primary_request["window_start"] + primary_request["window_end"]) // 2 + rng.randint(-30, 30)
        half_width = max(10, spec.window_margin)
        window_start = max(shift["start"], centre - half_width)
        window_end = min(shift["end"], centre + half_width)
        if window_end <= window_start:
            window_end = min(shift["end"], window_start + 10)
        alternative = {
            "id": alternative_id,
            "organisation": alternative_org["id"],
            "household": household_id,
            "depot": alternative_org["depot"],
            "ambient_crates": rng.randint(1, 3),
            # Hard alternatives consume already-scarce refrigerated capacity,
            # so choosing one normally forces a compensating route change.
            "chilled_crates": rng.randint(1, 2) if level == "hard" else rng.randint(0, 2),
            "window_start": window_start,
            "window_end": window_end,
        }
        alternative_requests.append(alternative)
        duplicate_households.append(
            {"household": household_id, "competing_requests": [primary_request_id, alternative_id]}
        )

    requests.extend(alternative_requests)
    requests.sort(key=lambda item: int(item["id"][1:]))

    instance = {
        "metadata": {
            "instance_id": instance_id,
            "difficulty": level,
            "scenario": "partially_serviceable" if make_impossible else "fully_serviceable",
            "seed": seed,
            "generator_version": GENERATOR_VERSION,
            "cold_chain_time_limit_enabled": False,
        },
        "parameters": {
            "service_minutes": 10,
            "loading_minutes": 5,
            "time_unit": "minutes_from_midnight",
            "window_semantics": "service_start",
            "max_trips_per_vehicle": 1,
        },
        "organisations": organisations,
        "households": households,
        "volunteers": volunteers,
        "vehicles": sorted(vehicle_shells, key=lambda item: int(item["id"][1:])),
        "requests": requests,
        "duplicate_households": duplicate_households,
        "travel_times": travel_times,
    }

    primary_status: list[dict[str, Any]] = [
        {"request": request_id, "status": "fulfilled", "vehicle": vehicle["vehicle"]}
        for vehicle in witness_vehicles
        for request_id in [stop["request"] for stop in vehicle["route"]]
    ]
    alternative_status = [
        {
            "request": duplicate["competing_requests"][1],
            "status": "covered_by_alternative",
            "covered_by": duplicate["competing_requests"][0],
        }
        for duplicate in duplicate_households
    ]
    if impossible_request_id is not None:
        primary_status.append(
            {
                "request": impossible_request_id,
                "status": "unserved",
                "reason": "ambient demand exceeds every vehicle capacity in its organisation",
            }
        )

    total_travel = 0
    for trip in witness_vehicles:
        vehicle = vehicles_by_id[trip["vehicle"]]
        previous_location = vehicle["home_depot"]
        for stop in trip["route"]:
            total_travel += travel_times[previous_location][stop["household"]]
            previous_location = stop["household"]
        total_travel += travel_times[previous_location][vehicle["home_depot"]]

    served_household_ids = {
        stop["household"] for trip in witness_vehicles for stop in trip["route"]
    }
    witness = {
        "status": "feasible_witness",
        "objective": {
            "households_served": len(served_household_ids),
            "priority_weight": sum(
                item["priority"] for item in households if item["id"] in served_household_ids
            ),
            "mean_travel_minutes": round(total_travel / len(witness_vehicles), 2) if witness_vehicles else 0,
            "vehicles_used": len(witness_vehicles),
        },
        "vehicles": witness_vehicles,
        "request_status": sorted(primary_status + alternative_status, key=lambda item: int(item["request"][1:])),
        "unserved_households": (
            [
                {
                    "household": impossible_household_id,
                    "reason": "ambient demand exceeds every vehicle capacity in its organisation",
                }
            ]
            if impossible_household_id is not None
            else []
        ),
    }
    return instance, witness


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--per-level", type=int, default=5)
    parser.add_argument("--seed", type=int, default=4248)
    parser.add_argument("--levels", nargs="+", choices=sorted(SPECS), default=sorted(SPECS))
    parser.add_argument(
        "--impossible-every",
        type=int,
        default=0,
        help="Make every Nth instance per difficulty partially serviceable (0 disables).",
    )
    args = parser.parse_args()

    if args.per_level < 1:
        raise SystemExit("--per-level must be at least 1")
    if args.impossible_every < 0:
        raise SystemExit("--impossible-every cannot be negative")

    for level_index, level in enumerate(args.levels):
        for instance_index in range(args.per_level):
            instance_seed = args.seed + level_index * 10_000 + instance_index
            instance_id = f"{level}_{instance_index + 1:03d}"
            make_impossible = (
                args.impossible_every > 0
                and (instance_index + 1) % args.impossible_every == 0
            )
            instance, witness = make_instance(
                level,
                instance_seed,
                instance_id,
                make_impossible=make_impossible,
            )
            destination = args.output_dir / level
            _json_write(destination / f"{instance_id}.json", instance)
            _json_write(destination / f"{instance_id}.witness.json", witness)
            (destination / f"{instance_id}.txt").write_text(render_instance(instance), encoding="utf-8")
            print(
                f"Generated {instance_id} (seed {instance_seed}, "
                f"scenario {instance['metadata']['scenario']})"
            )


if __name__ == "__main__":
    main()

