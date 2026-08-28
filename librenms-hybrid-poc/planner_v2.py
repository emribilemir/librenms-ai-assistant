#!/usr/bin/env python3
"""Structured semantic-plan contract.

Qwen owns natural-language interpretation. This module only defines, normalizes,
and validates the planner's structured output; it never parses user language.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Dict, Tuple
from zoneinfo import ZoneInfo

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

EVENT_WINDOW_SCHEMA = {
    "type": ["object", "null"],
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["default_24h", "relative", "absolute"],
        },
        "amount": {"type": "integer", "minimum": 1},
        "unit": {"type": "string", "enum": ["hour", "day", "week"]},
        "from": {"type": "string"},
        "to": {"type": "string"},
    },
}

REQUEST_TYPES = (
    "atomic_fact",
    "ports",
    "alerts",
    "events",
    "device_set",
    "device_set_status",
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
    "device_set_status",
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
    "device_set_status": "device_set_status",
    "investigation": "investigation",
    "historical_investigation": "historical_status",
}


def _parse_absolute_boundary(value: Any, *, end_of_day: bool = False):
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    local_zone = ZoneInfo("Europe/Istanbul")
    try:
        if "T" not in raw and " " not in raw:
            parsed_date = date.fromisoformat(raw)
            return datetime.combine(
                parsed_date,
                time(23, 59, 59) if end_of_day else time.min,
                tzinfo=local_zone,
            )
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(local_zone)
    except ValueError:
        return None


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
    out.setdefault("event_window", None)
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
    event_window = plan.get("event_window")

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

    set_routes = ("device_set", "device_set_status")
    if request_type not in set_routes and isinstance(filters, dict):
        non_null = [key for key, value in filters.items() if value is not None]
        if non_null:
            errors.append(
                "non-device_set route must not contain product filters: "
                + ", ".join(non_null)
            )

    if request_type in set_routes and isinstance(filters, dict):
        has_query = isinstance(device_query, str) and bool(device_query.strip())
        if not has_query and not any(value is not None for value in filters.values()):
            errors.append(
                f"{request_type} must contain a device_query or at least one filter"
            )

    if request_type not in (*set_routes, "unsupported"):
        has_query = isinstance(device_query, str) and bool(device_query.strip())
        if request_type in REQUEST_TYPES and not has_query:
            errors.append(f"{request_type} requires a non-empty device_query")

    investigation_routes = ("investigation", "historical_investigation")
    if event_window is not None and request_type not in investigation_routes:
        errors.append("event_window is only valid for investigation routes")
    if event_window is not None:
        if not isinstance(event_window, dict):
            errors.append("event_window must be an object or null")
        else:
            mode = event_window.get("mode")
            expected_keys = {
                "default_24h": {"mode"},
                "relative": {"mode", "amount", "unit"},
                "absolute": {"mode", "from", "to"},
            }
            if mode not in expected_keys:
                errors.append(
                    "event_window.mode must be default_24h, relative, or absolute"
                )
            elif set(event_window) != expected_keys[mode]:
                field_order = ("mode", "from", "to", "amount", "unit")
                fields = ", ".join(
                    sorted(expected_keys[mode], key=field_order.index)
                )
                errors.append(
                    f"{mode} event_window must contain exactly: {fields}"
                )
            if mode == "relative":
                amount = event_window.get("amount")
                if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
                    errors.append(
                        "relative event_window.amount must be a positive integer"
                    )
                if event_window.get("unit") not in ("hour", "day", "week"):
                    errors.append("relative event_window.unit must be hour, day, or week")
            if mode == "absolute":
                parsed_boundaries = {}
                for key in ("from", "to"):
                    value = event_window.get(key)
                    if not isinstance(value, str) or not value.strip():
                        errors.append(
                            f"absolute event_window.{key} must be a non-empty string"
                        )
                        continue
                    parsed = _parse_absolute_boundary(
                        value, end_of_day=(key == "to")
                    )
                    if parsed is None:
                        errors.append(
                            f"absolute event_window.{key} must be an ISO date "
                            "or timezone-aware datetime"
                        )
                    else:
                        parsed_boundaries[key] = parsed
                if (
                    set(parsed_boundaries) == {"from", "to"}
                    and parsed_boundaries["from"] > parsed_boundaries["to"]
                ):
                    errors.append("absolute event_window.from must not be after to")

    return not errors, errors
