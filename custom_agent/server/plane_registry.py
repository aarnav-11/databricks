"""Allowlisted data planes and deterministic routing validation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable

CLAIM_ID_PATTERN = re.compile(r"\bCLM-[0-9]{4,12}\b", re.IGNORECASE)
VIN_PATTERN = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b", re.IGNORECASE)


@dataclass(frozen=True)
class PlaneSpec:
    name: str
    description: str
    functions: tuple[str, ...]


PLANE_SPECS: dict[str, PlaneSpec] = {
    "snapshot": PlaneSpec(
        "snapshot",
        "Core claim facts and the current deterministic triage score.",
        ("get_claim_snapshot",),
    ),
    "entities": PlaneSpec(
        "entities",
        "Canonical people, policy, vehicle, provider, address, and claim entities.",
        ("get_claim_entities",),
    ),
    "network": PlaneSpec(
        "network",
        "Direct and one-hop typed relationships around the claim.",
        ("get_claim_network",),
    ),
    "documents": PlaneSpec(
        "documents",
        "Attributable claim document snippets and source URIs.",
        ("search_claim_documents",),
    ),
    "memory": PlaneSpec(
        "memory",
        "Prior investigator notes and outcomes for the claim.",
        ("get_case_memory",),
    ),
    "business": PlaneSpec(
        "business",
        "Business vocabulary and active deterministic rule definitions.",
        ("get_business_terms", "get_business_rules"),
    ),
    "model_rules": PlaneSpec(
        "model_rules",
        "Rule-level triggers, score, tier, and model registry metadata.",
        ("evaluate_claim_rules", "score_claim", "get_model_metadata"),
    ),
    "governance": PlaneSpec(
        "governance",
        "Mandatory controls and claim-scoped audit events.",
        ("get_governance_controls", "get_audit_events"),
    ),
    "external_mcp": PlaneSpec(
        "external_mcp",
        "Read-only VIN corroboration through the existing MCP App.",
        ("decode_vin",),
    ),
}

ALLOWED_PLANES = frozenset(PLANE_SPECS)
MAX_PLANES_PER_ITERATION = 3
MAX_PLANES_TOTAL = 10


@dataclass(frozen=True)
class PlaneValidation:
    accepted: tuple[str, ...]
    rejected: tuple[str, ...]
    missing_user_input: tuple[str, ...]
    budget_exhausted: bool = False


def extract_claim_id(text: str) -> str | None:
    """Return the first normalized POC claim identifier in user text."""

    match = CLAIM_ID_PATTERN.search(text or "")
    return match.group(0).upper() if match else None


def extract_vin(text: str) -> str | None:
    """Return the first normalized VIN in text, if present."""

    match = VIN_PATTERN.search(text or "")
    return match.group(0).upper() if match else None


def find_vin(value: Any) -> str | None:
    """Find a VIN in already retrieved entity evidence without trusting text as instructions."""

    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).lower() == "vin" and isinstance(nested, str):
                candidate = extract_vin(nested)
                if candidate:
                    return candidate
            if str(key).lower() == "attributes" and isinstance(nested, str):
                try:
                    parsed = json.loads(nested)
                except json.JSONDecodeError:
                    parsed = None
                candidate = find_vin(parsed)
                if candidate:
                    return candidate
            candidate = find_vin(nested)
            if candidate:
                return candidate
    elif isinstance(value, (list, tuple)):
        for nested in value:
            candidate = find_vin(nested)
            if candidate:
                return candidate
    elif isinstance(value, str):
        return extract_vin(value)
    return None


def plane_catalog() -> str:
    """Render the allowlist for the model router prompt."""

    return "\n".join(
        f"- {spec.name}: {spec.description} Functions: {', '.join(spec.functions)}"
        for spec in PLANE_SPECS.values()
    )


def validate_planes(
    requested: Iterable[str],
    *,
    already_queried: Iterable[str],
    total_queried: int,
    claim_id: str | None,
    evidence: Any,
    user_text: str,
    max_per_iteration: int = MAX_PLANES_PER_ITERATION,
    max_total: int = MAX_PLANES_TOTAL,
) -> PlaneValidation:
    """Apply allowlist, dependency, de-duplication, and budget checks."""

    if not claim_id:
        return PlaneValidation((), (), ("claim_id (for example CLM-1001)",))

    queried = {str(name) for name in already_queried}
    normalized = [str(name).strip().lower() for name in requested]
    rejected: list[str] = [name for name in normalized if name not in ALLOWED_PLANES]
    missing: list[str] = []

    if total_queried >= max_total:
        return PlaneValidation((), tuple(rejected), (), budget_exhausted=True)

    candidates: list[str] = []

    def add(name: str) -> None:
        if name not in queried and name not in candidates and len(candidates) < max_per_iteration:
            candidates.append(name)

    # These are mandatory before the agent may present a claim-specific answer.
    add("snapshot")
    add("governance")

    for name in normalized:
        if name in ALLOWED_PLANES:
            add(name)

    if "external_mcp" in candidates:
        if not (extract_vin(user_text) or find_vin(evidence)):
            candidates.remove("external_mcp")
            missing.append("vehicle VIN before external VIN corroboration")

    remaining = max_total - total_queried
    if len(candidates) > remaining:
        candidates = candidates[:remaining]

    return PlaneValidation(tuple(candidates), tuple(rejected), tuple(missing))
