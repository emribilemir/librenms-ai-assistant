import io
import json
import unittest

from chat_service.logging import RestrictedJsonLogger
from chat_service.pipeline_adapter import PipelineAdapter


class SafetyTests(unittest.TestCase):
    def test_rejected_investigation_text_is_never_emitted_or_retained(self):
        rejected = "REJECTED PRIVATE MODEL TEXT"
        def orchestrator(content, observer, is_cancelled):
            observer("planner", "started", None)
            observer("planner", "completed", 1)
            return {"final_answer": "Deterministik güvenli sonuç.", "grounding_trace": {"fallback_reason": "judge_rejected_claims", "generation_output": {"text": rejected}}, "timing_ms": {"planner_ms": 1}}
        result = PipelineAdapter(orchestrator=orchestrator).run("question", lambda *args: None, lambda: False)
        self.assertEqual(result["answer"], "Deterministik güvenli sonuç.")
        self.assertNotIn(rejected, json.dumps(result))
        self.assertTrue(result["used_fallback"])

    def test_json_logs_allow_only_safe_operational_fields(self):
        output = io.StringIO()
        logger = RestrictedJsonLogger(output)
        logger.write(user_id="u", thread_id="t", run_id="r", route="/v1/threads", stage="planner", duration_ms=7, error_code="planner_failed", content="secret", status=500, token="bearer")
        record = json.loads(output.getvalue())
        self.assertEqual(record, {"user_id": "u", "thread_id": "t", "run_id": "r", "route": "/v1/threads", "stage": "planner", "duration_ms": 7, "error_code": "planner_failed"})

