"""Bounded JSON protocol accepted by the SSH forced command."""

from dataclasses import dataclass
import json
from typing import Literal

from simulation.manifest import Manifest, manifest_sha256

from .errors import PublicScalar, RunnerError, RunnerEvent, RunnerResult


MAX_REQUEST_BYTES = 4096
MAX_OUTPUT_BYTES = 8192
_OPERATIONS = frozenset({"apply", "poll", "observe", "reset"})
_CONTROLS = frozenset({"status", "recover"})
_SAFE_DETAIL_KEYS = frozenset(
    {
        "changed",
        "diagnostic",
        "duration_ms",
        "exit_code",
        "manifest_sha256",
        "poll_mode",
        "service_active",
        "verified",
    }
)


@dataclass(frozen=True)
class OperationRequest:
    version: int
    action: Literal["apply", "poll", "observe", "reset"]
    scenario_id: str
    manifest_sha256: str


@dataclass(frozen=True)
class ControlRequest:
    version: int
    control: Literal["status", "recover"]
    manifest_sha256: str


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise RunnerError("duplicate_json_key")
        result[key] = value
    return result


def _constant(_: str) -> None:
    raise RunnerError("non_finite_number")


def parse_request(payload: bytes, manifest: Manifest) -> OperationRequest | ControlRequest:
    if len(payload) > MAX_REQUEST_BYTES:
        raise RunnerError("request_too_large")
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise RunnerError("invalid_encoding") from error
    try:
        raw = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
    except RunnerError:
        raise
    except json.JSONDecodeError as error:
        raise RunnerError("invalid_json") from error
    if not isinstance(raw, dict):
        raise RunnerError("request_shape_invalid")

    has_action = "action" in raw
    has_control = "control" in raw
    if has_action == has_control:
        raise RunnerError("request_shape_invalid")
    expected_keys = (
        {"version", "action", "scenario_id", "manifest_sha256"}
        if has_action
        else {"version", "control", "manifest_sha256"}
    )
    unknown = set(raw) - expected_keys
    if unknown:
        raise RunnerError("unknown_key")
    if set(raw) != expected_keys:
        raise RunnerError("request_shape_invalid")
    if type(raw["version"]) is not int or raw["version"] != 1:
        raise RunnerError("unsupported_version")
    expected_sha = manifest_sha256(manifest)
    if not isinstance(raw["manifest_sha256"], str) or raw["manifest_sha256"] != expected_sha:
        raise RunnerError("manifest_mismatch")

    if has_action:
        action = raw["action"]
        if not isinstance(action, str) or action not in _OPERATIONS:
            raise RunnerError("unsupported_action")
        scenario_id = raw["scenario_id"]
        known_ids = {scenario.id for scenario in manifest.scenarios}
        if not isinstance(scenario_id, str) or scenario_id not in known_ids:
            raise RunnerError("unknown_scenario")
        return OperationRequest(1, action, scenario_id, expected_sha)

    control = raw["control"]
    if not isinstance(control, str) or control not in _CONTROLS:
        raise RunnerError("unsupported_control")
    return ControlRequest(1, control, expected_sha)


def _details(items: tuple[tuple[str, PublicScalar], ...]) -> dict[str, PublicScalar]:
    result: dict[str, PublicScalar] = {}
    for key, value in items:
        if key not in _SAFE_DETAIL_KEYS or key in result:
            raise RunnerError("unsafe_output")
        if not isinstance(value, (str, int, bool)) and value is not None:
            raise RunnerError("unsafe_output")
        if isinstance(value, str) and (len(value) > 512 or "\n" in value or "\r" in value):
            raise RunnerError("unsafe_output")
        result[key] = value
    return result


def _encode(raw: dict[str, object]) -> bytes:
    try:
        payload = (json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode(
            "utf-8"
        )
    except (TypeError, ValueError) as error:
        raise RunnerError("unsafe_output") from error
    if len(payload) > MAX_OUTPUT_BYTES:
        raise RunnerError("output_too_large")
    return payload


def encode_event(event: RunnerEvent) -> bytes:
    if not event.event or not event.stage:
        raise RunnerError("unsafe_output")
    return _encode(
        {
            "type": "event",
            "event": event.event,
            "stage": event.stage,
            "details": _details(event.details),
        }
    )


def encode_terminal(result: RunnerResult) -> bytes:
    return _encode(
        {
            "type": "result",
            "success": result.success,
            "code": result.code,
            "retryable": result.retryable,
            "phase": result.phase,
            "scenario_id": result.scenario_id,
            "details": _details(result.details),
        }
    )
