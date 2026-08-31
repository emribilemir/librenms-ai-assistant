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

PORT_FILTER_SCHEMA = {
    "type": "object",
    "properties": {
        "admin_status": {"type": ["string", "null"], "enum": ["up", "down", None]},
        "oper_status": {"type": ["string", "null"], "enum": ["up", "down", None]},
    },
    "required": ["admin_status", "oper_status"],
}

EMPTY_PORT_FILTERS = {"admin_status": None, "oper_status": None}

DEVICE_FACTS = ("hostname", "model", "uptime", "location", "os")
PORT_FACTS = ("state", "speed", "description")

EMPTY_EVENT_FILTERS = {
    "scope": None,
    "status": None,
    "port_query": None,
    "window_minutes": None,
    "mode": None,
}

EVENT_FILTER_SCHEMA = {
    "type": ["object", "null"],
    "properties": {
        "scope": {
            "type": ["string", "null"],
            "enum": ["device_status", "port_status", None],
        },
        "status": {
            "type": ["string", "null"],
            "enum": ["up", "down", None],
        },
        "port_query": {"type": ["string", "null"]},
        "window_minutes": {
            "type": ["integer", "null"],
            "minimum": 1,
            "maximum": 10080,
        },
        "mode": {
            "type": ["string", "null"],
            "enum": ["latest", "any", None],
        },
    },
    "required": ["scope", "status", "port_query", "window_minutes", "mode"],
}

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
    "device_fact",
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
    "device_fact",
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
    "device_fact": "device_fact",
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
    out.setdefault("device_fact", None)
    out.setdefault("port_query", None)
    port_filters = dict(EMPTY_PORT_FILTERS)
    supplied_port_filters = out.get("port_filters")
    if isinstance(supplied_port_filters, dict):
        for key in port_filters:
            if key in supplied_port_filters:
                port_filters[key] = supplied_port_filters[key]
    out["port_filters"] = port_filters
    out.setdefault("port_fact", None)

    event_filters = dict(EMPTY_EVENT_FILTERS)
    supplied_event_filters = out.get("event_filters")
    if isinstance(supplied_event_filters, dict):
        for key in event_filters:
            if key in supplied_event_filters:
                event_filters[key] = supplied_event_filters[key]
    out["event_filters"] = event_filters

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
    device_fact = plan.get("device_fact")
    port_query = plan.get("port_query")
    port_filters = plan.get("port_filters")
    port_fact = plan.get("port_fact")
    event_filters = plan.get("event_filters")
    event_window = plan.get("event_window")

    if request_type not in REQUEST_TYPES:
        errors.append(f"invalid request_type: {request_type!r}")
    if intent not in INTENTS:
        errors.append(f"invalid intent: {intent!r}")
    if device_query is not None and not isinstance(device_query, str):
        errors.append("device_query must be string or null")

    if request_type == "device_fact":
        if device_fact not in DEVICE_FACTS:
            errors.append(
                "device_fact route requires one of: "
                + ", ".join(DEVICE_FACTS)
            )
    elif device_fact is not None:
        errors.append("non-device_fact route must not contain device_fact")

    if request_type == "ports":
        if port_fact not in (None, *PORT_FACTS):
            errors.append(
                "port_fact must be one of: " + ", ".join(PORT_FACTS)
            )
    elif port_fact is not None:
        errors.append("non-ports route must not contain port_fact")

    if port_query is not None and not isinstance(port_query, str):
        errors.append("port_query must be string or null")

    if request_type == "ports":
        if port_filters is not None and not isinstance(port_filters, dict):
            errors.append("port_filters must be an object or null")
        elif isinstance(port_filters, dict):
            if set(port_filters) != set(EMPTY_PORT_FILTERS):
                errors.append(
                    "port_filters must contain exactly: admin_status, oper_status"
                )
            for key in EMPTY_PORT_FILTERS:
                if port_filters.get(key) not in (None, "up", "down"):
                    errors.append(f"port_filters.{key} must be up, down, or null")
    elif port_query is not None:
        errors.append("non-ports route must not contain port constraints: port_query")
    elif isinstance(port_filters, dict) and any(
        value is not None for value in port_filters.values()
    ):
        errors.append("non-ports route must not contain port constraints: port_filters")
    elif port_filters is not None and not isinstance(port_filters, dict):
        errors.append("port_filters must be an object or null")

    if event_filters is not None:
        if not isinstance(event_filters, dict):
            errors.append("event_filters must be an object or null")
        else:
            if set(event_filters) != set(EMPTY_EVENT_FILTERS):
                errors.append(
                    "event_filters must contain exactly: "
                    "scope, status, port_query, window_minutes, mode"
                )
            else:
                scope = event_filters.get("scope")
                status = event_filters.get("status")
                event_port_query = event_filters.get("port_query")
                window_minutes = event_filters.get("window_minutes")
                event_mode = event_filters.get("mode")

                if scope not in (None, "device_status", "port_status"):
                    errors.append(
                        "event_filters.scope must be device_status, "
                        "port_status, or null"
                    )
                if status not in (None, "up", "down"):
                    errors.append(
                        "event_filters.status must be up, down, or null"
                    )
                if event_port_query is not None and (
                    not isinstance(event_port_query, str)
                    or not event_port_query.strip()
                ):
                    errors.append(
                        "event_filters.port_query must be "
                        "non-empty string or null"
                    )
                if window_minutes is not None and (
                    isinstance(window_minutes, bool)
                    or not isinstance(window_minutes, int)
                    or window_minutes < 1
                    or window_minutes > 10080
                ):
                    errors.append(
                        "event_filters.window_minutes must be "
                        "an integer from 1 to 10080 or null"
                    )
                if event_mode not in (None, "latest", "any"):
                    errors.append(
                        "event_filters.mode must be latest, any, or null"
                    )
                if scope == "port_status" and not event_port_query:
                    errors.append(
                        "port_status event scope requires port_query"
                    )
                if scope is None and any(
                    value is not None
                    for value in (
                        status,
                        event_port_query,
                        window_minutes,
                        event_mode,
                    )
                ):
                    errors.append(
                        "event_filters.scope is required when "
                        "event constraints are present"
                    )

            if request_type != "events" and any(
                value is not None for value in event_filters.values()
            ):
                errors.append(
                    "non-events route must not contain event_filters"
                )

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
