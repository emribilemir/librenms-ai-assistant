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
    "port-down": {"label": "Port Down", "example_ai_question": "Port down?"},
    "port-up": {"label": "Port Up", "example_ai_question": "Port up?"},
    "location-change": {"label": "Location Change", "example_ai_question": "Where?"},
    "device-down-up": {"label": "Device Down/Up", "example_ai_question": "Last down?"},
    "port-down-up-event": {"label": "Generate Port Event", "example_ai_question": "Events?"},
}


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

    def execute_scenario(self, scenario_id):
        self.calls.append(scenario_id)
        self.started.set()
        if self.release is not None:
            self.release.wait(timeout=2)
        return {
            "scenario_id": scenario_id,
            "snmp_state_changed": True,
            "librenms_completed": True,
            "verified": SCENARIOS[scenario_id]["label"] + " verified",
            "events": [],
            "example_question": SCENARIOS[scenario_id]["example_ai_question"],
        }

    def reset_baseline(self):
        self.calls.append("reset")
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
        environment = {"AI_DEMO_MODE": "1" if enabled else "0"}
        with patch.dict(os.environ, environment, clear=False), patch.object(
            app_module,
            "load_simulation_runner",
            return_value=runner or FakeSimulationRunner(),
            create=True,
        ):
            app = app_module.create_app(
                os.path.join(self.directory.name, "chat.sqlite3"), secret=SECRET
            )
        return TestClient(app)

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

    def test_demo_mode_on_lists_and_runs_only_the_five_scenarios(self):
        runner = FakeSimulationRunner()
        client = self.make_client(enabled=True, runner=runner)

        listing = client.get("/v1/demo/scenarios", headers=bearer())
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(
            {item["id"] for item in listing.json()["scenarios"]}, set(SCENARIOS)
        )

        for scenario_id in SCENARIOS:
            response = client.post(
                "/v1/demo/scenarios",
                headers=bearer(),
                json={"scenario_id": scenario_id},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["scenario_id"], scenario_id)

        self.assertEqual(runner.calls, list(SCENARIOS))

    def test_rejects_invalid_or_extra_browser_input(self):
        client = self.make_client(enabled=True)

        invalid = client.post(
            "/v1/demo/scenarios",
            headers=bearer(),
            json={"scenario_id": "shell-command"},
        )
        extra = client.post(
            "/v1/demo/scenarios",
            headers=bearer(),
            json={"scenario_id": "port-down", "path": "/tmp/fixture"},
        )

        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(extra.status_code, 400)

    def test_reset_is_a_separate_bounded_action(self):
        runner = FakeSimulationRunner()
        client = self.make_client(enabled=True, runner=runner)

        response = client.post("/v1/demo/reset", headers=bearer())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["verified"], "Baseline restored")
        self.assertEqual(runner.calls, ["reset"])

    def test_duplicate_trigger_is_rejected_while_a_scenario_is_running(self):
        runner = FakeSimulationRunner()
        runner.release = threading.Event()
        client = self.make_client(enabled=True, runner=runner)

        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(
                client.post,
                "/v1/demo/scenarios",
                headers=bearer(),
                json={"scenario_id": "port-down"},
            )
            self.assertTrue(runner.started.wait(timeout=1))
            duplicate = client.post(
                "/v1/demo/scenarios",
                headers=bearer(),
                json={"scenario_id": "port-up"},
            )
            runner.release.set()
            completed = first.result(timeout=2)

        self.assertEqual(completed.status_code, 200)
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(runner.calls, ["port-down"])


if __name__ == "__main__":
    unittest.main()
