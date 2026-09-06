"""Bounded user-facing result metadata built only from verified runtime objects."""

from __future__ import annotations


MAX_PORT_ROWS = 24


def _positive_int(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        value = int(value)
    return value if isinstance(value, int) and value > 0 else None


def _text(value, limit):
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:limit] if value else None


def build_structured_result(result):
    """Return a small allowlist-only port result, never parsed from answer text."""
    if result.get("route") != "ports":
        return None
    context = result.get("navigation_context")
    if not isinstance(context, dict):
        return None
    device = context.get("device")
    if not isinstance(device, dict):
        return None
    device_id = _positive_int(device.get("device_id"))
    if device_id is None:
        return None

    rows = []
    for item in context.get("ports") if isinstance(context.get("ports"), list) else []:
        if not isinstance(item, dict) or _positive_int(item.get("device_id")) != device_id:
            continue
        row = {"device_id": device_id}
        port_id = _positive_int(item.get("port_id"))
        if port_id is not None:
            row["port_id"] = port_id
        if_index = _positive_int(item.get("ifIndex"))
        if if_index is not None:
            row["ifIndex"] = if_index
        for source, target, limit in (
            ("ifName", "ifName", 120),
            ("ifDescr", "ifDescr", 180),
            ("ifAlias", "ifAlias", 180),
            ("ifAdminStatus", "admin_status", 32),
            ("ifOperStatus", "oper_status", 32),
        ):
            value = _text(item.get(source), limit)
            if value is not None:
                row[target] = value
        rows.append(row)
        if len(rows) == MAX_PORT_ROWS:
            break
    if not rows:
        return None

    safe_device = {"device_id": device_id}
    hostname = _text(device.get("hostname"), 160)
    if hostname is not None:
        safe_device["hostname"] = hostname
    return {"kind": "ports", "device": safe_device, "ports": rows}
