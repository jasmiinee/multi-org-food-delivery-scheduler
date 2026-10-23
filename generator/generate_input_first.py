"""Sample hard inputs independently of any route, schedule, solver or witness."""

from __future__ import annotations

import argparse
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path

from models import InputFirstInstance
from .render_natural_language import render_instance


GENERATOR_VERSION = "2.0.0-input-first"


@dataclass(frozen=True)
class Profile:
    name: str
    households: int
    duplicates: int
    windows: tuple[int, ...] = (20, 30, 40)
    ambient_capacity: tuple[int, int] = (7, 10)
    chilled_capacity: tuple[int, int] = (3, 5)
    demand: tuple[int, int] = (1, 3)
    chilled_probability: float = 0.35
    trained_driver_probability: float = 0.20


PROFILES = (
    Profile("mixed_resource_pressure", 22, 5),
    Profile("tight_windows", 24, 5, windows=(10, 15, 20)),
    Profile("scarce_training", 23, 5, trained_driver_probability=0.0),
    Profile("chilled_capacity_pressure", 25, 5, chilled_capacity=(2, 3), chilled_probability=0.65),
    Profile("staggered_shifts", 24, 5),
    Profile("distant_depots", 20, 4),
    Profile("aggregate_ambient_shortage", 25, 5, ambient_capacity=(4, 5), demand=(2, 3)),
    Profile("one_seat_training_conflict", 21, 4),
    Profile("training_shift_gap", 22, 5),
    Profile("combined_pressure", 25, 5, windows=(10, 15, 20), ambient_capacity=(5, 7),
            chilled_capacity=(2, 3), chilled_probability=0.55, trained_driver_probability=0.05),
)


def make_input_first_instance(profile_index: int, seed: int, instance_id: str) -> dict:
    """Return only an input instance. No vehicle assignments or stop times are made."""
    profile = PROFILES[profile_index]
    rng = random.Random(seed)
    organisations, volunteers, vehicles = [], [], []
    positions = {"D1": (10, 10), "D2": (60, 10), "D3": (35, 55)}

    # Resource limits are fixed before requests are sampled. They are never
    # increased to fit demand, and shifts are never drawn around a route.
    for index in range(3):
        org = f"O{index + 1}"
        depot = f"D{index + 1}"
        offset = index * 10
        if profile.name == "staggered_shifts":
            hours = ((480 + offset, 840 + offset), (480 + offset, 660 + offset),
                     (750 + offset, 900 + offset))
        else:
            hours = ((480 + offset, 900 + offset), (480 + offset, 720 + offset),
                     (600 + offset, 900 + offset))
        if profile.name == "training_shift_gap" and index == 1:
            hours = (hours[0], (480 + offset, 660), hours[2])
        shifts = [
            {"id": f"{org}_{name}", "start": bounds[0], "end": bounds[1]}
            for name, bounds in zip(("DAY", "EARLY", "LATE"), hours)
        ]
        organisations.append({"id": org, "depot": depot, "shifts": shifts})
        for local in range(3):
            number = index * 3 + local + 1
            trained = rng.random() < profile.trained_driver_probability
            seats = rng.choice((2, 3))
            if profile.name == "one_seat_training_conflict" and index == 0 and local == 0:
                trained, seats = False, 1
            if profile.name == "training_shift_gap" and index == 1:
                trained = False
            volunteers.append({
                "id": f"Driver_{number}", "organisation": org, "role": "driver",
                "shift_id": shifts[local]["id"], "trained": trained, "vehicle_id": f"V{number}",
            })
            vehicles.append({
                "id": f"V{number}", "organisation": org, "home_depot": depot,
                "driver_id": f"Driver_{number}", "seats": seats,
                "ambient_capacity": rng.randint(*profile.ambient_capacity),
                "chilled_capacity": rng.randint(*profile.chilled_capacity) if local == 0 else 0,
            })
        trained_shift = shifts[1] if profile.name == "training_shift_gap" and index == 1 else shifts[0]
        volunteers.extend([
            {"id": f"{org}_TrainedAssistant", "organisation": org, "role": "assistant",
             "shift_id": trained_shift["id"], "trained": True, "vehicle_id": None},
            {"id": f"{org}_Assistant", "organisation": org, "role": "assistant",
             "shift_id": shifts[2]["id"], "trained": False, "vehicle_id": None},
        ])

    households = []
    occupied = set(positions.values())
    for number in range(1, profile.households + 1):
        household = f"H{number}"
        if profile.name == "distant_depots":
            point = (rng.randint(5, 115), rng.randint(5, 100))
        else:
            point = (rng.randint(5, 70), rng.randint(5, 65))
        while point in occupied:
            point = (rng.randint(5, 70), rng.randint(5, 65))
        occupied.add(point)
        positions[household] = point
        households.append({
            "id": household, "needs_trained_volunteer": rng.random() < 0.35,
            "priority": rng.randint(1, 3),
        })

    forced_profile = profile.name in {"one_seat_training_conflict", "training_shift_gap"}
    if forced_profile:
        households[0]["needs_trained_volunteer"] = True
        duplicate_ids = {"H1"} | set(rng.sample([h["id"] for h in households[1:]], profile.duplicates - 1))
    else:
        duplicate_ids = set(rng.sample([h["id"] for h in households], profile.duplicates))

    # Organisation choices, items and windows are sampled as input facts.
    # There is no route or departure time to derive these values from.
    requests = []
    for household in households:
        hid = household["id"]
        org_indices = rng.sample(range(3), 2 if hid in duplicate_ids else 1)
        if hid == "H1" and profile.name == "one_seat_training_conflict":
            org_indices = [0, 1]
        elif hid == "H1" and profile.name == "training_shift_gap":
            org_indices = [1, 2]
        for org_index in org_indices:
            org = organisations[org_index]
            start = rng.randrange(510, 841, 5)
            chilled = rng.randint(1, 2) if rng.random() < profile.chilled_probability else 0
            if hid == "H1" and profile.name == "one_seat_training_conflict" and org_index == 0:
                chilled = 1
            if hid == "H1" and profile.name == "training_shift_gap" and org_index == 1:
                start = 780
            requests.append({
                "organisation": org["id"], "household": hid, "depot": org["depot"],
                "ambient_crates": rng.randint(*profile.demand), "chilled_crates": chilled,
                "window_start": start, "window_end": start + rng.choice(profile.windows),
            })
    # Request identifiers must not disclose a planted vehicle assignment or route order.
    rng.shuffle(requests)
    for number, request in enumerate(requests, 1):
        request["id"] = f"R{number}"

    locations = list(positions)
    travel = {
        origin: {
            destination: math.ceil(math.dist(positions[origin], positions[destination]))
            for destination in locations
        }
        for origin in locations
    }
    groups = [
        {"household": hid, "request_ids": [r["id"] for r in requests if r["household"] == hid]}
        for hid in sorted(duplicate_ids, key=lambda value: int(value[1:]))
    ]
    instance = {
        "metadata": {
            "instance_id": instance_id, "difficulty": "hard", "scenario": "unclassified",
            "seed": seed, "generator_version": GENERATOR_VERSION,
            "cold_chain_time_limit_enabled": False, "protocol_version": "v2",
            "generation_method": "input_first", "feasibility_status": "not_checked",
            "challenge_profile": profile.name,
        },
        "parameters": {
            "service_minutes": 10, "loading_minutes": 5,
            "time_unit": "minutes_from_midnight", "window_semantics": "service_start",
            "max_trips_per_vehicle": 1, "duplicate_policy": "independent_requests",
        },
        "organisations": organisations, "households": households,
        "volunteers": volunteers, "vehicles": vehicles, "requests": requests,
        "duplicate_households": groups, "travel_times": travel,
    }
    InputFirstInstance.model_validate(instance)
    return instance


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20261023)
    parser.add_argument("--per-profile", type=int, default=1)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.per_profile < 1:
        parser.error("--per-profile must be at least 1")
    generated = []
    for index, profile in enumerate(PROFILES):
        for repetition in range(args.per_profile):
            number = index * args.per_profile + repetition + 1
            instance_id = f"input_hard_{number:03d}"
            instance = make_input_first_instance(index, args.seed + index * 1000 + repetition, instance_id)
            generated.append(instance)
    destination = args.output_dir / "hard"
    manifest_path = args.output_dir / "generation_manifest.json"
    paths = [manifest_path] + [
        destination / (item["metadata"]["instance_id"] + suffix)
        for item in generated for suffix in (".json", ".txt")
    ]
    if not args.overwrite and any(path.exists() for path in paths):
        parser.error("Output already exists; use another directory or --overwrite explicitly")
    destination.mkdir(parents=True, exist_ok=True)
    cases = []
    for instance in generated:
        instance_id = instance["metadata"]["instance_id"]
        (destination / f"{instance_id}.json").write_text(json.dumps(instance, indent=2) + "\n", encoding="utf-8")
        (destination / f"{instance_id}.txt").write_text(render_instance(instance), encoding="utf-8")
        cases.append({
            "instance_id": instance_id, "challenge_profile": instance["metadata"]["challenge_profile"],
            "seed": instance["metadata"]["seed"], "households": len(instance["households"]),
            "requests": len(instance["requests"]), "duplicate_households": len(instance["duplicate_households"]),
            "vehicles": len(instance["vehicles"]), "feasibility_status": "not_checked",
        })
        print(f"Generated {instance_id}: {len(instance['households'])} households, {len(instance['requests'])} requests; feasibility not checked")
    manifest = {
        "generator_version": GENERATOR_VERSION, "protocol": "v2", "base_seed": args.seed,
        "construction": "Resources, geography and requests are sampled before any scheduling. No solver, route construction, feasibility rejection or witness generation is used.",
        "selection": "Every generated case is retained; profile labels are not included in model input text.",
        "cases": cases,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
