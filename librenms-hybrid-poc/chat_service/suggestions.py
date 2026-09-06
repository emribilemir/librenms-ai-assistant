"""Safe starter prompts derived from the current LibreNMS inventory."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


CAPABILITIES = (
    {"id": "status", "label": "Cihaz durumu", "prompt": "{hostname} açık mı?"},
    {"id": "specific_port", "label": "Port durumu", "prompt": "{hostname} port 2 ne durumda?", "requires_ports": True},
    {"id": "alerts", "label": "Aktif alarmlar", "prompt": "{hostname} üzerinde aktif alarm var mı?"},
    {"id": "events", "label": "Son olaylar", "prompt": "{hostname} son eventlerini göster"},
    {"id": "investigation", "label": "Cihaz incelemesi", "prompt": "{hostname}'da ne sorun var?"},
    {"id": "down_ports", "label": "Down portlar", "prompt": "{hostname}'ın down portları hangileri?", "requires_ports": True},
    {"id": "location", "label": "Konum", "prompt": "{hostname}'ın location bilgisi ne?"},
    {"id": "uptime", "label": "Çalışma süresi", "prompt": "{hostname} ne kadar süredir açık?"},
)


def _status(value: Any) -> str:
    if value in (1, True, "1", "true", "up"):
        return "up"
    if value in (0, False, "0", "false", "down"):
        return "down"
    return "unknown"


def build_contextual_examples(hostname: str, limit: int = 3) -> list[str]:
    """Build a small optional discovery set from verified capabilities."""
    by_id = {capability["id"]: capability for capability in CAPABILITIES}
    return [
        by_id[capability_id]["prompt"].format(hostname=hostname)
        for capability_id in ("status", "alerts", "investigation")
    ][:max(0, min(limit, 3))]


def build_picker_devices(
    devices: Iterable[Mapping[str, Any]], limit: int = 200
) -> list[dict[str, Any]]:
    """Expose only bounded fields from the current live device read."""
    by_hostname = {}
    for device in devices:
        hostname = str(device.get("hostname", "")).strip()[:160]
        if not hostname:
            continue
        key = hostname.casefold()
        if key in by_hostname:
            continue
        by_hostname[key] = {
            "hostname": hostname,
            "status": _status(device.get("status")),
            "examples": build_contextual_examples(hostname),
        }
    return sorted(
        by_hostname.values(), key=lambda device: device["hostname"].casefold()
    )[:max(0, min(limit, 200))]


def build_suggestions(
    devices: Iterable[Mapping[str, Any]], limit: int = 4, rotation: int = 0
) -> list[dict[str, str]]:
    """Return a rotating capability-first window for real devices marked up."""
    up_devices = sorted(
        (
            device
            for device in devices
            if device.get("status") in (1, True, "1", "true", "up")
            and str(device.get("hostname", "")).strip()
        ),
        key=lambda device: str(device.get("hostname", "")).strip(),
    )
    hostnames = list(dict.fromkeys(
        str(device.get("hostname", "")).strip() for device in up_devices
    ))
    has_port_metadata = any("port_count" in device for device in up_devices)
    port_hostnames = list(dict.fromkeys(
        str(device.get("hostname", "")).strip()
        for device in up_devices
        if int(device.get("port_count") or 0) > 0
    ))
    if not hostnames:
        return []
    eligible = [
        capability for capability in CAPABILITIES
        if not capability.get("requires_ports") or not has_port_metadata or port_hostnames
    ]
    if not eligible:
        return []
    window_size = max(0, min(limit, len(eligible)))
    if window_size == 0:
        return []
    offset = (max(0, int(rotation)) * window_size) % len(eligible)
    ordered = eligible[offset:] + eligible[:offset]
    suggestions = []
    for index, capability in enumerate(ordered[:window_size]):
        candidates = port_hostnames if capability.get("requires_ports") and has_port_metadata else hostnames
        hostname = candidates[index % len(candidates)]
        prompt = capability["prompt"].format(hostname=hostname)
        suggestions.append({
            "title": prompt,
            "label": capability["label"],
            "prompt": prompt,
        })
    return suggestions
