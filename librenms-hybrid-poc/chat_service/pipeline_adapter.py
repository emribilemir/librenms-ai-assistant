"""Safe translation between the hybrid orchestrator and the chat transport."""

from __future__ import annotations

import time


_METRICS = ("planner_ms", "resolver_ms", "backend_ms", "synthesis_ms", "time_to_first_token_ms", "time_to_first_visible_chunk_ms", "total_ms")


class PipelineAdapter:
    def __init__(self, orchestrator=None):
        self._orchestrator = orchestrator

    def run(self, content, observer, is_cancelled):
        if is_cancelled():
            return {"cancelled": True, "metrics": self._metrics({})}
        if self._orchestrator is None:
            import hybrid_poc
            result = hybrid_poc.orchestrate(content, observer=observer, is_cancelled=is_cancelled)
        else:
            result = self._orchestrator(content, observer, is_cancelled)
        if result.get("cancelled") or is_cancelled():
            return {"cancelled": True, "metrics": self._metrics(result.get("timing_ms", {}))}
        trace = result.get("grounding_trace") or {}
        timing = result.get("timing_ms", {})
        return {
            "answer": result.get("final_answer") or result.get("answer") or "İşlem desteklenmiyor.",
            "used_fallback": bool(trace.get("fallback_reason")),
            "metrics": self._metrics(timing if timing else result.get("metrics", {})),
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

