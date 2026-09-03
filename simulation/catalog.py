"""Closed semantic catalog for Simulation Lab mutations and observations."""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class SemanticSpec:
    name: str
    oid: str | None
    snmp_type: int | None
    indexed: bool = False
    allowed_values: frozenset[int] | frozenset[bool] | None = None
    max_length: int | None = None


SEMANTIC_CATALOG: Mapping[str, SemanticSpec] = MappingProxyType(
    {
        "sysUpTime": SemanticSpec("sysUpTime", "1.3.6.1.2.1.1.3.0", 67),
        "sysName": SemanticSpec("sysName", "1.3.6.1.2.1.1.5.0", 4, max_length=64),
        "sysLocation": SemanticSpec("sysLocation", "1.3.6.1.2.1.1.6.0", 4, max_length=128),
        "ifAdminStatus": SemanticSpec(
            "ifAdminStatus",
            "1.3.6.1.2.1.2.2.1.7",
            2,
            True,
            frozenset({1, 2}),
        ),
        "ifOperStatus": SemanticSpec(
            "ifOperStatus",
            "1.3.6.1.2.1.2.2.1.8",
            2,
            True,
            frozenset({1, 2}),
        ),
        "ifAlias": SemanticSpec(
            "ifAlias",
            "1.3.6.1.2.1.31.1.1.1.18",
            4,
            True,
            max_length=128,
        ),
        "endpointReachable": SemanticSpec(
            "endpointReachable",
            None,
            None,
            allowed_values=frozenset({True, False}),
        ),
    }
)


def _semantic(name: str) -> SemanticSpec:
    try:
        return SEMANTIC_CATALOG[name]
    except (KeyError, TypeError) as error:
        raise ValueError("unknown_semantic") from error


def _validate_index(spec: SemanticSpec, index: int | None) -> None:
    if spec.indexed:
        if index is None:
            raise ValueError("index_required")
        if isinstance(index, bool) or not isinstance(index, int):
            raise ValueError("invalid_index")
        if not 1 <= index <= 4096:
            raise ValueError("invalid_index")
    elif index is not None:
        raise ValueError("index_forbidden")


def resolve_oid(name: str, index: int | None) -> tuple[str, int]:
    """Resolve an approved semantic to an exact OID and SNMP type."""

    spec = _semantic(name)
    _validate_index(spec, index)
    if spec.oid is None or spec.snmp_type is None:
        raise ValueError("virtual_semantic")
    oid = f"{spec.oid}.{index}" if spec.indexed else spec.oid
    return oid, spec.snmp_type


def validate_semantic_value(name: str, index: int | None, value: object) -> None:
    """Validate a value without accepting caller-controlled OIDs or SNMP types."""

    spec = _semantic(name)
    _validate_index(spec, index)

    if spec.oid is None:
        if not isinstance(value, bool):
            raise ValueError("invalid_type")
    elif spec.snmp_type in {2, 67}:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("invalid_type")
        if spec.snmp_type == 67 and not 0 <= value <= 2**32 - 1:
            raise ValueError("invalid_range")
    elif spec.snmp_type == 4:
        if not isinstance(value, str):
            raise ValueError("invalid_type")
        if any(character in value for character in ("\x00", "\r", "\n")):
            raise ValueError("invalid_text")
        if spec.max_length is not None and len(value.encode("utf-8")) > spec.max_length:
            raise ValueError("value_too_long")
    else:  # pragma: no cover - catalog construction invariant
        raise ValueError("unsupported_snmp_type")

    if spec.allowed_values is not None and value not in spec.allowed_values:
        raise ValueError("invalid_enum")
