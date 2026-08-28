#!/usr/bin/env python3
"""Deterministic evidence contracts for grounded LibreNMS investigations."""

from datetime import date, datetime, time, timedelta
import re
from zoneinfo import ZoneInfo


ISTANBUL = ZoneInfo("Europe/Istanbul")
SCHEMA_VERSION = 1
PORT_LIMIT = 10
ALERT_LIMIT = 10
HISTORICAL_LIMIT = 5

CLAIM_KIND_TYPES = {
    "current_state": {"device_current_status"},
    "port_issue": {"port_admin_up_oper_down"},
    "alert": {"active_alert"},
    "history": {"historical_device_status", "historical_status_transition"},
    "uncertainty": {"root_cause_unknown"},
    "absence": {
        "no_actionable_port_contradiction",
        "no_active_alert",
        "no_recent_status_transition",
    },
}

_STATUS_EVENT = re.compile(
    r"^Device status changed to (?P<status>Up|Down)(?: from check)?\.?$",
    re.IGNORECASE,
)
_COUNT_VALUES = {
    "sıfır": 0,
    "bir": 1,
    "iki": 2,
    "üç": 3,
    "dört": 4,
    "beş": 5,
    "altı": 6,
    "yedi": 7,
    "sekiz": 8,
    "dokuz": 9,
    "on": 10,
}
_COUNT_TOKEN = r"(?:\d+|sıfır|bir|iki|üç|dört|beş|altı|yedi|sekiz|dokuz|on)"


def _claim_count(value):
    return _COUNT_VALUES.get(value, int(value) if value.isdigit() else None)


def _aware(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=ISTANBUL)
    return value.astimezone(ISTANBUL)


def _parse_boundary(value, *, end_of_day=False):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("absolute event window boundaries must be non-empty strings")
    raw = value.strip()
    if "T" not in raw and " " not in raw:
        parsed_date = date.fromisoformat(raw)
        return datetime.combine(
            parsed_date,
            time(23, 59, 59) if end_of_day else time.min,
            tzinfo=ISTANBUL,
        )
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        parsed_date = date.fromisoformat(raw)
        parsed = datetime.combine(
            parsed_date,
            time(23, 59, 59) if end_of_day else time.min,
            tzinfo=ISTANBUL,
        )
    return _aware(parsed)


def resolve_event_window(spec, request_time):
    """Resolve a validated planner window against one request timestamp."""
    now = _aware(request_time)
    mode = (spec or {}).get("mode", "default_24h")
    if mode == "default_24h":
        start = now - timedelta(hours=24)
        end = now
    elif mode == "relative":
        amount = (spec or {}).get("amount")
        unit = (spec or {}).get("unit")
        if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
            raise ValueError("relative event window amount must be a positive integer")
        units = {
            "hour": timedelta(hours=amount),
            "day": timedelta(days=amount),
            "week": timedelta(weeks=amount),
        }
        if unit not in units:
            raise ValueError("relative event window unit must be hour, day, or week")
        start = now - units[unit]
        end = now
    elif mode == "absolute":
        start = _parse_boundary((spec or {}).get("from"), end_of_day=False)
        end = _parse_boundary((spec or {}).get("to"), end_of_day=True)
        if start > end:
            raise ValueError("absolute event window start must not be after end")
    else:
        raise ValueError("event window mode must be default_24h, relative, or absolute")
    return {"mode": mode, "from": start.isoformat(), "to": end.isoformat()}


def event_window_backend_args(window):
    return {
        "from_time": _parse_boundary(window["from"]).strftime("%Y-%m-%d %H:%M:%S"),
        "to_time": _parse_boundary(window["to"], end_of_day=True).strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
    }


def _parse_event_timestamp(value):
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    try:
        return _aware(datetime.fromisoformat(raw))
    except ValueError:
        return None


def _status_value(value):
    if value in (True, 1, "1", "up", "UP"):
        return "up"
    if value in (False, 0, "0", "down", "DOWN"):
        return "down"
    return "unavailable"


def _numeric_sort(value):
    try:
        return (0, int(value))
    except (TypeError, ValueError):
        return (1, str(value or ""))


def _positive_int(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if not isinstance(value, str) or re.fullmatch(r"[1-9]\d*", value) is None:
        return None
    return int(value)


def _safe_severity(value):
    if value is None:
        return None
    text = str(value)
    return text if re.fullmatch(r"[A-Za-z0-9_-]{1,32}", text) else None


def _truncation(total, included):
    return {"total": total, "included": included, "omitted": max(total - included, 0)}


def _parse_status_events(events, window):
    start = _parse_boundary(window["from"])
    end = _parse_boundary(window["to"], end_of_day=True)
    parsed = []
    invalid_count = 0
    seen_event_ids = set()
    for event in events or []:
        match = _STATUS_EVENT.fullmatch(str(event.get("message") or "").strip())
        timestamp = _parse_event_timestamp(event.get("timestamp") or event.get("datetime"))
        if match is None or timestamp is None or not (start <= timestamp <= end):
            continue
        event_id = _positive_int(event.get("event_id"))
        if event_id is None or event_id in seen_event_ids:
            invalid_count += 1
            continue
        seen_event_ids.add(event_id)
        parsed.append(
            {
                "event_id": event_id,
                "status": match.group("status").casefold(),
                "timestamp": timestamp,
            }
        )
    parsed.sort(key=lambda item: item["timestamp"])
    deduplicated = []
    for event in parsed:
        if deduplicated and deduplicated[-1]["status"] == event["status"]:
            continue
        deduplicated.append(event)
    return deduplicated, invalid_count


def build_investigation_evidence(raw_evidence, event_window):
    """Build a compact, deterministic finding package from backend evidence."""
    raw = raw_evidence if isinstance(raw_evidence, dict) else {}
    device = raw.get("device") if isinstance(raw.get("device"), dict) else {}
    ports = raw.get("ports") if isinstance(raw.get("ports"), list) else []
    alerts = raw.get("alerts") if isinstance(raw.get("alerts"), list) else []
    events = raw.get("events") if isinstance(raw.get("events"), list) else []

    coverage = {}
    source_rows = (
        ("device", [device] if device else [], isinstance(raw.get("device"), dict)),
        ("ports", ports, isinstance(raw.get("ports"), list)),
        ("alerts", alerts, isinstance(raw.get("alerts"), list)),
        ("events", events, isinstance(raw.get("events"), list)),
    )
    for source, records, retrieved in source_rows:
        default_complete = source != "events"
        completeness_marker = getattr(records, "complete", default_complete)
        coverage[source] = {
            "retrieved": retrieved,
            "count": len(records),
            "complete": (
                completeness_marker is True
                if retrieved
                else False
            ),
            "invalid_count": 0,
        }

    findings = []
    device_id = _positive_int(device.get("device_id"))
    hostname = device.get("hostname")
    if device and device_id is not None:
        findings.append(
            {
                "id": f"device:{device_id}:current-status",
                "type": "device_current_status",
                "time_scope": "current",
                "value": _status_value(device.get("status")),
                "evidence_refs": ["device.status"],
            }
        )
    elif device:
        coverage["device"]["complete"] = False
        coverage["device"]["invalid_count"] += 1

    raw_actionable_ports = [
        port
        for port in ports
        if port.get("ifAdminStatus") == "up" and port.get("ifOperStatus") == "down"
    ]
    actionable_ports = []
    seen_port_ids = set()
    seen_ifindexes = set()
    for port in raw_actionable_ports:
        port_id = _positive_int(port.get("port_id"))
        if_index = _positive_int(port.get("ifIndex"))
        duplicate = (
            (port_id is not None and port_id in seen_port_ids)
            or (if_index is not None and if_index in seen_ifindexes)
        )
        if (port_id is None and if_index is None) or duplicate:
            coverage["ports"]["complete"] = False
            coverage["ports"]["invalid_count"] += 1
            continue
        if port_id is not None:
            seen_port_ids.add(port_id)
        if if_index is not None:
            seen_ifindexes.add(if_index)
        canonical_port = dict(port)
        canonical_port["port_id"] = port_id
        canonical_port["ifIndex"] = if_index
        actionable_ports.append(canonical_port)
    actionable_ports.sort(key=lambda port: _numeric_sort(port.get("ifIndex")))
    selected_ports = actionable_ports[:PORT_LIMIT]
    for port in selected_ports:
        port_id = port.get("port_id")
        if_index = port.get("ifIndex")
        identity = f"port_id={port_id}" if port_id is not None else f"ifIndex={if_index}"
        stable_id = (
            f"ifIndex-{if_index}"
            if if_index is not None
            else f"port_id-{port_id}"
        )
        findings.append(
            {
                "id": f"port:{stable_id}:admin-up-oper-down",
                "type": "port_admin_up_oper_down",
                "time_scope": "current",
                "port_id": port_id,
                "ifIndex": str(if_index) if if_index is not None else None,
                "ifName": port.get("ifName"),
                "ifAlias": port.get("ifAlias"),
                "admin_status": "up",
                "oper_status": "down",
                "evidence_refs": [
                    f"ports[{identity}].ifAdminStatus",
                    f"ports[{identity}].ifOperStatus",
                ],
            }
        )
    if (
        coverage["ports"]["retrieved"]
        and coverage["ports"]["complete"]
        and not actionable_ports
    ):
        findings.append(
            {
                "id": "ports:no-actionable-contradiction",
                "type": "no_actionable_port_contradiction",
                "time_scope": "current",
                "evidence_refs": ["coverage.ports"],
            }
        )

    severity_rank = {"critical": 0, "warning": 1}
    valid_alerts = []
    seen_alert_ids = set()
    for alert in alerts:
        alert_id = _positive_int(alert.get("alert_id", alert.get("id")))
        severity = _safe_severity(alert.get("severity"))
        if (
            alert_id is None
            or alert_id in seen_alert_ids
            or (alert.get("severity") is not None and severity is None)
        ):
            coverage["alerts"]["complete"] = False
            coverage["alerts"]["invalid_count"] += 1
            continue
        seen_alert_ids.add(alert_id)
        canonical_alert = dict(alert)
        canonical_alert["alert_id"] = alert_id
        canonical_alert["severity"] = severity
        valid_alerts.append(canonical_alert)
    sorted_alerts = sorted(
        valid_alerts,
        key=lambda alert: (
            severity_rank.get(str(alert.get("severity") or "").casefold(), 2),
            _numeric_sort(alert.get("alert_id", alert.get("id"))),
        ),
    )
    selected_alerts = sorted_alerts[:ALERT_LIMIT]
    for alert in selected_alerts:
        alert_id = alert.get("alert_id", alert.get("id"))
        findings.append(
            {
                "id": f"alert:{alert_id}:active",
                "type": "active_alert",
                "time_scope": "current",
                "alert_id": alert_id,
                "severity": alert.get("severity"),
                "name": alert.get("name") or alert.get("rule") or "Unnamed alert",
                "evidence_refs": [f"alerts[alert_id={alert_id}]"],
            }
        )
    if (
        coverage["alerts"]["retrieved"]
        and coverage["alerts"]["complete"]
        and not valid_alerts
    ):
        findings.append(
            {
                "id": "alerts:none-active",
                "type": "no_active_alert",
                "time_scope": "current",
                "evidence_refs": ["coverage.alerts"],
            }
        )

    status_events, invalid_event_count = _parse_status_events(events, event_window)
    if invalid_event_count:
        coverage["events"]["complete"] = False
        coverage["events"]["invalid_count"] += invalid_event_count
    historical = []
    for event in status_events:
        event_id = event["event_id"]
        historical.append(
            {
                "id": f"event:{event_id}:device-status",
                "type": "historical_device_status",
                "time_scope": "historical",
                "event_id": event_id,
                "value": event["status"],
                "timestamp": event["timestamp"].isoformat(),
                "evidence_refs": [f"events[event_id={event_id}].message"],
                "_sort_timestamp": event["timestamp"],
            }
        )
    previous = None
    for event in status_events:
        if previous is not None and previous["status"] != event["status"]:
            historical.append(
                {
                    "id": f"event-transition:{previous['event_id']}:{event['event_id']}",
                    "type": "historical_status_transition",
                    "time_scope": "historical",
                    "from": previous["status"],
                    "to": event["status"],
                    "from_event_id": previous["event_id"],
                    "to_event_id": event["event_id"],
                    "timestamp": event["timestamp"].isoformat(),
                    "evidence_refs": [
                        f"events[event_id={previous['event_id']}].message",
                        f"events[event_id={event['event_id']}].message",
                    ],
                    "_sort_timestamp": event["timestamp"],
                }
            )
        previous = event
    historical.sort(key=lambda finding: finding["_sort_timestamp"], reverse=True)
    selected_historical = historical[:HISTORICAL_LIMIT]
    for finding in selected_historical:
        finding.pop("_sort_timestamp", None)
        findings.append(finding)
    if (
        coverage["events"]["retrieved"]
        and coverage["events"]["complete"]
        and not any(
            item["type"] == "historical_status_transition" for item in historical
        )
    ):
        findings.append(
            {
                "id": "events:no-recent-transition",
                "type": "no_recent_status_transition",
                "time_scope": "historical",
                "evidence_refs": ["coverage.events", "time_window"],
            }
        )

    findings.append(
        {
            "id": "root-cause:unknown",
            "type": "root_cause_unknown",
            "time_scope": "current",
            "evidence_refs": ["root_cause"],
        }
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "device": {"device_id": device_id, "hostname": hostname},
        "coverage": coverage,
        "time_window": dict(event_window),
        "findings": findings,
        "root_cause": None,
        "truncation": {
            "ports": _truncation(len(actionable_ports), len(selected_ports)),
            "alerts": _truncation(len(sorted_alerts), len(selected_alerts)),
            "historical": _truncation(len(historical), len(selected_historical)),
        },
    }


def generation_schema(package):
    finding_ids = [finding["id"] for finding in package.get("findings") or []]
    return {
        "type": "object",
        "properties": {
            "claims": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "claim_kind": {
                            "type": "string",
                            "enum": list(CLAIM_KIND_TYPES),
                        },
                        "text": {"type": "string", "minLength": 1},
                        "finding_ids": {
                            "type": "array",
                            "minItems": 1,
                            "uniqueItems": True,
                            "items": {"type": "string", "enum": finding_ids},
                        },
                    },
                    "required": ["claim_kind", "text", "finding_ids"],
                },
            }
        },
        "required": ["claims"],
    }


def required_finding_ids(package):
    findings = package.get("findings") or []
    required = []

    def first_id(finding_type):
        return next(
            (item["id"] for item in findings if item.get("type") == finding_type),
            None,
        )

    for finding_type in (
        "device_current_status",
        "port_admin_up_oper_down",
    ):
        finding_id = first_id(finding_type)
        if finding_id is not None:
            required.append(finding_id)
    required.extend(
        item["id"]
        for item in findings
        if item.get("type") == "active_alert"
        and str(item.get("severity") or "").casefold() in ("critical", "warning")
    )
    transition_id = first_id("historical_status_transition")
    if transition_id is not None:
        required.append(transition_id)
    if package.get("root_cause") is None:
        root_cause_id = first_id("root_cause_unknown")
        if root_cause_id is not None:
            required.append(root_cause_id)
    return required


def validate_generation(output, package):
    errors = []
    if not isinstance(output, dict) or set(output) != {"claims"}:
        return ["generation output must contain exactly: claims"]
    claims = output.get("claims")
    if not isinstance(claims, list) or not claims:
        return ["generation claims must be a non-empty array"]
    finding_by_id = {
        finding["id"]: finding for finding in package.get("findings") or []
    }
    covered = set()
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict) or set(claim) != {
            "claim_kind",
            "text",
            "finding_ids",
        }:
            errors.append(f"claim {index} must contain exactly: claim_kind, text, finding_ids")
            continue
        kind = claim.get("claim_kind")
        text_value = claim.get("text")
        finding_ids = claim.get("finding_ids")
        if kind not in CLAIM_KIND_TYPES:
            errors.append(f"claim {index} has invalid claim_kind")
        if not isinstance(text_value, str) or not text_value.strip():
            errors.append(f"claim {index} text must be non-empty")
        if not isinstance(finding_ids, list) or not finding_ids:
            errors.append(f"claim {index} finding_ids must be a non-empty array")
            continue
        if len(finding_ids) != len(set(finding_ids)):
            errors.append(f"claim {index} contains duplicate finding ids")
        referenced = []
        for finding_id in finding_ids:
            finding = finding_by_id.get(finding_id)
            if finding is None:
                errors.append(f"unknown finding id: {finding_id}")
                continue
            referenced.append(finding)
            covered.add(finding_id)
        if kind in CLAIM_KIND_TYPES:
            allowed_types = CLAIM_KIND_TYPES[kind]
            for finding in referenced:
                if finding.get("type") not in allowed_types:
                    errors.append(
                        f"claim {index} kind {kind} cannot reference {finding.get('type')}"
                    )
        folded = text_value.casefold() if isinstance(text_value, str) else ""
        mentioned_severities = set()
        if kind == "alert":
            if "critical" in folded or "kritik" in folded:
                mentioned_severities.add("critical")
            if (
                "warning" in folded
                or re.search(r"\buyarı\s+seviy", folded)
                or re.search(r"\bseviy\w*\s+['\"=: -]*uyarı\b", folded)
                or re.search(r"\bşiddet\w*\s+['\"=: -]*uyarı\b", folded)
            ):
                mentioned_severities.add("warning")
        referenced_severities = {
            str(finding.get("severity") or "").casefold()
            for finding in referenced
            if finding.get("type") == "active_alert"
        }
        for severity in sorted(mentioned_severities - referenced_severities):
            errors.append(
                f"claim {index} mentions severity {severity} without matching evidence"
            )
        if kind == "alert":
            count_matches = re.findall(
                rf"\b({_COUNT_TOKEN})\s+"
                r"(?:(critical|kritik|warning|uyarı)\s+)?(?:aktif\s+)?alarm\b",
                folded,
            )
            severity_aliases = {
                "critical": "critical",
                "kritik": "critical",
                "warning": "warning",
                "uyarı": "warning",
            }
            for count_token, severity_token in count_matches:
                claimed_count = _claim_count(count_token)
                claimed_severity = severity_aliases.get(severity_token)
                matching_alerts = [
                    finding
                    for finding in referenced
                    if finding.get("type") == "active_alert"
                    and (
                        claimed_severity is None
                        or str(finding.get("severity") or "").casefold()
                        == claimed_severity
                    )
                ]
                if claimed_count != len(matching_alerts):
                    label = (
                        f"{claimed_severity} alerts"
                        if claimed_severity is not None
                        else "active alerts"
                    )
                    errors.append(
                        f"claim {index} claims {claimed_count} {label} "
                        f"but references {len(matching_alerts)}"
                    )
        mentioned_ports = set(
            re.findall(r"\bport\s+(\d+)\b", text_value or "", re.IGNORECASE)
        )
        referenced_ports = {
            str(finding.get("ifIndex"))
            for finding in referenced
            if finding.get("type") == "port_admin_up_oper_down"
        }
        for port in sorted(mentioned_ports - referenced_ports):
            errors.append(
                f"claim {index} mentions port {port} without matching evidence"
            )
        if kind == "port_issue":
            for count_token in re.findall(
                rf"\b({_COUNT_TOKEN})\s+(?:adet\s+)?port(?:ta|larda)?\b",
                folded,
            ):
                claimed_count = _claim_count(count_token)
                referenced_count = sum(
                    finding.get("type") == "port_admin_up_oper_down"
                    for finding in referenced
                )
                if claimed_count != referenced_count:
                    errors.append(
                        f"claim {index} claims {claimed_count} affected ports "
                        f"but references {referenced_count}"
                    )
    for finding_id in required_finding_ids(package):
        if finding_id not in covered:
            errors.append(f"missing required finding: {finding_id}")
    return errors


def _model_finding(finding):
    """Project a finding to typed fields; backend-controlled labels never reach Qwen."""
    fields_by_type = {
        "device_current_status": ("value",),
        "port_admin_up_oper_down": (
            "ifIndex",
            "admin_status",
            "oper_status",
        ),
        "active_alert": ("alert_id", "severity"),
        "historical_device_status": ("event_id", "value", "timestamp"),
        "historical_status_transition": (
            "from",
            "to",
            "from_event_id",
            "to_event_id",
            "timestamp",
        ),
        "root_cause_unknown": (),
        "no_actionable_port_contradiction": (),
        "no_active_alert": (),
        "no_recent_status_transition": (),
    }
    finding_type = finding.get("type")
    projected = {
        "id": finding.get("id"),
        "type": finding_type,
        "time_scope": finding.get("time_scope"),
    }
    for field in fields_by_type.get(finding_type, ()):
        value = finding.get(field)
        if field in {
            "port_id",
            "alert_id",
            "event_id",
            "from_event_id",
            "to_event_id",
        }:
            value = _positive_int(value)
        elif field == "ifIndex":
            parsed = _positive_int(value)
            value = str(parsed) if parsed is not None else None
        elif field == "severity":
            value = _safe_severity(value)
        elif field in {"value", "admin_status", "oper_status", "from", "to"}:
            value = value if value in {"up", "down", "unavailable"} else None
        elif field == "timestamp":
            parsed = _parse_event_timestamp(value)
            value = parsed.isoformat() if parsed is not None else None
        projected[field] = value
    return projected


def generation_payload(query, package):
    return {
        "query": query,
        "evidence_contract": {
            "schema_version": package.get("schema_version"),
            "device": {"device_id": (package.get("device") or {}).get("device_id")},
            "coverage": package.get("coverage"),
            "time_window": package.get("time_window"),
            "findings": [
                _model_finding(finding) for finding in package.get("findings") or []
            ],
            "root_cause": package.get("root_cause"),
            "truncation": package.get("truncation"),
        },
        "required_finding_ids": required_finding_ids(package),
    }


def judge_payload(query, generation, package):
    finding_by_id = {
        finding["id"]: finding for finding in package.get("findings") or []
    }
    claims = []
    for index, claim in enumerate(generation.get("claims") or []):
        claims.append(
            {
                "claim_index": index,
                "text": claim["text"],
                "evidence": [
                    _model_finding(finding_by_id[finding_id])
                    for finding_id in claim["finding_ids"]
                    if finding_id in finding_by_id
                ],
            }
        )
    return {
        "query_context_only_not_evidence": query,
        "claims": claims,
    }


def judge_schema(claim_count):
    return {
        "type": "object",
        "properties": {
            "verdicts": {
                "type": "array",
                "minItems": claim_count,
                "maxItems": claim_count,
                "items": {
                    "type": "object",
                    "properties": {
                        "claim_index": {
                            "type": "integer",
                            "enum": list(range(claim_count)),
                        },
                        "verdict": {
                            "type": "string",
                            "enum": [
                                "entailed",
                                "unsupported",
                                "contradicted",
                                "insufficient_evidence",
                            ],
                        },
                    },
                    "required": ["claim_index", "verdict"],
                },
            }
        },
        "required": ["verdicts"],
    }


def validate_judgement(output, claim_count):
    if not isinstance(output, dict) or set(output) != {"verdicts"}:
        return ["judge output must contain exactly: verdicts"]
    verdicts = output.get("verdicts")
    if not isinstance(verdicts, list) or len(verdicts) != claim_count:
        return ["judge must return exactly one verdict per claim"]
    seen = set()
    errors = []
    allowed = {"entailed", "unsupported", "contradicted", "insufficient_evidence"}
    for verdict in verdicts:
        if not isinstance(verdict, dict):
            errors.append("judge verdict must be an object")
            continue
        index = verdict.get("claim_index")
        value = verdict.get("verdict")
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < claim_count:
            errors.append("judge verdict has invalid claim_index")
        elif index in seen:
            errors.append(f"judge returned duplicate claim_index: {index}")
        else:
            seen.add(index)
        if value not in allowed:
            errors.append("judge verdict has invalid verdict")
    if seen != set(range(claim_count)):
        errors.append("judge verdicts do not cover every claim")
    return errors


def format_evidence_fallback(package):
    lines = ["Doğrulanmış bulgular:"]
    hostname = (package.get("device") or {}).get("hostname")
    for finding in package.get("findings") or []:
        finding_type = finding.get("type")
        if finding_type == "device_current_status":
            lines.append(
                f"- device_current_status | hostname={hostname} | status={finding.get('value')}"
            )
        elif finding_type == "port_admin_up_oper_down":
            lines.append(
                "- port_admin_up_oper_down | "
                f"ifIndex={finding.get('ifIndex')} | admin=up | oper=down"
            )
        elif finding_type == "active_alert":
            lines.append(
                "- active_alert | "
                f"alert_id={finding.get('alert_id')} | severity={finding.get('severity')} | "
                f"name={finding.get('name')}"
            )
        elif finding_type == "historical_status_transition":
            lines.append(
                "- historical_status_transition | "
                f"from={finding.get('from')} | to={finding.get('to')} | "
                f"timestamp={finding.get('timestamp')}"
            )
        elif finding_type in {
            "no_actionable_port_contradiction",
            "no_active_alert",
            "no_recent_status_transition",
        }:
            lines.append(f"- {finding_type}")
        elif finding_type == "root_cause_unknown":
            lines.append("- root_cause | value=unknown")
    for category, details in (package.get("truncation") or {}).items():
        if details.get("omitted", 0):
            lines.append(
                f"- truncation | category={category} | omitted={details['omitted']}"
            )
    return "\n".join(lines)
