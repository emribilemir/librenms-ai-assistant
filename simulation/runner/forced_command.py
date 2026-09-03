"""Bounded stdin/stdout entry point for the dedicated SSH forced command."""

from pathlib import Path
import sys
from typing import BinaryIO

from simulation.manifest import Manifest, load_manifest

from .core import LabRunner
from .errors import RunnerError, RunnerResult
from .processes import ProcessAdapter
from .protocol import MAX_REQUEST_BYTES, encode_event, encode_terminal, parse_request
from .storage import PosixOwnershipPolicy, RunnerLayout, RunnerStorage


PRODUCTION_MANIFEST = Path("/opt/librenms-ai-lab/manifest/scenarios.json")


def build_runner_from_environment(
    manifest: Manifest | None = None,
    *,
    event_sink=None,
) -> LabRunner:
    """Build only the fixed production layout; no path or command env overrides exist."""

    resolved_manifest = manifest or load_manifest(PRODUCTION_MANIFEST)
    layout = RunnerLayout.production()
    storage = RunnerStorage(layout, PosixOwnershipPolicy())
    return LabRunner(
        resolved_manifest,
        storage,
        ProcessAdapter(layout),
        event_sink=event_sink,
    )


def _error_result(error: RunnerError) -> RunnerResult:
    phase = "manual_recovery_required" if error.code == "manual_recovery_required" else "unknown"
    return RunnerResult(False, error.code, error.retryable, phase, None)


def _exit_code(result: RunnerResult) -> int:
    if result.success:
        return 0
    if result.phase == "manual_recovery_required" or result.code == "manual_recovery_required":
        return 4
    return 3 if result.retryable else 2


def main(
    *,
    stdin: BinaryIO | None = None,
    stdout: BinaryIO | None = None,
    manifest_path: Path = PRODUCTION_MANIFEST,
) -> int:
    input_stream = stdin or sys.stdin.buffer
    output_stream = stdout or sys.stdout.buffer
    terminal: RunnerResult
    try:
        manifest = load_manifest(manifest_path)

        def emit(event):
            output_stream.write(encode_event(event))
            output_stream.flush()

        runner = build_runner_from_environment(manifest, event_sink=emit)
        payload = input_stream.read(MAX_REQUEST_BYTES + 1)
        request = parse_request(payload, manifest)
        terminal = runner.execute(request)
    except RunnerError as error:
        terminal = _error_result(error)
    except Exception:
        terminal = RunnerResult(False, "internal_error", True, "unknown", None)
    try:
        output_stream.write(encode_terminal(terminal))
        output_stream.flush()
    except Exception:
        return 3
    return _exit_code(terminal)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
