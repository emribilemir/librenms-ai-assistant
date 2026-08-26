#!/usr/bin/env python3
"""Structured semantic-plan contract.

Qwen owns natural-language interpretation. This module only defines, normalizes,
and validates the planner's structured output; it never parses user language.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

DEVICE_FILTER_SCHEMA = {
    "type": "object",
    "properties": {
        "brand": {"type": ["string", "null"]},
        "family": {"type": ["string", "null"]},
        "port_count": {"type": ["integer", "null"], "minimum": 1},
        "poe": {"type": ["boolean", "null"]},
    },
    "required": ["brand", "family", "port_count", "poe"],
}

EMPTY_FILTERS = {"brand": None, "family": None, "port_count": None, "poe": None}

REQUEST_TYPES = (
    "atomic_fact",
    "ports",
    "alerts",
    "events",
    "device_set",
    "investigation",
    "historical_investigation",
    "unsupported",
)

INTENTS = (
    "device_status",
    "device_ports",
    "device_alerts",
    "device_events",
    "device_set",
    "investigation",
    "historical_status",
    "unsupported",
    "unknown",
)

ROUTE_TO_INTENT = {
    "atomic_fact": "device_status",
    "ports": "device_ports",
    "alerts": "device_alerts",
    "events": "device_events",
    "device_set": "device_set",
    "investigation": "investigation",
    "historical_investigation": "historical_status",
}


def normalize_plan_filters(plan: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy with a complete filter object for compatibility callers."""
    out = dict(plan)
    filters = dict(EMPTY_FILTERS)
    supplied = out.get("device_filters")
    if isinstance(supplied, dict):
        for key in filters:
            if key in supplied:
                filters[key] = supplied[key]
    out["device_filters"] = filters
    return out


def validate_plan(plan: Any) -> Tuple[bool, list[str]]:
    """Validate structure and cross-field contracts without semantic repair."""
    errors: list[str] = []
    if not isinstance(plan, dict):
        return False, ["planner output is not a JSON object"]

    required = ("request_type", "intent", "device_query", "device_filters")
    for key in required:
        if key not in plan:
            errors.append(f"missing required field: {key}")

    request_type = plan.get("request_type")
    intent = plan.get("intent")
    device_query = plan.get("device_query")
    filters = plan.get("device_filters")

    if request_type not in REQUEST_TYPES:
        errors.append(f"invalid request_type: {request_type!r}")
    if intent not in INTENTS:
        errors.append(f"invalid intent: {intent!r}")
    if device_query is not None and not isinstance(device_query, str):
        errors.append("device_query must be string or null")

    if not isinstance(filters, dict):
        errors.append("device_filters must be an object")
    else:
        if set(filters) != set(EMPTY_FILTERS):
            errors.append(
                "device_filters must contain exactly: brand, family, port_count, poe"
            )
        brand = filters.get("brand")
        family = filters.get("family")
        port_count = filters.get("port_count")
        poe = filters.get("poe")
        if brand is not None and not isinstance(brand, str):
            errors.append("device_filters.brand must be string or null")
        if family is not None and not isinstance(family, str):
            errors.append("device_filters.family must be string or null")
        if port_count is not None and (
            isinstance(port_count, bool)
            or not isinstance(port_count, int)
            or port_count < 1
        ):
            errors.append("device_filters.port_count must be positive integer or null")
        if poe is not None and not isinstance(poe, bool):
            errors.append("device_filters.poe must be boolean or null")

    expected_intent = ROUTE_TO_INTENT.get(request_type)
    if expected_intent and intent != expected_intent:
        errors.append(
            f"request_type {request_type!r} requires intent {expected_intent!r}"
        )

    if request_type != "device_set" and isinstance(filters, dict):
        non_null = [key for key, value in filters.items() if value is not None]
        if non_null:
            errors.append(
                "non-device_set route must not contain product filters: "
                + ", ".join(non_null)
            )

    if request_type == "device_set" and isinstance(filters, dict):
        has_query = isinstance(device_query, str) and bool(device_query.strip())
        if not has_query and not any(value is not None for value in filters.values()):
            errors.append("device_set must contain a device_query or at least one filter")

    if request_type not in ("device_set", "unsupported"):
        has_query = isinstance(device_query, str) and bool(device_query.strip())
        if request_type in REQUEST_TYPES and not has_query:
            errors.append(f"{request_type} requires a non-empty device_query")

    return not errors, errors
