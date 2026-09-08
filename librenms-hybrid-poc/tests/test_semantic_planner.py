#!/usr/bin/env python3
"""Small offline tests for semantic-plan ownership and validation."""

import importlib.util
import json
import os
import unittest
from unittest.mock import patch

import hybrid_poc
import planner_v2

POC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = os.path.join(POC, "hybrid-gold-v3")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


resolver_v5 = load_module(
    "resolver_v5_test", os.path.join(POC, "resolver_v5.py")
)
dummy_backend = load_module(
    "dummy_backend_test", os.path.join(GOLD, "dummy_backend.py")
)
with open(os.path.join(GOLD, "dummy_inventory.json"), encoding="utf-8") as stream:
    INVENTORY = json.load(stream)


class SemanticPlanContractTests(unittest.TestCase):
    def test_accepts_relative_event_window_on_investigation(self):
        plan = {
            "request_type": "investigation",
            "intent": "investigation",
            "device_query": "lab-j9772a-01",
            "device_filters": dict(planner_v2.EMPTY_FILTERS),
            "event_window": {"mode": "relative", "amount": 7, "unit": "day"},
        }

        self.assertEqual(planner_v2.validate_plan(plan), (True, []))

    def test_rejects_event_window_on_direct_events_route(self):
        plan = {
            "request_type": "events",
            "intent": "device_events",
            "device_query": "lab-j9772a-01",
            "device_filters": dict(planner_v2.EMPTY_FILTERS),
            "event_window": {"mode": "relative", "amount": 7, "unit": "day"},
        }

        valid, errors = planner_v2.validate_plan(plan)

        self.assertFalse(valid)
        self.assertIn("event_window is only valid for investigation routes", errors)

    def test_rejects_invalid_absolute_event_window_shape(self):
        plan = {
            "request_type": "historical_investigation",
            "intent": "historical_status",
            "device_query": "lab-j9772a-01",
            "device_filters": dict(planner_v2.EMPTY_FILTERS),
            "event_window": {"mode": "absolute", "from": "2026-08-20"},
        }

        valid, errors = planner_v2.validate_plan(plan)

        self.assertFalse(valid)
        self.assertIn("absolute event_window must contain exactly: mode, from, to", errors)

    def test_rejects_non_iso_absolute_event_window_before_backend_execution(self):
        plan = {
            "request_type": "historical_investigation",
            "intent": "historical_status",
            "device_query": "lab-j9772a-01",
            "device_filters": dict(planner_v2.EMPTY_FILTERS),
            "event_window": {"mode": "absolute", "from": "dün", "to": "bugün"},
        }

        valid, errors = planner_v2.validate_plan(plan)

        self.assertFalse(valid)
        self.assertIn("absolute event_window.from must be an ISO date or timezone-aware datetime", errors)
        self.assertIn("absolute event_window.to must be an ISO date or timezone-aware datetime", errors)

    def test_rejects_absolute_event_window_with_reversed_boundaries(self):
        plan = {
            "request_type": "historical_investigation",
            "intent": "historical_status",
            "device_query": "lab-j9772a-01",
            "device_filters": dict(planner_v2.EMPTY_FILTERS),
            "event_window": {
                "mode": "absolute",
                "from": "2026-08-21T12:00:00+03:00",
                "to": "2026-08-20T12:00:00+03:00",
            },
        }

        valid, errors = planner_v2.validate_plan(plan)

        self.assertFalse(valid)
        self.assertIn("absolute event_window.from must not be after to", errors)

    def test_accepts_valid_device_set_status_plan_with_reference(self):
        plan = {
            "request_type": "device_set_status",
            "intent": "device_set_status",
            "device_query": "J4850A",
            "device_filters": dict(planner_v2.EMPTY_FILTERS),
        }
        self.assertEqual(planner_v2.validate_plan(plan), (True, []))

    def test_accepts_valid_device_set_status_plan_with_filters(self):
        plan = {
            "request_type": "device_set_status",
            "intent": "device_set_status",
            "device_query": None,
            "device_filters": {
                "brand": None,
                "family": "2530",
                "port_count": 48,
                "poe": False,
            },
        }
        self.assertEqual(planner_v2.validate_plan(plan), (True, []))

    def test_rejects_empty_device_set_status_plan(self):
        plan = {
            "request_type": "device_set_status",
            "intent": "device_set_status",
            "device_query": None,
            "device_filters": dict(planner_v2.EMPTY_FILTERS),
        }
        valid, errors = planner_v2.validate_plan(plan)
        self.assertFalse(valid)
        self.assertIn(
            "device_set_status must contain a device_query or at least one filter",
            errors,
        )

    def test_accepts_valid_device_set_plan(self):
        plan = {
            "request_type": "device_set",
            "intent": "device_set",
            "device_query": None,
            "device_filters": {
                "brand": "HP ProCurve",
                "family": "2530",
                "port_count": 48,
                "poe": False,
            },
        }
        self.assertEqual(planner_v2.validate_plan(plan), (True, []))

    def test_rejects_route_intent_mismatch(self):
        plan = {
            "request_type": "ports",
            "intent": "device_set",
            "device_query": "J9774A",
            "device_filters": dict(planner_v2.EMPTY_FILTERS),
        }
        valid, errors = planner_v2.validate_plan(plan)
        self.assertFalse(valid)
        self.assertIn("request_type 'ports' requires intent 'device_ports'", errors)

    def test_rejects_product_filters_on_non_device_set_route(self):
        plan = {
            "request_type": "atomic_fact",
            "intent": "device_status",
            "device_query": "J9774A",
            "device_filters": {
                "brand": None,
                "family": None,
                "port_count": 48,
                "poe": None,
            },
        }
        valid, errors = planner_v2.validate_plan(plan)
        self.assertFalse(valid)
        self.assertIn(
            "non-device_set route must not contain product filters: port_count",
            errors,
        )

    def test_rejects_empty_device_set(self):
        plan = {
            "request_type": "device_set",
            "intent": "device_set",
            "device_query": None,
            "device_filters": dict(planner_v2.EMPTY_FILTERS),
        }
        valid, errors = planner_v2.validate_plan(plan)
        self.assertFalse(valid)
        self.assertIn(
            "device_set must contain a device_query or at least one filter",
            errors,
        )

    def test_rejects_missing_filter_field(self):
        plan = {
            "request_type": "atomic_fact",
            "intent": "device_status",
            "device_query": "J9774A",
            "device_filters": {"brand": None, "family": None, "port_count": None},
        }
        valid, errors = planner_v2.validate_plan(plan)
        self.assertFalse(valid)
        self.assertIn(
            "device_filters must contain exactly: brand, family, port_count, poe",
            errors,
        )

    def test_rejects_device_route_without_explicit_reference(self):
        plan = {
            "request_type": "atomic_fact",
            "intent": "device_status",
            "device_query": None,
            "device_filters": dict(planner_v2.EMPTY_FILTERS),
        }
        valid, errors = planner_v2.validate_plan(plan)
        self.assertFalse(valid)
        self.assertIn("atomic_fact requires a non-empty device_query", errors)


class OrchestratorSemanticPlannerTests(unittest.TestCase):
    def test_qwen_plan_filters_device_set_through_resolver_v5(self):
        plan = {
            "request_type": "device_set",
            "intent": "device_set",
            "device_query": None,
            "device_filters": {
                "brand": "HP ProCurve",
                "family": "2530",
                "port_count": 48,
                "poe": False,
            },
        }
        backend = dummy_backend.SpyBackend()
        with patch.object(
            hybrid_poc,
            "ollama_chat",
            return_value=(json.dumps(plan), "stop", 1.0),
        ):
            trace = hybrid_poc.orchestrate(
                "PoE'siz 48 port 2530 cihazları",
                inventory=INVENTORY,
                backend=backend,
                planner_schema="gold",
                resolver_module=resolver_v5,
            )
        self.assertTrue(trace["planner_llm_called"])
        self.assertEqual(trace["planner_output"]["raw"]["method"], "llm")
        self.assertEqual(trace["route"], "device_set")
        self.assertEqual(
            {model["sku"] for model in trace["resolver_output"]["models"]},
            {"J9775A"},
        )
        self.assertEqual(trace["tool_calls"], [])

    def test_invalid_plan_stops_before_resolver_and_backend(self):
        invalid = {
            "request_type": "ports",
            "intent": "device_set",
            "device_query": "J9774A",
            "device_filters": dict(planner_v2.EMPTY_FILTERS),
        }
        backend = dummy_backend.SpyBackend()
        with patch.object(
            hybrid_poc,
            "ollama_chat",
            return_value=(json.dumps(invalid), "stop", 1.0),
        ):
            trace = hybrid_poc.orchestrate(
                "J9774A portlarını göster",
                inventory=INVENTORY,
                backend=backend,
                planner_schema="gold",
                resolver_module=resolver_v5,
            )
        self.assertTrue(trace["planner_failure"])
        self.assertEqual(trace["route"], "unknown")
        self.assertIn(
            "request_type 'ports' requires intent 'device_ports'",
            trace["planner_errors"],
        )
        self.assertEqual(trace["tool_calls"], [])


class DeviceSetFormattingTests(unittest.TestCase):
    def test_device_set_formatter_does_not_claim_inventory_status(self):
        result = {
            "outcome": "resolved",
            "models": [
                {"sku": "J9775A", "canonical_name": "J9775A 2530-48G"}
            ],
            "devices": [{"hostname": "lab-j9775a-01", "status": "up"}],
            "unevaluated_count": 0,
            "unevaluated_fields": [],
        }
        text = resolver_v5.format_device_set(result)
        self.assertIn("J9775A 2530-48G", text)
        self.assertIn("lab-j9775a-01", text)
        self.assertNotIn("(up)", text)

if __name__ == "__main__":
    unittest.main()
