import json
import os
import unittest
from unittest.mock import patch

from chat_service.pipeline_adapter import PipelineAdapter


class PipelineInspectionTests(unittest.TestCase):
    @staticmethod
    def _run(result, *, demo_mode):
        def orchestrator(content, observer, is_cancelled):
            return result

        environment = {"AI_DEMO_MODE": "1"} if demo_mode else {}
        with patch.dict(os.environ, environment, clear=True):
            return PipelineAdapter(orchestrator=orchestrator).run(
                "question", lambda *args: None, lambda: False
            )

    def test_demo_mode_off_does_not_build_inspection(self):
        response = self._run(
            {
                "final_answer": "validated",
                "route": "ports",
                "planner_output": {
                    "plan": {"request_type": "ports", "intent": "device_ports"}
                },
                "synthesis_llm_called": False,
            },
            demo_mode=False,
        )

        self.assertNotIn("inspection", response)

    def test_direct_read_reuses_only_allowlisted_runtime_metadata(self):
        result = {
            "final_answer": "lab-j9772a-01 Port 2 admin=up, oper=down.",
            "route": "ports",
            "intent": "device_ports",
            "planner_output": {
                "plan": {
                    "request_type": "ports",
                    "intent": "device_ports",
                    "device_query": "lab-j9772a-01",
                },
                "raw": {"content": "secret planner draft", "prompt": "hidden"},
            },
            "resolver_output": {
                "outcome": "resolved",
                "device": {
                    "device_id": 1,
                    "hostname": "lab-j9772a-01",
                    "secret": "resolver-secret",
                },
            },
            "tool_calls": [
                {
                    "tool": "get_device",
                    "args": {"hostname": "lab-j9772a-01", "token": "do-not-copy"},
                    "result": {"raw": "large response"},
                },
                {
                    "tool": "get_ports",
                    "args": {"device_id": 1, "headers": {"Authorization": "secret"}},
                    "result": [{"raw": "large response"}],
                },
                {"tool": "shell", "args": {"command": "cat .env"}},
            ],
            "structured_findings": None,
            "synthesis_llm_called": False,
            "navigation_context": {
                "device": {"device_id": 1, "hostname": "lab-j9772a-01"},
                "ports": [
                    {
                        "device_id": 1,
                        "port_id": 2,
                        "ifIndex": 2,
                        "ifAdminStatus": "up",
                        "ifOperStatus": "down",
                    }
                ],
                "alerts": [],
                "events": [],
            },
            "llm_input": {"system": "hidden prompt"},
            "llm_output": {"draft": "unvalidated"},
            "grounding_trace": {"private": "full trace"},
        }

        response = self._run(result, demo_mode=True)

        self.assertIn("inspection", response)
        self.assertEqual(
            response["inspection"],
            {
                "planner": {
                    "request_type": "ports",
                    "intent": "device_ports",
                },
                "resolution": {
                    "device_id": 1,
                    "hostname": "lab-j9772a-01",
                    "port_id": 2,
                    "ifIndex": 2,
                },
                "route": "ports",
                "tools": [
                    {"name": "get_device", "args": {"hostname": "lab-j9772a-01"}},
                    {"name": "get_ports", "args": {"device_id": 1}},
                ],
                "findings": [],
                "synthesis_llm_called": False,
                "navigation_targets": [
                    {
                        "kind": "port",
                        "label": "Port detayını aç",
                        "entity_id": 2,
                        "href": "/device/1/port/port=2",
                    }
                ],
            },
        )
        serialized = json.dumps(response["inspection"])
        for forbidden in (
            "secret",
            "prompt",
            "raw",
            "Authorization",
            "llm_input",
            "llm_output",
            "grounding_trace",
            "cat .env",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_port_route_carries_bounded_structured_rows_from_verified_runtime_objects(self):
        result = {
            "final_answer": "debug-shaped fallback text must not be parsed",
            "route": "ports",
            "navigation_context": {
                "device": {"device_id": 1, "hostname": "lab-j9772a-02"},
                "ports": [
                    {
                        "device_id": 1,
                        "port_id": 2,
                        "ifIndex": 2,
                        "ifName": "2",
                        "ifDescr": "GigabitEthernet 2",
                        "ifAlias": "Test-Down",
                        "ifAdminStatus": "up",
                        "ifOperStatus": "down",
                        "secret": "must not cross the boundary",
                    },
                    {
                        "device_id": 1,
                        "port_id": 3,
                        "ifIndex": 3,
                        "ifName": "3",
                        "ifAlias": "Disabled",
                        "ifAdminStatus": "down",
                        "ifOperStatus": "down",
                    },
                ],
            },
        }

        response = self._run(result, demo_mode=False)

        self.assertEqual(response["structured_result"], {
            "kind": "ports",
            "device": {"device_id": 1, "hostname": "lab-j9772a-02"},
            "ports": [
                {
                    "device_id": 1, "port_id": 2, "ifIndex": 2,
                    "ifName": "2", "ifDescr": "GigabitEthernet 2", "ifAlias": "Test-Down",
                    "admin_status": "up", "oper_status": "down",
                },
                {
                    "device_id": 1, "port_id": 3, "ifIndex": 3,
                    "ifName": "3", "ifAlias": "Disabled",
                    "admin_status": "down", "oper_status": "down",
                },
            ],
        })
        self.assertNotIn("secret", json.dumps(response["structured_result"]))

    def test_port_speed_query_carries_requested_fact_and_verified_speed(self):
        result = {
            "final_answer": "lab-j9772a-01 portları:\nPort 2: 1 Gbps",
            "route": "ports",
            "planner_output": {"plan": {"port_fact": "speed"}},
            "navigation_context": {
                "device": {"device_id": 1, "hostname": "lab-j9772a-01"},
                "ports": [
                    {
                        "device_id": 1,
                        "port_id": 2,
                        "ifIndex": 2,
                        "ifName": "2",
                        "ifAdminStatus": "up",
                        "ifOperStatus": "down",
                        "ifSpeed": 1_000_000_000,
                    }
                ],
            },
        }

        response = self._run(result, demo_mode=False)

        self.assertEqual(response["structured_result"]["requested_fact"], "speed")
        self.assertEqual(response["structured_result"]["ports"][0]["speed_bps"], 1_000_000_000)

    def test_port_speed_query_does_not_invent_missing_speed(self):
        result = {
            "final_answer": "lab-j9772a-01 Port 2 için LibreNMS'te hız bilgisi bulunmuyor.",
            "route": "ports",
            "planner_output": {"plan": {"port_fact": "speed"}},
            "navigation_context": {
                "device": {"device_id": 1, "hostname": "lab-j9772a-01"},
                "ports": [{"device_id": 1, "port_id": 2, "ifIndex": 2, "ifName": "2"}],
            },
        }

        response = self._run(result, demo_mode=False)

        self.assertEqual(response["structured_result"]["requested_fact"], "speed")
        self.assertNotIn("speed_bps", response["structured_result"]["ports"][0])

    def test_alert_route_carries_bounded_rows_without_raw_state_or_private_fields(self):
        result = {
            "final_answer": "88: Port status up/down (severity=critical, state=1)",
            "route": "alerts",
            "navigation_context": {
                "device": {"device_id": 1, "hostname": "lab-j9772a-01"},
                "alerts": [
                    {
                        "device_id": 1,
                        "alert_id": 88,
                        "severity": "critical",
                        "name": "Port status up/down",
                        "state": 1,
                        "secret": "must not cross the boundary",
                    },
                    {
                        "device_id": 1,
                        "alert_id": 133,
                        "severity": "warning",
                        "rule": "LAB - Port admin up oper down",
                        "state": 1,
                    },
                    {"device_id": 2, "alert_id": 999, "severity": "critical", "name": "Other device"},
                ],
            },
        }

        response = self._run(result, demo_mode=False)

        self.assertEqual(response["structured_result"], {
            "kind": "alerts",
            "device": {"device_id": 1, "hostname": "lab-j9772a-01"},
            "alerts": [
                {"device_id": 1, "alert_id": 88, "severity": "critical", "name": "Port status up/down"},
                {"device_id": 1, "alert_id": 133, "severity": "warning", "name": "LAB - Port admin up oper down"},
            ],
        })
        serialized = json.dumps(response["structured_result"])
        self.assertNotIn("state", serialized)
        self.assertNotIn("secret", serialized)
        self.assertNotIn("Other device", serialized)

    def test_alert_route_carries_a_structured_empty_state(self):
        response = self._run({
            "final_answer": "lab-j9772a-01 üzerinde aktif alarm bulunmuyor.",
            "route": "alerts",
            "navigation_context": {
                "device": {"device_id": 1, "hostname": "lab-j9772a-01"},
                "alerts": [],
            },
        }, demo_mode=False)

        self.assertEqual(response["structured_result"], {
            "kind": "alerts",
            "device": {"device_id": 1, "hostname": "lab-j9772a-01"},
            "alerts": [],
        })

    def test_event_route_carries_bounded_timeline_rows_from_verified_runtime_objects(self):
        result = {
            "final_answer": "2026-09-08 08:12:03 [2] ifOperStatus: up -> down",
            "route": "events",
            "navigation_context": {
                "device": {"device_id": 1, "hostname": "lab-j9772a-01"},
                "events": [
                    {
                        "device_id": 1,
                        "event_id": 203,
                        "timestamp": "2026-09-08 08:12:03",
                        "severity": 2,
                        "message": "ifOperStatus: up -> down",
                        "type": "interface",
                        "reference": "2",
                        "secret": "must not cross the boundary",
                    },
                    {
                        "device_id": 2,
                        "event_id": 999,
                        "timestamp": "2026-09-08 08:13:03",
                        "severity": 4,
                        "message": "Other device",
                    },
                ],
            },
        }

        response = self._run(result, demo_mode=False)

        self.assertEqual(response["structured_result"], {
            "kind": "events",
            "device": {"device_id": 1, "hostname": "lab-j9772a-01"},
            "events": [{
                "device_id": 1,
                "event_id": 203,
                "timestamp": "2026-09-08 08:12:03",
                "severity": "2",
                "message": "ifOperStatus: up -> down",
                "type": "interface",
                "reference": "2",
            }],
        })
        serialized = json.dumps(response["structured_result"])
        self.assertNotIn("secret", serialized)
        self.assertNotIn("Other device", serialized)

    def test_event_route_carries_a_structured_empty_state(self):
        response = self._run({
            "final_answer": "Bu cihaz için event bulunamadı.",
            "route": "events",
            "navigation_context": {
                "device": {"device_id": 1, "hostname": "lab-j9772a-01"},
                "events": [],
            },
        }, demo_mode=False)

        self.assertEqual(response["structured_result"], {
            "kind": "events",
            "device": {"device_id": 1, "hostname": "lab-j9772a-01"},
            "events": [],
        })

    def test_investigation_reuses_bounded_structured_findings(self):
        findings = [
            {
                "id": "port:ifIndex-2:admin-up-oper-down",
                "type": "port_admin_up_oper_down",
                "time_scope": "current",
                "port_id": 2,
                "ifIndex": "2",
                "admin_status": "up",
                "oper_status": "down",
                "evidence_refs": ["ports[port_id=2].ifAdminStatus"],
                "raw_payload": "must not be copied",
            },
            {
                "id": "alert:8:active",
                "type": "active_alert",
                "alert_id": 8,
                "severity": "critical",
                "name": "Port status",
                "evidence_refs": ["alerts[alert_id=8]"],
            },
        ]
        result = {
            "final_answer": "validated investigation",
            "route": "investigation",
            "intent": "investigation",
            "planner_output": {
                "plan": {
                    "request_type": "investigation",
                    "intent": "investigation",
                }
            },
            "resolver_output": {
                "outcome": "resolved",
                "device": {"device_id": 1, "hostname": "lab-j9772a-01"},
            },
            "tool_calls": [
                {"tool": "get_device", "args": {"hostname": "lab-j9772a-01"}},
                {"tool": "get_ports", "args": {"device_id": 1}},
                {"tool": "get_alerts", "args": {"device_id": 1}},
                {
                    "tool": "get_events",
                    "args": {
                        "device_id": 1,
                        "from_time": "2026-09-04 10:00:00",
                        "to_time": "2026-09-05 10:00:00",
                    },
                },
            ],
            "structured_findings": {"schema_version": 1, "findings": findings},
            "synthesis_llm_called": True,
            "navigation_context": {
                "device": {"device_id": 1, "hostname": "lab-j9772a-01"},
                "ports": [],
                "alerts": [],
                "events": [],
            },
        }

        response = self._run(result, demo_mode=True)
        self.assertIn("inspection", response)
        inspection = response["inspection"]

        self.assertEqual(
            inspection["planner"],
            {"request_type": "investigation", "intent": "investigation"},
        )
        self.assertEqual(inspection["route"], "investigation")
        self.assertEqual(
            inspection["resolution"],
            {"device_id": 1, "hostname": "lab-j9772a-01"},
        )
        self.assertEqual(
            [tool["name"] for tool in inspection["tools"]],
            ["get_device", "get_ports", "get_alerts", "get_events"],
        )
        self.assertEqual(inspection["findings"][0]["port_id"], 2)
        self.assertEqual(inspection["findings"][1]["severity"], "critical")
        self.assertNotIn("raw_payload", inspection["findings"][0])
        self.assertIs(inspection["synthesis_llm_called"], True)

    def test_ambiguous_resolution_does_not_invent_device_or_port(self):
        result = {
            "final_answer": "clarification",
            "route": "clarification",
            "intent": "device_ports",
            "planner_output": {
                "plan": {"request_type": "ports", "intent": "device_ports"}
            },
            "resolver_output": {
                "outcome": "ambiguous",
                "candidates": [
                    {"device_id": 1, "hostname": "first"},
                    {"device_id": 2, "hostname": "second"},
                ],
            },
            "tool_calls": [],
            "structured_findings": None,
            "synthesis_llm_called": False,
            "navigation_context": {"device": None, "ports": []},
        }

        response = self._run(result, demo_mode=True)
        self.assertIn("inspection", response)
        inspection = response["inspection"]

        self.assertNotIn("resolution", inspection)
        self.assertEqual(inspection["route"], "clarification")

    def test_tool_and_finding_lists_and_strings_are_bounded(self):
        result = {
            "final_answer": "validated",
            "route": "investigation",
            "intent": "investigation",
            "planner_output": {
                "plan": {"request_type": "investigation", "intent": "investigation"}
            },
            "resolver_output": {"outcome": "no_match"},
            "tool_calls": [
                {"tool": "get_device", "args": {"hostname": "x" * 1000}}
                for _ in range(30)
            ],
            "structured_findings": {
                "findings": [
                    {"id": f"finding-{index}", "type": "root_cause_unknown", "name": "y" * 1000}
                    for index in range(30)
                ]
            },
            "synthesis_llm_called": True,
            "navigation_context": {},
        }

        response = self._run(result, demo_mode=True)
        self.assertIn("inspection", response)
        inspection = response["inspection"]

        self.assertLessEqual(len(inspection["tools"]), 12)
        self.assertLessEqual(len(inspection["findings"]), 12)
        self.assertLessEqual(len(inspection["tools"][0]["args"]["hostname"]), 160)
        self.assertLessEqual(len(inspection["findings"][0]["name"]), 240)


if __name__ == "__main__":
    unittest.main()
