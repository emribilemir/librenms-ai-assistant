import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
RUN_PATH = ROOT / "simulation" / "run.py"
SPEC = importlib.util.spec_from_file_location("emr55_simulation_run", RUN_PATH)
simulation_run = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = simulation_run
SPEC.loader.exec_module(simulation_run)


class FixtureMutationTests(unittest.TestCase):
    def test_replaces_only_the_requested_snmp_record(self):
        source = (
            "1.3.6.1.2.1.1.6.0|4|Test Lab\n"
            "1.3.6.1.2.1.2.2.1.8.2|2|2\n"
        )

        result = simulation_run.replace_record(
            source, "1.3.6.1.2.1.2.2.1.8.2", "2", "1"
        )

        self.assertEqual(
            result,
            "1.3.6.1.2.1.1.6.0|4|Test Lab\n"
            "1.3.6.1.2.1.2.2.1.8.2|2|1\n",
        )

    def test_rejects_missing_or_duplicate_records(self):
        with self.assertRaisesRegex(ValueError, "expected exactly one record"):
            simulation_run.replace_record("", "1.2.3", "2", "1")

        with self.assertRaisesRegex(ValueError, "expected exactly one record"):
            simulation_run.replace_record(
                "1.2.3|2|2\n1.2.3|2|2\n", "1.2.3", "2", "1"
            )


class ProcessSelectionTests(unittest.TestCase):
    def test_accepts_one_numeric_responder_pid(self):
        self.assertEqual(simulation_run.single_responder_pid("24260\n"), 24260)

    def test_rejects_missing_multiple_or_non_numeric_pids(self):
        for value in ("", "24260\n24261\n", "not-a-pid\n"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(RuntimeError, "exactly one responder"):
                    simulation_run.single_responder_pid(value)


class EventSelectionTests(unittest.TestCase):
    def test_selects_newest_matching_port_transition(self):
        events = [
            {
                "event_id": 12,
                "type": "interface",
                "reference": "2",
                "message": "ifOperStatus: up -> down",
            },
            {
                "event_id": 11,
                "type": "interface",
                "reference": "2",
                "message": "ifOperStatus: up -> down",
            },
            {
                "event_id": 13,
                "type": "interface",
                "reference": "3",
                "message": "ifOperStatus: up -> down",
            },
        ]

        event = simulation_run.find_new_event(
            events,
            after_id=10,
            event_type="interface",
            reference="2",
            message_fragment="up -> down",
        )

        self.assertEqual(event["event_id"], 12)

    def test_returns_none_when_no_new_event_matches(self):
        event = simulation_run.find_new_event(
            [{"event_id": 10, "type": "down", "message": "Device down"}],
            after_id=10,
            event_type="down",
            reference=None,
            message_fragment="Device status changed to Down",
        )

        self.assertIsNone(event)


class ScenarioManifestTests(unittest.TestCase):
    def test_manifest_contains_only_the_bounded_showcase(self):
        scenarios = json.loads(
            (ROOT / "simulation" / "scenarios.json").read_text(encoding="utf-8")
        )

        self.assertEqual(
            set(scenarios),
            {
                "port-down",
                "port-up",
                "location-change",
                "device-down-up",
                "port-down-up-event",
            },
        )
        for scenario in scenarios.values():
            self.assertTrue(scenario["example_ai_question"])
            self.assertTrue(scenario["expected"])

    def test_execute_scenario_reuses_the_existing_runner_and_bounds_result(self):
        event = {
            "event_id": 42,
            "timestamp": "2026-09-04 12:00:00",
            "message": "ifOperStatus: up -> down",
            "ignored": "not exposed",
        }
        with (
            patch.object(simulation_run, "preflight") as preflight,
            patch.object(simulation_run, "api_backend", return_value="backend"),
            patch.dict(
                simulation_run.SCENARIO_RUNNERS,
                {"port-down": lambda backend: (True, f"{backend} verified", [event])},
                clear=True,
            ),
            patch.object(
                simulation_run,
                "load_scenarios",
                return_value={
                    "port-down": {"example_ai_question": "Port 2 ne durumda?"}
                },
            ),
        ):
            result = simulation_run.execute_scenario("port-down")

        preflight.assert_called_once_with()
        self.assertEqual(
            result,
            {
                "scenario_id": "port-down",
                "snmp_state_changed": True,
                "librenms_completed": True,
                "verified": "backend verified",
                "events": [
                    {
                        "event_id": 42,
                        "timestamp": "2026-09-04 12:00:00",
                        "message": "ifOperStatus: up -> down",
                    }
                ],
                "example_question": "Port 2 ne durumda?",
            },
        )


if __name__ == "__main__":
    unittest.main()
