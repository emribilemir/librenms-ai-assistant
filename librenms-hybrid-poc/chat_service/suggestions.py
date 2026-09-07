"""Safe starter prompts derived from the current LibreNMS inventory."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


CAPABILITIES = (
    {"id": "model", "label": "Model bilgisi", "prompt": "{hostname} modeli ne?"},
    {"id": "active_down_ports", "label": "Bağlantısı düşmüş aktif portlar", "prompt": "{hostname}'ta admin up olup oper down portlar hangileri?", "requires_ports": True},
    {"id": "recent_history", "label": "Son 24 saat incelemesi", "prompt": "{hostname} son 24 saatte neler olmuş?"},
    {"id": "investigation", "label": "Cihaz incelemesi", "prompt": "{hostname}'de ne sorun var?"},
    {"id": "os", "label": "İşletim sistemi", "prompt": "{hostname} işletim sistemi ne?"},
    {"id": "uptime", "label": "Çalışma süresi", "prompt": "{hostname} ne kadar süredir açık?"},
    {"id": "location", "label": "Konum", "prompt": "{hostname}'ın location bilgisi ne?"},
    {"id": "port_speed", "label": "Port hızı", "prompt": "{hostname} port 2 hızı ne?", "requires_ports": True},
    {"id": "port_description", "label": "Port açıklaması", "prompt": "{hostname} port 2 açıklaması ne?", "requires_ports": True},
    {"id": "down_ports", "label": "Down portlar", "prompt": "{hostname}'ın down portları hangileri?", "requires_ports": True},
    {"id": "disabled_ports", "label": "Disabled portlar", "prompt": "{hostname}'ın disabled portları hangileri?", "requires_ports": True},
    {"id": "port_last_down", "label": "Port en son ne zaman down oldu?", "prompt": "{hostname} port 2 en son ne zaman down oldu?", "requires_ports": True},
    {"id": "alerts", "label": "Aktif alarmlar", "prompt": "{hostname} üzerinde aktif alarm var mı?"},
    {"id": "events", "label": "Son olaylar", "prompt": "{hostname} son eventlerini göster"},
    {"id": "status", "label": "Cihaz durumu", "prompt": "{hostname} açık mı?"},
    {"id": "specific_port", "label": "Port durumu", "prompt": "{hostname} port 2 ne durumda?", "requires_ports": True},
)


def _status(value: Any) -> str:
    if value in (1, True, "1", "true", "up"):
        return "up"
    if value in (0, False, "0", "false", "down"):
        return "down"
    return "unknown"


def _eligible_capabilities(has_ports: bool) -> list[dict[str, Any]]:
    return [
        capability for capability in CAPABILITIES
        if has_ports or not capability.get("requires_ports")
    ]


def _contextual_example_pool(hostname: str, has_ports: bool) -> list[str]:
    return [
        capability["prompt"].format(hostname=hostname)
        for capability in _eligible_capabilities(has_ports)
    ]


def build_contextual_examples(
    hostname: str, has_ports: bool = False, limit: int = 3, rotation: int = 0
) -> list[str]:
    """Return one deterministic, compact discovery window for a selected device."""
    examples = _contextual_example_pool(hostname, has_ports)
    window_size = max(0, min(limit, 3, len(examples)))
    if not window_size:
        return []
    offset = (max(0, int(rotation)) * window_size) % len(examples)
    return (examples[offset:] + examples[:offset])[:window_size]


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
            "examples": _contextual_example_pool(
                hostname, int(device.get("port_count") or 0) > 0
            ),
        }
    return sorted(
        by_hostname.values(), key=lambda device: device["hostname"].casefold()
    )[:max(0, min(limit, 200))]


def build_suggestions(
    devices: Iterable[Mapping[str, Any]], limit: int = 4, rotation: int = 0
) -> list[dict[str, str]]:
    """Return a rotating capability-first window for the current live inventory."""
    live_devices = sorted(
        (
            device
            for device in devices
            if str(device.get("hostname", "")).strip()
        ),
        key=lambda device: str(device.get("hostname", "")).strip(),
    )
    up_devices = [
        device for device in live_devices
        if device.get("status") in (1, True, "1", "true", "up")
    ]
    suggestion_devices = up_devices or live_devices
    hostnames = list(dict.fromkeys(
        str(device.get("hostname", "")).strip() for device in suggestion_devices
    ))
    port_hostnames = list(dict.fromkeys(
        str(device.get("hostname", "")).strip()
        for device in up_devices
        if int(device.get("port_count") or 0) > 0
    ))
    if not hostnames:
        return []
    eligible = _eligible_capabilities(bool(port_hostnames))
    if not eligible:
        return []
    window_size = max(0, min(limit, len(eligible)))
    if window_size == 0:
        return []
    offset = (max(0, int(rotation)) * window_size) % len(eligible)
    ordered = eligible[offset:] + eligible[:offset]
    suggestions = []
    for index, capability in enumerate(ordered[:window_size]):
        candidates = port_hostnames if capability.get("requires_ports") else hostnames
        hostname = candidates[index % len(candidates)]
        prompt = capability["prompt"].format(hostname=hostname)
        suggestions.append({
            "title": prompt,
            "label": capability["label"],
            "prompt": prompt,
        })
    return suggestions
