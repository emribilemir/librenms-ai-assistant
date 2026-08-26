#!/usr/bin/env python3
"""Small offline tests for semantic-plan ownership and validation."""

import unittest

import planner_v2


class SemanticPlanContractTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
