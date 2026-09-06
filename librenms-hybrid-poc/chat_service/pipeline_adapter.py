"""Safe translation between the hybrid orchestrator and the chat transport."""

from __future__ import annotations

import os

from librenms_backend import LibreNMSBackend

from .inspection import build_inspection
from .navigation import build_navigation_targets


_METRICS = ("planner_ms", "resolver_ms", "backend_ms", "synthesis_ms", "time_to_first_token_ms", "time_to_first_visible_chunk_ms", "total_ms")


class PipelineAdapter:
    def __init__(self, orchestrator=None, device_source=None, ports_source=None, include_inspection=None):
        self._orchestrator = orchestrator
        self._device_source = device_source
        self._ports_source = ports_source
        self._include_inspection = (
            os.environ.get("AI_DEMO_MODE") == "1"
            if include_inspection is None
            else bool(include_inspection)
        )

    def list_devices(self):
        source = self._device_source
        if source is None:
            source = LibreNMSBackend().list_devices
        return source()

    def list_suggestion_devices(self):
        source = self._device_source
        ports_source = self._ports_source
        if source is None:
            backend = LibreNMSBackend()
            source = backend.list_devices
            ports_source = backend.get_ports
        devices = [dict(device) for device in source()]
        if ports_source is None:
            return devices
        up_devices = sorted(
            (
                device for device in devices
                if device.get("status") in (1, True, "1", "true", "up")
                and str(device.get("hostname", "")).strip()
            ),
            key=lambda device: str(device.get("hostname", "")).strip(),
        )
        for device in up_devices[1:3]:
            device_id = device.get("device_id")
            device["port_count"] = (
                len(ports_source(device_id=device_id))
                if device_id is not None else 0
            )
        return devices

    def run(self, content, observer, is_cancelled):
        if is_cancelled():
            return {"cancelled": True, "metrics": self._metrics({})}
        last_stage = "internal"
        completed_metrics = {}

        def observed(stage, state, duration):
            nonlocal last_stage
            last_stage = stage
            if state == "completed":
                metric = {"planner": "planner_ms", "resolver": "resolver_ms", "librenms": "backend_ms", "synthesis": "synthesis_ms"}.get(stage)
                if metric is not None:
                    completed_metrics[metric] = duration
            observer(stage, state, duration)

        try:
            if self._orchestrator is None:
                import live_query
                result = live_query.run_live_query(
                    content,
                    backend=LibreNMSBackend(),
                    planner_schema="gold",
                    observer=observed,
                    is_cancelled=is_cancelled,
                )
            else:
                result = self._orchestrator(content, observed, is_cancelled)
        except Exception:
            return {
                "error": self._error(last_stage),
                "metrics": self._metrics(completed_metrics),
            }
        if result.get("cancelled") or is_cancelled():
            return {"cancelled": True, "metrics": self._metrics(result.get("timing_ms", {}))}
        if result.get("planner_failure"):
            return {
                "error": self._error("planner", "planner_invalid_output"),
                "metrics": self._metrics(result.get("timing_ms", {})),
            }
        trace = result.get("grounding_trace") or {}
        timing = result.get("timing_ms", {})
        response = {
            "answer": result.get("final_answer") or result.get("answer") or "İşlem desteklenmiyor.",
            "used_fallback": bool(trace.get("fallback_reason")),
            "metrics": self._metrics(timing if timing else result.get("metrics", {})),
        }
        navigation_targets = build_navigation_targets(result)
        if navigation_targets:
            response["navigation_targets"] = navigation_targets
        if self._include_inspection:
            response["inspection"] = build_inspection(result, navigation_targets)
        return response

    @staticmethod
    def _error(stage, code=None):
        stage = stage if stage in {"planner", "resolver", "librenms", "synthesis", "storage"} else "internal"
        messages = {
            "planner": "Plan oluşturulamadı.",
            "resolver": "Cihaz çözümlenemedi.",
            "librenms": "LibreNMS verisi alınamadı.",
            "synthesis": "Yanıt güvenle oluşturulamadı.",
            "storage": "Sonuç kaydedilemedi.",
            "internal": "İşlem tamamlanamadı.",
        }
        return {
            "stage": stage,
            "code": code or f"{stage}_failed",
            "retryable": True,
            "message": messages[stage],
        }

    @staticmethod
    def _metrics(timing):
        metrics = {
            "planner_ms": timing.get("planner_ms"),
            "resolver_ms": timing.get("resolver_ms", timing.get("resolve_ms")),
            "backend_ms": timing.get("backend_ms"),
            "synthesis_ms": timing.get("synthesis_ms"),
            "time_to_first_token_ms": timing.get("time_to_first_token_ms"),
            "time_to_first_visible_chunk_ms": timing.get("time_to_first_visible_chunk_ms"),
            "total_ms": timing.get("total_ms"),
        }
        for key, value in metrics.items():
            if value is not None:
                metrics[key] = max(0, int(value))
        return metrics
