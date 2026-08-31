#!/usr/bin/env python3
"""Deterministic direct-read formatters/selectors for EMR-52.

This module never parses user language. Qwen planner owns semantics; this module
only consumes structured fields and LibreNMS-normalized data.
"""

from __future__ import annotations

import re
import time

DEVICE_FACTS = ("hostname", "model", "uptime", "location", "os")
PORT_FACTS = ("state", "speed", "description")
EMPTY_EVENT_FILTERS = {
    "scope": None,
    "status": None,
    "port_query": None,
    "window_minutes": None,
    "mode": None,
}

_IFOPER_RE = re.compile(r"^ifOperStatus:\s*(up|down)\s*->\s*(up|down)\s*$", re.I)


def duration_text(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    seconds = int(value)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days} gün")
    if hours:
        parts.append(f"{hours} saat")
    if minutes:
        parts.append(f"{minutes} dakika")
    if secs or not parts:
        parts.append(f"{secs} saniye")
    return " ".join(parts)


def format_device_fact(hostname, device, fact):
    device = device if isinstance(device, dict) else {}

    if fact == "hostname":
        value = device.get("sysName") or device.get("hostname")
        return (
            f"{hostname} cihaz adı: {value}."
            if value
            else f"{hostname} için hostname verisi mevcut değil."
        )

    if fact == "model":
        value = device.get("hardware") or device.get("sysDescr")
        return (
            f"{hostname} modeli: {value}."
            if value
            else f"{hostname} için model verisi mevcut değil."
        )

    if fact == "uptime":
        raw = device.get("uptime")
        text = duration_text(raw)
        return (
            f"{hostname} uptime: {text} ({int(raw)} saniye)."
            if text is not None
            else f"{hostname} için uptime verisi mevcut değil."
        )

    if fact == "location":
        raw = device.get("location")
        value = raw.get("location") if isinstance(raw, dict) else raw
        return (
            f"{hostname} location: {value}."
            if value not in (None, "")
            else f"{hostname} için location verisi mevcut değil."
        )

    if fact == "os":
        value = device.get("os")
        version = device.get("version")
        if value:
            suffix = f" ({version})" if version else ""
            return f"{hostname} işletim sistemi: {value}{suffix}."
        return f"{hostname} için os verisi mevcut değil."

    return f"{hostname} için istenen cihaz bilgisi desteklenmiyor."


def format_speed(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return None
    value = float(value)
    for divisor, unit in (
        (1_000_000_000, "Gbps"),
        (1_000_000, "Mbps"),
        (1_000, "Kbps"),
    ):
        if value >= divisor:
            amount = value / divisor
            rendered = str(int(amount)) if amount.is_integer() else f"{amount:g}"
            return f"{rendered} {unit}"
    rendered = str(int(value)) if value.is_integer() else f"{value:g}"
    return f"{rendered} bps"


def format_ports_fact(hostname, ports, fact="state"):
    """Render already-selected LibreNMS ports without interpreting user text."""
    if not ports:
        return f"{hostname} için port verisi bulunmuyor."

    lines = []
    for port in ports:
        label = port.get("ifName", port.get("ifIndex"))

        if fact in (None, "state"):
            lines.append(
                f"Port {label}: admin={port.get('ifAdminStatus')} "
                f"oper={port.get('ifOperStatus')}"
                f"{(' (' + str(port['ifAlias']) + ')') if port.get('ifAlias') else ''}"
            )
            continue

        if fact == "speed":
            speed = format_speed(port.get("ifSpeed"))
            lines.append(f"Port {label}: {speed or 'hız verisi mevcut değil'}")
            continue

        if fact == "description":
            alias = port.get("ifAlias")
            interface = port.get("ifDescr")
            chunks = [f"açıklama={alias}" if alias else "açıklama mevcut değil"]
            if interface:
                chunks.append(f"arayüz={interface}")
            lines.append(f"Port {label}: " + ", ".join(chunks))
            continue

        lines.append(f"Port {label}: istenen port bilgisi desteklenmiyor")

    return f"{hostname} portları:\n" + "\n".join(lines)


def parse_ifoper_transition(event):
    """Parse only LibreNMS' machine-generated interface transition shape."""
    if not isinstance(event, dict) or event.get("type") != "interface":
        return None
    message = event.get("message")
    if not isinstance(message, str):
        return None
    match = _IFOPER_RE.fullmatch(message.strip())
    if not match:
        return None
    return match.group(1).lower(), match.group(2).lower()


def select_event_facts(events, *, scope, status=None, port_id=None):
    """Select authoritative status transitions from normalized LibreNMS events."""
    selected = []
    for event in events or []:
        if not isinstance(event, dict):
            continue

        if scope == "device_status":
            event_status = event.get("type")
            if event_status not in ("up", "down"):
                continue
            if status is None or event_status == status:
                selected.append(event)
            continue

        if scope == "port_status":
            if str(event.get("reference")) != str(port_id):
                continue
            transition = parse_ifoper_transition(event)
            if transition is None:
                continue
            if status is None or transition[1] == status:
                selected.append(event)

    return selected


def event_time_args(window_minutes, *, now_epoch=None):
    """Translate a structured relative window to LibreNMS API from/to params."""
    if window_minutes is None:
        return {}
    now_epoch = time.time() if now_epoch is None else now_epoch
    return {
        "from_time": time.strftime(
            "%Y-%m-%d %H:%M:%S",
            time.localtime(now_epoch - window_minutes * 60),
        ),
        "to_time": time.strftime(
            "%Y-%m-%d %H:%M:%S",
            time.localtime(now_epoch),
        ),
    }


def format_event_fact(hostname, events, filters, *, port=None):
    """Render selected transitions without exposing arbitrary event free text."""
    scope = filters.get("scope")
    status = filters.get("status")
    mode = filters.get("mode")
    window_minutes = filters.get("window_minutes")
    label = "UP" if status == "up" else "DOWN" if status == "down" else "durum değişikliği"
    window_text = (
        f"Son {window_minutes} dakikalık event aralığında"
        if window_minutes is not None
        else "İncelenen event kayıtlarında"
    )

    if not events:
        if scope == "port_status" and port is not None:
            port_label = port.get("ifName", port.get("ifIndex"))
            return f"{window_text} Port {port_label} için {label} kaydı bulunmadı."
        return f"{window_text} {hostname} için {label} kaydı bulunmadı."

    if mode == "latest":
        event = events[0]
        timestamp = event.get("timestamp") or event.get("datetime") or "zaman bilgisi yok"
        if scope == "port_status" and port is not None:
            port_label = port.get("ifName", port.get("ifIndex"))
            transition = parse_ifoper_transition(event)
            target = (transition or (None, status))[1]
            target_label = str(target).upper() if target else "durum değişikliği"
            return (
                f"Port {port_label} en son {timestamp} tarihinde operational olarak "
                f"{target_label} durumuna geçmiş."
            )
        event_status = event.get("type")
        target_label = str(event_status).upper() if event_status in ("up", "down") else label
        return f"{hostname} en son {timestamp} tarihinde {target_label} durumuna geçmiş."

    return f"{window_text} {len(events)} eşleşen {label} kaydı bulundu."
