# EMR-55 LibreNMS AI Simulation Lab Design

**Date:** 2026-09-03  
**Status:** Approved direction, implementation pending  
**Linear:** EMR-55

## 1. Purpose and boundaries

The Simulation Lab turns the current UTM-based SNMPSIM environment into a repeatable demo and validation tool. It must prove the chain from a controlled SNMP change through LibreNMS polling to the AI Assistant answer and bounded structured evidence.

The lab is not part of the read-only product surface. It is an explicitly enabled local/development control plane with the following boundaries:

- The existing chat pipeline, FastAPI service, reusable React frontend, and LibreNMS plugin remain the primary architecture.
- No AI orchestration or simulation command execution is added to PHP.
- No browser request may contain a shell command, path, OID mutation, poller command, SSH option, or credential.
- The production-style chat endpoints remain read-only and available to `global-read` users.
- Simulation endpoints require both `AI_LAB_ENABLED=1` and an identity token carrying an administrator-only `lab: true` claim.
- The lab runner accepts only a scenario identifier and a fixed action from a manifest-backed allowlist.
- Raw LibreNMS payloads, model prompts, tokens, and grounding traces are not written to chat history.
- Generated demo artifacts are bounded, sanitized, local, and gitignored.

The first target is the existing Mac + UTM lab. The design keeps the runner transport behind an interface so a future VM-local controller can replace SSH without changing the browser API or UI.

## 2. Existing environment used by the design

The current UTM guest stores eleven SNMPSIM fixtures under `/opt/snmpsim-lab/data/`, runs the simulator from `/opt/snmpsim-lab/run-up-only.sh`, and exposes selected loopback agents on UDP port `1611`. The main scenario device, `lab-j9772a-01`, already has IF-MIB rows for four ports, including admin/oper state, speed, and alias OIDs. Several other fixture endpoints are intentionally absent from the active `devices-up.txt` set and can support deterministic down-to-up scenarios.

The simulator currently runs as a manually launched process rather than a managed service. EMR-55 will introduce a dedicated `snmpsim-lab.service` before enabling mutations. The installer must detect the existing responder, preserve its command/data, create a recoverable backup, and refuse to replace it if validation fails.

## 3. Chosen architecture

```text
LibreNMS plugin page
  └── reusable React app
        ├── Assistant view ── /ai-api/v1/threads + SSE
        └── Simulation Lab ── /ai-api/v1/lab/runs + SSE
                                  |
                                  v
                         existing Mac FastAPI
                           ├── scenario manifest
                           ├── existing LibreNMS read-only backend
                           └── LabRunnerTransport
                                  |
                           restricted SSH key
                                  |
                                  v
                         UTM allowlisted runner
                           ├── SNMPSIM fixture/state
                           ├── snmpsim-lab.service
                           └── LibreNMS discovery/poller
```

The existing Mac FastAPI service remains the sole browser-facing backend. It gains a lab router, but lab execution stays isolated from chat orchestration. The VM does not expose a new HTTP service.

The Mac service invokes the UTM runner with `subprocess` argument arrays and `shell=False`. A dedicated SSH key uses a restricted account and forced command. The VM runner is root-owned, validates all input against its deployed manifest, uses a filesystem lock, and never evaluates command text supplied by the client.

Rejected alternatives:

1. A VM HTTP controller would add a second exposed backend, authentication protocol, and deployment lifecycle.
2. PHP-side `exec` or sudo would mix privileged lab mutation into the LibreNMS presentation plugin and violate the established boundary.
3. General SSH access from the browser or user-configurable commands is not acceptable.

## 4. Repository layout

The implementation adds clear top-level ownership without moving the stable pipeline unnecessarily:

```text
chat-ui/                              reusable Assistant + Lab frontend
librenms-hybrid-poc/
  chat_service/                       browser-facing API and SSE
  simulation_api/                     lab router, service, transport, evidence
integrations/librenms/AiAssistant/    LibreNMS plugin and asset packaging
simulation/
  scenarios.json                     source-of-truth scenario manifest
  fixtures/                          versioned sanitized baseline fixtures
  runner/                             VM-only allowlisted runner
  systemd/                            snmpsim-lab unit
  packaging/                          install, verify, and rollback scripts
scripts/                              local startup and acceptance entrypoints
docs/
  demo-validation-guide.md
  architecture.md
artifacts/simulation/                 generated and gitignored
```

The README explains this map. Existing directory names remain stable to avoid a broad import/deployment migration unrelated to the lab.

## 5. Scenario manifest

`simulation/scenarios.json` is the single source of truth for the Mac API, VM runner, UI, documentation checks, and acceptance runner. JSON is chosen to avoid adding a YAML parser dependency to the constrained VM runner.

The manifest has a version, target definitions, and scenario records. Each scenario includes:

```json
{
  "id": "port-admin-up-oper-down",
  "name": "Port link failure",
  "description": "Keep administration enabled while the link goes down.",
  "device": "lab-j9772a-01",
  "precondition": "port 2 is admin up and oper up",
  "mutation": {
    "kind": "snmprec-values",
    "values": [{"semantic": "ifOperStatus", "index": 2, "value": 2}]
  },
  "expected_snmp": [{"semantic": "ifOperStatus", "index": 2, "value": 2}],
  "poll_mode": "poller",
  "expected_librenms_surface": [{"kind": "port", "ifIndex": 2, "ifOperStatus": "down"}],
  "expected_api_evidence": [{"resource": "device_ports", "selector": {"ifIndex": 2}}],
  "example_questions": ["lab-j9772a-01 cihazında admin açık olup linki down olan port var mı?"],
  "expected_answer_semantics": ["port_identity", "admin_up", "oper_down"],
  "reset_state": "baseline"
}
```

Manifest validation rejects unknown keys, duplicate IDs, unknown devices, paths, raw OIDs outside the semantic catalog, shell strings, unsupported actions, oversized values, and scenarios without a reset state. A semantic catalog maps approved names to exact OIDs and types inside the runner; manifest authors do not provide arbitrary filesystem destinations or commands.

Every mutation scenario must declare `expected_snmp`; apply/reset verification is derived from this explicit contract rather than inferred from the requested mutation.

The initial manifest contains at least these repeatable scenarios:

1. device up to down;
2. device down to up;
3. port admin up and oper up;
4. port admin up and oper down;
5. port down to up transition;
6. port alias/description change;
7. location change;
8. uptime reset/simulated reboot;
9. one down port among multiple ports;
10. event-producing device or port transition.

An alert-trigger scenario is included only when an installed lab alert rule is detected. It is reported as unavailable rather than falsely passing when no compatible rule exists.

## 6. VM runner and reversible state

The runner supports exactly four actions:

- `apply <scenario-id>`
- `poll <scenario-id>`
- `observe <scenario-id>`
- `reset <scenario-id>`

Scenario state follows the fixed lifecycle `baseline -> applied -> polled -> observed -> ai_verified -> reset`. The state machine explicitly allows `baseline -> observe`, treats `baseline -> reset` as a safe no-op, rejects repeated apply with `409 scenario_already_applied`, and permits reset from applied or failed state. `manual_recovery_required` permits only recovery/status operations. Applying or selecting a different scenario while any scenario is not reset fails with `409 reset_required`.

The actual forced SSH command carries a small versioned JSON request on standard input; the public FastAPI schema still exposes the four fixed actions. The runner returns bounded JSON events and safe log excerpts on standard output. Standard error is mapped to stable error codes and is not forwarded raw to the browser.

Before the first mutation, installation creates a root-owned baseline containing:

- active device endpoint membership;
- the selected fixture files;
- manifest SHA-256;
- service definition and previous responder command metadata.

Every runner operation obtains an exclusive lock. Fixture writes use a temporary sibling file, fsync, atomic rename, ownership verification, and post-write parsing. Endpoint membership changes use the same atomic pattern. The runner clears only the affected SNMPSIM cache entries and restarts `snmpsim-lab.service`. It then performs a direct `snmpget`/`snmpwalk` semantic check before reporting apply success.

`poll` runs only fixed root-owned wrappers for the target manifest device:

```text
sudo -u librenms /opt/librenms/discovery.php -h <allowlisted-hostname>
sudo -u librenms /opt/librenms/poller.php -h <allowlisted-hostname>
```

The hostname comes from the deployed manifest, never from the HTTP request. Output is reduced to exit status, duration, and allowlisted diagnostic lines. Timeouts terminate the process group and produce a retryable stable error.

`reset` restores the baseline atomically, clears affected caches, restarts the service, verifies SNMP, and optionally runs the scenario's declared poll mode. Apply or reset failure triggers a best-effort rollback and leaves a visible `manual_recovery_required` state if the baseline cannot be restored automatically.

The packaging script installs:

- `/opt/librenms-ai-lab/runner/` and the manifest;
- `/etc/systemd/system/snmpsim-lab.service`;
- a dedicated restricted SSH user/key policy;
- a narrowly scoped sudoers entry for the root-owned runner only;
- state under `/var/lib/librenms-ai-lab/`;
- recoverable backups under `/opt/librenms/.ai-assistant-backups/` or a sibling lab backup root.

It does not change LibreNMS core source files.

## 7. Authentication and authorization

The plugin continues authorizing the Assistant page with `global-read`. Its signed token gains a boolean `lab` claim derived only from `auth()->user()->hasRole('admin')`. Non-admin users receive `lab: false` and never see the Lab navigation item.

Backend enforcement is independent of UI visibility. Every `/v1/lab` request must satisfy all of the following:

1. valid existing HMAC identity token;
2. exact `lab: true` claim;
3. `AI_LAB_ENABLED=1`;
4. configured SSH host, user, key path, pinned host key, and local/deployed manifest SHA match.

Development auth requires both the existing explicit development mode and `AI_LAB_DEV_AUTH=1`. No development token, SSH key, LibreNMS API token, or shared secret enters the production bundle or repository.

Lab mutation endpoints use a per-user run registry for ownership plus one global lab mutation lock because all administrators share the same VM, fixtures, responder, and LibreNMS state. Any concurrent mutation or scenario switch returns `409 lab_busy` or `409 reset_required`. Read-only Assistant runs may continue, but mutation and evidence capture for a scenario are globally serialized to preserve causal proof.

## 8. Public lab API and event contract

All paths are below the existing authenticated `/v1` application:

- `GET /v1/lab/scenarios` returns available sanitized manifest records and capability flags.
- `GET /v1/lab/status` returns enabled state, runner reachability, manifest agreement, active scenario, and recovery state.
- `POST /v1/lab/runs` accepts `{scenario_id, action}` and returns SSE.
- `GET /v1/lab/runs/{id}` returns a bounded result for refresh and acceptance collection.
- `POST /v1/lab/runs/{id}/ai-check` runs the manifest example question through the existing Mac-side hybrid pipeline; AI validation is never a VM runner action.
- `GET /v1/lab/artifacts/{id}.json|md` is local-development-only and returns a generated acceptance artifact owned by the requesting admin.

Lab run summaries are persisted in a separate SQLite database configured by `AI_LAB_DATABASE`; they are not added to the chat history schema. The database stores the owner subject, scenario/action, status, timestamps, stable error fields, manifest SHA, and bounded sanitized result JSON. It does not store SSH output, raw LibreNMS payloads, model prompts, credentials, or full grounding traces. WAL, foreign keys, busy timeout, per-query owner filtering, and a schema version follow the existing chat store conventions. Artifact downloads are generated from these sanitized records.

SSE uses real runner/service boundaries:

```text
lab.run.started
lab.runner.started
lab.fixture.completed       # apply/reset when applicable
lab.snmpsim.restarted       # apply/reset when applicable
lab.snmp.verified           # apply/reset
lab.discovery.completed     # declared modes only
lab.poller.completed        # declared modes only
lab.evidence.completed      # observe/acceptance
lab.ai.completed            # acceptance check when requested
lab.run.completed
```

Failures emit `error {stage, code, retryable, message}` followed by `lab.run.completed` with failed status. No fake timers or optimistic stage completion is shown. Heartbeats use the existing SSE convention.

The FastAPI lab service coordinates the boundaries: apply/reset and SNMP verification come from the runner, poll/discovery come from its fixed wrappers, and LibreNMS/API/AI observations are collected on the Mac through existing Python interfaces. The browser receives one ordered stream and cannot select a lower-level command.

LibreNMS updates are eventually consistent after discovery/poller completion. Evidence collection therefore uses bounded probes configured with a maximum attempt count and interval, with scenario-specific values capped by service-wide limits. Exhaustion produces the stable retryable error code `evidence_timeout`; the UI never advances a proof stage based on elapsed time alone.

## 9. Evidence model

Each lab run returns separate `expected` and `observed` sections:

```json
{
  "scenario_id": "port-admin-up-oper-down",
  "captured_at": "2026-09-03T10:00:00Z",
  "expected": {
    "snmp": [],
    "librenms": [],
    "answer_semantics": []
  },
  "observed": {
    "snmp": [],
    "librenms": [],
    "ai": {"question": "...", "answer": "...", "structured_evidence": []}
  },
  "verification_links": [],
  "checks": [],
  "status": "pass"
}
```

Observed LibreNMS evidence is collected through the existing read-only `LibreNMSBackend` methods. It is normalized and reduced to fields needed by the scenario. Device, port, alert, and event IDs remain available so the UI can build contextual LibreNMS deep links. SQL evidence is documentation-only in the first implementation unless the API cannot provide a required field; any later DB adapter must be independently read-only and allowlist exact prepared queries.

The AI validation step runs the existing hybrid pipeline against a manifest example question. It records the final answer, route, normalized tool names/arguments, and sanitized structured findings required for the expected semantics. It does not retain prompts, model output drafts, judge details, raw API payloads, bearer tokens, or the full grounding trace.

Current-state and historical-transition checks are distinct. A current `ifOperStatus=down` observation does not prove a down transition; the latter requires a timestamped LibreNMS event or explicitly reports insufficient historical evidence.

## 10. Frontend experience

The reusable frontend gains an admin-only `Simulation Lab` destination beside the Assistant view. It uses the same scoped CSS, LibreNMS typography/colors, and assistant-ui-compatible interaction quality, but it is visually marked as a lab control plane.

Desktop layout:

- compact scenario rail with capability/status filters;
- central scenario description and expected behavior;
- a sticky action bar containing Apply, Run poll/discovery, Observe, Run AI check, and Reset;
- a chronological real-event activity stream;
- a collapsible proof panel with Expected and Observed tabs;
- contextual links to LibreNMS device, port, eventlog, and alert surfaces;
- example questions that can be copied or sent into a new Assistant thread.

The UI never displays or constructs a shell command. A human-readable “runner action” label comes from the sanitized manifest, such as “Port 2 operational state → down.” Destructive-looking mutations require confirmation, identify the target device, and keep Reset prominent. Navigation away from an applied scenario warns when reset is still pending.

The Lab is responsive, keyboard accessible, and screen-reader announced. Progress, success, and failure derive only from SSE events. Non-admin users neither render Lab controls nor receive lab data from the API.

## 11. Acceptance artifacts and demo guide

`scripts/run-demo-acceptance.py` can execute one scenario or the declared matrix. By default it requires interactive confirmation before mutation; CI uses only the fake runner. An explicit `--authorized-live-lab` flag is required for UTM mutation.

Each result produces:

- `artifacts/simulation/<timestamp>-<scenario>.json` with the structured record;
- `artifacts/simulation/<timestamp>-summary.md` with a readable table.

The artifacts directory is gitignored. Tests use committed fixtures under `simulation/tests/fixtures/`, not generated live output.

`docs/demo-validation-guide.md` maps each supported utility to:

- LibreNMS UI location and contextual URL shape;
- API endpoint/resource;
- authoritative DB table/field where useful for manual troubleshooting;
- poller/event log search terms;
- AI direct-read or structured tool path;
- manual cross-check procedure;
- current-state versus transition interpretation.

It covers device status, identity/sysName, model/sysDescr, uptime, location, port list, admin/oper state, speed, alias, device and port transitions, events, and alerts. The guide also includes the technical explanation requested for Murat Bey: structured operational data uses controlled tools/direct reads; unstructured documentation or institutional knowledge may later use RAG.

The root README is updated with project purpose, architecture, deterministic grounding rationale, supported and unsupported scope, lab setup, SNMPSIM/LibreNMS/Assistant setup, environment example, minimum-step startup, Simulation Lab, acceptance commands, demo walkthrough, proof guide, security guarantees, and limitations. The documented hardware/model limitations are framed as deliberate latency and reliability trade-offs.

## 12. Testing strategy

Implementation follows test-driven development.

### Offline Python tests

- manifest schema, semantic/OID allowlist, duplicate and malicious input rejection;
- runner atomic mutation, lock, cache targeting, reset, rollback, and timeout behavior against temporary fixtures;
- no `shell=True`, no browser-controlled path/hostname/command, and exact SSH argument construction;
- manifest SHA mismatch and host-key mismatch fail closed;
- admin claim, lab feature flag, ownership, concurrency, SSE order, cancellation, and stable errors;
- evidence normalization, bounded fields, transition semantics, sanitization, and artifact generation;
- existing 124-test pipeline/chat regression suite remains green.

### Frontend tests

- admin/non-admin navigation and direct-route protection;
- scenario reducer, action confirmation, real stage ordering, cancellation/failure, reset warning, and retry;
- Expected/Observed proof rendering and deep-link construction;
- send-example-question integration with Assistant threads;
- responsive rail and accessible activity/proof disclosures;
- no raw command or secret in rendered configuration.

### Packaging/plugin tests

- admin-derived `lab` claim cannot be enabled by settings or browser input;
- deployed paths exclude LibreNMS core sources;
- service, runner, sudoers, restricted key, backup, verification, and rollback contracts;
- production assets remain fixed names and cache-busted.

### Browser and live acceptance

Standalone Playwright uses the real lab API with a deterministic fake transport and temporary fixtures. Authorized UTM acceptance then proves apply → SNMP verify → discovery/poller → LibreNMS evidence → AI answer → reset for at least eight manifest scenarios. Every live scenario must leave the baseline restored, the SNMPSIM service healthy, and `/opt/librenms` core `git status` clean.

The frozen minimum live set is: device up-to-down, device down-to-up, port admin-up/oper-up, port admin-up/oper-down, port down-to-up transition, port alias change, location change, and uptime reset. Each begins from independently verified baseline state. One-down-port-among-many and event-producing transition remain additional targets; alert acceptance is capability-gated.

## 13. Rollout and rollback

Rollout is deliberately staged:

1. manifest/runner unit tests with temporary fixtures;
2. FastAPI lab API with fake transport;
3. standalone Lab UI and Playwright;
4. VM backup and runner/systemd installation without mutation;
5. runner health and manifest SHA verification;
6. one low-risk location scenario, poll, evidence capture, and reset;
7. remaining non-alert scenarios;
8. optional alert scenario after rule detection;
9. full demo matrix and documentation walkthrough;
10. plugin bundle deployment and authenticated UTM UI acceptance.

Rollback disables `AI_LAB_ENABLED`, hides the Lab UI, restores the previous responder command/service and fixtures from the timestamped backup, removes the restricted lab SSH authorization/sudoers entry, and leaves the read-only Assistant running. Chat service and history are not rolled back unless independently required.

## 14. Definition of done

EMR-55 is complete only when:

- an admin can select, apply, observe, and reset the required scenario categories from a distinct Lab surface;
- actions are manifest-backed and no arbitrary shell/data mutation boundary exists;
- SNMPSIM state is verified before LibreNMS polling;
- expected and observed LibreNMS evidence and contextual links are visible;
- an example AI question produces an answer plus sanitized structured proof;
- current state and historical transition claims are tested separately;
- at least eight scenarios produce JSON and Markdown PASS/FAIL records;
- reset is repeatable and failed runs provide a recovery path; a run is always FAIL when reset or baseline-health verification fails, even if mutation, evidence, and AI checks passed;
- the validation guide and root README support a new developer and the Murat Bey demo;
- no secret, personal path, generated artifact, or raw trace is committed;
- all existing and new offline suites pass;
- authorized UTM acceptance finishes with the baseline restored and LibreNMS core clean.

## 15. Linear implementation split

EMR-55 remains the parent epic. Implementation and review gates follow the frozen child-task dependency graph:

1. EMR-58 / EMR-55A — manifest, semantic catalog, deterministic SHA, and state contract;
2. EMR-59 / EMR-55B — VM runner, managed SNMPSIM, restricted SSH, reversible state;
3. EMR-60 / EMR-55C — FastAPI lab router, authorization, transport, SSE, global lock, and separate run store;
4. EMR-61 / EMR-55D — normalized evidence, AI validation, and artifacts;
5. EMR-62 / EMR-55E — admin-only React Lab and proof experience;
6. EMR-63 / EMR-55F — authorized UTM matrix, rollback drill, validation guide, and README.

EMR-58 completes first. EMR-59 and EMR-60 may then proceed independently. EMR-61 requires EMR-58 and EMR-60; EMR-62 requires EMR-60 and can use the fake transport. EMR-63 begins only after EMR-59, EMR-61, and EMR-62 have passed their review gates.
