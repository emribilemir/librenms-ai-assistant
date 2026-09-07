"""Bounded user-facing result metadata built only from verified runtime objects."""

from __future__ import annotations


MAX_RESULT_ROWS = 24


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


def _safe_device(context):
    device = context.get("device")
    if not isinstance(device, dict):
        return None
    device_id = _positive_int(device.get("device_id"))
    if device_id is None:
        return None
    safe = {"device_id": device_id}
    hostname = _text(device.get("hostname"), 160)
    if hostname is not None:
        safe["hostname"] = hostname
    return safe


def _port_result(context, device):
    device_id = device["device_id"]

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
        if len(rows) == MAX_RESULT_ROWS:
            break
    if not rows:
        return None
    return {"kind": "ports", "device": device, "ports": rows}


def _alert_result(context, device):
    device_id = device["device_id"]
    rows = []
    alerts = context.get("alerts")
    for item in alerts if isinstance(alerts, list) else []:
        if not isinstance(item, dict) or _positive_int(item.get("device_id")) != device_id:
            continue
        row = {"device_id": device_id}
        alert_id = _positive_int(item.get("alert_id"))
        if alert_id is not None:
            row["alert_id"] = alert_id
        severity = _text(item.get("severity"), 32)
        if severity is not None:
            row["severity"] = severity
        name = _text(item.get("name") or item.get("rule"), 240)
        if name is not None:
            row["name"] = name
        rows.append(row)
        if len(rows) == MAX_RESULT_ROWS:
            break
    return {"kind": "alerts", "device": device, "alerts": rows}


def build_structured_result(result):
    """Return bounded allowlist-only result metadata, never parsed from answer text."""
    route = result.get("route")
    if route not in {"ports", "alerts"}:
        return None
    context = result.get("navigation_context")
    if not isinstance(context, dict):
        return None
    device = _safe_device(context)
    if device is None:
        return None
    if route == "ports":
        return _port_result(context, device)
    return _alert_result(context, device)
