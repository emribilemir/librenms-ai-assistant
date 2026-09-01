import unittest

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

