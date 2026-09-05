"""Deterministic read-only LibreNMS links from verified pipeline entities."""

from __future__ import annotations


def _entity_id(value):
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _device_target(device_id):
    return {
        "kind": "device",
        "label": "LibreNMS'te cihazı aç",
        "entity_id": device_id,
        "href": f"/device/{device_id}",
    }


def _port_target(device_id, port_id):
    return {
        "kind": "port",
        "label": "Port detayını aç",
        "entity_id": port_id,
        "href": f"/device/{device_id}/port/port={port_id}",
    }


def _events_target(device_id):
    return {
        "kind": "events",
        "label": "Event geçmişini aç",
        "entity_id": device_id,
        "href": f"/device/{device_id}/logs/eventlog",
    }


def _alerts_target(device_id):
    return {
        "kind": "alerts",
        "label": "Cihaz alarmlarını aç",
        "entity_id": device_id,
        "href": f"/device/{device_id}/alerts",
    }


def _verified_records(records, device_id, id_key):
    verified = []
    for record in records if isinstance(records, list) else []:
        if not isinstance(record, dict):
            continue
        entity_id = _entity_id(record.get(id_key))
        record_device_id = _entity_id(record.get("device_id"))
        if entity_id is not None and record_device_id == device_id:
            verified.append({**record, id_key: entity_id, "device_id": device_id})
    return verified


def build_navigation_targets(result):
    """Build at most three links without reading answer or user text."""
    route = result.get("route")
    context = result.get("navigation_context")
    if not isinstance(context, dict):
        return []

    device = context.get("device")
    if not isinstance(device, dict):
        return []
    device_id = _entity_id(device.get("device_id"))
    if device_id is None:
        return []

    if route in {"atomic", "device_fact"}:
        return [_device_target(device_id)]
    if route == "ports":
        ports = _verified_records(context.get("ports"), device_id, "port_id")
        return [_port_target(device_id, ports[0]["port_id"])] if len(ports) == 1 else []
    if route == "events":
        return [_events_target(device_id)]
    if route == "alerts":
        return [_alerts_target(device_id)]
    if route not in {"investigation", "historical_investigation"}:
        return []

    targets = []
    ports = _verified_records(context.get("ports"), device_id, "port_id")
    problematic_ports = [
        port for port in ports
        if port.get("ifAdminStatus") == "up" and port.get("ifOperStatus") == "down"
    ]
    if problematic_ports:
        targets.append(_port_target(device_id, problematic_ports[0]["port_id"]))
    if _verified_records(context.get("alerts"), device_id, "alert_id"):
        targets.append(_alerts_target(device_id))
    if _verified_records(context.get("events"), device_id, "event_id"):
        targets.append(_events_target(device_id))
    if not targets:
        targets.append(_device_target(device_id))
    return targets[:3]
