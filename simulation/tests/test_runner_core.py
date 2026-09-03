from contextlib import contextmanager
from pathlib import Path
import unittest

from simulation import SemanticValue, load_manifest, manifest_sha256
from simulation.runner.errors import RunnerError
from simulation.runner.processes import ProcessResult, VerificationResult
from simulation.runner.protocol import ControlRequest, OperationRequest
from simulation.state import ScenarioPhase, ScenarioState


MANIFEST = load_manifest(Path(__file__).resolve().parents[1] / "scenarios.json")
SHA = manifest_sha256(MANIFEST)
LOCATION = next(item for item in MANIFEST.scenarios if item.id == "location-change")
DEVICE_DOWN = next(item for item in MANIFEST.scenarios if item.id == "device-up-to-down")


class FakeStorage:
    def __init__(self, phase=ScenarioPhase.BASELINE, scenario_id=None):
        self.state = ScenarioState(phase, scenario_id, SHA)
        self.calls = []
        self.fixture = b"1.3.6.1.2.1.1.6.0|4|Baseline\n"
        self.membership = (
            b"127.0.0.11|lab-j9772a-01|J9772A\n"
            b"127.0.0.13|lab-j9775a-01|J9775A\n"
        )
        self.inventory = (
            b"127.0.0.11|lab-j9772a-01|J9772A\n"
            b"127.0.0.13|lab-j9775a-01|J9775A\n"
        )
        self.fail_restore = False
        self.acquire_count = 0

    @contextmanager
    def acquire(self):
        self.acquire_count += 1
        self.calls.append("lock")
        yield

    def load_state(self, manifest):
        self.calls.append("load")
        return self.state

    def save_state(self, state):
        self.calls.append(f"save:{state.phase.value}")
        self.state = state

    def capture_baseline(self, manifest):
        self.calls.append("capture")

    def restore_baseline(self, manifest):
        self.calls.append("restore")
        if self.fail_restore:
            raise RunnerError("baseline_restore_failed", stage="reset")
        self.fixture = b"1.3.6.1.2.1.1.6.0|4|Baseline\n"
        self.membership = b"127.0.0.11|lab-j9772a-01|J9772A\n"

    def read_fixture(self, target):
        self.calls.append(f"read_fixture:{target.id}")
        return self.fixture

    def write_fixture(self, target, payload):
        self.calls.append(f"write_fixture:{target.id}")
        self.fixture = payload

    def read_membership(self):
        self.calls.append("read_membership")
        return self.membership

    def read_inventory(self):
        self.calls.append("read_inventory")
        return self.inventory

    def write_membership(self, payload):
        self.calls.append("write_membership")
        self.membership = payload

    def clear_target_cache(self, target):
        self.calls.append(f"clear:{target.id}")
        return ()


class FakeProcesses:
    def __init__(self):
        self.calls = []
        self.verify_results = []
        self.active = True
        self.poll_error = None
        self.restart_error = None

    def restart_snmpsim(self):
        self.calls.append("restart")
        if self.restart_error:
            raise self.restart_error
        return ProcessResult(0, 1, (), False)

    def service_active(self):
        self.calls.append("active")
        return self.active

    def run_poll(self, target, mode):
        self.calls.append(f"poll:{target.id}:{mode}")
        if self.poll_error:
            raise self.poll_error
        return ()

    def verify_snmp(self, target, expected):
        semantics = ",".join(item.semantic for item in expected)
        self.calls.append(f"verify:{target.id}:{semantics}")
        if self.verify_results:
            return self.verify_results.pop(0)
        return VerificationResult(True, "verified")


def operation(action, scenario_id="location-change", sha=SHA):
    return OperationRequest(1, action, scenario_id, sha)


class LabRunnerTests(unittest.TestCase):
    def build(self, storage=None, processes=None, events=None, cancelled=None):
        from simulation.runner.core import LabRunner

        return LabRunner(
            MANIFEST,
            storage or FakeStorage(),
            processes or FakeProcesses(),
            event_sink=(events if events is not None else []).append,
            cancelled=cancelled or (lambda: False),
        )

    def test_manifest_mismatch_fails_before_lock(self):
        storage = FakeStorage()
        result = self.build(storage).execute(operation("apply", sha="0" * 64))
        self.assertFalse(result.success)
        self.assertEqual(result.code, "manifest_mismatch")
        self.assertEqual(storage.acquire_count, 0)

    def test_status_is_locked_read_only_and_reports_current_state(self):
        storage = FakeStorage(ScenarioPhase.POLLED, "location-change")
        result = self.build(storage).execute(ControlRequest(1, "status", SHA))
        self.assertTrue(result.success)
        self.assertEqual(result.phase, "polled")
        self.assertEqual(result.scenario_id, "location-change")
        self.assertEqual(storage.calls, ["lock", "load"])

    def test_apply_value_mutates_restarts_verifies_and_persists(self):
        storage, processes, events = FakeStorage(), FakeProcesses(), []
        result = self.build(storage, processes, events).execute(operation("apply"))
        self.assertTrue(result.success)
        self.assertEqual(result.phase, "applied")
        self.assertIn(b"Murat Bey Demo Lab", storage.fixture)
        self.assertEqual(
            storage.calls,
            [
                "lock",
                "load",
                "capture",
                "read_fixture:lab-j9772a-01",
                "write_fixture:lab-j9772a-01",
                "save:applied",
                "clear:lab-j9772a-01",
            ],
        )
        self.assertEqual(processes.calls, ["restart", "verify:lab-j9772a-01:sysLocation"])
        self.assertEqual(
            [event.event for event in events],
            [
                "operation.started",
                "baseline.captured",
                "mutation.completed",
                "service.restarted",
                "verification.completed",
                "operation.completed",
            ],
        )

    def test_apply_endpoint_membership_uses_inventory(self):
        storage = FakeStorage()
        result = self.build(storage).execute(operation("apply", DEVICE_DOWN.id))
        self.assertTrue(result.success)
        self.assertNotIn(b"lab-j9772a-01", storage.membership)
        self.assertIn(b"lab-j9775a-01", storage.membership)
        self.assertIn("read_inventory", storage.calls)

    def test_poll_uses_declared_mode_and_rejects_scenario_switch(self):
        storage, processes = FakeStorage(ScenarioPhase.APPLIED, "location-change"), FakeProcesses()
        result = self.build(storage, processes).execute(operation("poll"))
        self.assertTrue(result.success)
        self.assertEqual(result.phase, "polled")
        self.assertEqual(processes.calls, ["poll:lab-j9772a-01:poller"])

        conflict = self.build(storage, processes).execute(operation("apply", "uptime-reset"))
        self.assertFalse(conflict.success)
        self.assertEqual(conflict.code, "reset_required")

        repeated_storage = FakeStorage(ScenarioPhase.APPLIED, "location-change")
        repeated = self.build(repeated_storage).execute(operation("apply"))
        self.assertFalse(repeated.success)
        self.assertEqual(repeated.code, "scenario_already_applied")

    def test_observe_supports_baseline_and_applied_states(self):
        for phase in (ScenarioPhase.BASELINE, ScenarioPhase.APPLIED):
            storage = FakeStorage(phase, None if phase is ScenarioPhase.BASELINE else "location-change")
            result = self.build(storage).execute(operation("observe"))
            self.assertTrue(result.success)
            self.assertEqual(result.phase, "observed")

    def test_reset_restores_all_targets_and_proves_service_and_reachability(self):
        for phase in (
            ScenarioPhase.APPLIED,
            ScenarioPhase.POLLED,
            ScenarioPhase.OBSERVED,
            ScenarioPhase.AI_VERIFIED,
            ScenarioPhase.FAILED,
        ):
            error = "poll_failed" if phase is ScenarioPhase.FAILED else None
            storage = FakeStorage()
            storage.state = ScenarioState(phase, "location-change", SHA, error)
            processes = FakeProcesses()
            result = self.build(storage, processes).execute(operation("reset"))
            self.assertTrue(result.success, (phase, result))
            self.assertEqual(result.phase, "reset")
            self.assertEqual(processes.calls[0:2], ["restart", "active"])
            self.assertEqual(sum(call.startswith("verify:") for call in processes.calls), 2)

        baseline = FakeStorage()
        result = self.build(baseline).execute(operation("reset"))
        self.assertTrue(result.success)
        self.assertEqual(baseline.calls, ["lock", "load"])

    def test_recover_only_succeeds_after_baseline_health_check(self):
        storage = FakeStorage()
        storage.state = ScenarioState(
            ScenarioPhase.MANUAL_RECOVERY_REQUIRED,
            "location-change",
            SHA,
            "rollback_failed",
        )
        result = self.build(storage).execute(ControlRequest(1, "recover", SHA))
        self.assertTrue(result.success)
        self.assertEqual(result.phase, "reset")

    def test_apply_verification_failure_rolls_back_and_returns_original_error(self):
        storage, processes = FakeStorage(), FakeProcesses()
        processes.verify_results.append(VerificationResult(False, "snmp_mismatch"))
        result = self.build(storage, processes).execute(operation("apply"))
        self.assertFalse(result.success)
        self.assertEqual(result.code, "snmp_mismatch")
        self.assertEqual(result.phase, "reset")
        self.assertIn("restore", storage.calls)

    def test_rollback_failure_persists_manual_recovery(self):
        storage, processes = FakeStorage(), FakeProcesses()
        storage.fail_restore = True
        processes.verify_results.append(VerificationResult(False, "snmp_mismatch"))
        result = self.build(storage, processes).execute(operation("apply"))
        self.assertFalse(result.success)
        self.assertEqual(result.code, "manual_recovery_required")
        self.assertEqual(result.phase, "manual_recovery_required")
        self.assertEqual(storage.state.last_error_code, "rollback_failed")

    def test_reset_health_failure_enters_manual_recovery(self):
        storage = FakeStorage(ScenarioPhase.APPLIED, "location-change")
        processes = FakeProcesses()
        processes.active = False
        result = self.build(storage, processes).execute(operation("reset"))
        self.assertFalse(result.success)
        self.assertEqual(result.phase, "manual_recovery_required")

    def test_poll_failure_persists_failed_state_without_raw_error_data(self):
        storage = FakeStorage(ScenarioPhase.APPLIED, "location-change")
        processes = FakeProcesses()
        processes.poll_error = RuntimeError("/secret/path token=do-not-leak")
        result = self.build(storage, processes).execute(operation("poll"))
        self.assertFalse(result.success)
        self.assertEqual(result.code, "internal_error")
        self.assertNotIn("secret", repr(result))

    def test_cancellation_returns_one_bounded_terminal_result(self):
        calls = iter((False, True))
        result = self.build(cancelled=lambda: next(calls, True)).execute(operation("apply"))
        self.assertFalse(result.success)
        self.assertEqual(result.code, "cancelled")
        self.assertTrue(result.retryable)

    def test_cancellation_after_mutation_cannot_skip_rollback(self):
        storage = FakeStorage()
        checks = iter((False, False, True))
        result = self.build(storage=storage, cancelled=lambda: next(checks, True)).execute(
            operation("apply")
        )
        self.assertFalse(result.success)
        self.assertEqual(result.code, "cancelled")
        self.assertEqual(result.phase, "reset")
        self.assertIn("restore", storage.calls)

    def test_reset_cancelled_before_restore_keeps_the_active_state(self):
        storage = FakeStorage(ScenarioPhase.APPLIED, "location-change")
        checks = iter((False, True))
        result = self.build(storage=storage, cancelled=lambda: next(checks, True)).execute(
            operation("reset")
        )
        self.assertFalse(result.success)
        self.assertEqual(result.code, "cancelled")
        self.assertEqual(result.phase, "applied")
        self.assertNotIn("restore", storage.calls)

    def test_poll_and_observe_cancelled_before_work_preserve_state(self):
        for action in ("poll", "observe"):
            storage = FakeStorage(ScenarioPhase.APPLIED, "location-change")
            checks = iter((False, True))
            result = self.build(storage=storage, cancelled=lambda: next(checks, True)).execute(
                operation(action)
            )
            with self.subTest(action=action):
                self.assertFalse(result.success)
                self.assertEqual(result.code, "cancelled")
                self.assertEqual(result.phase, "applied")

    def test_global_busy_returns_retryable_without_loading_state(self):
        storage = FakeStorage()

        @contextmanager
        def busy():
            raise RunnerError("lab_busy", retryable=True)
            yield

        storage.acquire = busy
        result = self.build(storage).execute(operation("apply"))
        self.assertFalse(result.success)
        self.assertEqual(result.code, "lab_busy")
        self.assertTrue(result.retryable)
        self.assertNotIn("load", storage.calls)


if __name__ == "__main__":
    unittest.main()
