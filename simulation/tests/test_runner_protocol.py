from contextlib import contextmanager
import json
from pathlib import Path
import unittest

from simulation import load_manifest, manifest_sha256
from simulation.runner.errors import RunnerError, RunnerEvent, RunnerResult
from simulation.runner.protocol import (
    ControlRequest,
    OperationRequest,
    encode_event,
    encode_terminal,
    parse_request,
)


MANIFEST = load_manifest(Path(__file__).resolve().parents[1] / "scenarios.json")
MANIFEST_SHA = manifest_sha256(MANIFEST)


def operation(**changes):
    request = {
        "version": 1,
        "action": "apply",
        "scenario_id": "location-change",
        "manifest_sha256": MANIFEST_SHA,
    }
    request.update(changes)
    return json.dumps(request, separators=(",", ":")).encode()


def control(**changes):
    request = {"version": 1, "control": "status", "manifest_sha256": MANIFEST_SHA}
    request.update(changes)
    return json.dumps(request, separators=(",", ":")).encode()


class RunnerProtocolTests(unittest.TestCase):
    def test_accepts_exact_operations_and_controls(self):
        for action in ("apply", "poll", "observe", "reset"):
            parsed = parse_request(operation(action=action), MANIFEST)
            self.assertIsInstance(parsed, OperationRequest)
            self.assertEqual(parsed.action, action)
            self.assertEqual(parsed.scenario_id, "location-change")

        for name in ("status", "recover"):
            parsed = parse_request(control(control=name), MANIFEST)
            self.assertIsInstance(parsed, ControlRequest)
            self.assertEqual(parsed.control, name)

    def test_rejects_oversized_invalid_or_trailing_json(self):
        cases = (
            (b" " * 4097, "request_too_large"),
            (b"\xff", "invalid_encoding"),
            (b"{", "invalid_json"),
            (operation() + b"{}", "invalid_json"),
            (b'{"version":1,"version":1}', "duplicate_json_key"),
            (b'{"version":NaN}', "non_finite_number"),
        )
        for payload, code in cases:
            with self.subTest(code=code), self.assert_runner_error(code):
                parse_request(payload, MANIFEST)

    def test_rejects_shape_version_manifest_and_membership_failures(self):
        cases = (
            (operation(extra=True), "unknown_key"),
            (operation(version=True), "unsupported_version"),
            (operation(version=1.0), "unsupported_version"),
            (operation(version=2), "unsupported_version"),
            (operation(manifest_sha256="0" * 64), "manifest_mismatch"),
            (operation(action="execute"), "unsupported_action"),
            (operation(scenario_id="not-in-manifest"), "unknown_scenario"),
            (control(control="delete"), "unsupported_control"),
            (
                json.dumps(
                    {
                        "version": 1,
                        "action": "apply",
                        "control": "status",
                        "scenario_id": "location-change",
                        "manifest_sha256": MANIFEST_SHA,
                    }
                ).encode(),
                "request_shape_invalid",
            ),
        )
        for payload, code in cases:
            with self.subTest(code=code), self.assert_runner_error(code):
                parse_request(payload, MANIFEST)

    def test_rejects_execution_material_at_the_transport_boundary(self):
        for field, value in (
            ("command", "touch /tmp/pwned"),
            ("path", "/etc/shadow"),
            ("oid", "1.3.6.1.4.1.999"),
            ("hostname", "attacker.example"),
            ("value", "$(id)"),
        ):
            request = json.loads(operation())
            request[field] = value
            with self.subTest(field=field), self.assert_runner_error("unknown_key"):
                parse_request(json.dumps(request).encode(), MANIFEST)

    def test_encodes_bounded_single_line_public_records(self):
        event = RunnerEvent("stage.completed", "apply", (("duration_ms", 12),))
        result = RunnerResult(True, "completed", False, "applied", "location-change")

        event_payload = encode_event(event)
        result_payload = encode_terminal(result)

        self.assertTrue(event_payload.endswith(b"\n"))
        self.assertTrue(result_payload.endswith(b"\n"))
        self.assertNotIn(b"\n", event_payload[:-1])
        self.assertEqual(json.loads(event_payload)["event"], "stage.completed")
        self.assertEqual(json.loads(result_payload)["code"], "completed")
        self.assertLessEqual(len(event_payload), 8192)
        self.assertLessEqual(len(result_payload), 8192)

    @contextmanager
    def assert_runner_error(self, code):
        with self.assertRaises(RunnerError) as caught:
            yield
        self.assertEqual(caught.exception.code, code)


if __name__ == "__main__":
    unittest.main()
