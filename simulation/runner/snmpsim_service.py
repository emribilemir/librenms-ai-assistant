"""Build and exec the fixed SNMPSIM responder command for systemd."""

import os
from pathlib import Path

from simulation.manifest import Manifest, load_manifest

from .errors import RunnerError
from .snmprec import MembershipRecord, parse_membership


RESPONDER = "/opt/snmpsim-venv/bin/snmpsim-command-responder"
LAB_ROOT = Path("/opt/snmpsim-lab")
MANIFEST_PATH = Path("/opt/librenms-ai-lab/manifest/scenarios.json")
MAX_MEMBERSHIP_BYTES = 4 * 1024 * 1024


def _membership_map(records: tuple[MembershipRecord, ...]) -> dict[str, MembershipRecord]:
    return {record.hostname: record for record in records}


def build_responder_argv(
    manifest: Manifest,
    active_payload: bytes,
    inventory_payload: bytes,
) -> tuple[str, ...]:
    active = parse_membership(active_payload)
    inventory = parse_membership(inventory_payload)
    inventory_by_host = _membership_map(inventory)
    inventory_records = set(inventory)
    if any(record not in inventory_records for record in active):
        raise RunnerError("active_target_not_in_inventory")

    manifest_by_host = {target.hostname: target for target in manifest.targets}
    for target in manifest.targets:
        record = inventory_by_host.get(target.hostname)
        if record is None or record.address != target.agent_address or target.agent_port != 1611:
            raise RunnerError("manifest_inventory_mismatch")

    argv = [
        RESPONDER,
        "--process-user=librenms",
        "--process-group=librenms",
        "--cache-dir=/opt/snmpsim-lab/cache",
    ]
    for record in active:
        declared = manifest_by_host.get(record.hostname)
        fixture = declared.fixture if declared is not None else record.hostname
        argv.extend(
            (
                "--v3-engine-id=auto",
                f"--data-dir=/opt/snmpsim-lab/data/{fixture}",
                f"--agent-udpv4-endpoint={record.address}:1611",
            )
        )
    return tuple(argv)


def _read_fixed(path: Path) -> bytes:
    try:
        metadata = path.stat(follow_symlinks=False)
    except OSError as error:
        raise RunnerError("service_input_unavailable") from error
    if path.is_symlink() or not path.is_file() or not 0 < metadata.st_size <= MAX_MEMBERSHIP_BYTES:
        raise RunnerError("service_input_invalid")
    try:
        return path.read_bytes()
    except OSError as error:
        raise RunnerError("service_input_unavailable") from error


def main() -> int:
    manifest = load_manifest(MANIFEST_PATH)
    argv = build_responder_argv(
        manifest,
        _read_fixed(LAB_ROOT / "devices-up.txt"),
        _read_fixed(LAB_ROOT / "devices.txt"),
    )
    for argument in argv:
        if not argument.startswith("--data-dir="):
            continue
        data_dir = Path(argument.removeprefix("--data-dir="))
        try:
            data_dir.resolve(strict=True).relative_to((LAB_ROOT / "data").resolve(strict=True))
        except (OSError, ValueError) as error:
            raise RunnerError("service_fixture_invalid") from error
        if data_dir.is_symlink() or not data_dir.is_dir():
            raise RunnerError("service_fixture_invalid")
    os.execv(RESPONDER, list(argv))
    return 1  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
