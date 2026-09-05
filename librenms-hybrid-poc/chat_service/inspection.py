"""Bounded, allowlist-only metadata for the local demo inspector."""

from __future__ import annotations


MAX_TOOLS = 12
MAX_FINDINGS = 12
MAX_NAVIGATION_TARGETS = 3

TOOL_ARGS = {
    "list_devices": (),
    "get_device": ("hostname", "device_id"),
    "get_ports": ("device_id",),
    "get_alerts": ("device_id",),
    "get_events": ("device_id", "from_time", "to_time"),
}

FINDING_STRING_FIELDS = {
    "id",
    "type",
    "time_scope",
    "value",
    "ifName",
    "ifAlias",
    "admin_status",
    "oper_status",
    "severity",
    "name",
    "timestamp",
    "from",
    "to",
}
FINDING_ID_FIELDS = {
    "port_id",
    "alert_id",
    "event_id",
    "from_event_id",
    "to_event_id",
}
NAVIGATION_KINDS = {"device", "port", "events", "alerts"}


def _text(value, limit):
    if not isinstance(value, str) or not value:
        return None
    return value[:limit]


def _positive_int(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        parsed = int(value)
        return parsed if parsed > 0 else None
    return None


def _safe_tool_args(name, args):
    if not isinstance(args, dict):
        return {}
    safe = {}
    for key in TOOL_ARGS[name]:
        value = args.get(key)
        if key == "device_id":
            value = _positive_int(value)
        elif key == "hostname":
            value = _text(value, 160)
        else:
            value = _text(value, 64)
        if value is not None:
            safe[key] = value
    return safe


def _tools(calls):
    safe = []
    for call in calls if isinstance(calls, list) else []:
        if not isinstance(call, dict):
            continue
        name = call.get("tool")
        if name not in TOOL_ARGS:
            continue
        safe.append({"name": name, "args": _safe_tool_args(name, call.get("args"))})
        if len(safe) == MAX_TOOLS:
            break
    return safe


def _finding(item):
    if not isinstance(item, dict):
        return None
    safe = {}
    for key in FINDING_STRING_FIELDS:
        value = _text(item.get(key), 240)
        if value is not None:
            safe[key] = value
    for key in FINDING_ID_FIELDS:
        value = _positive_int(item.get(key))
        if value is not None:
            safe[key] = value
    if_index = item.get("ifIndex")
    if isinstance(if_index, str):
        if_index = _text(if_index, 32)
    else:
        if_index = _positive_int(if_index)
    if if_index is not None:
        safe["ifIndex"] = if_index
    references = item.get("evidence_refs")
    if isinstance(references, list):
        safe_refs = [
            value
            for value in (_text(reference, 160) for reference in references[:6])
            if value is not None
        ]
        if safe_refs:
            safe["evidence_refs"] = safe_refs
    return safe if safe.get("type") else None


def _findings(package):
    values = package.get("findings") if isinstance(package, dict) else None
    safe = []
    for item in values if isinstance(values, list) else []:
        bounded = _finding(item)
        if bounded:
            safe.append(bounded)
        if len(safe) == MAX_FINDINGS:
            break
    return safe


def _navigation_targets(targets):
    safe = []
    for target in targets if isinstance(targets, list) else []:
        if not isinstance(target, dict) or target.get("kind") not in NAVIGATION_KINDS:
            continue
        entity_id = _positive_int(target.get("entity_id"))
        label = _text(target.get("label"), 80)
        href = _text(target.get("href"), 240)
        if entity_id is None or label is None or href is None or not href.startswith("/"):
            continue
        safe.append(
            {
                "kind": target["kind"],
                "label": label,
                "entity_id": entity_id,
                "href": href,
            }
        )
        if len(safe) == MAX_NAVIGATION_TARGETS:
            break
    return safe


def _resolution(result):
    context = result.get("navigation_context")
    context = context if isinstance(context, dict) else {}
    resolver = result.get("resolver_output")
    resolver = resolver if isinstance(resolver, dict) else {}

    device = context.get("device")
    if not isinstance(device, dict) and resolver.get("outcome") == "resolved":
        device = resolver.get("device")
    device = device if isinstance(device, dict) else {}

    resolution = {}
    device_id = _positive_int(device.get("device_id"))
    hostname = _text(device.get("hostname"), 160)
    if device_id is not None:
        resolution["device_id"] = device_id
    if hostname is not None:
        resolution["hostname"] = hostname

    ports = context.get("ports")
    if result.get("route") == "ports" and isinstance(ports, list) and len(ports) == 1:
        port = ports[0] if isinstance(ports[0], dict) else {}
        port_device_id = _positive_int(port.get("device_id"))
        if device_id is None or port_device_id == device_id:
            port_id = _positive_int(port.get("port_id"))
            if_index = _positive_int(port.get("ifIndex"))
            if port_id is not None:
                resolution["port_id"] = port_id
            if if_index is not None:
                resolution["ifIndex"] = if_index
    return resolution


def build_inspection(result, navigation_targets):
    """Collect only explicitly approved structured fields from one runtime result."""
    plan_container = result.get("planner_output")
    plan = plan_container.get("plan") if isinstance(plan_container, dict) else None
    plan = plan if isinstance(plan, dict) else {}
    planner = {}
    request_type = _text(plan.get("request_type"), 64)
    intent = _text(plan.get("intent"), 64)
    if request_type is not None:
        planner["request_type"] = request_type
    if intent is not None:
        planner["intent"] = intent

    inspection = {}
    if planner:
        inspection["planner"] = planner
    resolution = _resolution(result)
    if resolution:
        inspection["resolution"] = resolution
    route = _text(result.get("route"), 64)
    if route is not None:
        inspection["route"] = route
    inspection["tools"] = _tools(result.get("tool_calls"))
    inspection["findings"] = _findings(result.get("structured_findings"))
    if isinstance(result.get("synthesis_llm_called"), bool):
        inspection["synthesis_llm_called"] = result["synthesis_llm_called"]
    inspection["navigation_targets"] = _navigation_targets(navigation_targets)
    return inspection
