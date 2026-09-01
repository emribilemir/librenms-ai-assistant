import json
import unittest
from unittest.mock import patch

import hybrid_poc
import planner_v2


HOST = "lab-j9772a-01"

DEVICE = {
    "device_id": 1,
    "hostname": HOST,
    "sysName": HOST,
    "status": 1,
    "hardware": "J9772A 2530-48G-PoEP",
    "uptime": 12346,
    "location": {"location": "Test Lab"},
    "os": "procurve",
    "version": "YA.16.10",
}

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
        "ifSpeed": 1_000_000_000,
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
        "ifSpeed": 1_000_000_000,
    },
]

EVENTS = [
    {
        "event_id": 201,
        "device_id": 1,
        "timestamp": "2026-08-31 12:00:00",
        "type": "interface",
        "reference": "2",
        "message": "ifOperStatus: up -> down",
        "severity": 3,
    },
    {
        "event_id": 200,
        "device_id": 1,
        "timestamp": "2026-08-31 11:00:00",
        "type": "down",
        "reference": None,
        "message": "Device status changed to Down from snmp check.",
        "severity": 2,
    },
]


class Resolver:
    @staticmethod
    def resolve_device(query, inventory):
        return {
            "outcome": "resolved",
            "reason": "exact",
            "device": {"hostname": HOST, "device_id": 999},
        }

    @staticmethod
    def resolve_device_set(query, inventory, filters=None):
        return {"outcome": "resolved", "devices": []}

    @staticmethod
    def format_atomic(hostname, status):
        return f"{hostname}:{status}"

    @staticmethod
    def format_clarification(candidates):
        return "clarification"

    @staticmethod
    def format_device_set(result):
        return "device-set"


class Backend:
    def __init__(self):
        self.calls = []

    def _record(self, tool, args, result):
        self.calls.append({"tool": tool, "args": args, "result": result})
        return result

    def get_device(self, *, hostname=None, device_id=None):
        return self._record(
            "get_device",
            {"hostname": hostname} if hostname is not None else {"device_id": device_id},
            dict(DEVICE),
        )

    def get_ports(self, *, device_id):
        return self._record("get_ports", {"device_id": device_id}, list(PORTS))

    def get_events(self, *, device_id, from_time=None, to_time=None):
        args = {"device_id": device_id}
        if from_time is not None:
            args["from_time"] = from_time
        if to_time is not None:
            args["to_time"] = to_time
        return self._record("get_events", args, list(EVENTS))

    def get_alerts(self, *, device_id):
        return self._record("get_alerts", {"device_id": device_id}, [])

    def trace(self):
        return list(self.calls)


def run(plan):
    backend = Backend()
    with patch.object(
        hybrid_poc,
        "ollama_chat",
        return_value=(json.dumps(plan), "stop", 1.0),
    ):
        result = hybrid_poc.orchestrate(
            "test",
            inventory={"devices": []},
            backend=backend,
            planner_schema="gold",
            resolver_module=Resolver,
        )
    return result


class PlannerContractTests(unittest.TestCase):
    def test_device_fact_plan_is_valid(self):
        plan = {
            "request_type": "device_fact",
            "intent": "device_fact",
            "device_query": HOST,
            "device_filters": dict(planner_v2.EMPTY_FILTERS),
            "device_fact": "model",
        }
        self.assertEqual(planner_v2.validate_plan(plan), (True, []))

    def test_port_speed_plan_is_valid(self):
        plan = {
            "request_type": "ports",
            "intent": "device_ports",
            "device_query": HOST,
            "device_filters": dict(planner_v2.EMPTY_FILTERS),
            "port_query": "2",
            "port_filters": {"admin_status": None, "oper_status": None},
            "port_fact": "speed",
        }
        self.assertEqual(planner_v2.validate_plan(plan), (True, []))

    def test_temporal_event_plan_is_valid(self):
        plan = {
            "request_type": "events",
            "intent": "device_events",
            "device_query": HOST,
            "device_filters": dict(planner_v2.EMPTY_FILTERS),
            "event_filters": {
                "scope": "port_status",
                "status": "down",
                "port_query": "2",
                "window_minutes": 30,
                "mode": "latest",
            },
        }
        self.assertEqual(planner_v2.validate_plan(plan), (True, []))


class PipelineTests(unittest.TestCase):
    def test_device_model_direct_read(self):
        result = run({
            "request_type": "device_fact",
            "intent": "device_fact",
            "device_query": HOST,
            "device_filters": dict(planner_v2.EMPTY_FILTERS),
            "device_fact": "model",
        })
        self.assertEqual(result["route"], "device_fact")
        self.assertIn("J9772A 2530-48G-PoEP", result["final_answer"])
        self.assertFalse(result["synthesis_llm_called"])

    def test_port_speed_direct_read(self):
        result = run({
            "request_type": "ports",
            "intent": "device_ports",
            "device_query": HOST,
            "device_filters": dict(planner_v2.EMPTY_FILTERS),
            "port_query": "2",
            "port_filters": {"admin_status": None, "oper_status": None},
            "port_fact": "speed",
        })
        self.assertEqual(result["route"], "ports")
        self.assertIn("1 Gbps", result["final_answer"])
        self.assertFalse(result["synthesis_llm_called"])

    def test_port_latest_down_uses_real_port_id(self):
        result = run({
            "request_type": "events",
            "intent": "device_events",
            "device_query": HOST,
            "device_filters": dict(planner_v2.EMPTY_FILTERS),
            "event_filters": {
                "scope": "port_status",
                "status": "down",
                "port_query": "2",
                "window_minutes": None,
                "mode": "latest",
            },
        })
        self.assertEqual(result["route"], "events")
        self.assertIn("Port 2", result["final_answer"])
        self.assertIn("DOWN", result["final_answer"])
        self.assertFalse(result["synthesis_llm_called"])


if __name__ == "__main__":
    unittest.main()
