import sys
import types
import unittest
from unittest.mock import patch

from chat_service.pipeline_adapter import PipelineAdapter
from chat_service.runs import ActiveRunRegistry, RunConflictError


class CancellationTests(unittest.TestCase):
    def test_active_run_blocks_only_its_own_thread(self):
        registry = ActiveRunRegistry()
        registry.start("thread-a", "run-a")
        with self.assertRaises(RunConflictError):
            registry.start("thread-a", "run-b")
        registry.start("thread-b", "run-b")

    def test_cancellation_prevents_later_pipeline_stages(self):
        entered = []
        def orchestrator(content, observer, is_cancelled):
            for stage in ("planner", "resolver", "librenms"):
                if is_cancelled():
                    return {"cancelled": True}
                entered.append(stage)
                observer(stage, "started", None)
                observer(stage, "completed", 1)
                if stage == "planner":
                    cancelled[0] = True
            return {"final_answer": "unreachable", "timing_ms": {}}
        cancelled = [False]
        result = PipelineAdapter(orchestrator=orchestrator).run("q", lambda *args: None, lambda: cancelled[0])
        self.assertTrue(result["cancelled"])
        self.assertEqual(entered, ["planner"])

    def test_default_adapter_uses_live_backend_and_gold_orchestration(self):
        calls = []
        backend = object()
        fake_live_query = types.SimpleNamespace(
            run_live_query=lambda content, **kwargs: calls.append((content, kwargs)) or {
                "final_answer": "ok", "timing_ms": {}
            }
        )
        with patch("chat_service.pipeline_adapter.LibreNMSBackend", return_value=backend), \
             patch.dict(sys.modules, {"live_query": fake_live_query}):
            result = PipelineAdapter().run("soru", lambda *args: None, lambda: False)
        self.assertEqual(result["answer"], "ok")
        self.assertIs(calls[0][1]["backend"], backend)
        self.assertEqual(calls[0][1]["planner_schema"], "gold")

    def test_planner_failure_is_a_stage_specific_error_not_a_safe_success(self):
        result = PipelineAdapter(orchestrator=lambda *args: {
            "planner_failure": True, "planner_errors": ["invalid JSON"],
            "timing_ms": {"planner_ms": 1, "total_ms": 1},
        }).run("q", lambda *args: None, lambda: False)
        self.assertEqual(result["error"], {
            "stage": "planner", "code": "planner_invalid_output",
            "retryable": True, "message": "Plan oluşturulamadı.",
        })

    def test_pipeline_exception_preserves_completed_stage_metrics(self):
        def broken(content, observer, is_cancelled):
            observer("planner", "started", None)
            observer("planner", "completed", 17)
            raise RuntimeError("backend unavailable")
        result = PipelineAdapter(orchestrator=broken).run("q", lambda *args: None, lambda: False)
        self.assertEqual(result["error"]["stage"], "planner")
        self.assertEqual(result["metrics"]["planner_ms"], 17)
