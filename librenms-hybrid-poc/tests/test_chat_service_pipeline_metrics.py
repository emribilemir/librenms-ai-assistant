import unittest
from unittest.mock import patch

import hybrid_poc


class _Backend:
    def trace(self):
        return []


class PipelineMetricTests(unittest.TestCase):
    def test_unsupported_request_skips_resolver_and_uses_monotonic_metrics(self):
        events = []
        def planner(*args, **kwargs):
            return ('{"request_type":"unsupported","intent":"unknown","device_query":null}', "stop", 1)
        with patch.object(hybrid_poc, "ollama_chat", planner), patch.object(hybrid_poc.time, "time", side_effect=AssertionError("wall clock metric")):
            trace = hybrid_poc.orchestrate("yeniden başlat", observer=lambda *event: events.append(event))
        self.assertEqual(trace["route"], "unsupported")
        self.assertNotIn("resolver.started", [event[0] + "." + event[1] for event in events])
        self.assertGreaterEqual(trace["timing_ms"]["total_ms"], 0)

    def test_backend_metric_counts_only_adapter_call_time(self):
        class Resolver:
            @staticmethod
            def resolve_device(query, inventory):
                return {"outcome": "resolved", "device": {"hostname": "sw-1"}}
            @staticmethod
            def format_atomic(hostname, status):
                hybrid_poc.time.sleep(0.03)
                return "yanıt"
        class Backend(_Backend):
            def get_device(self, **kwargs):
                hybrid_poc.time.sleep(0.01)
                return {"status": 1}
        def planner(*args, **kwargs):
            return ('{"request_type":"atomic_fact","intent":"device_status","device_query":"sw-1"}', "stop", 1)
        with patch.object(hybrid_poc, "ollama_chat", planner):
            trace = hybrid_poc.orchestrate("durum", backend=Backend(), resolver_module=Resolver())
        self.assertLess(trace["timing_ms"]["backend_ms"], 25)
