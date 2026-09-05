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
    hostnames = sorted(
        {
            str(device.get("hostname", "")).strip()
            for device in devices
            if device.get("status") in (1, True, "1", "true", "up")
            and str(device.get("hostname", "")).strip()
        }
    )[:limit]
    return [
        {
            "title": PROMPTS[index % len(PROMPTS)][0].format(hostname=hostname),
            "label": PROMPTS[index % len(PROMPTS)][1],
            "prompt": PROMPTS[index % len(PROMPTS)][2].format(hostname=hostname),
        }
        for index, hostname in enumerate(hostnames)
    ]
