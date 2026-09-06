"""Safe starter prompts derived from the current LibreNMS inventory."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


PROMPTS = (
    (
        "{hostname} açık mı?",
        "Cihaz durumu",
        "{hostname} açık mı?",
    ),
    (
        "{hostname} port 2 ne durumda?",
        "Port durumu",
        "{hostname} port 2 ne durumda?",
    ),
    (
        "{hostname}'in down portları hangileri?",
        "Down portlar",
        "{hostname}'in down portları hangileri?",
    ),
    (
        "{hostname} üzerinde aktif alarm var mı?",
        "Aktif alarmlar",
        "{hostname} üzerinde aktif alarm var mı?",
    ),
)


def build_suggestions(
    devices: Iterable[Mapping[str, Any]], limit: int = 4
) -> list[dict[str, str]]:
    """Return deterministic prompts for real devices currently marked up."""
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
    suggestions = []
    for index, template in enumerate(PROMPTS[:limit]):
        hostname = hostnames[index] if index < len(hostnames) else None
        if index in (1, 2) and has_port_metadata:
            hostname = port_hostnames[(index - 1) % len(port_hostnames)] if port_hostnames else None
        if not hostname:
            continue
        suggestions.append({
            "title": template[0].format(hostname=hostname),
            "label": template[1],
            "prompt": template[2].format(hostname=hostname),
        })
    return suggestions
