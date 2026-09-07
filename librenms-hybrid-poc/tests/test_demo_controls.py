import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import json
import os
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import chat_service.app as app_module


SECRET = b"0123456789abcdef0123456789abcdef"
SCENARIOS = {
    "port-down": {"label": "Portu düşür", "example_ai_question": "Port down?"},
    "port-up": {"label": "Portu kaldır", "example_ai_question": "Port up?"},
    "location-change": {"label": "Konumu değiştir", "example_ai_question": "Where?"},
    "device-down-up": {"label": "Cihazı düşür / geri getir", "example_ai_question": "Last down?"},
    "port-down-up-event": {"label": "Port olayı üret", "example_ai_question": "Events?"},
    "investigation-incident": {"label": "İnceleme olayı hazırla", "example_ai_question": "Investigate?"},
}
TARGETS = [
    {
        "id": "lab-j9772a-01",
        "hostname": "lab-j9772a-01",
        "device_id": 1,
        "supported_scenarios": list(SCENARIOS),
    }
]


def bearer():
    now = int(time.time())
    payload = {
        "sub": "alice",
        "name": "Alice",
        "iss": "librenms",
        "aud": "ai-assistant",
        "iat": now,
        "exp": now + 3600,
    }
    body = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).rstrip(b"=")
    signature = base64.urlsafe_b64encode(
        hmac.new(SECRET, body, hashlib.sha256).digest()
    ).rstrip(b"=")
    return {"Authorization": f"Bearer v1.{body.decode()}.{signature.decode()}"}


class FakeSimulationRunner:
    def __init__(self):
        self.calls = []
        self.started = threading.Event()
        self.release = None

    def load_scenarios(self):
        return SCENARIOS

    def demo_metadata(self):
        return {
            "supported_targets": TARGETS,
            "scenarios": [
                {
                    "id": scenario_id,
                    **metadata,
                    "supported_target_ids": ["lab-j9772a-01"],
                }
                for scenario_id, metadata in SCENARIOS.items()
            ],
        }

    def execute_scenario(self, scenario_id, target_id):
        self.calls.append((scenario_id, target_id))
        self.started.set()
        if self.release is not None:
            self.release.wait(timeout=2)
        return {
            "scenario_id": scenario_id,
            "target_id": target_id,
            "snmp_state_changed": True,
            "librenms_completed": True,
            "verified": SCENARIOS[scenario_id]["label"] + " verified",
            "events": [],
            "example_question": SCENARIOS[scenario_id]["example_ai_question"],
        }

    def reset_baseline(self, target_id):
        self.calls.append(("reset", target_id))
        return {
            "changed": True,
            "location": "Test Lab",
            "admin": "up",
            "oper": "down",
        }


class DemoControlRouteTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.directory.cleanup()

    def make_client(self, *, enabled, runner=None):
        environment = {"AI_DEMO_MODE_ALLOWED": "1" if enabled else "0"}
        with patch.dict(os.environ, environment, clear=False), patch.object(
            app_module,
            "load_simulation_runner",
            return_value=runner or FakeSimulationRunner(),
            create=True,
        ):
            app = app_module.create_app(
                os.path.join(self.directory.name, "chat.sqlite3"), secret=SECRET
            )
        client = TestClient(app)
        if enabled:
            response = client.post("/v1/demo-mode", headers=bearer(), json={"enabled": True})
            self.assertEqual(response.status_code, 200)
        return client

    def test_demo_mode_off_does_not_register_endpoints(self):
        client = self.make_client(enabled=False)

        self.assertEqual(client.get("/v1/demo/scenarios", headers=bearer()).status_code, 404)
        self.assertEqual(
            client.post(
                "/v1/demo/scenarios",
                headers=bearer(),
                json={"scenario_id": "port-down"},
            ).status_code,
            404,
        )
        self.assertEqual(client.post("/v1/demo/reset", headers=bearer()).status_code, 404)

    def test_demo_mode_on_lists_targets_and_runs_only_bounded_pairs(self):
        runner = FakeSimulationRunner()
        client = self.make_client(enabled=True, runner=runner)

        listing = client.get("/v1/demo/scenarios", headers=bearer())
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(
            {item["id"] for item in listing.json()["scenarios"]}, set(SCENARIOS)
        )
        self.assertEqual(listing.json()["supported_targets"], TARGETS)

        for scenario_id in SCENARIOS:
            response = client.post(
                "/v1/demo/scenarios",
                headers=bearer(),
                json={"scenario_id": scenario_id, "target_id": "lab-j9772a-01"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["scenario_id"], scenario_id)

        self.assertEqual(
            runner.calls,
            [(scenario_id, "lab-j9772a-01") for scenario_id in SCENARIOS],
        )

    def test_rejects_invalid_or_extra_browser_input(self):
        client = self.make_client(enabled=True)

        invalid = client.post(
            "/v1/demo/scenarios",
            headers=bearer(),
            json={"scenario_id": "shell-command", "target_id": "lab-j9772a-01"},
        )
        extra = client.post(
            "/v1/demo/scenarios",
            headers=bearer(),
            json={
                "scenario_id": "port-down",
                "target_id": "lab-j9772a-01",
                "path": "/tmp/fixture",
            },
        )
        hostname_override = client.post(
            "/v1/demo/scenarios",
            headers=bearer(),
            json={
                "scenario_id": "port-down",
                "target_id": "lab-j9772a-01",
                "hostname": "victim.example",
            },
        )
        unknown_target = client.post(
            "/v1/demo/scenarios",
            headers=bearer(),
            json={"scenario_id": "port-down", "target_id": "victim.example"},
        )

        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(extra.status_code, 400)
        self.assertEqual(hostname_override.status_code, 400)
        self.assertEqual(unknown_target.status_code, 422)

    def test_reset_is_a_separate_bounded_action(self):
        runner = FakeSimulationRunner()
        client = self.make_client(enabled=True, runner=runner)

        response = client.post(
            "/v1/demo/reset",
            headers=bearer(),
            json={"target_id": "lab-j9772a-01"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["verified"], "Baseline restored")
        self.assertEqual(runner.calls, [("reset", "lab-j9772a-01")])

    def test_duplicate_trigger_is_rejected_while_a_scenario_is_running(self):
        runner = FakeSimulationRunner()
        runner.release = threading.Event()
        client = self.make_client(enabled=True, runner=runner)

        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(
                client.post,
                "/v1/demo/scenarios",
                headers=bearer(),
                json={"scenario_id": "port-down", "target_id": "lab-j9772a-01"},
            )
            self.assertTrue(runner.started.wait(timeout=1))
            duplicate = client.post(
                "/v1/demo/scenarios",
                headers=bearer(),
                json={"scenario_id": "port-up", "target_id": "lab-j9772a-01"},
            )
            runner.release.set()
            completed = first.result(timeout=2)

        self.assertEqual(completed.status_code, 200)
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(runner.calls, [("port-down", "lab-j9772a-01")])


if __name__ == "__main__":
    unittest.main()
