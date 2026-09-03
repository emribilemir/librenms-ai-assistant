"""Pure lifecycle contract shared by the Simulation Lab runner and API."""

from dataclasses import dataclass
from enum import Enum
import re
from typing import Collection


_SCENARIO_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_ERROR_CODE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_MANIFEST_SHA = re.compile(r"^[0-9a-f]{64}$")


class ScenarioPhase(str, Enum):
    BASELINE = "baseline"
    APPLIED = "applied"
    POLLED = "polled"
    OBSERVED = "observed"
    AI_VERIFIED = "ai_verified"
    RESET = "reset"
    FAILED = "failed"
    MANUAL_RECOVERY_REQUIRED = "manual_recovery_required"


@dataclass(frozen=True)
class ScenarioState:
    phase: ScenarioPhase
    scenario_id: str | None
    manifest_sha256: str
    last_error_code: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.phase, ScenarioPhase)
            or not isinstance(self.manifest_sha256, str)
            or _MANIFEST_SHA.fullmatch(self.manifest_sha256) is None
        ):
            raise ValueError("invalid_state")
        empty_phases = {ScenarioPhase.BASELINE, ScenarioPhase.RESET}
        error_phases = {ScenarioPhase.FAILED, ScenarioPhase.MANUAL_RECOVERY_REQUIRED}
        if self.phase in empty_phases:
            valid = self.scenario_id is None and self.last_error_code is None
        elif self.phase in error_phases:
            valid = _valid_scenario_id(self.scenario_id) and _valid_error_code(self.last_error_code)
        else:
            valid = _valid_scenario_id(self.scenario_id) and self.last_error_code is None
        if not valid:
            raise ValueError("invalid_state")


class StateTransitionError(ValueError):
    def __init__(self, code: str, current: ScenarioPhase, action: str):
        self.code = code
        self.current = current
        self.action = action
        super().__init__(f"{code}: {current.value} + {action}")


_TRANSITIONS = {
    (ScenarioPhase.BASELINE, "apply"): ScenarioPhase.APPLIED,
    (ScenarioPhase.RESET, "apply"): ScenarioPhase.APPLIED,
    (ScenarioPhase.APPLIED, "poll"): ScenarioPhase.POLLED,
    (ScenarioPhase.APPLIED, "observe"): ScenarioPhase.OBSERVED,
    (ScenarioPhase.APPLIED, "reset"): ScenarioPhase.RESET,
    (ScenarioPhase.POLLED, "observe"): ScenarioPhase.OBSERVED,
    (ScenarioPhase.POLLED, "reset"): ScenarioPhase.RESET,
    (ScenarioPhase.BASELINE, "observe"): ScenarioPhase.OBSERVED,
    (ScenarioPhase.OBSERVED, "ai_check"): ScenarioPhase.AI_VERIFIED,
    (ScenarioPhase.OBSERVED, "reset"): ScenarioPhase.RESET,
    (ScenarioPhase.FAILED, "reset"): ScenarioPhase.RESET,
    (ScenarioPhase.AI_VERIFIED, "reset"): ScenarioPhase.RESET,
    (ScenarioPhase.MANUAL_RECOVERY_REQUIRED, "recover"): ScenarioPhase.RESET,
}


def _raise(code: str, state: ScenarioState, action: str) -> None:
    raise StateTransitionError(code, state.phase, action)


def _valid_scenario_id(value: str | None) -> bool:
    return isinstance(value, str) and _SCENARIO_ID.fullmatch(value) is not None


def _valid_error_code(value: str | None) -> bool:
    return isinstance(value, str) and _ERROR_CODE.fullmatch(value) is not None


def _validate_membership(
    state: ScenarioState,
    scenario_id: str | None,
    known_scenario_ids: Collection[str],
    action: str,
) -> None:
    known = frozenset(known_scenario_ids)
    if state.scenario_id is not None and state.scenario_id not in known:
        _raise("unknown_scenario", state, action)
    if scenario_id is not None and _valid_scenario_id(scenario_id) and scenario_id not in known:
        _raise("unknown_scenario", state, action)


def transition(
    state: ScenarioState,
    action: str,
    scenario_id: str | None = None,
    *,
    known_scenario_ids: Collection[str],
) -> ScenarioState:
    """Return the next immutable state or a stable conflict/ordering error."""

    _validate_membership(state, scenario_id, known_scenario_ids, action)
    if action == "status":
        return state
    if state.phase is ScenarioPhase.MANUAL_RECOVERY_REQUIRED and action != "recover":
        _raise("manual_recovery_required", state, action)

    if action == "apply" and state.scenario_id is not None:
        code = "scenario_already_applied" if state.scenario_id == scenario_id else "reset_required"
        _raise(code, state, action)

    begins_scenario = action == "apply" or (state.phase is ScenarioPhase.BASELINE and action == "observe")
    if begins_scenario:
        if not _valid_scenario_id(scenario_id):
            _raise("invalid_scenario_id", state, action)
    elif scenario_id is not None:
        _raise("invalid_scenario_id", state, action)

    if state.phase is ScenarioPhase.BASELINE and action == "reset":
        return state

    try:
        next_phase = _TRANSITIONS[(state.phase, action)]
    except KeyError:
        _raise("invalid_transition", state, action)

    if next_phase is ScenarioPhase.RESET:
        return ScenarioState(next_phase, None, state.manifest_sha256)
    next_scenario_id = scenario_id if begins_scenario else state.scenario_id
    return ScenarioState(next_phase, next_scenario_id, state.manifest_sha256)


def failed(
    state: ScenarioState,
    error_code: str,
    *,
    known_scenario_ids: Collection[str],
) -> ScenarioState:
    """Move an active scenario to failed without overloading normal actions."""

    _validate_membership(state, None, known_scenario_ids, "fail")
    if not _valid_error_code(error_code):
        _raise("invalid_error_code", state, "fail")
    if state.phase not in {
        ScenarioPhase.APPLIED,
        ScenarioPhase.POLLED,
        ScenarioPhase.OBSERVED,
        ScenarioPhase.AI_VERIFIED,
    } or state.scenario_id is None:
        _raise("invalid_transition", state, "fail")
    return ScenarioState(ScenarioPhase.FAILED, state.scenario_id, state.manifest_sha256, error_code)


def recovery_required(
    state: ScenarioState,
    error_code: str,
    *,
    known_scenario_ids: Collection[str],
) -> ScenarioState:
    """Record that automatic reset could not restore the shared lab baseline."""

    _validate_membership(state, None, known_scenario_ids, "recovery_required")
    if not _valid_error_code(error_code):
        _raise("invalid_error_code", state, "recovery_required")
    if state.scenario_id is None or state.phase in {ScenarioPhase.BASELINE, ScenarioPhase.RESET}:
        _raise("invalid_transition", state, "recovery_required")
    return ScenarioState(
        ScenarioPhase.MANUAL_RECOVERY_REQUIRED,
        state.scenario_id,
        state.manifest_sha256,
        error_code,
    )
