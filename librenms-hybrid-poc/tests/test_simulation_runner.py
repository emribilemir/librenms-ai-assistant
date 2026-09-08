import importlib.util
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
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

    def test_remote_fixture_io_uses_bounded_sudo_for_mixed_lab_ownership(self):
        target = simulation_run.TARGETS["lab-j9772a-02"]
        with patch.object(
            simulation_run,
            "ssh",
            return_value=SimpleNamespace(stdout="fixture body\n", returncode=0),
        ) as ssh:
            self.assertEqual(simulation_run.read_fixture(target), "fixture body\n")
            simulation_run.write_fixture(target, "replacement\n")

        read_call, write_call = ssh.call_args_list
        self.assertEqual(read_call.args, (f"sudo -n cat {target.fixture}",))
        self.assertIn("sudo -n sh -c", write_call.args[0])
        self.assertIn(target.fixture, write_call.args[0])
        self.assertEqual(write_call.kwargs["input_text"], "replacement\n")

    def test_offline_fixture_moves_use_bounded_sudo(self):
        target = simulation_run.TARGETS["lab-j9772a-02"]
        with (
            patch.object(simulation_run, "fixture_state", side_effect=["online", "offline"]),
            patch.object(simulation_run, "ssh", return_value=SimpleNamespace(returncode=0)) as ssh,
        ):
            simulation_run.take_device_offline(target)
            self.assertTrue(simulation_run.restore_online_fixture(target))

        self.assertEqual(
            [call.args[0] for call in ssh.call_args_list],
            [
                f"sudo -n mv {target.fixture} {target.offline_fixture}",
                f"sudo -n mv {target.offline_fixture} {target.fixture}",
            ],
        )


class ProcessSelectionTests(unittest.TestCase):
    def test_accepts_one_numeric_responder_pid(self):
        self.assertEqual(simulation_run.single_responder_pid("24260\n"), 24260)

    def test_rejects_missing_multiple_or_non_numeric_pids(self):
        for value in ("", "24260\n24261\n", "not-a-pid\n"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(RuntimeError, "exactly one responder"):
                    simulation_run.single_responder_pid(value)

    def test_stop_responder_uses_the_boot_persistent_systemd_unit(self):
        with (
            patch.object(simulation_run, "systemd_responder_available", return_value=True),
            patch.object(simulation_run, "responder_pid", side_effect=[24260, None]),
            patch.object(simulation_run, "ssh", return_value=SimpleNamespace(returncode=0)) as ssh,
        ):
            stopped = simulation_run.stop_responder()

        self.assertEqual(stopped, 24260)
        ssh.assert_called_once_with("sudo -n systemctl stop librenms-snmpsim.service")

    def test_start_responder_uses_systemd_and_waits_for_the_target(self):
        target = simulation_run.TARGETS["lab-j9772a-01"]
        with (
            patch.object(simulation_run, "systemd_responder_available", return_value=True),
            patch.object(simulation_run, "responder_pid", side_effect=[None, 24261]),
            patch.object(simulation_run, "snmp_available", return_value=True),
            patch.object(simulation_run, "ssh", return_value=SimpleNamespace(returncode=0)) as ssh,
        ):
            started = simulation_run.start_responder(target, target_online=True)

        self.assertEqual(started, 24261)
        ssh.assert_called_once_with("sudo -n systemctl start librenms-snmpsim.service")


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
                "investigation-incident",
            },
        )
        for scenario in scenarios.values():
            self.assertTrue(scenario["example_ai_question"])
            self.assertTrue(scenario["expected"])

        self.assertEqual(
            {key: value["label"] for key, value in scenarios.items()},
            {
                "port-down": "Portu düşür",
                "port-up": "Portu kaldır",
                "location-change": "Konumu değiştir",
                "device-down-up": "Cihazı düşür / geri getir",
                "port-down-up-event": "Port olayı üret",
                "investigation-incident": "İnceleme olayı hazırla",
            },
        )

        self.assertEqual(
            {
                scenario_id: scenario["example_ai_question"]
                for scenario_id, scenario in scenarios.items()
            },
            {
                "port-down": "{hostname} port 2 ne durumda?",
                "port-up": "{hostname} port 2 ne durumda?",
                "location-change": "{hostname}'in location bilgisi ne?",
                "device-down-up": "{hostname} en son ne zaman down oldu?",
                "port-down-up-event": "{hostname} son eventlerini göster",
                "investigation-incident": (
                    "{hostname} cihazında şu an ne sorun var, son 24 saatte neler olmuş?"
                ),
            },
        )

    def test_target_resolution_is_allowlisted_and_keeps_operational_values_together(self):
        alpha = simulation_run.DemoTarget(
            target_id="alpha",
            hostname="alpha.lab",
            device_id=11,
            fixture="/fixtures/alpha/public.snmprec",
            offline_fixture="/fixtures/alpha/offline.snmprec",
            snmp_endpoint="udp:127.0.0.31:1611",
            supported_scenarios=("port-down",),
        )
        beta = simulation_run.DemoTarget(
            target_id="beta",
            hostname="beta.lab",
            device_id=12,
            fixture="/fixtures/beta/public.snmprec",
            offline_fixture="/fixtures/beta/offline.snmprec",
            snmp_endpoint="udp:127.0.0.32:1611",
            supported_scenarios=("port-up",),
        )

        self.assertEqual(
            simulation_run.resolve_target("alpha", {"alpha": alpha, "beta": beta}),
            alpha,
        )
        self.assertEqual(
            simulation_run.resolve_target("beta", {"alpha": alpha, "beta": beta}),
            beta,
        )
        with self.assertRaisesRegex(ValueError, "unsupported target"):
            simulation_run.resolve_target("alpha.lab", {"alpha": alpha, "beta": beta})

    def test_production_metadata_exposes_only_verified_mutable_targets(self):
        metadata = simulation_run.demo_metadata()

        self.assertEqual(
            metadata["supported_targets"],
            [
                {
                    "id": "lab-j9772a-01",
                    "hostname": "lab-j9772a-01",
                    "device_id": 1,
                    "supported_scenarios": [
                        "port-down",
                        "port-up",
                        "location-change",
                        "device-down-up",
                        "port-down-up-event",
                        "investigation-incident",
                    ],
                },
                {
                    "id": "lab-j9772a-02",
                    "hostname": "lab-j9772a-02",
                    "device_id": 2,
                    "supported_scenarios": [
                        "port-down",
                        "port-up",
                        "location-change",
                        "device-down-up",
                        "port-down-up-event",
                        "investigation-incident",
                    ],
                },
            ],
        )
        self.assertTrue(all(
            scenario["supported_target_ids"] == ["lab-j9772a-01", "lab-j9772a-02"]
            for scenario in metadata["scenarios"]
        ))
        self.assertEqual(
            metadata["scenarios"][-1]["example_question"],
            "lab-j9772a-01 cihazında şu an ne sorun var, son 24 saatte neler olmuş?",
        )

    def test_execute_scenario_reuses_the_existing_runner_and_bounds_result(self):
        event = {
            "event_id": 42,
            "timestamp": "2026-09-04 12:00:00",
            "message": "ifOperStatus: up -> down",
            "ignored": "not exposed",
        }
        with (
            patch.object(simulation_run, "preflight") as preflight,
            patch.object(simulation_run, "ensure_online") as ensure_online,
            patch.object(simulation_run, "api_backend", return_value="backend"),
            patch.dict(
                simulation_run.SCENARIO_RUNNERS,
                {
                    "port-down": lambda backend, target: (
                        True,
                        f"{backend} {target.hostname} verified",
                        [event],
                    )
                },
                clear=True,
            ),
            patch.object(
                simulation_run,
                "load_scenarios",
                return_value={
                    "port-down": {"example_ai_question": "{hostname} Port 2 ne durumda?"}
                },
            ),
        ):
            result = simulation_run.execute_scenario("port-down", "lab-j9772a-01")

        preflight.assert_called_once_with(simulation_run.TARGETS["lab-j9772a-01"])
        ensure_online.assert_called_once_with(
            simulation_run.TARGETS["lab-j9772a-01"]
        )
        self.assertEqual(
            result,
            {
                "scenario_id": "port-down",
                "snmp_state_changed": True,
                "librenms_completed": True,
                "target_id": "lab-j9772a-01",
                "verified": "backend lab-j9772a-01 verified",
                "events": [
                    {
                        "event_id": 42,
                        "timestamp": "2026-09-04 12:00:00",
                        "message": "ifOperStatus: up -> down",
                    }
                ],
                "proof": [],
                "expected_investigation": None,
                "example_question": "lab-j9772a-01 Port 2 ne durumda?",
            },
        )

    def test_execute_scenario_propagates_the_second_allowlisted_target(self):
        runner = unittest.mock.Mock(return_value=(False, "second verified", []))
        with (
            patch.object(simulation_run, "preflight") as preflight,
            patch.object(simulation_run, "ensure_online") as ensure_online,
            patch.object(simulation_run, "api_backend", return_value="backend"),
            patch.dict(simulation_run.SCENARIO_RUNNERS, {"port-up": runner}, clear=True),
            patch.object(
                simulation_run,
                "load_scenarios",
                return_value={"port-up": {"example_ai_question": "{hostname} Port 2 ne durumda?"}},
            ),
        ):
            result = simulation_run.execute_scenario("port-up", "lab-j9772a-02")

        second = simulation_run.TARGETS["lab-j9772a-02"]
        preflight.assert_called_once_with(second)
        ensure_online.assert_called_once_with(second)
        runner.assert_called_once_with("backend", second)
        self.assertEqual(result["target_id"], "lab-j9772a-02")
        self.assertEqual(result["example_question"], "lab-j9772a-02 Port 2 ne durumda?")

    def test_investigation_incident_returns_real_verified_contract(self):
        target = simulation_run.TARGETS["lab-j9772a-01"]
        down_event = {
            "event_id": 201,
            "timestamp": "2026-09-07 09:00:00",
            "type": "down",
            "message": "Device status changed to Down",
        }
        up_event = {
            "event_id": 202,
            "timestamp": "2026-09-07 09:01:00",
            "type": "up",
            "message": "Device status changed to Up",
        }
        port_event = {
            "event_id": 203,
            "timestamp": "2026-09-07 09:02:00",
            "type": "interface",
            "reference": "2",
            "message": "ifOperStatus: up -> down",
        }
        backend = unittest.mock.Mock()
        backend.get_alerts.return_value = [
            {
                "alert_id": 88,
                "rule_id": 13,
                "severity": "warning",
                "name": "LAB - Port admin up oper down",
            }
        ]

        with (
            patch.object(simulation_run, "ensure_online", return_value=False),
            patch.object(simulation_run, "set_record", side_effect=[False, True, True]),
            patch.object(simulation_run, "poll_device", return_value=True),
            patch.object(simulation_run, "run_device_down_up", return_value=(True, "ok", [down_event, up_event])),
            patch.object(simulation_run, "current_events", side_effect=[[], [port_event]]),
            patch.object(simulation_run, "require_port", return_value={"ifAdminStatus": "up", "ifOperStatus": "down"}),
        ):
            changed, verified, events, details = simulation_run.run_investigation_incident(
                backend, target
            )

        self.assertTrue(changed)
        self.assertEqual(verified, "İnceleme olayı hazır")
        self.assertEqual([event["event_id"] for event in events], [201, 202, 203])
        self.assertEqual(details["proof"][2]["event_id"], 203)
        self.assertEqual(details["proof"][3]["alert_id"], 88)
        self.assertEqual(
            details["expected_investigation"],
            {
                "target_id": "lab-j9772a-01",
                "hostname": "lab-j9772a-01",
                "device_id": 1,
                "required_route": "investigation",
                "required_tools": ["get_device", "get_ports", "get_alerts", "get_events"],
                "required_finding_types": [
                    "device_current_status",
                    "port_admin_up_oper_down",
                    "active_alert",
                    "historical_status_transition",
                ],
                "required_event_ids": [201, 202],
                "required_synthesis_llm_called": True,
            },
        )

    def test_failed_scenario_recovers_only_the_selected_target_baseline(self):
        target = simulation_run.TARGETS["lab-j9772a-01"]

        with (
            patch.object(simulation_run, "preflight"),
            patch.object(simulation_run, "ensure_online"),
            patch.object(simulation_run, "api_backend", return_value="backend"),
            patch.dict(
                simulation_run.SCENARIO_RUNNERS,
                {
                    "port-down": unittest.mock.Mock(
                        side_effect=RuntimeError("poll verification failed")
                    )
                },
                clear=True,
            ),
            patch.object(simulation_run, "load_scenarios", return_value={"port-down": {}}),
            patch.object(simulation_run, "reset_baseline") as reset,
        ):
            with self.assertRaisesRegex(RuntimeError, "poll verification failed"):
                simulation_run.execute_scenario("port-down", target.target_id)

        reset.assert_called_once_with(target)


if __name__ == "__main__":
    unittest.main()
