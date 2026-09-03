# EMR-58 Simulation Manifest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce the single validated Simulation Lab scenario manifest, semantic OID catalog, deterministic manifest identity, and lifecycle contract required by EMR-59 through EMR-63.

**Architecture:** A dependency-free top-level Python package owns strict JSON parsing and immutable domain records. The committed JSON manifest contains trusted target/scenario definitions but never raw commands or filesystem destinations; exact OIDs live only in the Python semantic catalog. A separate pure state module enforces the frozen lifecycle without performing VM, API, database, or UI work.

**Tech Stack:** Python 3.14 standard library, JSON, `dataclasses`, `enum`, `hashlib`, `unittest`.

**Spec:** `docs/superpowers/specs/2026-09-03-emr-55-simulation-lab-design.md`

## Global Constraints

- EMR-58 contains no VM mutation, SSH, FastAPI endpoint, database, React UI, or live UTM operation.
- JSON remains the manifest format; do not add YAML or another dependency.
- Manifest authors may not provide shell strings, filesystem paths, executable names, or free-form OIDs.
- `poll_mode` is exactly `none`, `poller`, `discovery`, or `discovery_then_poller`.
- Every mutation scenario has explicit `expected_snmp` and `reset_state: "baseline"`.
- Device-down semantics use endpoint membership, never a synthetic device-status OID.
- Exact OIDs and SNMP types exist only in the semantic catalog.
- Public/UI manifest output excludes agent addresses, fixture identifiers, mutation values, exact OIDs, and reset internals.
- Manifest identity is SHA-256 of canonical validated JSON, not formatting-dependent source bytes.
- Existing 124 Python, 48 frontend, and 9 plugin regression tests must remain green.

---

## File map

- Create `simulation/__init__.py`: stable exports used by Mac API and VM runner.
- Create `simulation/catalog.py`: exact semantic-to-OID/type/index/value allowlist.
- Create `simulation/manifest.py`: strict loader, immutable records, canonical hash, and sanitized public projection.
- Create `simulation/state.py`: frozen scenario lifecycle and transition errors.
- Create `simulation/scenarios.json`: versioned target and ten-scenario source of truth.
- Create `simulation/tests/test_catalog.py`: catalog and typed-value behavior.
- Create `simulation/tests/test_manifest.py`: valid manifest, malicious input, public projection, and hash behavior.
- Create `simulation/tests/test_state.py`: lifecycle, conflicts, reset, failure, and recovery behavior.
- Create `simulation/README.md`: contract ownership and consumer instructions.
- Modify `README.md`: add the repository map and point to the Simulation contract without claiming the runner/UI exists.

### Task 1: Semantic OID catalog

**Files:**
- Create: `simulation/__init__.py`
- Create: `simulation/catalog.py`
- Test: `simulation/tests/test_catalog.py`

**Interfaces:**
- Produces: `SemanticSpec(name: str, oid: str | None, snmp_type: int | None, indexed: bool, allowed_values: frozenset[int] | frozenset[bool] | None, max_length: int | None)`.
- Produces: `SEMANTIC_CATALOG: Mapping[str, SemanticSpec]`.
- Produces: `resolve_oid(name: str, index: int | None) -> tuple[str, int]`.
- Produces: `validate_semantic_value(name: str, index: int | None, value: object) -> None`.
- Consumed by: Task 2 manifest validation and later EMR-59 runner mutation/verification.

- [x] **Step 1: Write catalog tests that name each security boundary**

Create `simulation/tests/test_catalog.py` with these literal cases:

```python
import unittest

from simulation.catalog import resolve_oid, validate_semantic_value


class SemanticCatalogTests(unittest.TestCase):
    def test_resolves_only_approved_scalar_and_indexed_semantics(self):
        self.assertEqual(resolve_oid("sysLocation", None), ("1.3.6.1.2.1.1.6.0", 4))
        self.assertEqual(resolve_oid("ifOperStatus", 2), ("1.3.6.1.2.1.2.2.1.8.2", 2))
        with self.assertRaisesRegex(ValueError, "unknown_semantic"):
            resolve_oid("1.3.6.1.4.1.999", None)
        with self.assertRaisesRegex(ValueError, "index_required"):
            resolve_oid("ifOperStatus", None)
        with self.assertRaisesRegex(ValueError, "index_forbidden"):
            resolve_oid("sysLocation", 1)

    def test_rejects_wrong_types_enums_ranges_and_oversized_text(self):
        for name, index, value, code in (
            ("ifAdminStatus", 1, 3, "invalid_enum"),
            ("ifOperStatus", 1, "down", "invalid_type"),
            ("sysUpTime", None, -1, "invalid_range"),
            ("ifAlias", 1, "x" * 129, "value_too_long"),
        ):
            with self.subTest(name=name, value=value), self.assertRaisesRegex(ValueError, code):
                validate_semantic_value(name, index, value)

    def test_accepts_values_used_by_the_initial_scenarios(self):
        for name, index, value in (
            ("sysLocation", None, "Murat Bey Demo Lab"),
            ("sysUpTime", None, 300),
            ("ifAdminStatus", 2, 1),
            ("ifOperStatus", 2, 2),
            ("ifAlias", 4, "Demo-Uplink"),
            ("endpointReachable", None, False),
        ):
            validate_semantic_value(name, index, value)

    def test_virtual_reachability_is_validated_but_never_resolved_to_an_oid(self):
        validate_semantic_value("endpointReachable", None, True)
        with self.assertRaisesRegex(ValueError, "virtual_semantic"):
            resolve_oid("endpointReachable", None)
        with self.assertRaisesRegex(ValueError, "invalid_type"):
            validate_semantic_value("endpointReachable", None, 1)
```

- [x] **Step 2: Run the catalog tests and verify RED**

Run: `python3 -m unittest simulation.tests.test_catalog -v`  
Expected: import failure because `simulation.catalog` does not exist.

- [x] **Step 3: Implement the closed semantic catalog**

Create `simulation/catalog.py` with exactly these approved semantics:

```python
from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class SemanticSpec:
    name: str
    oid: str | None
    snmp_type: int | None
    indexed: bool = False
    allowed_values: frozenset[int] | frozenset[bool] | None = None
    max_length: int | None = None


SEMANTIC_CATALOG = MappingProxyType({
    "sysUpTime": SemanticSpec("sysUpTime", "1.3.6.1.2.1.1.3.0", 67),
    "sysName": SemanticSpec("sysName", "1.3.6.1.2.1.1.5.0", 4, max_length=64),
    "sysLocation": SemanticSpec("sysLocation", "1.3.6.1.2.1.1.6.0", 4, max_length=128),
    "ifAdminStatus": SemanticSpec("ifAdminStatus", "1.3.6.1.2.1.2.2.1.7", 2, True, frozenset({1, 2})),
    "ifOperStatus": SemanticSpec("ifOperStatus", "1.3.6.1.2.1.2.2.1.8", 2, True, frozenset({1, 2})),
    "ifAlias": SemanticSpec("ifAlias", "1.3.6.1.2.1.31.1.1.1.18", 4, True, max_length=128),
    "endpointReachable": SemanticSpec("endpointReachable", None, None, allowed_values=frozenset({True, False})),
})
```

Implement `resolve_oid` so virtual semantics raise `virtual_semantic`, indexed semantics require integer indexes from 1 through 4096, and scalar semantics reject indexes. Implement `validate_semantic_value` so `endpointReachable` accepts booleans only; SNMP types 2/67 require non-boolean integers; uptime is nonnegative and at most `2**32 - 1`; enum fields use the exact sets above; and SNMP type 4 requires UTF-8 strings within `max_length` bytes with no NUL, CR, or LF.

Export these interfaces from `simulation/__init__.py`.

- [x] **Step 4: Run the catalog tests and verify GREEN**

Run: `python3 -m unittest simulation.tests.test_catalog -v`  
Expected: 4 tests pass.

- [x] **Step 5: Commit the semantic boundary**

```bash
git add simulation/__init__.py simulation/catalog.py simulation/tests/test_catalog.py
git commit -m "feat(simulation): add semantic OID catalog"
```

### Task 2: Strict manifest loader and canonical identity

**Files:**
- Create: `simulation/manifest.py`
- Test: `simulation/tests/test_manifest.py`
- Modify: `simulation/__init__.py`

**Interfaces:**
- Consumes: `SEMANTIC_CATALOG`, `resolve_oid`, and `validate_semantic_value` from Task 1.
- Produces: immutable `Target`, `SemanticValue`, `SurfaceExpectation`, `EvidenceSelector`, `EvidenceExpectation`, `Scenario`, and `Manifest` dataclasses.
- Produces: `load_manifest(path: str | Path) -> Manifest`.
- Produces: `validate_manifest(raw: object) -> Manifest`.
- Produces: `manifest_sha256(manifest: Manifest) -> str`.
- Produces: `public_manifest(manifest: Manifest) -> dict[str, object]`.
- Produces: `ManifestValidationError(code: str, path: str)` whose string form begins with the stable code.

- [x] **Step 1: Write strict loader tests against hand-built valid and malicious inputs**

Create `simulation/tests/test_manifest.py`. Use a complete literal minimal manifest with one loopback target and one location scenario. Assert:

```python
manifest = validate_manifest(VALID_MANIFEST)
self.assertEqual(manifest.version, 1)
self.assertEqual(manifest.scenarios[0].poll_mode, "poller")
self.assertEqual(manifest.scenarios[0].expected_snmp[0].semantic, "sysLocation")
self.assertRegex(manifest_sha256(manifest), r"^[0-9a-f]{64}$")
```

Add independent cases expecting these stable errors:

```text
unknown_key
duplicate_scenario_id
unknown_device
unsupported_poll_mode
unsupported_mutation_kind
raw_oid_forbidden
path_forbidden
shell_string_forbidden
reset_state_required
expected_snmp_required
semantic_value_invalid
device_down_requires_endpoint_membership
```

The malicious fixtures must include keys such as `command`, `path`, and `oid`, plus values such as `"$(touch /tmp/pwned)"`; assert they are rejected rather than executed or normalized.

Add a canonical hash test that validates two dictionaries with different key order and expects identical SHA-256. Change one semantic value and expect a different SHA-256.

Add a public projection test asserting the output contains `id`, `name`, `description`, `device`, `precondition`, `poll_mode`, expected human-facing surfaces, example questions, and answer semantics, while recursively containing none of:

```text
agent_address
agent_port
fixture
mutation
expected_snmp
oid
path
command
reset_state
```

- [x] **Step 2: Run manifest tests and verify RED**

Run: `python3 -m unittest simulation.tests.test_manifest -v`  
Expected: import failure because `simulation.manifest` does not exist.

- [x] **Step 3: Implement immutable records and exact schemas**

Define these record shapes in `simulation/manifest.py`:

```python
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
```

Use exact key sets at every object level. Target IDs, fixture IDs, hostnames, scenario IDs, semantic labels, and evidence selectors use bounded regex/length checks. Agent addresses must be loopback IPv4 and the initial agent port must equal `1611`. Mutation kinds are exactly `snmprec_values` and `endpoint_membership`; the latter has only `active: bool` and no values.

Reject any dictionary key named `command`, `shell`, `path`, `file`, `executable`, `argv`, or `oid` at any depth before domain conversion. Also reject strings containing shell control syntax only in mutation/control objects; natural-language descriptions and example questions remain ordinary bounded text.

Validate surface/evidence records as discriminated typed schemas so arbitrary nested values cannot cross into the public projection. Reject duplicate JSON keys and non-finite numeric constants while loading. Canonicalize from the validated domain back to one stable primitive dictionary, serialize once with `allow_nan=False`, store immutable bytes, and compute:

```python
return hashlib.sha256(manifest.canonical).hexdigest()
```

Update `simulation/__init__.py` with all public manifest exports.

- [x] **Step 4: Run manifest and catalog tests and verify GREEN**

Run: `python3 -m unittest simulation.tests.test_catalog simulation.tests.test_manifest -v`  
Expected: all catalog and manifest tests pass.

- [x] **Step 5: Commit the validated manifest API**

```bash
git add simulation/__init__.py simulation/manifest.py simulation/tests/test_manifest.py
git commit -m "feat(simulation): validate scenario manifests"
```

### Task 3: Ten-scenario source-of-truth manifest

**Files:**
- Create: `simulation/scenarios.json`
- Modify: `simulation/tests/test_manifest.py`

**Interfaces:**
- Consumes: `load_manifest`, semantic catalog, and exact schemas from Tasks 1–2.
- Produces: committed manifest version `1` with target IDs `lab-j9772a-01` and `lab-j9775a-01`.
- Produces: exact scenario IDs consumed later by runner/API/UI/docs.

- [x] **Step 1: Add failing production-manifest contract tests**

Load `simulation/scenarios.json` relative to the test file and assert this literal scenario-ID set:

```python
{
    "device-up-to-down",
    "device-down-to-up",
    "port-admin-up-oper-up",
    "port-admin-up-oper-down",
    "port-down-to-up-transition",
    "port-alias-change",
    "location-change",
    "uptime-reset",
    "single-down-port",
    "event-producing-port-transition",
}
```

Assert every scenario has at least one example question, expected API evidence, expected LibreNMS surface, answer semantic, and explicit expected SNMP entry. Assert the device-down mutation kind is `endpoint_membership` with `endpoint_active is False`; assert no scenario semantic name is absent from `SEMANTIC_CATALOG`. Assert manifest SHA equals a 64-character lowercase hexadecimal value and is stable over two loads.

- [x] **Step 2: Run the production manifest test and verify RED**

Run: `python3 -m unittest simulation.tests.test_manifest -v`  
Expected: file-not-found failure for `simulation/scenarios.json`.

- [x] **Step 3: Create the production manifest with exact scenario semantics**

Create two targets:

| Target | Agent | Baseline | Capability |
| --- | --- | --- | --- |
| `lab-j9772a-01` | `127.0.0.11:1611` | active | device, ports, location, uptime, events |
| `lab-j9775a-01` | `127.0.0.13:1611` | inactive | device reachability |

Create these scenario mutations and expected SNMP contracts:

| Scenario | Mutation | Expected SNMP | Poll mode |
| --- | --- | --- | --- |
| `device-up-to-down` | endpoint active `false` on `lab-j9772a-01` | endpoint unreachable marker | poller |
| `device-down-to-up` | endpoint active `true` on `lab-j9775a-01` | `sysName=lab-j9775a-01` | discovery_then_poller |
| `port-admin-up-oper-up` | port 2 admin `1`, oper `1` | same two values | poller |
| `port-admin-up-oper-down` | port 2 admin `1`, oper `2` | same two values | poller |
| `port-down-to-up-transition` | port 2 admin `1`, oper `1` from baseline oper-down | same two values | poller |
| `port-alias-change` | port 4 alias `Demo-Uplink` | same alias | poller |
| `location-change` | location `Murat Bey Demo Lab` | same location | poller |
| `uptime-reset` | uptime `300` ticks | same uptime | poller |
| `single-down-port` | ports 1/3/4 admin+oper up; port 2 admin up/oper down | all eight values | poller |
| `event-producing-port-transition` | port 1 admin up/oper down | same two values | poller |

Represent endpoint reachability in `expected_snmp` with the Task 1 non-OID virtual semantic `endpointReachable`. The later runner uses this semantic for reachability checks and never writes it to an SNMPREC file.

Use bounded Turkish descriptions and example questions already supported by the hybrid pipeline. Evidence records contain only resource names and selectors such as `ifIndex`, not API tokens, URLs with credentials, SQL, or commands.

- [x] **Step 4: Run all Simulation contract tests and verify GREEN**

Run: `python3 -m unittest discover -s simulation/tests -p 'test_*.py' -v`  
Expected: all tests pass and load the committed ten-scenario manifest.

- [x] **Step 5: Commit the scenario source of truth**

```bash
git add simulation/catalog.py simulation/scenarios.json simulation/tests/test_catalog.py simulation/tests/test_manifest.py
git commit -m "feat(simulation): define initial lab scenarios"
```

### Task 4: Frozen lifecycle and conflict contract

**Files:**
- Create: `simulation/state.py`
- Create: `simulation/tests/test_state.py`
- Modify: `simulation/__init__.py`

**Interfaces:**
- Produces: `ScenarioPhase` values `baseline`, `applied`, `polled`, `observed`, `ai_verified`, `reset`, `failed`, and `manual_recovery_required`.
- Produces: `ScenarioState(phase, scenario_id, manifest_sha256, last_error_code=None)`.
- Produces: `transition(state: ScenarioState, action: str, scenario_id: str | None = None, *, known_scenario_ids: Collection[str]) -> ScenarioState`.
- Produces: `StateTransitionError(code: str, current: ScenarioPhase, action: str)`.
- Consumed by: EMR-59 persistent runner state and EMR-60 API conflict mapping.

- [x] **Step 1: Write the state-table tests**

Create literal table-driven tests covering:

```python
allowed = (
    ("baseline", "apply", "applied"),
    ("reset", "apply", "applied"),
    ("applied", "poll", "polled"),
    ("applied", "observe", "observed"),
    ("applied", "reset", "reset"),
    ("polled", "observe", "observed"),
    ("polled", "reset", "reset"),
    ("baseline", "observe", "observed"),
    ("observed", "ai_check", "ai_verified"),
    ("observed", "reset", "reset"),
    ("failed", "reset", "reset"),
    ("ai_verified", "reset", "reset"),
    ("manual_recovery_required", "recover", "reset"),
)
```

Assert `baseline + reset` is a safe no-op preserving baseline. Assert `baseline + observe` requires membership in the supplied canonical manifest scenario-ID set and later transitions preserve it until reset clears it. Assert persisted states whose scenario is absent from that set fail closed with `unknown_scenario`. Assert repeated apply raises `scenario_already_applied`; applying another scenario from any non-reset active state raises `reset_required`; mutation during `manual_recovery_required` raises `manual_recovery_required`; invalid action/order raises `invalid_transition`. Test `failed(state, error_code)` independently from applied and polled states, and assert empty error codes are rejected. Constructor invariants reject invalid phase/ID/SHA/error combinations.

- [x] **Step 2: Run state tests and verify RED**

Run: `python3 -m unittest simulation.tests.test_state -v`  
Expected: import failure because `simulation.state` does not exist.

- [x] **Step 3: Implement a pure transition table**

Use a `str, Enum` phase type and an explicit `(phase, action) -> next_phase` dictionary. Handle conflict codes before table lookup:

```python
if action == "apply" and state.scenario_id:
    code = "scenario_already_applied" if state.scenario_id == scenario_id else "reset_required"
    raise StateTransitionError(code, state.phase, action)
if state.phase is ScenarioPhase.MANUAL_RECOVERY_REQUIRED and action not in {"recover", "status"}:
    raise StateTransitionError("manual_recovery_required", state.phase, action)
```

`reset` clears `scenario_id` and `last_error_code`. `fail` requires an error code supplied through a separate `failed(state, error_code) -> ScenarioState` helper so generic transition calls cannot invent error state. `recovery_required(state, error_code) -> ScenarioState` creates the only manual-recovery state.

Update `simulation/__init__.py` exports.

- [x] **Step 4: Run state and all Simulation tests and verify GREEN**

Run: `python3 -m unittest discover -s simulation/tests -p 'test_*.py' -v`  
Expected: all catalog, manifest, production manifest, and state tests pass.

- [x] **Step 5: Commit the lifecycle contract**

```bash
git add simulation/__init__.py simulation/state.py simulation/tests/test_state.py
git commit -m "feat(simulation): enforce scenario lifecycle"
```

### Task 5: Consumer documentation and complete regression gate

**Files:**
- Create: `simulation/README.md`
- Modify: `README.md`

**Interfaces:**
- Documents: import and validation contract for EMR-59/60 consumers.
- Documents: public manifest versus privileged manifest boundary.
- Documents: state transition/error mapping and canonical SHA deployment check.
- Does not claim: a deployed runner, enabled API, finished UI, or passing live UTM scenarios.

- [x] **Step 1: Write consumer documentation with executable examples**

Document this exact loading pattern:

```python
from pathlib import Path
from simulation import load_manifest, manifest_sha256, public_manifest

manifest = load_manifest(Path("simulation/scenarios.json"))
deployment_identity = manifest_sha256(manifest)
browser_safe_payload = public_manifest(manifest)
```

Document that EMR-59 receives the privileged immutable records, EMR-60 compares the canonical SHA and returns only `public_manifest`, and UI/docs consumers never read the source JSON directly. Include the frozen state/action table and stable conflict codes.

Add a concise root README repository-map entry pointing to `simulation/` as “validated contracts and scenarios; runner/UI follow in EMR-59/62.”

- [x] **Step 2: Run the complete EMR-58 verification set**

Run:

```bash
python3 -m unittest discover -s simulation/tests -p 'test_*.py' -v
.venv/bin/python3 -m unittest discover -s librenms-hybrid-poc -p 'test_*.py' -v
cd chat-ui && npm test -- --runInBand && npm run build
cd .. && .venv/bin/python3 -m unittest discover -s integrations/librenms/AiAssistant/tests -p 'test_*.py' -v
git diff --check
```

Expected: Simulation tests pass; existing Python reports 124 tests passing; frontend reports 7 suites / 48 tests and Vite build success; plugin reports 9 tests passing; diff check has no output.

- [x] **Step 3: Review the EMR-58 acceptance checklist against evidence**

Confirm from test output and source review:

- one JSON manifest is consumed through one loader;
- all ten required IDs exist;
- every mutation has explicit expected SNMP;
- no raw path, command, or free OID can validate;
- endpoint membership is the only device-down mutation;
- state conflicts use stable codes;
- canonical SHA is deterministic;
- public projection is sanitized;
- nested surface/evidence records use typed schemas and cannot smuggle privileged keys;
- raw JSON rejects duplicate keys and non-finite numbers;
- canonical bytes and nested records are immutable;
- lifecycle transitions verify scenario membership against the loaded manifest;
- no VM, API, DB, UI, secret, personal path, or generated artifact was introduced.

- [x] **Step 4: Commit the EMR-58 documentation and verification record**

```bash
git add README.md simulation/README.md
git commit -m "docs(simulation): document manifest contract"
```

- [ ] **Step 5: Push the independently reviewable EMR-58 slice**

```bash
git push origin codex/librenms-ai-assistant
```

Expected: remote branch advances to the final EMR-58 commit and `git status --short` remains empty.
