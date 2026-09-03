"""Strict, dependency-free Simulation Lab manifest validation."""

from dataclasses import dataclass
import hashlib
import ipaddress
import json
from pathlib import Path
import re
from typing import Any

from .catalog import SEMANTIC_CATALOG, validate_semantic_value


_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_HOSTNAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$")
_LABEL = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_POLL_MODES = frozenset({"none", "poller", "discovery", "discovery_then_poller"})
_MUTATION_KINDS = frozenset({"snmprec_values", "endpoint_membership"})
_FORBIDDEN_KEYS = {
    "oid": "raw_oid_forbidden",
    "path": "path_forbidden",
    "file": "path_forbidden",
    "command": "shell_string_forbidden",
    "shell": "shell_string_forbidden",
    "executable": "shell_string_forbidden",
    "argv": "shell_string_forbidden",
}
_SHELL_SYNTAX = re.compile(r"\$\(|`|[;&|<>]|\r|\n")


class ManifestValidationError(ValueError):
    def __init__(self, code: str, path: str):
        self.code = code
        self.path = path
        super().__init__(f"{code}: {path}")


@dataclass(frozen=True)
class Target:
    id: str
    hostname: str
    agent_address: str
    agent_port: int
    fixture: str
    baseline_active: bool
    capabilities: tuple[str, ...]


@dataclass(frozen=True)
class SemanticValue:
    semantic: str
    index: int | None
    value: int | str | bool


@dataclass(frozen=True)
class SurfaceExpectation:
    kind: str
    field: str | None = None
    value: int | str | None = None
    if_index: int | None = None
    if_admin_status: str | None = None
    if_oper_status: str | None = None
    if_alias: str | None = None
    status: str | None = None
    reachable: bool | None = None
    event_type: str | None = None


@dataclass(frozen=True)
class EvidenceSelector:
    hostname: str | None = None
    if_index: int | None = None
    event_type: str | None = None


@dataclass(frozen=True)
class EvidenceExpectation:
    resource: str
    selector: EvidenceSelector


@dataclass(frozen=True)
class Scenario:
    id: str
    name: str
    description: str
    device: str
    precondition: str
    mutation_kind: str
    mutation_values: tuple[SemanticValue, ...]
    endpoint_active: bool | None
    expected_snmp: tuple[SemanticValue, ...]
    poll_mode: str
    expected_librenms_surface: tuple[SurfaceExpectation, ...]
    expected_api_evidence: tuple[EvidenceExpectation, ...]
    example_questions: tuple[str, ...]
    expected_answer_semantics: tuple[str, ...]
    reset_state: str


@dataclass(frozen=True)
class Manifest:
    version: int
    targets: tuple[Target, ...]
    scenarios: tuple[Scenario, ...]
    canonical: bytes


def _error(code: str, path: str) -> None:
    raise ManifestValidationError(code, path)


def _scan_forbidden_keys(value: object, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in _FORBIDDEN_KEYS:
                _error(_FORBIDDEN_KEYS[key], f"{path}.{key}")
            _scan_forbidden_keys(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _scan_forbidden_keys(nested, f"{path}[{index}]")


def _object(value: object, path: str, keys: set[str], required: set[str] | None = None) -> dict[str, Any]:
    if not isinstance(value, dict):
        _error("invalid_type", path)
    unknown = set(value) - keys
    if unknown:
        _error("unknown_key", f"{path}.{sorted(unknown)[0]}")
    missing = (required if required is not None else keys) - set(value)
    if missing:
        _error("missing_key", f"{path}.{sorted(missing)[0]}")
    return value


def _array(value: object, path: str, *, nonempty: bool = False) -> list[Any]:
    if not isinstance(value, list):
        _error("invalid_type", path)
    if nonempty and not value:
        _error("empty_value", path)
    return value


def _text(value: object, path: str, *, maximum: int = 500, pattern: re.Pattern[str] | None = None) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        _error("invalid_text", path)
    if pattern is not None and pattern.fullmatch(value) is None:
        _error("invalid_text", path)
    return value


def _control_text(value: object, path: str, *, pattern: re.Pattern[str] = _LABEL) -> str:
    text = _text(value, path, maximum=64, pattern=pattern)
    if _SHELL_SYNTAX.search(text):
        _error("shell_string_forbidden", path)
    return text


def _keys(value: dict[str, object], path: str, allowed: set[str]) -> None:
    unknown = set(value) - allowed
    if unknown:
        _error("unknown_key", f"{path}.{sorted(unknown)[0]}")


def _semantic_value(value: object, path: str, *, control: bool) -> SemanticValue:
    raw = _object(value, path, {"semantic", "index", "value"})
    semantic = _control_text(raw["semantic"], f"{path}.semantic")
    index = raw["index"]
    semantic_value = raw["value"]
    if control and isinstance(semantic_value, str) and _SHELL_SYNTAX.search(semantic_value):
        _error("shell_string_forbidden", f"{path}.value")
    try:
        validate_semantic_value(semantic, index, semantic_value)
    except ValueError as error:
        _error("semantic_value_invalid", f"{path}: {error}")
    return SemanticValue(semantic, index, semantic_value)


def _target(value: object, path: str) -> Target:
    raw = _object(
        value,
        path,
        {"id", "hostname", "agent_address", "agent_port", "fixture", "baseline_active", "capabilities"},
    )
    target_id = _control_text(raw["id"], f"{path}.id", pattern=_IDENTIFIER)
    hostname = _control_text(raw["hostname"], f"{path}.hostname", pattern=_HOSTNAME)
    fixture = _control_text(raw["fixture"], f"{path}.fixture", pattern=_IDENTIFIER)
    address = _text(raw["agent_address"], f"{path}.agent_address", maximum=15)
    try:
        parsed_address = ipaddress.ip_address(address)
    except ValueError:
        _error("invalid_agent_address", f"{path}.agent_address")
    if parsed_address.version != 4 or not parsed_address.is_loopback:
        _error("invalid_agent_address", f"{path}.agent_address")
    if (
        isinstance(raw["agent_port"], bool)
        or not isinstance(raw["agent_port"], int)
        or raw["agent_port"] != 1611
    ):
        _error("invalid_agent_port", f"{path}.agent_port")
    if not isinstance(raw["baseline_active"], bool):
        _error("invalid_type", f"{path}.baseline_active")
    capabilities = tuple(
        _control_text(item, f"{path}.capabilities[{index}]")
        for index, item in enumerate(_array(raw["capabilities"], f"{path}.capabilities", nonempty=True))
    )
    if len(capabilities) != len(set(capabilities)):
        _error("duplicate_capability", f"{path}.capabilities")
    return Target(
        target_id,
        hostname,
        address,
        1611,
        fixture,
        raw["baseline_active"],
        capabilities,
    )


def _positive_index(value: object, path: str, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 4096:
        _error(code, path)
    return value


def _surface(value: object, path: str) -> SurfaceExpectation:
    raw = _object(
        value,
        path,
        {
            "kind",
            "field",
            "value",
            "ifIndex",
            "ifAdminStatus",
            "ifOperStatus",
            "ifAlias",
            "status",
            "reachable",
            "event_type",
        },
        {"kind"},
    )
    kind = _control_text(raw["kind"], f"{path}.kind")
    if kind == "device" and "field" in raw:
        if set(raw) != {"kind", "field", "value"}:
            _error("invalid_surface", path)
        field = raw["field"]
        if not isinstance(field, str) or field not in {"location", "uptime"}:
            _error("invalid_surface", f"{path}.field")
        surface_value = raw["value"]
        if field == "location":
            if not isinstance(surface_value, str) or not surface_value or len(surface_value.encode("utf-8")) > 128:
                _error("invalid_surface", f"{path}.value")
        elif isinstance(surface_value, bool) or not isinstance(surface_value, int) or surface_value < 0:
            _error("invalid_surface", f"{path}.value")
        return SurfaceExpectation(kind, field=field, value=surface_value)

    if kind == "device":
        if set(raw) != {"kind", "status", "reachable"}:
            _error("invalid_surface", path)
        if (
            not isinstance(raw["status"], str)
            or raw["status"] not in {"up", "down"}
            or not isinstance(raw["reachable"], bool)
        ):
            _error("invalid_surface", path)
        return SurfaceExpectation(kind, status=raw["status"], reachable=raw["reachable"])

    if kind == "port":
        allowed = {"kind", "ifIndex", "ifAdminStatus", "ifOperStatus", "ifAlias"}
        if not {"kind", "ifIndex"} <= set(raw) or set(raw) - allowed or len(raw) < 3:
            _error("invalid_surface", path)
        if_index = _positive_index(raw["ifIndex"], f"{path}.ifIndex", "invalid_surface")
        for key in ("ifAdminStatus", "ifOperStatus"):
            if key in raw and (
                not isinstance(raw[key], str) or raw[key] not in {"up", "down"}
            ):
                _error("invalid_surface", f"{path}.{key}")
        if_alias = raw.get("ifAlias")
        if if_alias is not None and (
            not isinstance(if_alias, str) or not if_alias or len(if_alias.encode("utf-8")) > 128
        ):
            _error("invalid_surface", f"{path}.ifAlias")
        return SurfaceExpectation(
            kind,
            if_index=if_index,
            if_admin_status=raw.get("ifAdminStatus"),
            if_oper_status=raw.get("ifOperStatus"),
            if_alias=if_alias,
        )

    if kind == "event":
        if set(raw) != {"kind", "ifIndex", "event_type"}:
            _error("invalid_surface", path)
        return SurfaceExpectation(
            kind,
            if_index=_positive_index(raw["ifIndex"], f"{path}.ifIndex", "invalid_surface"),
            event_type=_control_text(raw["event_type"], f"{path}.event_type"),
        )

    _error("invalid_surface", f"{path}.kind")


def _evidence(value: object, path: str) -> EvidenceExpectation:
    raw = _object(value, path, {"resource", "selector"})
    resource = _control_text(raw["resource"], f"{path}.resource")
    selector = _object(
        raw["selector"],
        f"{path}.selector",
        {"hostname", "ifIndex", "event_type"},
        set(),
    )
    if resource == "device":
        if set(selector) != {"hostname"}:
            _error("invalid_selector", f"{path}.selector")
        hostname = selector["hostname"]
        if not isinstance(hostname, str) or _HOSTNAME.fullmatch(hostname) is None:
            _error("invalid_selector", f"{path}.selector.hostname")
        return EvidenceExpectation(resource, EvidenceSelector(hostname=hostname))
    if resource == "device_ports":
        if set(selector) != {"ifIndex"}:
            _error("invalid_selector", f"{path}.selector")
        return EvidenceExpectation(
            resource,
            EvidenceSelector(
                if_index=_positive_index(selector["ifIndex"], f"{path}.selector.ifIndex", "invalid_selector")
            ),
        )
    if resource == "device_events":
        if set(selector) != {"ifIndex", "event_type"}:
            _error("invalid_selector", f"{path}.selector")
        event_type = selector["event_type"]
        if not isinstance(event_type, str) or _LABEL.fullmatch(event_type) is None:
            _error("invalid_selector", f"{path}.selector.event_type")
        return EvidenceExpectation(
            resource,
            EvidenceSelector(
                if_index=_positive_index(selector["ifIndex"], f"{path}.selector.ifIndex", "invalid_selector"),
                event_type=event_type,
            ),
        )
    _error("invalid_selector", f"{path}.resource")


def _scenario(value: object, path: str, target_ids: set[str]) -> Scenario:
    keys = {
        "id",
        "name",
        "description",
        "device",
        "precondition",
        "mutation",
        "expected_snmp",
        "poll_mode",
        "expected_librenms_surface",
        "expected_api_evidence",
        "example_questions",
        "expected_answer_semantics",
        "reset_state",
    }
    raw = _object(value, path, keys, keys - {"reset_state"})
    scenario_id = _control_text(raw["id"], f"{path}.id", pattern=_IDENTIFIER)
    device = _control_text(raw["device"], f"{path}.device", pattern=_IDENTIFIER)
    if device not in target_ids:
        _error("unknown_device", f"{path}.device")
    if raw.get("reset_state") != "baseline":
        _error("reset_state_required", f"{path}.reset_state")
    poll_mode = raw["poll_mode"]
    if not isinstance(poll_mode, str) or poll_mode not in _POLL_MODES:
        _error("unsupported_poll_mode", f"{path}.poll_mode")

    mutation = _object(raw["mutation"], f"{path}.mutation", {"kind", "values", "active"}, {"kind"})
    kind = mutation["kind"]
    if not isinstance(kind, str) or kind not in _MUTATION_KINDS:
        _error("unsupported_mutation_kind", f"{path}.mutation.kind")
    mutation_values: tuple[SemanticValue, ...]
    endpoint_active: bool | None
    if kind == "snmprec_values":
        _keys(mutation, f"{path}.mutation", {"kind", "values"})
        values = _array(mutation.get("values"), f"{path}.mutation.values", nonempty=True)
        mutation_values = tuple(
            _semantic_value(item, f"{path}.mutation.values[{index}]", control=True)
            for index, item in enumerate(values)
        )
        if any(SEMANTIC_CATALOG[item.semantic].oid is None for item in mutation_values):
            _error("semantic_value_invalid", f"{path}.mutation.values")
        endpoint_active = None
    else:
        _keys(mutation, f"{path}.mutation", {"kind", "active"})
        if not isinstance(mutation.get("active"), bool):
            _error("invalid_type", f"{path}.mutation.active")
        mutation_values = ()
        endpoint_active = mutation["active"]

    expected_raw = _array(raw["expected_snmp"], f"{path}.expected_snmp")
    if not expected_raw:
        _error("expected_snmp_required", f"{path}.expected_snmp")
    expected = tuple(
        _semantic_value(item, f"{path}.expected_snmp[{index}]", control=False)
        for index, item in enumerate(expected_raw)
    )
    unreachable = any(item.semantic == "endpointReachable" and item.value is False for item in expected)
    if unreachable and (kind != "endpoint_membership" or endpoint_active is not False):
        _error("device_down_requires_endpoint_membership", f"{path}.mutation")

    surfaces = tuple(
        _surface(item, f"{path}.expected_librenms_surface[{index}]")
        for index, item in enumerate(
            _array(raw["expected_librenms_surface"], f"{path}.expected_librenms_surface", nonempty=True)
        )
    )
    evidence = tuple(
        _evidence(item, f"{path}.expected_api_evidence[{index}]")
        for index, item in enumerate(
            _array(raw["expected_api_evidence"], f"{path}.expected_api_evidence", nonempty=True)
        )
    )
    questions = tuple(
        _text(item, f"{path}.example_questions[{index}]", maximum=500)
        for index, item in enumerate(_array(raw["example_questions"], f"{path}.example_questions", nonempty=True))
    )
    answer_semantics = tuple(
        _control_text(item, f"{path}.expected_answer_semantics[{index}]")
        for index, item in enumerate(
            _array(raw["expected_answer_semantics"], f"{path}.expected_answer_semantics", nonempty=True)
        )
    )

    return Scenario(
        scenario_id,
        _text(raw["name"], f"{path}.name", maximum=120),
        _text(raw["description"], f"{path}.description"),
        device,
        _text(raw["precondition"], f"{path}.precondition"),
        kind,
        mutation_values,
        endpoint_active,
        expected,
        poll_mode,
        surfaces,
        evidence,
        questions,
        answer_semantics,
        "baseline",
    )


def _semantic_primitive(value: SemanticValue) -> dict[str, object]:
    return {"semantic": value.semantic, "index": value.index, "value": value.value}


def _surface_primitive(surface: SurfaceExpectation) -> dict[str, object]:
    result: dict[str, object] = {"kind": surface.kind}
    fields = (
        ("field", surface.field),
        ("value", surface.value),
        ("ifIndex", surface.if_index),
        ("ifAdminStatus", surface.if_admin_status),
        ("ifOperStatus", surface.if_oper_status),
        ("ifAlias", surface.if_alias),
        ("status", surface.status),
        ("reachable", surface.reachable),
        ("event_type", surface.event_type),
    )
    result.update((key, value) for key, value in fields if value is not None)
    return result


def _evidence_primitive(evidence: EvidenceExpectation) -> dict[str, object]:
    selector: dict[str, object] = {}
    if evidence.selector.hostname is not None:
        selector["hostname"] = evidence.selector.hostname
    if evidence.selector.if_index is not None:
        selector["ifIndex"] = evidence.selector.if_index
    if evidence.selector.event_type is not None:
        selector["event_type"] = evidence.selector.event_type
    return {"resource": evidence.resource, "selector": selector}


def _canonical_primitive(targets: tuple[Target, ...], scenarios: tuple[Scenario, ...]) -> dict[str, object]:
    return {
        "version": 1,
        "targets": [
            {
                "id": target.id,
                "hostname": target.hostname,
                "agent_address": target.agent_address,
                "agent_port": target.agent_port,
                "fixture": target.fixture,
                "baseline_active": target.baseline_active,
                "capabilities": list(target.capabilities),
            }
            for target in targets
        ],
        "scenarios": [
            {
                "id": scenario.id,
                "name": scenario.name,
                "description": scenario.description,
                "device": scenario.device,
                "precondition": scenario.precondition,
                "mutation": (
                    {"kind": scenario.mutation_kind, "values": [_semantic_primitive(v) for v in scenario.mutation_values]}
                    if scenario.mutation_kind == "snmprec_values"
                    else {"kind": scenario.mutation_kind, "active": scenario.endpoint_active}
                ),
                "expected_snmp": [_semantic_primitive(v) for v in scenario.expected_snmp],
                "poll_mode": scenario.poll_mode,
                "expected_librenms_surface": [
                    _surface_primitive(surface) for surface in scenario.expected_librenms_surface
                ],
                "expected_api_evidence": [
                    _evidence_primitive(evidence) for evidence in scenario.expected_api_evidence
                ],
                "example_questions": list(scenario.example_questions),
                "expected_answer_semantics": list(scenario.expected_answer_semantics),
                "reset_state": scenario.reset_state,
            }
            for scenario in scenarios
        ],
    }


def validate_manifest(raw: object) -> Manifest:
    _scan_forbidden_keys(raw)
    root = _object(raw, "$", {"version", "targets", "scenarios"})
    if isinstance(root["version"], bool) or not isinstance(root["version"], int) or root["version"] != 1:
        _error("unsupported_version", "$.version")
    targets = tuple(
        _target(item, f"$.targets[{index}]")
        for index, item in enumerate(_array(root["targets"], "$.targets", nonempty=True))
    )
    target_ids = [target.id for target in targets]
    if len(target_ids) != len(set(target_ids)):
        _error("duplicate_target_id", "$.targets")
    scenarios = tuple(
        _scenario(item, f"$.scenarios[{index}]", set(target_ids))
        for index, item in enumerate(_array(root["scenarios"], "$.scenarios", nonempty=True))
    )
    scenario_ids = [scenario.id for scenario in scenarios]
    if len(scenario_ids) != len(set(scenario_ids)):
        _error("duplicate_scenario_id", "$.scenarios")
    canonical = json.dumps(
        _canonical_primitive(targets, scenarios),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return Manifest(1, targets, scenarios, canonical)


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _error("duplicate_json_key", f"$.{key}")
        result[key] = value
    return result


def _reject_non_finite(value: str) -> None:
    _error("non_finite_number", f"$.{value}")


def load_manifest(path: str | Path) -> Manifest:
    source = Path(path)
    try:
        raw = json.loads(
            source.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_finite,
        )
    except ManifestValidationError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ManifestValidationError("manifest_read_failed", str(source)) from error
    return validate_manifest(raw)


def manifest_sha256(manifest: Manifest) -> str:
    return hashlib.sha256(manifest.canonical).hexdigest()


def public_manifest(manifest: Manifest) -> dict[str, object]:
    return {
        "version": manifest.version,
        "manifest_sha256": manifest_sha256(manifest),
        "targets": [
            {
                "id": target.id,
                "hostname": target.hostname,
                "baseline_active": target.baseline_active,
                "capabilities": list(target.capabilities),
            }
            for target in manifest.targets
        ],
        "scenarios": [
            {
                "id": scenario.id,
                "name": scenario.name,
                "description": scenario.description,
                "device": scenario.device,
                "precondition": scenario.precondition,
                "poll_mode": scenario.poll_mode,
                "expected_librenms_surface": [
                    _surface_primitive(surface) for surface in scenario.expected_librenms_surface
                ],
                "expected_api_evidence": [
                    _evidence_primitive(evidence) for evidence in scenario.expected_api_evidence
                ],
                "example_questions": list(scenario.example_questions),
                "expected_answer_semantics": list(scenario.expected_answer_semantics),
            }
            for scenario in manifest.scenarios
        ],
    }
