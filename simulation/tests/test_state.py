from contextlib import contextmanager
import unittest

from simulation.state import (
    ScenarioPhase,
    ScenarioState,
    StateTransitionError,
    failed,
    recovery_required,
    transition,
)


MANIFEST_SHA = "a" * 64


def state(phase, scenario_id=None, error_code=None):
    return ScenarioState(ScenarioPhase(phase), scenario_id, MANIFEST_SHA, error_code)


class ScenarioStateTests(unittest.TestCase):
    def test_allows_only_the_frozen_lifecycle_edges(self):
        allowed = (
            ("baseline", "apply", "applied"),
            ("reset", "apply", "applied"),
            ("applied", "poll", "polled"),
            ("applied", "observe", "observed"),
            ("applied", "reset", "reset"),
            ("polled", "observe", "observed"),
            ("polled", "reset", "reset"),
            ("baseline", "observe", "observed"),
            ("observed", "ai_check", "ai_verified"),
            ("observed", "reset", "reset"),
            ("failed", "reset", "reset"),
            ("ai_verified", "reset", "reset"),
            ("manual_recovery_required", "recover", "reset"),
        )
        for current, action, expected in allowed:
            scenario_id = None if current in {"baseline", "reset"} else "location-change"
            supplied_id = "location-change" if action in {"apply", "observe"} and scenario_id is None else None
            with self.subTest(current=current, action=action):
                result = transition(state(current, scenario_id), action, supplied_id)
                self.assertEqual(result.phase, ScenarioPhase(expected))
                if expected == "reset":
                    self.assertIsNone(result.scenario_id)
                else:
                    self.assertEqual(result.scenario_id, "location-change")
                self.assertEqual(result.manifest_sha256, MANIFEST_SHA)

    def test_baseline_reset_is_a_safe_noop(self):
        current = state("baseline")
        self.assertIs(transition(current, "reset"), current)

    def test_status_is_a_safe_noop_in_every_phase(self):
        for phase in ScenarioPhase:
            current = state(
                phase.value,
                None if phase in {ScenarioPhase.BASELINE, ScenarioPhase.RESET} else "location-change",
            )
            with self.subTest(phase=phase):
                self.assertIs(transition(current, "status"), current)

    def test_apply_and_baseline_observe_require_a_valid_scenario_id(self):
        for action in ("apply", "observe"):
            for scenario_id in (None, "", "UPPER CASE", "../escape"):
                with self.subTest(action=action, scenario_id=scenario_id), self.assert_transition_error(
                    "invalid_scenario_id"
                ):
                    transition(state("baseline"), action, scenario_id)

    def test_repeated_or_switched_apply_returns_stable_conflicts(self):
        with self.assert_transition_error("scenario_already_applied"):
            transition(state("applied", "location-change"), "apply", "location-change")
        for phase in ("applied", "polled", "observed", "ai_verified", "failed"):
            with self.subTest(phase=phase), self.assert_transition_error("reset_required"):
                transition(state(phase, "location-change"), "apply", "uptime-reset")

    def test_manual_recovery_blocks_everything_except_status_and_recover(self):
        current = state("manual_recovery_required", "location-change", "reset_failed")
        for action in ("apply", "poll", "observe", "ai_check", "reset"):
            with self.subTest(action=action), self.assert_transition_error("manual_recovery_required"):
                transition(current, action, "location-change" if action == "apply" else None)

    def test_invalid_order_returns_stable_error(self):
        for current, action in (
            ("baseline", "poll"),
            ("applied", "ai_check"),
            ("polled", "ai_check"),
            ("ai_verified", "observe"),
            ("reset", "poll"),
        ):
            with self.subTest(current=current, action=action), self.assert_transition_error(
                "invalid_transition"
            ):
                transition(state(current, None if current in {"baseline", "reset"} else "location-change"), action)

    def test_failure_and_recovery_helpers_require_stable_error_codes(self):
        for phase in ("applied", "polled"):
            result = failed(state(phase, "location-change"), "runner_timeout")
            self.assertEqual(result.phase, ScenarioPhase.FAILED)
            self.assertEqual(result.last_error_code, "runner_timeout")
            self.assertEqual(result.scenario_id, "location-change")

        recovery = recovery_required(state("failed", "location-change", "runner_timeout"), "reset_failed")
        self.assertEqual(recovery.phase, ScenarioPhase.MANUAL_RECOVERY_REQUIRED)
        self.assertEqual(recovery.last_error_code, "reset_failed")

        for helper in (failed, recovery_required):
            with self.subTest(helper=helper.__name__), self.assert_transition_error("invalid_error_code"):
                helper(state("applied", "location-change"), "")

    @contextmanager
    def assert_transition_error(self, code):
        with self.assertRaises(StateTransitionError) as caught:
            yield
        self.assertEqual(caught.exception.code, code)


if __name__ == "__main__":
    unittest.main()
