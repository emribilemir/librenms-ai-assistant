"""Safe starter prompts derived from the current LibreNMS inventory."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


PROMPTS = (
    (
        "{hostname} durumunu kontrol et",
        "Güncel cihaz durumu",
        "{hostname} cihazının mevcut durumunu göster.",
    ),
    (
        "{hostname} portlarını incele",
        "Down portlar",
        "{hostname} üzerindeki down portları göster.",
    ),
    (
        "{hostname} alarmlarını kontrol et",
        "Aktif alarmlar",
        "{hostname} için aktif alarmları göster.",
    ),
    (
        "{hostname} olaylarını incele",
        "Son olaylar",
        "{hostname} cihazının son olaylarını göster.",
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
