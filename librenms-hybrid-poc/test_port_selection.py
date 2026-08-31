#!/usr/bin/env python3
"""Focused tests for structured port selection/filtering (EMR-46)."""

import importlib.util
import json
import os
import unittest
from unittest.mock import patch

import hybrid_poc
import planner_v2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = os.path.join(ROOT, "librenms-hybrid-poc", "hybrid-gold-v3")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


resolver_v5 = load_module(
    "resolver_v5_port_test", os.path.join(GOLD, "resolver_candidate_v5.py")
)
with open(os.path.join(GOLD, "dummy_inventory.json"), encoding="utf-8") as stream:
    INVENTORY = json.load(stream)


PORTS = [
    {
        "port_id": 1,
        "device_id": 1,
        "ifIndex": 1,
        "ifName": "1",
        "ifDescr": "GigabitEthernet1",
        "ifAdminStatus": "up",
        "ifOperStatus": "up",
        "ifAlias": "Uplink",
    },
    {
        "port_id": 2,
        "device_id": 1,
        "ifIndex": 2,
        "ifName": "2",
        "ifDescr": "GigabitEthernet2",
        "ifAdminStatus": "up",
        "ifOperStatus": "down",
        "ifAlias": "Test-Down",
    },
    {
        "port_id": 3,
        "device_id": 1,
        "ifIndex": 3,
        "ifName": "3",
        "ifDescr": "GigabitEthernet3",
        "ifAdminStatus": "down",
        "ifOperStatus": "down",
        "ifAlias": "Disabled",
    },
    {
        "port_id": 4,
        "device_id": 1,
        "ifIndex": 4,
        "ifName": "4",
        "ifDescr": "GigabitEthernet4",
        "ifAdminStatus": "up",
        "ifOperStatus": "up",
        "ifAlias": "Client",
    },
]


class PortBackend:
    def __init__(self):
        self.calls = []

    def reset_trace(self):
        self.calls = []

    def _record(self, tool, args, result):
        self.calls.append({"tool": tool, "args": args, "result": result})
        return result

    def get_device(self, *, hostname=None, device_id=None):
        return self._record(
            "get_device",
            {"hostname": hostname},
            {"device_id": 1, "hostname": hostname, "status": 1},
        )

    def get_ports(self, *, device_id):
        return self._record("get_ports", {"device_id": device_id}, list(PORTS))

    def trace(self):
        return list(self.calls)


class PortPlanContractTests(unittest.TestCase):
    def test_normalizer_supplies_empty_port_fields_for_legacy_plans(self):
        normalized = planner_v2.normalize_plan_filters(
            {
                "request_type": "ports",
                "intent": "device_ports",
                "device_query": "lab-j9772a-01",
                "device_filters": dict(planner_v2.EMPTY_FILTERS),
            }
        )
        self.assertIsNone(normalized["port_query"])
        self.assertEqual(normalized["port_filters"], planner_v2.EMPTY_PORT_FILTERS)

    def test_accepts_structured_port_query_and_filters(self):
        plan = {
            "request_type": "ports",
            "intent": "device_ports",
            "device_query": "lab-j9772a-01",
            "device_filters": dict(planner_v2.EMPTY_FILTERS),
            "port_query": "2",
            "port_filters": {"admin_status": "up", "oper_status": "down"},
        }
        self.assertEqual(planner_v2.validate_plan(plan), (True, []))

    def test_rejects_non_port_route_with_port_constraints(self):
        plan = {
            "request_type": "atomic_fact",
            "intent": "device_status",
            "device_query": "lab-j9772a-01",
            "device_filters": dict(planner_v2.EMPTY_FILTERS),
            "port_query": "2",
            "port_filters": {"admin_status": None, "oper_status": None},
        }
        valid, errors = planner_v2.validate_plan(plan)
        self.assertFalse(valid)
        self.assertIn("non-ports route must not contain port constraints: port_query", errors)


class PortSelectionExecutionTests(unittest.TestCase):
    def _run(self, plan, query):
        backend = PortBackend()
        with patch.object(
            hybrid_poc,
            "ollama_chat",
            return_value=(json.dumps(plan), "stop", 1.0),
        ):
            trace = hybrid_poc.orchestrate(
                query,
                inventory=INVENTORY,
                backend=backend,
                planner_schema="gold",
                resolver_module=resolver_v5,
            )
        return trace

    def _plan(self, *, port_query=None, admin=None, oper=None):
        return {
            "request_type": "ports",
            "intent": "device_ports",
            "device_query": "lab-j9772a-01",
            "device_filters": dict(planner_v2.EMPTY_FILTERS),
            "port_query": port_query,
            "port_filters": {"admin_status": admin, "oper_status": oper},
        }

    def test_specific_port_returns_only_that_port(self):
        trace = self._run(
            self._plan(port_query="2"),
            "lab-j9772a-01 port 2 ne durumda?",
        )
        self.assertEqual(trace["route"], "ports")
        self.assertIn("Port 2: admin=up oper=down (Test-Down)", trace["final_answer"])
        self.assertNotIn("Port 1:", trace["final_answer"])
        self.assertNotIn("Port 3:", trace["final_answer"])
        self.assertEqual(trace["tool_calls"][1]["args"], {"device_id": 1})
        self.assertFalse(trace["synthesis_llm_called"])

    def test_down_ports_means_operationally_down(self):
        trace = self._run(
            self._plan(oper="down"),
            "lab-j9772a-01'in down portları hangileri?",
        )
        self.assertIn("Port 2: admin=up oper=down", trace["final_answer"])
        self.assertIn("Port 3: admin=down oper=down", trace["final_answer"])
        self.assertNotIn("Port 1:", trace["final_answer"])
        self.assertNotIn("Port 4:", trace["final_answer"])

    def test_admin_up_oper_down_returns_only_link_down_port(self):
        trace = self._run(
            self._plan(admin="up", oper="down"),
            "lab-j9772a-01 aktif ama bağlantısı düşmüş portlar hangileri?",
        )
        self.assertIn("Port 2: admin=up oper=down", trace["final_answer"])
        self.assertNotIn("Port 3:", trace["final_answer"])


if __name__ == "__main__":
    unittest.main()
