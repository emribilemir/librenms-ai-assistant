import unittest

from chat_service.pipeline_adapter import PipelineAdapter


def run_result(result):
    return PipelineAdapter(
        orchestrator=lambda content, observer, is_cancelled: result
    ).run("question", lambda *args: None, lambda: False)


class NavigationTargetTests(unittest.TestCase):
    def test_device_target_uses_verified_backend_device_id(self):
        result = run_result({
            "route": "atomic",
            "final_answer": "up",
            "navigation_context": {"device": {"device_id": 7}},
        })
        self.assertEqual(result["navigation_targets"], [{
            "kind": "device",
            "label": "LibreNMS'te cihazı aç",
            "entity_id": 7,
            "href": "/device/7",
        }])

    def test_specific_port_target_uses_port_id_not_human_port_number(self):
        result = run_result({
            "route": "ports",
            "final_answer": "Port 2 down",
            "navigation_context": {
                "device": {"device_id": 7},
                "ports": [{"device_id": "7", "port_id": "41", "ifIndex": "2"}],
            },
        })
        self.assertEqual(result["navigation_targets"], [{
            "kind": "port",
            "label": "Port detayını aç",
            "entity_id": 41,
            "href": "/device/7/port/port=41",
        }])

    def test_events_and_alerts_use_verified_device_level_fallbacks(self):
        cases = (
            ("events", "events", "Event geçmişini aç", "/device/9/logs/eventlog"),
            ("alerts", "alerts", "Cihaz alarmlarını aç", "/device/9/alerts"),
        )
        for route, kind, label, href in cases:
            with self.subTest(route=route):
                result = run_result({
                    "route": route,
                    "final_answer": "result",
                    "navigation_context": {"device": {"device_id": 9}},
                })
                self.assertEqual(result["navigation_targets"], [{
                    "kind": kind,
                    "label": label,
                    "entity_id": 9,
                    "href": href,
                }])

    def test_unknown_ambiguous_and_unverified_entities_have_no_targets(self):
        unsafe_contexts = (
            {"route": "no_match", "navigation_context": {"device": {"device_id": 1}}},
            {"route": "clarification", "navigation_context": {"device": {"device_id": 1}}},
            {"route": "ports", "navigation_context": {"device": {"device_id": 1}, "ports": [{"device_id": 2, "port_id": 3}]}},
            {"route": "atomic", "navigation_context": {"device": {"device_id": "1/../../login"}}},
            {"route": "unsupported", "navigation_context": {"device": {"device_id": 1}}},
        )
        for unsafe in unsafe_contexts:
            with self.subTest(route=unsafe["route"]):
                result = run_result({"final_answer": "safe", **unsafe})
                self.assertNotIn("navigation_targets", result)

    def test_investigation_caps_useful_targets_at_three_without_link_spam(self):
        result = run_result({
            "route": "investigation",
            "final_answer": "issues",
            "navigation_context": {
                "device": {"device_id": 1},
                "ports": [
                    {"device_id": 1, "port_id": 21, "ifAdminStatus": "up", "ifOperStatus": "down"},
                    {"device_id": 1, "port_id": 22, "ifAdminStatus": "up", "ifOperStatus": "down"},
                ],
                "alerts": [{"alert_id": 88, "device_id": 1}],
                "events": [{"event_id": 104, "device_id": 1}],
            },
        })
        self.assertEqual(result["navigation_targets"], [
            {"kind": "port", "label": "Port detayını aç", "entity_id": 21, "href": "/device/1/port/port=21"},
            {"kind": "alerts", "label": "Cihaz alarmlarını aç", "entity_id": 1, "href": "/device/1/alerts"},
            {"kind": "events", "label": "Event geçmişini aç", "entity_id": 1, "href": "/device/1/logs/eventlog"},
        ])


if __name__ == "__main__":
    unittest.main()
