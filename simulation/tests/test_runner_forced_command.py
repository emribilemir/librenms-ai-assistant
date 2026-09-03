from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch

from simulation import load_manifest, manifest_sha256
from simulation.runner.errors import RunnerResult


MANIFEST_PATH = Path(__file__).resolve().parents[1] / "scenarios.json"
SHA = manifest_sha256(load_manifest(MANIFEST_PATH))


class FakeRunner:
    def __init__(self, result):
        self.result = result
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        return self.result


class ForcedCommandTests(unittest.TestCase):
    def invoke(self, payload, result=None):
        from simulation.runner.forced_command import main

        runner = FakeRunner(result or RunnerResult(True, "ok", False, "baseline", None))
        output = BytesIO()
        with patch("simulation.runner.forced_command.build_runner_from_environment", return_value=runner):
            exit_code = main(
                stdin=BytesIO(payload),
                stdout=output,
                manifest_path=MANIFEST_PATH,
            )
        return exit_code, output.getvalue(), runner

    def test_reads_one_request_and_emits_exactly_one_terminal_record(self):
        payload = (
            '{"version":1,"control":"status","manifest_sha256":"' + SHA + '"}'
        ).encode()
        exit_code, output, runner = self.invoke(payload)
        self.assertEqual(exit_code, 0)
        self.assertEqual(output.count(b'"type":"result"'), 1)
        self.assertEqual(len(runner.requests), 1)

    def test_validation_retryable_and_recovery_exit_codes_are_stable(self):
        invalid_code, invalid_output, _ = self.invoke(b"{}")
        self.assertEqual(invalid_code, 2)
        self.assertEqual(invalid_output.count(b'"type":"result"'), 1)
        self.assertNotIn(b"Traceback", invalid_output)

        payload = (
            '{"version":1,"control":"status","manifest_sha256":"' + SHA + '"}'
        ).encode()
        retry_code, _, _ = self.invoke(
            payload,
            RunnerResult(False, "lab_busy", True, "unknown", None),
        )
        recovery_code, _, _ = self.invoke(
            payload,
            RunnerResult(False, "manual_recovery_required", False, "manual_recovery_required", "location-change"),
        )
        self.assertEqual(retry_code, 3)
        self.assertEqual(recovery_code, 4)

    def test_oversized_or_internal_failure_is_sanitized_once(self):
        code, output, _ = self.invoke(b"x" * 4097)
        self.assertEqual(code, 2)
        self.assertEqual(output.count(b'"type":"result"'), 1)

        from simulation.runner.forced_command import main

        class ExplodingInput:
            def read(self, amount):
                raise RuntimeError("/private/secret")

        output = BytesIO()
        code = main(stdin=ExplodingInput(), stdout=output, manifest_path=MANIFEST_PATH)
        self.assertEqual(code, 3)
        self.assertEqual(output.getvalue().count(b'"type":"result"'), 1)
        self.assertNotIn(b"secret", output.getvalue())

    def test_runner_exception_is_sanitized_to_one_terminal(self):
        from simulation.runner.forced_command import main

        class ExplodingRunner:
            def execute(self, request):
                raise RuntimeError("token=never-return-this")

        payload = (
            '{"version":1,"control":"status","manifest_sha256":"' + SHA + '"}'
        ).encode()
        output = BytesIO()
        with patch(
            "simulation.runner.forced_command.build_runner_from_environment",
            return_value=ExplodingRunner(),
        ):
            code = main(stdin=BytesIO(payload), stdout=output, manifest_path=MANIFEST_PATH)
        self.assertEqual(code, 3)
        self.assertEqual(output.getvalue().count(b'"type":"result"'), 1)
        self.assertNotIn(b"never-return", output.getvalue())


if __name__ == "__main__":
    unittest.main()
