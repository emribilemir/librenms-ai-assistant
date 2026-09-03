"""Fixed process boundary for SNMPSIM, LibreNMS and semantic SNMP checks."""

from dataclasses import dataclass
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
from time import perf_counter
from typing import Callable

from simulation.catalog import resolve_oid
from simulation.manifest import SemanticValue, Target

from .errors import RunnerError
from .storage import RunnerLayout


_SENSITIVE = re.compile(r"password|authorization|bearer|secret|api[-_ ]?key|token", re.IGNORECASE)
_MAX_CAPTURE_BYTES = 64 * 1024
_MAX_DIAGNOSTIC_LINES = 20
_MAX_DIAGNOSTIC_CHARS = 256


@dataclass(frozen=True)
class ProcessResult:
    exit_code: int
    duration_ms: int
    diagnostics: tuple[str, ...]
    timed_out: bool


@dataclass(frozen=True)
class VerificationResult:
    success: bool
    code: str
    observations: tuple[tuple[str, int | None, int | str | bool], ...] = ()


def _is_allowed(argv: tuple[str, ...], allowed: tuple[tuple[str, ...], ...]) -> bool:
    return any(argv == command for command in allowed if command)


def _diagnostics(payload: bytes, allowed_prefixes: tuple[str, ...]) -> tuple[str, ...]:
    if not allowed_prefixes:
        return ()
    text = payload[:_MAX_CAPTURE_BYTES].decode("utf-8", errors="replace")
    result: list[str] = []
    for raw_line in text.splitlines():
        line = " ".join(raw_line.split())[:_MAX_DIAGNOSTIC_CHARS]
        if not line or _SENSITIVE.search(line):
            continue
        if not any(line.startswith(prefix) for prefix in allowed_prefixes):
            continue
        result.append(line)
        if len(result) == _MAX_DIAGNOSTIC_LINES:
            break
    return tuple(result)


def run_fixed(
    argv: tuple[str, ...],
    timeout_s: int,
    allowed_commands: tuple[tuple[str, ...], ...],
    allowed_output_prefixes: tuple[str, ...],
) -> ProcessResult:
    if (
        not argv
        or any(not isinstance(argument, str) or not argument or "\x00" in argument for argument in argv)
        or not _is_allowed(argv, allowed_commands)
    ):
        raise RunnerError("command_not_allowed")
    if isinstance(timeout_s, bool) or not isinstance(timeout_s, int) or not 1 <= timeout_s <= 360:
        raise RunnerError("invalid_timeout")

    started = perf_counter()
    timed_out = False
    with tempfile.TemporaryFile() as stdout_stream, tempfile.TemporaryFile() as stderr_stream:
        try:
            process = subprocess.Popen(
                list(argv),
                stdin=subprocess.DEVNULL,
                stdout=stdout_stream,
                stderr=stderr_stream,
                shell=False,
                start_new_session=True,
            )
        except OSError as error:
            raise RunnerError("process_start_failed", retryable=True) from error
        try:
            process.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
        stdout_stream.seek(0)
        stdout = stdout_stream.read(_MAX_CAPTURE_BYTES)
    duration_ms = max(0, round((perf_counter() - started) * 1000))
    exit_code = -1 if timed_out or process.returncode is None else process.returncode
    return ProcessResult(exit_code, duration_ms, _diagnostics(stdout, allowed_output_prefixes), timed_out)


Invoke = Callable[
    [tuple[str, ...], int, tuple[tuple[str, ...], ...], tuple[str, ...]],
    ProcessResult,
]


class ProcessAdapter:
    def __init__(self, layout: RunnerLayout, *, invoke: Invoke = run_fixed):
        self.layout = layout
        self.invoke = invoke

    def _run(
        self,
        argv: tuple[str, ...],
        timeout_s: int,
        output_prefixes: tuple[str, ...] = (),
    ) -> ProcessResult:
        return self.invoke(argv, timeout_s, (argv,), output_prefixes)

    def restart_snmpsim(self) -> ProcessResult:
        argv = ("/usr/bin/systemctl", "restart", "snmpsim-lab.service")
        result = self._run(argv, 30)
        if result.timed_out:
            raise RunnerError("process_timeout", retryable=True, stage="restart")
        if result.exit_code != 0:
            raise RunnerError("service_restart_failed", retryable=True, stage="restart")
        return result

    def service_active(self) -> bool:
        argv = ("/usr/bin/systemctl", "is-active", "--quiet", "snmpsim-lab.service")
        result = self._run(argv, 10)
        return not result.timed_out and result.exit_code == 0

    def run_poll(self, target: Target, mode: str) -> tuple[ProcessResult, ...]:
        scripts: tuple[Path, ...]
        if mode == "none":
            scripts = ()
        elif mode == "poller":
            scripts = (self.layout.librenms_root / "poller.php",)
        elif mode == "discovery":
            scripts = (self.layout.librenms_root / "discovery.php",)
        elif mode == "discovery_then_poller":
            scripts = (
                self.layout.librenms_root / "discovery.php",
                self.layout.librenms_root / "poller.php",
            )
        else:
            raise RunnerError("unsupported_poll_mode")

        results: list[ProcessResult] = []
        for script in scripts:
            argv = (
                "/usr/sbin/runuser",
                "-u",
                "librenms",
                "--",
                str(script),
                "-h",
                target.hostname,
            )
            result = self._run(argv, 360, ("Discovery", "Polling", "SNMP", "RRD", "SQL"))
            if result.timed_out:
                raise RunnerError("process_timeout", retryable=True, stage="poll")
            if result.exit_code != 0:
                raise RunnerError("poll_failed", retryable=True, stage="poll")
            results.append(result)
        return tuple(results)

    def _snmpget(self, target: Target, oid: str) -> ProcessResult:
        argv = (
            "/usr/bin/snmpget",
            "-v2c",
            "-c",
            "public",
            "-t",
            "1",
            "-r",
            "0",
            "-Oqvt",
            f"udp:{target.agent_address}:{target.agent_port}",
            oid,
        )
        return self._run(argv, 5, ("",))

    @staticmethod
    def _normalize_observed(value: str, expected: int | str | bool) -> int | str:
        normalized = value.strip()
        if len(normalized) >= 2 and normalized[0] == normalized[-1] == '"':
            normalized = normalized[1:-1]
        if isinstance(expected, int) and not isinstance(expected, bool):
            try:
                return int(normalized, 10)
            except ValueError:
                return normalized
        return normalized

    def verify_snmp(self, target: Target, expected: tuple[SemanticValue, ...]) -> VerificationResult:
        observations: list[tuple[str, int | None, int | str | bool]] = []
        for item in expected:
            if item.semantic == "endpointReachable":
                probe_oid, _ = resolve_oid("sysName", None)
                result = self._snmpget(target, probe_oid)
                reachable = not result.timed_out and result.exit_code == 0
                observations.append((item.semantic, item.index, reachable))
                if reachable is not item.value:
                    return VerificationResult(False, "snmp_mismatch", tuple(observations))
                continue
            oid, _ = resolve_oid(item.semantic, item.index)
            result = self._snmpget(target, oid)
            if result.timed_out or result.exit_code != 0 or not result.diagnostics:
                return VerificationResult(False, "snmp_unreachable", tuple(observations))
            observed = self._normalize_observed(result.diagnostics[0], item.value)
            observations.append((item.semantic, item.index, observed))
            if observed != item.value:
                return VerificationResult(False, "snmp_mismatch", tuple(observations))
        return VerificationResult(True, "verified", tuple(observations))
