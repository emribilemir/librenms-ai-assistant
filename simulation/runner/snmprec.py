"""Pure, strict transforms for SNMPREC fixtures and endpoint membership."""

from dataclasses import dataclass
import ipaddress
import re

from simulation.catalog import resolve_oid, validate_semantic_value
from simulation.manifest import SemanticValue, Target

from .errors import RunnerError


_MAX_PAYLOAD_BYTES = 4 * 1024 * 1024
_OID = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*))+$")
_HOSTNAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$")
_INTEGER_TYPES = frozenset({2, 65, 66, 67, 70})


@dataclass(frozen=True)
class SnmpRecord:
    oid: str
    snmp_type: int
    value: int | str


@dataclass(frozen=True)
class MembershipRecord:
    address: str
    hostname: str
    model: str


def _decode(payload: bytes, code: str) -> str:
    if not payload or len(payload) > _MAX_PAYLOAD_BYTES:
        raise RunnerError(code)
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise RunnerError("invalid_encoding") from error
    if "\r" in text or "\x00" in text:
        raise RunnerError(code)
    return text


def parse_snmprec(payload: bytes) -> tuple[SnmpRecord, ...]:
    text = _decode(payload, "invalid_snmprec")
    records: list[SnmpRecord] = []
    seen: set[str] = set()
    for line in text.splitlines():
        fields = line.split("|")
        if len(fields) != 3 or not fields[0] or not fields[1]:
            raise RunnerError("invalid_snmprec")
        oid, raw_type, raw_value = fields
        if _OID.fullmatch(oid) is None or len(oid) > 256:
            raise RunnerError("invalid_oid")
        if oid in seen:
            raise RunnerError("duplicate_oid")
        if not raw_type.isascii() or not raw_type.isdigit():
            raise RunnerError("invalid_snmp_type")
        snmp_type = int(raw_type)
        if not 1 <= snmp_type <= 255:
            raise RunnerError("invalid_snmp_type")
        value: int | str
        if snmp_type in _INTEGER_TYPES:
            try:
                value = int(raw_value, 10)
            except ValueError as error:
                raise RunnerError("invalid_snmp_value") from error
            if snmp_type != 2 and value < 0:
                raise RunnerError("invalid_snmp_value")
        else:
            if "|" in raw_value or len(raw_value.encode("utf-8")) > 65535:
                raise RunnerError("invalid_snmp_value")
            value = raw_value
        seen.add(oid)
        records.append(SnmpRecord(oid, snmp_type, value))
    if not records:
        raise RunnerError("invalid_snmprec")
    return tuple(records)


def _serialize_snmprec(records: tuple[SnmpRecord, ...]) -> bytes:
    return ("".join(f"{record.oid}|{record.snmp_type}|{record.value}\n" for record in records)).encode("utf-8")


def apply_semantic_values(payload: bytes, values: tuple[SemanticValue, ...]) -> bytes:
    records = parse_snmprec(payload)
    updates: dict[str, tuple[int, int | str]] = {}
    semantic_keys: set[tuple[str, int | None]] = set()
    for item in values:
        semantic_key = (item.semantic, item.index)
        if semantic_key in semantic_keys:
            raise RunnerError("duplicate_semantic_update")
        semantic_keys.add(semantic_key)
        try:
            validate_semantic_value(item.semantic, item.index, item.value)
        except ValueError as error:
            raise RunnerError("semantic_value_invalid") from error
        try:
            oid, snmp_type = resolve_oid(item.semantic, item.index)
        except ValueError as error:
            code = "virtual_semantic" if str(error) == "virtual_semantic" else "semantic_value_invalid"
            raise RunnerError(code) from error
        updates[oid] = (snmp_type, item.value)

    by_oid = {record.oid: record for record in records}
    for oid, (expected_type, _) in updates.items():
        if oid not in by_oid:
            raise RunnerError("semantic_oid_missing")
        if by_oid[oid].snmp_type != expected_type:
            raise RunnerError("semantic_type_mismatch")

    transformed = tuple(
        SnmpRecord(record.oid, record.snmp_type, updates[record.oid][1])
        if record.oid in updates
        else record
        for record in records
    )
    output = _serialize_snmprec(transformed)
    parse_snmprec(output)
    return output


def parse_membership(payload: bytes) -> tuple[MembershipRecord, ...]:
    text = _decode(payload, "invalid_membership")
    records: list[MembershipRecord] = []
    addresses: set[str] = set()
    hostnames: set[str] = set()
    for line in text.splitlines():
        fields = line.split("|")
        if len(fields) != 3:
            raise RunnerError("invalid_membership")
        address, hostname, model = fields
        try:
            parsed_address = ipaddress.ip_address(address)
        except ValueError as error:
            raise RunnerError("invalid_membership") from error
        if parsed_address.version != 4 or not parsed_address.is_loopback:
            raise RunnerError("invalid_membership")
        if _HOSTNAME.fullmatch(hostname) is None:
            raise RunnerError("invalid_membership")
        if not model or len(model.encode("utf-8")) > 128 or any(ord(char) < 32 for char in model):
            raise RunnerError("invalid_membership")
        if address in addresses or hostname in hostnames:
            raise RunnerError("duplicate_membership")
        addresses.add(address)
        hostnames.add(hostname)
        records.append(MembershipRecord(address, hostname, model))
    if not records:
        raise RunnerError("invalid_membership")
    return tuple(records)


def _serialize_membership(records: tuple[MembershipRecord, ...]) -> bytes:
    return ("".join(f"{record.address}|{record.hostname}|{record.model}\n" for record in records)).encode("utf-8")


def set_endpoint_active(
    active_payload: bytes,
    inventory_payload: bytes,
    target: Target,
    active: bool,
) -> bytes:
    if not isinstance(active, bool):
        raise RunnerError("invalid_endpoint_state")
    inventory = parse_membership(inventory_payload)
    current = parse_membership(active_payload)
    inventory_by_host = {record.hostname: record for record in inventory}
    target_record = inventory_by_host.get(target.hostname)
    if target_record is None or target_record.address != target.agent_address:
        raise RunnerError("target_not_in_inventory")
    inventory_records = set(inventory)
    if any(record not in inventory_records for record in current):
        raise RunnerError("active_target_not_in_inventory")
    active_hosts = {record.hostname for record in current}
    if active:
        active_hosts.add(target.hostname)
    else:
        active_hosts.discard(target.hostname)
    transformed = tuple(record for record in inventory if record.hostname in active_hosts)
    if not transformed:
        raise RunnerError("empty_active_membership")
    output = _serialize_membership(transformed)
    parse_membership(output)
    return output
