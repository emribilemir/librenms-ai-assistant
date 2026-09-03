# EMR-59 VM Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans and superpowers:test-driven-development task-by-task. This plan intentionally stops before live UTM installation; authorized deployment and mutation acceptance belong to EMR-63.

**Goal:** Build a root-owned, manifest-backed, reversible VM runner package for the existing UTM SNMPSIM lab without exposing arbitrary command, path, OID, hostname, or mutation input.

**Architecture:** The forced SSH command reads one bounded JSON request from standard input and dispatches only typed operation/control messages. A pure runner core receives injected filesystem/process adapters for offline tests, mutates only paths derived from the deployed manifest and fixed layout, persists lifecycle state atomically, and rolls back to a captured baseline on failure. Static packaging assets install the runner, service unit, restricted account policy, and recoverable baseline without touching LibreNMS core.

**Tech Stack:** Python 3.14 standard library, existing `simulation` contracts, systemd 257 unit, POSIX shell packaging checks, `unittest`.

**Spec:** `docs/superpowers/specs/2026-09-03-emr-55-simulation-lab-design.md`

## Verified UTM facts (read-only inspection, 2026-09-03)

- Guest: Debian 13 ARM64, systemd 257.
- Current responder is a manually launched `librenms:librenms` process; `snmpsim-lab.service` does not exist.
- Fixed binaries: `/opt/snmpsim-venv/bin/snmpsim-command-responder`, `/usr/bin/snmpget`, `/usr/bin/snmpwalk`, `/usr/sbin/runuser`.
- Runtime data: `/opt/snmpsim-lab/data/{manifest-target-id}/public.snmprec`, cache `/opt/snmpsim-lab/cache`.
- Membership source: `/opt/snmpsim-lab/devices.txt`; current active set: root-owned `/opt/snmpsim-lab/devices-up.txt`.
- `lab-j9772a-01` is active at `127.0.0.11:1611`; `lab-j9775a-01` exists at `127.0.0.13:1611` but is inactive.
- The target SNMPREC file contains the exact catalog OIDs and four IF-MIB indexes used by EMR-58.

## Global constraints

- No live VM mutation, service stop/start, user creation, sudoers write, or SSH-key installation in EMR-59 verification.
- The browser and Mac API never provide a command, executable, filesystem path, hostname, IP, OID, SNMP type, or mutation value.
- Public operations remain exactly `apply`, `poll`, `observe`, and `reset`.
- Internal transport controls use a distinct request shape and are exactly `status` and `recover`.
- Every request includes the caller's canonical manifest SHA; mismatch fails before lock/state/filesystem/process work.
- Every operation takes one global nonblocking lock. Busy returns `lab_busy`.
- Writes use sibling temporary files, file and directory fsync, atomic replace, bounded modes, ownership checks, and post-write parse.
- Process calls are fixed argument arrays with `shell=False`, bounded output, timeouts, process-group termination, and stable errors.
- Apply failures attempt baseline restoration; failed restoration persists `manual_recovery_required`.
- Reset success requires baseline files restored, service active, and baseline SNMP reachability verified.
- Installer and rollback operate only under `/opt/librenms-ai-lab`, `/var/lib/librenms-ai-lab`, the one service/sudoers file, the dedicated user's authorized_keys, and the existing SNMPSIM lab paths. LibreNMS core source remains untouched.

## File map

- Create `simulation/runner/__init__.py`: stable runner exports.
- Create `simulation/runner/errors.py`: stable error/result records and bounded safe diagnostics.
- Create `simulation/runner/protocol.py`: bounded duplicate-safe JSON input and output framing.
- Create `simulation/runner/snmprec.py`: strict SNMPREC parse/update and active membership transform.
- Create `simulation/runner/storage.py`: fixed layout, atomic bytes/JSON writes, persistent state and lock.
- Create `simulation/runner/processes.py`: fixed command runner, timeout/process-group handling, output reducer.
- Create `simulation/runner/core.py`: apply/poll/observe/reset/recover/status orchestration.
- Create `simulation/runner/forced_command.py`: stdin-to-runner entry point with terminal JSON result.
- Create `simulation/runner/snmpsim_service.py`: service launcher built only from deployed manifest and active membership.
- Create `simulation/systemd/snmpsim-lab.service`: hardened service definition.
- Create `simulation/packaging/install-runner.sh`: validate, back up, install disabled-by-default, and print activation command.
- Create `simulation/packaging/activate-runner.sh`: explicit legacy-process handoff with automatic rollback.
- Create `simulation/packaging/verify-runner.sh`: ownership/unit/SHA/forced-command checks.
- Create `simulation/packaging/rollback-runner.sh`: restore baseline and previous manual launcher.
- Create `simulation/packaging/librenms-ai-lab.sudoers`: exact forced runner command only.
- Create `simulation/tests/test_runner_protocol.py`.
- Create `simulation/tests/test_runner_snmprec.py`.
- Create `simulation/tests/test_runner_storage.py`.
- Create `simulation/tests/test_runner_processes.py`.
- Create `simulation/tests/test_runner_core.py`.
- Create `simulation/tests/test_runner_packaging.py`.
- Modify `simulation/README.md` and root `README.md` with accurate deployable/not-live status.

## Task 1: Forced-command protocol and stable errors

**Interfaces:**

```python
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

def parse_request(payload: bytes, manifest: Manifest) -> OperationRequest | ControlRequest
def encode_event(event: RunnerEvent) -> bytes
def encode_terminal(result: RunnerResult) -> bytes
```

- [x] Write tests for maximum 4096 bytes, UTF-8/JSON errors, duplicate keys, NaN/Infinity, exact root keys, exact version, SHA equality, exact four operations, exact two controls, manifest scenario membership, trailing JSON, and hostile command/path/OID fields.
- [x] Run `python3 -m unittest simulation.tests.test_runner_protocol -v` and verify RED from missing module.
- [x] Implement typed requests plus `RunnerError(code, retryable=False, stage=None)` and immutable `RunnerEvent`/`RunnerResult`. Errors expose stable codes and bounded allowlisted diagnostic fields only.
- [x] Run protocol tests GREEN and commit `feat(simulation): add runner protocol`.

## Task 2: Strict SNMPREC and membership transformations

**Interfaces:**

```python
@dataclass(frozen=True)
class SnmpRecord:
    oid: str
    snmp_type: int
    value: int | str

def parse_snmprec(payload: bytes) -> tuple[SnmpRecord, ...]
def apply_semantic_values(payload: bytes, values: tuple[SemanticValue, ...]) -> bytes
def parse_membership(payload: bytes, manifest: Manifest) -> tuple[MembershipRecord, ...]
def set_endpoint_active(active_payload: bytes, inventory_payload: bytes, target: Target, active: bool) -> bytes
```

- [x] Write tests using exact UTM line shapes. Cover duplicate/malformed OIDs, unknown types, invalid UTF-8, missing catalog OID, type mismatch, duplicate requested semantics, virtual mutation rejection, CR/LF/NUL injection, deterministic newline preservation, duplicate membership, unknown inventory target, idempotent activation/deactivation, and stable ordering.
- [x] Run the new test module RED.
- [x] Implement pure byte transforms. Never accept caller paths; exact OID/type comes from `resolve_oid` and values re-run `validate_semantic_value`.
- [x] Run catalog/manifest/SNMPREC tests GREEN and commit `feat(simulation): add reversible fixture transforms`.

## Task 3: Atomic storage, persistent state, and global lock

**Interfaces:**

```python
@dataclass(frozen=True)
class RunnerLayout:
    install_root: Path
    state_root: Path
    snmpsim_root: Path
    librenms_root: Path

class RunnerStorage:
    def acquire(self) -> ContextManager[None]
    def load_state(self, manifest: Manifest) -> ScenarioState
    def save_state(self, state: ScenarioState) -> None
    def capture_baseline(self, manifest: Manifest) -> None
    def restore_baseline(self, manifest: Manifest) -> None
    def write_fixture(self, target: Target, payload: bytes) -> None
    def write_membership(self, payload: bytes) -> None
    def clear_target_cache(self, target: Target) -> tuple[str, ...]
```

- [x] Write temp-directory tests for fixed path derivation, symlink rejection, traversal-proof target IDs, mode/owner verifier calls, nonblocking lock conflict, atomic replace, fsync, canonical state JSON, corrupt/stale/unknown state rejection, baseline capture-once, manifest SHA mismatch, exact restore set, and cache deletion restricted to the target's known DBM names.
- [x] Run storage tests RED.
- [x] Implement storage without recursive delete, caller globs, unresolved environment variables, or broad roots. Make owner verification injectable for offline tests and mandatory in production.
- [x] Run storage plus EMR-58 tests GREEN and commit `feat(simulation): persist runner state atomically`.

## Task 4: Fixed process adapter and output reducer

**Interfaces:**

```python
class ProcessAdapter:
    def restart_snmpsim(self) -> ProcessResult
    def service_active(self) -> bool
    def verify_snmp(self, target: Target, expected: tuple[SemanticValue, ...]) -> VerificationResult
    def run_poll(self, target: Target, mode: str) -> tuple[ProcessResult, ...]

def run_fixed(
    argv: tuple[str, ...],
    timeout_s: int,
    allowed_commands: tuple[tuple[str, ...], ...],
    allowed_output_prefixes: tuple[str, ...],
) -> ProcessResult
```

- [x] Write fake-subprocess tests proving `shell=False`, new process group, exact executable arrays, allowlisted hostname from Target, poll mode order, no poll for `none`, timeout group termination, output byte/line caps, redaction of token/password/auth-like lines, nonzero/timeout stable codes, and endpoint-unreachable verification semantics.
- [x] Run process tests RED.
- [x] Implement only fixed binaries: `/usr/bin/systemctl`, `/usr/sbin/runuser`, LibreNMS discovery/poller, and `/usr/bin/snmpget`. Normalize SNMP output by semantic type and never return raw stderr.
- [x] Run process tests GREEN and commit `feat(simulation): add fixed runner processes`.

## Task 5: Runner orchestration and rollback

**Interfaces:**

```python
class LabRunner:
    def execute(self, request: OperationRequest | ControlRequest) -> RunnerResult

def build_runner_from_environment() -> LabRunner
def main() -> int
```

- [x] Write fake storage/process tests for status, apply (SNMP value and endpoint membership), poll, baseline observe, applied observe, reset from every allowed state, recover, SHA mismatch before lock, global busy, repeated/switch conflicts, exact event order, apply verification failure rollback, reset health failure, and rollback failure to manual recovery.
- [x] Add cancellation/exception tests proving terminal result exactly once and no raw exception/stdout/stderr/path leaks.
- [x] Run core tests RED.
- [x] Implement orchestration against EMR-58 `transition`, `failed`, and `recovery_required`, always passing the loaded manifest ID set.
- [x] Implement `forced_command.main`: read at most 4097 bytes, parse one request, stream bounded JSONL events, emit one terminal record, and use exit codes `0` success, `2` validation/conflict, `3` retryable/runtime, `4` recovery required.
- [x] Run all runner tests GREEN and commit `feat(simulation): orchestrate reversible lab runs`.

## Task 6: SNMPSIM service launcher and packaging contract

- [x] Write packaging tests that inspect exact service, sudoers, shell scripts, and launcher. Require no user input in service command, manifest-backed endpoints, `User=librenms`, `NoNewPrivileges=true`, `PrivateTmp=true`, `ProtectSystem=strict`, bounded `ReadWritePaths`, no shell `eval`, dedicated account `librenms-ai-lab`, forced `restrict,command=...` authorized key, one exact sudo command, `sshd -t`/`systemd-analyze verify`, backups, SHA checks, activation rollback, and no `/opt/librenms` source writes.
- [x] Run packaging tests and `bash -n simulation/packaging/*.sh` RED.
- [x] Implement launcher and static packaging assets. `install-runner.sh` stages/version-checks/backups but does not stop the legacy process or enable/start the service. `activate-runner.sh` is the only handoff point and restores the previous `/opt/snmpsim-lab/run-up-only.sh` flow if service verification fails.
- [x] Make all destination roots constants and reject alternate broad roots. Public-key material is supplied as a file at install time and is never committed.
- [x] Run packaging/unit tests GREEN and commit `feat(simulation): package restricted VM runner`.

## Task 7: Documentation, review, and complete regression gate

- [ ] Document offline tests, exact installer/activation/verify/rollback sequence, prerequisites, ownership, SSH forced-command setup, recovery behavior, and explicit EMR-63 live authorization boundary.
- [ ] Update root repository map without claiming the UTM runner is installed.
- [ ] Run:

```bash
python3 -m unittest discover -s simulation/tests -p 'test_*.py' -v
.venv/bin/python3 -m unittest discover -s librenms-hybrid-poc -p 'test_*.py' -v
cd chat-ui && npm test -- --runInBand && npm run build
cd .. && .venv/bin/python3 -m unittest discover -s integrations/librenms/AiAssistant/tests -p 'test_*.py' -v
bash -n simulation/packaging/*.sh
git diff --check
```

- [ ] Security-review the complete EMR-59 diff. Critical/Important findings block push.
- [ ] Confirm no secrets, private keys, absolute personal paths, VM-generated state, baseline copies, or artifacts are tracked.
- [ ] Commit docs and push `codex/librenms-ai-assistant`; leave the worktree intact for EMR-60/61/62/63.

## Acceptance evidence

- Forced transport cannot express arbitrary execution or mutation material.
- Manifest SHA and scenario membership are checked before side effects.
- Fixture/membership transforms are pure, typed, deterministic, and reversible.
- Global lock and persisted lifecycle reject concurrency and scenario switches.
- Process arrays and filesystem targets are fixed and test-proven.
- Any failed apply/reset proves baseline restoration or persists manual recovery.
- Installer is inert until explicit activation; rollback is packaged and testable.
- Existing chat/backend/plugin behavior remains green.
- `/opt/librenms` core is neither changed nor written by package logic.
