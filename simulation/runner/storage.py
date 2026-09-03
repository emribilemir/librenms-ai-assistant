"""Atomic, fixed-layout persistence for the restricted VM runner."""

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import json
import os
from pathlib import Path
import pwd
import grp
import tempfile
from typing import Iterator

from simulation.manifest import Manifest, Target, manifest_sha256
from simulation.state import ScenarioPhase, ScenarioState, StateTransitionError, transition

from .errors import RunnerError
from .snmprec import parse_membership, parse_snmprec


def _state_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate state key")
        result[key] = value
    return result


def _state_constant(_: str) -> None:
    raise ValueError("non-finite state value")


@dataclass(frozen=True)
class RunnerLayout:
    install_root: Path
    state_root: Path
    snmpsim_root: Path
    librenms_root: Path

    @classmethod
    def production(cls) -> "RunnerLayout":
        return cls(
            Path("/opt/librenms-ai-lab"),
            Path("/var/lib/librenms-ai-lab"),
            Path("/opt/snmpsim-lab"),
            Path("/opt/librenms"),
        )


class OwnershipPolicy:
    """Applies and verifies the configured owner after an atomic replacement."""

    def apply_and_verify(self, path: Path, owner: str) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def verify(self, path: Path, owner: str) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class PosixOwnershipPolicy(OwnershipPolicy):
    def _ids(self, owner: str) -> tuple[int, int]:
        if owner == "root":
            return 0, 0
        if owner == "librenms":
            try:
                return pwd.getpwnam("librenms").pw_uid, grp.getgrnam("librenms").gr_gid
            except KeyError as error:
                raise RunnerError("owner_unavailable") from error
        raise RunnerError("owner_unavailable")

    def apply_and_verify(self, path: Path, owner: str) -> None:
        user_id, group_id = self._ids(owner)
        try:
            os.chown(path, user_id, group_id, follow_symlinks=False)
        except OSError as error:
            raise RunnerError("ownership_failed") from error
        self.verify(path, owner)

    def verify(self, path: Path, owner: str) -> None:
        user_id, group_id = self._ids(owner)
        try:
            metadata = path.stat(follow_symlinks=False)
        except OSError as error:
            raise RunnerError("ownership_failed") from error
        if path.is_symlink() or metadata.st_uid != user_id or metadata.st_gid != group_id:
            raise RunnerError("ownership_mismatch")


class RunnerStorage:
    def __init__(self, layout: RunnerLayout, ownership: OwnershipPolicy):
        self.layout = layout
        self.ownership = ownership

    @property
    def state_path(self) -> Path:
        return self.layout.state_root / "state.json"

    @property
    def lock_path(self) -> Path:
        return self.layout.state_root / "runner.lock"

    @property
    def membership_path(self) -> Path:
        return self.layout.snmpsim_root / "devices-up.txt"

    @property
    def inventory_path(self) -> Path:
        return self.layout.snmpsim_root / "devices.txt"

    @property
    def baseline_root(self) -> Path:
        return self.layout.state_root / "baseline"

    def fixture_path(self, target: Target) -> Path:
        return self.layout.snmpsim_root / "data" / target.fixture / "public.snmprec"

    def _safe_path(self, path: Path, root: Path, *, missing: bool = False) -> None:
        try:
            relative_parent = path.parent.relative_to(root)
            root_resolved = root.resolve(strict=True)
            parent_resolved = path.parent.resolve(strict=True)
            parent_resolved.relative_to(root_resolved)
        except (FileNotFoundError, ValueError) as error:
            raise RunnerError("unsafe_path") from error
        if root.is_symlink():
            raise RunnerError("unsafe_path")
        cursor = root
        for component in relative_parent.parts:
            cursor = cursor / component
            if cursor.is_symlink():
                raise RunnerError("unsafe_path")
        if path.is_symlink():
            raise RunnerError("unsafe_path")
        if path.exists() and not path.is_file():
            raise RunnerError("unsafe_path")
        if not missing and not path.exists():
            raise RunnerError("missing_file")

    def _read(self, path: Path, root: Path, *, owner: str) -> bytes:
        self._safe_path(path, root)
        self.ownership.verify(path, owner)
        try:
            return path.read_bytes()
        except OSError as error:
            raise RunnerError("storage_read_failed", retryable=True) from error

    def _atomic_write(self, path: Path, payload: bytes, *, mode: int, owner: str, root: Path) -> None:
        self._safe_path(path, root, missing=True)
        descriptor = -1
        temporary_path: Path | None = None
        try:
            descriptor, raw_path = tempfile.mkstemp(prefix=".runner-", dir=path.parent)
            temporary_path = Path(raw_path)
            os.fchmod(descriptor, mode)
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                descriptor = -1
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, path)
            temporary_path = None
            self.ownership.apply_and_verify(path, owner)
            directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            directory_fd = os.open(path.parent, directory_flags)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except RunnerError:
            raise
        except OSError as error:
            raise RunnerError("storage_write_failed", retryable=True) from error
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if temporary_path is not None:
                try:
                    temporary_path.unlink()
                except FileNotFoundError:
                    pass

    @contextmanager
    def acquire(self) -> Iterator[None]:
        self._safe_path(self.lock_path, self.layout.state_root, missing=True)
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(self.lock_path, flags, 0o600)
            self.ownership.apply_and_verify(self.lock_path, "root")
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise RunnerError("lab_busy", retryable=True) from error
            try:
                yield
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        except RunnerError:
            raise
        except OSError as error:
            raise RunnerError("lock_failed", retryable=True) from error
        finally:
            if "descriptor" in locals():
                os.close(descriptor)

    def load_state(self, manifest: Manifest) -> ScenarioState:
        if not self.state_path.exists():
            if self.state_path.is_symlink():
                raise RunnerError("unsafe_path")
            return ScenarioState(ScenarioPhase.BASELINE, None, manifest_sha256(manifest))
        payload = self._read(self.state_path, self.layout.state_root, owner="root")
        try:
            raw = json.loads(payload, object_pairs_hook=_state_pairs, parse_constant=_state_constant)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            raise RunnerError("state_corrupt") from error
        expected_keys = {"phase", "scenario_id", "manifest_sha256", "last_error_code"}
        if not isinstance(raw, dict) or set(raw) != expected_keys:
            raise RunnerError("state_corrupt")
        expected_sha = manifest_sha256(manifest)
        if raw["manifest_sha256"] != expected_sha:
            raise RunnerError("manifest_mismatch")
        try:
            state = ScenarioState(
                ScenarioPhase(raw["phase"]),
                raw["scenario_id"],
                raw["manifest_sha256"],
                raw["last_error_code"],
            )
        except (TypeError, ValueError) as error:
            raise RunnerError("state_corrupt") from error
        known_ids = {scenario.id for scenario in manifest.scenarios}
        try:
            transition(state, "status", known_scenario_ids=known_ids)
        except StateTransitionError as error:
            raise RunnerError(error.code) from error
        return state

    def save_state(self, state: ScenarioState) -> None:
        payload = (
            json.dumps(
                {
                    "phase": state.phase.value,
                    "scenario_id": state.scenario_id,
                    "manifest_sha256": state.manifest_sha256,
                    "last_error_code": state.last_error_code,
                },
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
        self._atomic_write(
            self.state_path,
            payload,
            mode=0o600,
            owner="root",
            root=self.layout.state_root,
        )

    def capture_baseline(self, manifest: Manifest) -> None:
        marker = self.baseline_root / "manifest.sha256"
        if self.baseline_root.exists():
            if self.baseline_root.is_symlink() or not self.baseline_root.is_dir():
                raise RunnerError("unsafe_path")
            if not marker.exists():
                raise RunnerError("baseline_corrupt")
            saved_sha = self._read(marker, self.layout.state_root, owner="root").decode(
                "ascii", errors="strict"
            ).strip()
            if saved_sha != manifest_sha256(manifest):
                raise RunnerError("baseline_manifest_mismatch")
            return

        fixtures_root = self.baseline_root / "fixtures"
        try:
            fixtures_root.mkdir(parents=True, mode=0o700)
        except OSError as error:
            raise RunnerError("baseline_capture_failed") from error
        membership = self._read(self.membership_path, self.layout.snmpsim_root, owner="root")
        parse_membership(membership)
        self._atomic_write(
            self.baseline_root / "devices-up.txt",
            membership,
            mode=0o600,
            owner="root",
            root=self.layout.state_root,
        )
        for target in manifest.targets:
            fixture = self._read(self.fixture_path(target), self.layout.snmpsim_root, owner="librenms")
            parse_snmprec(fixture)
            self._atomic_write(
                fixtures_root / f"{target.id}.snmprec",
                fixture,
                mode=0o600,
                owner="root",
                root=self.layout.state_root,
            )
        self._atomic_write(
            marker,
            (manifest_sha256(manifest) + "\n").encode("ascii"),
            mode=0o600,
            owner="root",
            root=self.layout.state_root,
        )

    def restore_baseline(self, manifest: Manifest) -> None:
        marker = self.baseline_root / "manifest.sha256"
        if not marker.exists():
            raise RunnerError("baseline_missing")
        saved_sha = self._read(marker, self.layout.state_root, owner="root").decode(
            "ascii", errors="strict"
        ).strip()
        if saved_sha != manifest_sha256(manifest):
            raise RunnerError("baseline_manifest_mismatch")
        membership = self._read(
            self.baseline_root / "devices-up.txt", self.layout.state_root, owner="root"
        )
        self.write_membership(membership)
        for target in manifest.targets:
            fixture = self._read(
                self.baseline_root / "fixtures" / f"{target.id}.snmprec",
                self.layout.state_root,
                owner="root",
            )
            self.write_fixture(target, fixture)

    def read_fixture(self, target: Target) -> bytes:
        return self._read(self.fixture_path(target), self.layout.snmpsim_root, owner="librenms")

    def read_membership(self) -> bytes:
        return self._read(self.membership_path, self.layout.snmpsim_root, owner="root")

    def read_inventory(self) -> bytes:
        return self._read(self.inventory_path, self.layout.snmpsim_root, owner="librenms")

    def write_fixture(self, target: Target, payload: bytes) -> None:
        parse_snmprec(payload)
        self._atomic_write(
            self.fixture_path(target),
            payload,
            mode=0o644,
            owner="librenms",
            root=self.layout.snmpsim_root,
        )

    def write_membership(self, payload: bytes) -> None:
        parse_membership(payload)
        self._atomic_write(
            self.membership_path,
            payload,
            mode=0o644,
            owner="root",
            root=self.layout.snmpsim_root,
        )

    def clear_target_cache(self, target: Target) -> tuple[str, ...]:
        cache_root = self.layout.snmpsim_root / "cache"
        if cache_root.is_symlink() or not cache_root.is_dir():
            raise RunnerError("unsafe_path")
        prefix = str(self.fixture_path(target).with_suffix("")).replace("/", "_") + ".dbm"
        allowed_names = {prefix, prefix + "-shm", prefix + "-wal"}
        removed: list[str] = []
        try:
            for candidate in cache_root.iterdir():
                if candidate.name not in allowed_names:
                    continue
                self._safe_path(candidate, cache_root)
                self.ownership.verify(candidate, "librenms")
                candidate.unlink()
                removed.append(candidate.name)
        except RunnerError:
            raise
        except OSError as error:
            raise RunnerError("cache_clear_failed", retryable=True) from error
        return tuple(sorted(removed))
