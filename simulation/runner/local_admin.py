"""Fixed local installation/rollback helpers; not part of the SSH protocol."""

from simulation.manifest import load_manifest, manifest_sha256
from simulation.state import ScenarioPhase

from .errors import RunnerResult
from .forced_command import PRODUCTION_MANIFEST, build_runner_from_environment
from .protocol import ControlRequest, OperationRequest, encode_terminal


def capture_baseline() -> None:
    manifest = load_manifest(PRODUCTION_MANIFEST)
    runner = build_runner_from_environment(manifest)
    with runner.storage.acquire():
        state = runner.storage.load_state(manifest)
        runner.storage.capture_baseline(manifest)
        runner.storage.save_state(state)


def status() -> RunnerResult:
    manifest = load_manifest(PRODUCTION_MANIFEST)
    runner = build_runner_from_environment(manifest)
    return runner.execute(ControlRequest(1, "status", manifest_sha256(manifest)))


def reset_current() -> RunnerResult:
    manifest = load_manifest(PRODUCTION_MANIFEST)
    runner = build_runner_from_environment(manifest)
    state = runner.storage.load_state(manifest)
    sha = manifest_sha256(manifest)
    if state.phase is ScenarioPhase.MANUAL_RECOVERY_REQUIRED:
        request = ControlRequest(1, "recover", sha)
    else:
        scenario_id = state.scenario_id or manifest.scenarios[0].id
        request = OperationRequest(1, "reset", scenario_id, sha)
    return runner.execute(request)


def write_result(result: RunnerResult) -> int:
    import sys

    sys.stdout.buffer.write(encode_terminal(result))
    sys.stdout.buffer.flush()
    if result.success:
        return 0
    return 4 if result.phase == "manual_recovery_required" else 3
