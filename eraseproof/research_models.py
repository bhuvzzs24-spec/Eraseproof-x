"""Versioned experiment inputs. Expected labels are documentation, never oracle inputs."""

from pathlib import Path
from typing import Literal, Annotated
import json
from pydantic import BaseModel, ConfigDict, Field, model_validator

ACTIONS = {
    "skip_cache",
    "skip_search",
    "analytics_residue",
    "order_field",
    "pause_redis",
    "late_index",
    "duplicate_stale",
    "crash_after_cache",
    "pause_deletion",
    "error_after_cache",
    "crash_verifier",
    "omit_search_adapter",
    "sql_rollback",
    "race_orders",
}
TARGETS = {"customer", "orders", "cache", "search", "analytics", "event_history"}


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,48}$")
    name: str
    description: str
    category: str
    targets: list[str]
    actions: list[str]
    initial_state: str
    workflow: dict
    activation: str
    expected_data_state: Literal["ABSENT", "RESIDUAL", "UNAVAILABLE", "PENDING"]
    expected_orchestration: str
    expected_verification: str
    expected_method_outcome: str | None = None
    recovery: str
    trial_timeout_seconds: int = Field(ge=30, le=180)
    settling_seconds: int = Field(ge=3, le=15)
    seed_source: str

    @model_validator(mode="after")
    def supported(self):
        if set(self.actions) - ACTIONS or set(self.targets) - TARGETS:
            raise ValueError("unsupported fault action or target")
        if len(self.actions) != len(set(self.actions)):
            raise ValueError("duplicate fault action")
        return self


class Tier(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customers: int = Field(ge=1, le=8)
    orders_per_customer: int = Field(ge=0, le=16)


class Entry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: str
    tier: str
    seeds: list[Annotated[int, Field(ge=0, le=2147483647)]] = Field(min_length=1, max_length=16)
    repeats: int = Field(ge=1, le=10)
    consistency_profile: Literal["default", "extended"] = "default"


class Matrix(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str
    maximum_seconds: int = Field(ge=60, le=7200)
    concurrency: int = Field(ge=1, le=4)
    tiers: dict[str, Tier]
    entries: list[Entry] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def valid_entries(self):
        if any(e.tier not in self.tiers for e in self.entries):
            raise ValueError("unknown workload tier")
        if any(len(e.seeds) != len(set(e.seeds)) for e in self.entries):
            raise ValueError("duplicate seeds")
        return self


def catalog(
    path: str = "research/phase-4/config/scenarios.v1.json",
) -> tuple[str, dict[str, Scenario]]:
    raw = json.loads(Path(path).read_text())
    if raw["version"] != "scenario-catalog-v1":
        raise ValueError("unsupported scenario catalog version")
    parsed = [Scenario.model_validate(item) for item in raw["scenarios"]]
    if len({s.id for s in parsed}) != len(parsed):
        raise ValueError("duplicate scenario ID")
    return raw["version"], {s.id: s for s in parsed}


def matrix(path: str) -> Matrix:
    parsed = Matrix.model_validate_json(Path(path).read_text())
    _, registry = catalog()
    if any(e.scenario not in registry for e in parsed.entries):
        raise ValueError("unknown scenario")
    return parsed
