"""Typed, reversible orchestration for one shared SNMPSIM lab."""

from collections.abc import Callable

from simulation.manifest import Manifest, Scenario, SemanticValue, Target, manifest_sha256
from simulation.state import (
    ScenarioPhase,
    ScenarioState,
    StateTransitionError,
    failed,
    recovery_required,
    transition,
)

from .errors import RunnerError, RunnerEvent, RunnerResult
from .processes import ProcessAdapter
from .protocol import ControlRequest, OperationRequest
from .snmprec import apply_semantic_values, set_endpoint_active
from .storage import RunnerStorage


EventSink = Callable[[RunnerEvent], None]
CancellationPredicate = Callable[[], bool]


class LabRunner:
    def __init__(
        self,
        manifest: Manifest,
        storage: RunnerStorage,
        processes: ProcessAdapter,
        *,
        event_sink: EventSink | None = None,
        cancelled: CancellationPredicate | None = None,
    ):
        self.manifest = manifest
        self.storage = storage
        self.processes = processes
        self.event_sink = event_sink or (lambda _event: None)
        self.cancelled = cancelled or (lambda: False)
        self.sha = manifest_sha256(manifest)
        self.known_ids = frozenset(item.id for item in manifest.scenarios)
        self.scenarios = {item.id: item for item in manifest.scenarios}
        self.targets = {item.id: item for item in manifest.targets}

    def _event(self, event: str, stage: str, **details: str | int | bool | None) -> None:
        self.event_sink(RunnerEvent(event, stage, tuple(details.items())))

    def _check_cancelled(self, stage: str) -> None:
        try:
            is_cancelled = self.cancelled()
        except Exception as error:
            raise RunnerError("cancellation_check_failed", retryable=True, stage=stage) from error
        if is_cancelled:
            raise RunnerError("cancelled", retryable=True, stage=stage)

    @staticmethod
    def _public_error(error: Exception, *, stage: str | None = None) -> RunnerError:
        if isinstance(error, RunnerError):
            return error
        if isinstance(error, StateTransitionError):
            return RunnerError(error.code, stage=stage)
        return RunnerError("internal_error", retryable=True, stage=stage)

    @staticmethod
    def _result(state: ScenarioState | None, *, success: bool, error: RunnerError | None = None) -> RunnerResult:
        return RunnerResult(
            success,
            "ok" if error is None else error.code,
            False if error is None else error.retryable,
            "unknown" if state is None else state.phase.value,
            None if state is None else state.scenario_id,
        )

    def _scenario_target(self, scenario: Scenario) -> Target:
        try:
            return self.targets[scenario.device]
        except KeyError as error:  # Defensive: a validated manifest cannot reach this.
            raise RunnerError("unknown_target") from error

    @staticmethod
    def _require_current_scenario(state: ScenarioState, scenario: Scenario) -> None:
        if state.scenario_id is not None and state.scenario_id != scenario.id:
            raise RunnerError("reset_required")

    def _verify(self, target: Target, expected: tuple[SemanticValue, ...], stage: str) -> None:
        verification = self.processes.verify_snmp(target, expected)
        if not verification.success:
            raise RunnerError(verification.code, retryable=True, stage=stage)
        self._event("verification.completed", stage, verified=True)

    def _restore_health(self) -> None:
        self.storage.restore_baseline(self.manifest)
        for target in self.manifest.targets:
            self.storage.clear_target_cache(target)
        self.processes.restart_snmpsim()
        self._event("service.restarted", "reset")
        if not self.processes.service_active():
            raise RunnerError("service_inactive", retryable=True, stage="reset")
        for target in self.manifest.targets:
            expected = (SemanticValue("endpointReachable", None, target.baseline_active),)
            verification = self.processes.verify_snmp(target, expected)
            if not verification.success:
                raise RunnerError("baseline_verification_failed", retryable=True, stage="reset")
        self._event("baseline.verified", "reset", service_active=True, verified=True)

    def _mark_manual_recovery(self, state: ScenarioState) -> ScenarioState:
        manual = recovery_required(
            state,
            "rollback_failed",
            known_scenario_ids=self.known_ids,
        )
        self.storage.save_state(manual)
        return manual

    def _apply(self, state: ScenarioState, scenario: Scenario) -> ScenarioState:
        active = transition(
            state,
            "apply",
            scenario.id,
            known_scenario_ids=self.known_ids,
        )
        target = self._scenario_target(scenario)
        mutation_started = False
        try:
            self._check_cancelled("apply")
            self.storage.capture_baseline(self.manifest)
            self._event("baseline.captured", "apply", manifest_sha256=self.sha)
            if scenario.mutation_kind == "snmprec_values":
                payload = apply_semantic_values(
                    self.storage.read_fixture(target),
                    scenario.mutation_values,
                )
                mutation_started = True
                self.storage.write_fixture(target, payload)
            elif scenario.mutation_kind == "endpoint_membership":
                payload = set_endpoint_active(
                    self.storage.read_membership(),
                    self.storage.read_inventory(),
                    target,
                    bool(scenario.endpoint_active),
                )
                mutation_started = True
                self.storage.write_membership(payload)
            else:  # Defensive: manifest validation already rejects this.
                raise RunnerError("unsupported_mutation_kind")
            self.storage.save_state(active)
            self._event("mutation.completed", "apply", changed=True)
            self.storage.clear_target_cache(target)
            self._check_cancelled("restart")
            self.processes.restart_snmpsim()
            self._event("service.restarted", "apply")
            self._check_cancelled("apply")
            self._verify(target, scenario.expected_snmp, "apply")
            return active
        except Exception as caught:
            error = self._public_error(caught, stage="apply")
            if not mutation_started:
                raise error
            try:
                self._restore_health()
                reset = ScenarioState(ScenarioPhase.RESET, None, self.sha)
                self.storage.save_state(reset)
            except Exception:
                manual = self._mark_manual_recovery(active)
                raise RunnerError("manual_recovery_required", stage=manual.phase.value) from caught
            raise RunnerError(error.code, retryable=error.retryable, stage=error.stage) from caught

    def _poll(self, state: ScenarioState, scenario: Scenario) -> ScenarioState:
        self._require_current_scenario(state, scenario)
        next_state = transition(state, "poll", known_scenario_ids=self.known_ids)
        self._check_cancelled("poll")
        try:
            self.processes.run_poll(self._scenario_target(scenario), scenario.poll_mode)
        except Exception as caught:
            error = self._public_error(caught, stage="poll")
            failed_state = failed(state, error.code, known_scenario_ids=self.known_ids)
            self.storage.save_state(failed_state)
            raise error
        self.storage.save_state(next_state)
        self._event("poll.completed", "poll", poll_mode=scenario.poll_mode)
        return next_state

    def _observe(self, state: ScenarioState, scenario: Scenario) -> ScenarioState:
        self._require_current_scenario(state, scenario)
        begins = state.phase is ScenarioPhase.BASELINE
        next_state = transition(
            state,
            "observe",
            scenario.id if begins else None,
            known_scenario_ids=self.known_ids,
        )
        self._check_cancelled("observe")
        try:
            self._verify(self._scenario_target(scenario), scenario.expected_snmp, "observe")
        except Exception as caught:
            error = self._public_error(caught, stage="observe")
            failure_base = next_state if begins else state
            failed_state = failed(failure_base, error.code, known_scenario_ids=self.known_ids)
            self.storage.save_state(failed_state)
            raise error
        self.storage.save_state(next_state)
        return next_state

    def _reset(self, state: ScenarioState, scenario: Scenario | None, *, recover: bool) -> ScenarioState:
        if scenario is not None:
            self._require_current_scenario(state, scenario)
        action = "recover" if recover else "reset"
        next_state = transition(state, action, known_scenario_ids=self.known_ids)
        if next_state is state:
            return state
        self._check_cancelled("reset")
        try:
            self._restore_health()
        except Exception as caught:
            manual = self._mark_manual_recovery(state)
            raise RunnerError("manual_recovery_required", stage=manual.phase.value) from caught
        self.storage.save_state(next_state)
        self._event("reset.completed", "reset", changed=True, verified=True)
        return next_state

    def _dispatch(
        self,
        state: ScenarioState,
        request: OperationRequest | ControlRequest,
    ) -> ScenarioState:
        if isinstance(request, ControlRequest):
            if request.control == "status":
                transition(state, "status", known_scenario_ids=self.known_ids)
                return state
            return self._reset(state, None, recover=True)

        scenario = self.scenarios[request.scenario_id]
        if request.action == "apply":
            return self._apply(state, scenario)
        if request.action == "poll":
            return self._poll(state, scenario)
        if request.action == "observe":
            return self._observe(state, scenario)
        return self._reset(state, scenario, recover=False)

    def _validate_request(self, request: OperationRequest | ControlRequest) -> RunnerError | None:
        if not isinstance(request, (OperationRequest, ControlRequest)):
            return RunnerError("request_shape_invalid")
        if type(request.version) is not int or request.version != 1:
            return RunnerError("unsupported_version")
        if isinstance(request, OperationRequest):
            if request.action not in {"apply", "poll", "observe", "reset"}:
                return RunnerError("unsupported_action")
            if request.scenario_id not in self.scenarios:
                return RunnerError("unknown_scenario")
        elif request.control not in {"status", "recover"}:
            return RunnerError("unsupported_control")
        if request.manifest_sha256 != self.sha:
            return RunnerError("manifest_mismatch")
        return None

    def execute(self, request: OperationRequest | ControlRequest) -> RunnerResult:
        state: ScenarioState | None = None
        validation_error = self._validate_request(request)
        if validation_error is not None:
            return self._result(state, success=False, error=validation_error)
        try:
            self._check_cancelled("request")
            with self.storage.acquire():
                state = self.storage.load_state(self.manifest)
                action = request.control if isinstance(request, ControlRequest) else request.action
                self._event("operation.started", action)
                state = self._dispatch(state, request)
                self._event("operation.completed", action)
                return self._result(state, success=True)
        except Exception as caught:
            error = self._public_error(caught)
            try:
                if state is not None:
                    state = self.storage.load_state(self.manifest)
            except Exception:
                pass
            return self._result(state, success=False, error=error)
