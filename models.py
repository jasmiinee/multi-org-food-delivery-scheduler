"""Typed structural models shared by the generator and direct-model tooling."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Metadata(StrictModel):
    instance_id: str
    difficulty: Literal["worked_example", "easy", "medium", "hard"]
    scenario: Literal["fully_serviceable", "partially_serviceable"]
    seed: int
    generator_version: str
    cold_chain_time_limit_enabled: Literal[False]


class Parameters(StrictModel):
    service_minutes: int = Field(gt=0)
    loading_minutes: int = Field(ge=0)
    time_unit: Literal["minutes_from_midnight"]
    window_semantics: Literal["service_start"]
    max_trips_per_vehicle: Literal[1]


class Shift(StrictModel):
    id: str
    start: int = Field(ge=0, le=1439)
    end: int = Field(ge=1, le=1440)


class Organisation(StrictModel):
    id: str
    depot: str
    shifts: list[Shift] = Field(min_length=1)


class Household(StrictModel):
    id: str
    needs_trained_volunteer: bool
    priority: int = Field(ge=1, le=3)


class Volunteer(StrictModel):
    id: str
    organisation: str
    role: Literal["driver", "assistant"]
    shift_id: str
    trained: bool
    vehicle_id: str | None


class Vehicle(StrictModel):
    id: str
    organisation: str
    home_depot: str
    driver_id: str
    seats: int = Field(ge=1)
    ambient_capacity: int = Field(ge=0)
    chilled_capacity: int = Field(ge=0)


class Request(StrictModel):
    id: str
    organisation: str
    household: str
    depot: str
    ambient_crates: int = Field(ge=0)
    chilled_crates: int = Field(ge=0)
    window_start: int = Field(ge=0, le=1439)
    window_end: int = Field(ge=0, le=1439)


class DuplicateHousehold(StrictModel):
    household: str
    competing_requests: list[str] = Field(min_length=2)


class Instance(StrictModel):
    metadata: Metadata
    parameters: Parameters
    organisations: list[Organisation] = Field(min_length=1)
    households: list[Household] = Field(min_length=1)
    volunteers: list[Volunteer] = Field(min_length=1)
    vehicles: list[Vehicle] = Field(min_length=1)
    requests: list[Request] = Field(min_length=1)
    duplicate_households: list[DuplicateHousehold]
    travel_times: dict[str, dict[str, int]]


TimeText = Annotated[str, StringConstraints(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")]


class Objective(StrictModel):
    households_served: int = Field(ge=0)
    priority_weight: int = Field(ge=0)
    mean_travel_minutes: float = Field(ge=0)
    vehicles_used: int = Field(ge=0)


class RouteStop(StrictModel):
    request: str
    household: str
    service_start: TimeText


class VehicleSchedule(StrictModel):
    vehicle: str
    driver: str
    assistants: list[str]
    loading_start: TimeText
    departure: TimeText
    route: list[RouteStop] = Field(min_length=1)
    return_time: TimeText = Field(alias="return", serialization_alias="return")


class RequestStatus(StrictModel):
    request: str
    status: Literal["fulfilled", "covered_by_alternative", "unserved"]
    vehicle: str | None = None
    covered_by: str | None = None
    reason: str | None = None


class UnservedHousehold(StrictModel):
    household: str
    reason: str = Field(min_length=1)


class Schedule(StrictModel):
    status: Literal["candidate", "feasible", "optimal", "feasible_witness"]
    objective: Objective
    vehicles: list[VehicleSchedule]
    request_status: list[RequestStatus]
    unserved_households: list[UnservedHousehold]

