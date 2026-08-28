"""Declarative evidence-plane registry and deterministic routing validation."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

DEFAULT_CLAIM_ID_PATTERN = r"\bCLM-[0-9]{4,12}\b"
SUPPORTED_KINDS = frozenset({"table", "vector_search", "mcp"})


@dataclass(frozen=True)
class PlaneSpec:
    name: str
    description: str
    kind: str
    env_var: str
    lookup_columns: tuple[str, ...] = ()
    mandatory: bool = False
    max_rows: int = 20


DEFAULT_PLANE_SPECS: tuple[PlaneSpec, ...] = (
    PlaneSpec(
        "claim_profile",
        "Core claim facts from claim_360.",
        "table",
        "CLAIM_TABLE",
        ("claim_id",),
        mandatory=True,
    ),
    PlaneSpec(
        "fraud_metrics",
        "Claim-level fraud indicators and metrics from claim_fraud_metrics.",
        "table",
        "CLAIM_FRAUD_METRICS_TABLE",
        ("claim_id",),
        mandatory=True,
    ),
    PlaneSpec(
        "party_profile",
        "Related person or organization details from party_360.",
        "table",
        "PARTY_TABLE",
        ("party_id", "claimant_party_id", "insured_party_id", "claim_id"),
    ),
    PlaneSpec(
        "location_profile",
        "Related location details from location_360.",
        "table",
        "LOCATION_TABLE",
        ("location_id", "loss_location_id", "address_id", "claim_id"),
    ),
    PlaneSpec(
        "policy_profile",
        "Related policy details from policy_360.",
        "table",
        "POLICY_TABLE",
        ("policy_id", "claim_id"),
    ),
    PlaneSpec(
        "document_search",
        "Semantically relevant evidence from the configured AI Search index.",
        "vector_search",
        "VECTOR_SEARCH_INDEX",
    ),
    PlaneSpec(
        "knowledge_graph",
        "Read-only Ontobricks knowledge-graph lookup through the linked MCP App.",
        "mcp",
        "MCP_APP_NAME",
    ),
)

MAX_PLANES_PER_ITERATION = 3
MAX_PLANES_TOTAL = 10


@dataclass(frozen=True)
class PlaneValidation:
    accepted: tuple[str, ...]
    rejected: tuple[str, ...]
    missing_user_input: tuple[str, ...]
    budget_exhausted: bool = False


def _spec_from_dict(payload: Mapping[str, Any]) -> PlaneSpec:
    name = str(payload.get("name", "")).strip().lower()
    kind = str(payload.get("kind", "")).strip().lower()
    env_var = str(payload.get("env_var", "")).strip()
    description = str(payload.get("description", "")).strip()
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        raise ValueError(f"Invalid plane name: {name!r}")
    if kind not in SUPPORTED_KINDS:
        raise ValueError(f"Unsupported plane kind for {name}: {kind!r}")
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", env_var):
        raise ValueError(f"Invalid env_var for {name}: {env_var!r}")
    lookup_columns = tuple(str(value) for value in payload.get("lookup_columns", ()))
    return PlaneSpec(
        name=name,
        description=description or name.replace("_", " "),
        kind=kind,
        env_var=env_var,
        lookup_columns=lookup_columns,
        mandatory=bool(payload.get("mandatory", False)),
        max_rows=max(1, min(int(payload.get("max_rows", 20)), 100)),
    )


def load_plane_specs(config_json: str | None = None) -> dict[str, PlaneSpec]:
    """Load defaults and merge optional additions or overrides by plane name.

    `SUPERVISOR_RESOURCE_CONFIG_JSON` accepts either a JSON list of plane
    objects or `{\"planes\": [...]}`. This keeps the default App configuration
    small while allowing a new resource to be added without editing Python.
    """

    specs = {spec.name: spec for spec in DEFAULT_PLANE_SPECS}
    raw = config_json if config_json is not None else os.getenv("SUPERVISOR_RESOURCE_CONFIG_JSON", "")
    if not raw.strip():
        return specs
    parsed = json.loads(raw)
    planes = parsed.get("planes", []) if isinstance(parsed, dict) else parsed
    if not isinstance(planes, list):
        raise ValueError("Resource configuration must contain a list of planes")
    for payload in planes:
        if not isinstance(payload, dict):
            raise ValueError("Every plane configuration must be a JSON object")
        spec = _spec_from_dict(payload)
        specs[spec.name] = spec
    return specs


def extract_claim_id(text: str) -> str | None:
    """Return a claim identifier using the configurable claim-ID regex."""

    pattern = os.getenv("CLAIM_ID_REGEX", DEFAULT_CLAIM_ID_PATTERN)
    try:
        match = re.search(pattern, text or "", re.IGNORECASE)
    except re.error as exc:
        raise ValueError("CLAIM_ID_REGEX is not a valid regular expression") from exc
    if not match:
        return None
    value = match.group(1) if match.lastindex else match.group(0)
    return value.upper()


def plane_catalog(specs: Mapping[str, PlaneSpec] | None = None) -> str:
    active_specs = specs or load_plane_specs()
    lines = []
    for spec in active_specs.values():
        requirement = " Mandatory baseline." if spec.mandatory else ""
        lines.append(
            f"- {spec.name} [{spec.kind}, {spec.env_var}]: {spec.description}{requirement}"
        )
    return "\n".join(lines)


def validate_planes(
    requested: Iterable[str],
    *,
    already_queried: Iterable[str],
    total_queried: int,
    claim_id: str | None,
    evidence: Any,
    user_text: str,
    plane_specs: Mapping[str, PlaneSpec] | None = None,
    max_per_iteration: int = MAX_PLANES_PER_ITERATION,
    max_total: int = MAX_PLANES_TOTAL,
) -> PlaneValidation:
    """Apply the registry allowlist, de-duplication, and bounded-loop budgets."""

    del evidence, user_text  # Kept in the interface for future dependency policies.
    if not claim_id:
        example = os.getenv("CLAIM_ID_EXAMPLE", "CLM-1001")
        return PlaneValidation((), (), (f"claim_id (for example {example})",))

    specs = plane_specs or load_plane_specs()
    queried = {str(name) for name in already_queried}
    normalized = [str(name).strip().lower() for name in requested]
    rejected = [name for name in normalized if name not in specs]

    if total_queried >= max_total:
        return PlaneValidation((), tuple(rejected), (), budget_exhausted=True)

    candidates: list[str] = []

    def add(name: str) -> None:
        if name not in queried and name not in candidates and len(candidates) < max_per_iteration:
            candidates.append(name)

    for spec in specs.values():
        if spec.mandatory:
            add(spec.name)
    for name in normalized:
        if name in specs:
            add(name)

    remaining = max_total - total_queried
    return PlaneValidation(
        tuple(candidates[:remaining]),
        tuple(rejected),
        (),
        budget_exhausted=False,
    )
