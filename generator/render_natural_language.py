"""Render a structured benchmark instance as the natural-language model input."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def hhmm(minutes: int) -> str:
    if not 0 <= minutes < 24 * 60:
        raise ValueError(f"Minute value outside one day: {minutes}")
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def yes_no(value: bool) -> str:
    return "yes" if value else "no"


def render_instance(instance: dict[str, Any]) -> str:
    metadata = instance["metadata"]
    params = instance["parameters"]
    is_v2 = metadata.get("protocol_version") == "v2"
    organisations = {item["id"]: item for item in instance["organisations"]}
    households = {item["id"]: item for item in instance["households"]}

    lines: list[str] = [
        f"Food-delivery scheduling instance: {metadata['instance_id']}",
        f"Difficulty: {metadata['difficulty']}",
        "",
        "Rules and objective",
        f"- Each service takes {params['service_minutes']} minutes.",
        f"- Loading takes {params['loading_minutes']} minutes immediately before departure.",
        "- A delivery window constrains the service start time. Early arrival is allowed, followed by waiting.",
        "- Every used vehicle makes one loop from and back to its own depot, and makes at most one trip.",
        "- A vehicle may serve only requests belonging to its own organisation.",
        "- Drivers use only their own vehicle. Assistants may join at most one vehicle from their organisation.",
        "- Seats include the driver. The full trip, including loading and return, must fit every team member's shift.",
        "- Ambient and chilled crate capacities are separate. Chilled crates require sufficient chilled capacity.",
        "- There is no separate time-based cold-chain limit in this version.",
        "- A specialised-needs household requires at least one trained driver or assistant on its vehicle.",
        (
            "- Each request may be fulfilled at most once. Different organisations may each fulfil their own request for the same household."
            if is_v2 else
            "- At most one competing request may be fulfilled for a duplicate household."
        ),
        (
            "- First maximize distinct households served; then their priority weight counted once per household; then maximize fulfilled requests; then minimize mean travel per used vehicle; then vehicles used; then vehicle ID."
            if is_v2 else
            "- First maximize households served; then priority weight; then minimize mean travel per used vehicle; then vehicles used; then vehicle ID."
        ),
        "- Mean travel is total depot and inter-stop travel divided by used vehicles; loading, waiting and service are excluded.",
        "",
        "Organisations and shifts",
    ]

    if is_v2:
        lines.insert(2, "Protocol: v2 (independent requests)")
        index = lines.index("Rules and objective") + 1
        lines[index:index] = [
            "- Duplicate requests are separate deliveries. Fulfil both when jointly feasible under the objective order; do not merge their items or windows.",
            "- A household is served when at least one of its requests is fulfilled; count the household and its priority once.",
            "- Every unfulfilled request is unserved and needs a reason, even if another organisation delivered to its household. Do not use covered_by_alternative.",
        ]

    for org in instance["organisations"]:
        shifts = ", ".join(
            f"{shift['id']} {hhmm(shift['start'])}-{hhmm(shift['end'])}"
            for shift in org["shifts"]
        )
        lines.append(f"- {org['id']}: depot {org['depot']}; shifts: {shifts}.")

    lines.extend(["", "Households"])
    for household in instance["households"]:
        lines.append(
            f"- {household['id']}: priority {household['priority']}; "
            f"needs trained volunteer: {yes_no(household['needs_trained_volunteer'])}."
        )

    lines.extend(["", "Volunteers"])
    for volunteer in instance["volunteers"]:
        vehicle = volunteer["vehicle_id"] or "none"
        lines.append(
            f"- {volunteer['id']}: {volunteer['role']} for {volunteer['organisation']}; "
            f"shift {volunteer['shift_id']}; trained: {yes_no(volunteer['trained'])}; "
            f"own vehicle: {vehicle}."
        )

    lines.extend(["", "Vehicles"])
    for vehicle in instance["vehicles"]:
        lines.append(
            f"- {vehicle['id']}: {vehicle['organisation']}, depot {vehicle['home_depot']}, "
            f"driver {vehicle['driver_id']}, seats {vehicle['seats']}, "
            f"ambient capacity {vehicle['ambient_capacity']}, chilled capacity {vehicle['chilled_capacity']}."
        )

    lines.extend(["", "Delivery requests"])
    for request in instance["requests"]:
        household = households[request["household"]]
        lines.append(
            f"- {request['id']}: {request['organisation']} serves {request['household']} from "
            f"{request['depot']}; ambient {request['ambient_crates']}; chilled {request['chilled_crates']}; "
            f"window {hhmm(request['window_start'])}-{hhmm(request['window_end'])}; "
            f"trained volunteer needed: {yes_no(household['needs_trained_volunteer'])}; "
            f"household priority {household['priority']}."
        )

    lines.extend(["", "Duplicate households"])
    if instance["duplicate_households"]:
        for duplicate in instance["duplicate_households"]:
            if is_v2:
                lines.append(
                    f"- {duplicate['household']}: independent requests "
                    f"{', '.join(duplicate['request_ids'])}; each requires its own delivery."
                )
            else:
                lines.append(
                    f"- {duplicate['household']}: choose at most one of "
                    f"{', '.join(duplicate['competing_requests'])}."
                )
    else:
        lines.append("- None.")

    locations = [org["depot"] for org in organisations.values()] + list(households)
    lines.extend(["", "Travel times in minutes (symmetric)", "origin,destination,minutes"])
    matrix = instance["travel_times"]
    for left_index, origin in enumerate(locations):
        for destination in locations[left_index + 1 :]:
            lines.append(f"{origin},{destination},{matrix[origin][destination]}")

    lines.extend(
        [
            "",
            "Produce the final schedule using the required JSON output format. Include every request in request_status.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("instance", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    instance = json.loads(args.instance.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_instance(instance), encoding="utf-8")


if __name__ == "__main__":
    main()

