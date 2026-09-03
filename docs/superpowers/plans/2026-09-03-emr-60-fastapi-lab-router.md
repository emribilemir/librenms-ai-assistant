# EMR-60 FastAPI Simulation Lab Router Implementation Plan

> **Execution:** Use the approved EMR-55 design, test-driven development, and
> verification-before-completion. EMR-60 uses a fake transport offline and does
> not install or mutate the UTM VM.

**Goal:** Extend the existing browser-facing FastAPI service with an admin-only,
manifest-backed Simulation Lab API, separate run persistence, one global run
lock, bounded SSE, and a fixed restricted-SSH transport without adding another
backend or exposing runner control material to the browser.

**Architecture:** LibreNMS continues signing the existing identity token and
adds one server-derived boolean `lab` claim. FastAPI independently enforces the
claim, feature flag, transport configuration, manifest agreement, ownership,
and global concurrency. A transport interface lets offline tests use a
deterministic fake while production invokes the EMR-59 forced command through
one exact `ssh` argv and bounded JSONL stdin/stdout. Lab records live in their
own SQLite database and never enter chat history.

**Spec:** `docs/superpowers/specs/2026-09-03-emr-55-simulation-lab-design.md`

## Constraints

- Existing `/v1/threads`, chat SSE, Python hybrid pipeline, plugin page, and
  reusable frontend remain backward compatible.
- No browser field becomes a hostname, address, port, path, OID, command,
  executable, mutation value, poll mode, or SSH argument.
- Public mutations remain exactly `{scenario_id, action}` with actions
  `apply`, `poll`, `observe`, and `reset`.
- Every lab route requires a valid identity with exact `lab: true`; development
  requires both `AI_DEV_AUTH=1` and `AI_LAB_DEV_AUTH=1`.
- `AI_LAB_ENABLED=1`, valid fixed SSH configuration, pinned known-hosts input,
  and local/deployed canonical manifest SHA agreement are all required.
- One global active lab run is permitted across all admins. Ownership filtering
  applies to every persisted-run query.
- SSE progress is derived only from transport events. No fake progress timers.
- SSH stdout/JSON lines, stderr, raw LibreNMS payloads, prompts, model drafts,
  credentials, and grounding traces are never persisted or returned.
- EMR-60 ends at fake-transport API verification. Evidence normalization,
  AI proof, artifacts, UI, and live UTM acceptance belong to EMR-61/62/63.

## Task 1: Admin identity claim and plugin signer

- [x] Add failing Python auth tests for boolean `lab`, missing-claim fail-closed
  behavior on lab routes, non-boolean rejection, and dual development flags.
- [x] Add failing plugin contract tests proving `lab` comes only from the
  authenticated user's admin role and reaches the signed payload/config.
- [x] Implement `Identity.lab`, verifier validation, plugin `hasRole('admin')`
  signing, and backward-compatible non-lab chat auth.
- [x] Run auth/plugin regression tests and commit
  `feat(simulation): authorize admin lab identities`.

## Task 2: Separate lab SQLite store and global run lease

- [ ] Add failing tests for WAL, foreign keys, busy timeout, schema version,
  create/get/complete, bounded sanitized JSON, ownership isolation, one global
  running row, cancellation/failure, and no chat-table coupling.
- [ ] Implement `chat_service/lab_store.py` with its own `AI_LAB_DATABASE`,
  transactions, stable conflict/not-found errors, and a partial unique index
  that permits only one globally running lab run.
- [ ] Run store tests and commit
  `feat(simulation): persist isolated lab runs`.

## Task 3: Fixed restricted-SSH transport

- [ ] Add failing tests for exact argv, `shell=False`, no remote command,
  `BatchMode`, `IdentitiesOnly`, strict host-key checking, one absolute key and
  known-hosts file, bounded stdin/stdout/line counts, timeout process-group
  termination, cancellation, manifest SHA, safe event/result parsing, and raw
  stderr/exception suppression.
- [ ] Implement `chat_service/lab_transport.py`. Validate configuration at the
  trust boundary; accept only typed manifest operations/controls; reject all
  unexpected runner JSON fields/events and nonterminal/multiple terminal output.
- [ ] Add deterministic `FakeLabTransport` for API tests without networking.
- [ ] Run transport tests and commit
  `feat(simulation): add restricted lab transport`.

## Task 4: Admin-only FastAPI lab router and SSE

- [ ] Add failing TestClient tests for `/v1/lab/scenarios`, `/status`, run POST,
  owned run GET, disabled/misconfigured/mismatch states, non-admin denial,
  unknown fields/scenarios/actions, one global active run, disconnect/cancel,
  heartbeat, exact event mapping/order, stable errors, and sanitized persistence.
- [ ] Implement `chat_service/lab_service.py` and mount its routes into the
  existing `create_app`. Load the same validated manifest used by the runner;
  return only `public_manifest` data and capability flags.
- [ ] Map EMR-59 events to the public `lab.*` contract and always emit exactly
  one `lab.run.completed` terminal event after success/failure.
- [ ] Expose EMR-61-owned `ai-check` and artifact paths only as explicit
  `501 feature_not_implemented` placeholders if route stability requires them;
  do not fabricate evidence or AI results.
- [ ] Run lab API plus all existing chat tests and commit
  `feat(simulation): expose admin lab API`.

## Task 5: Documentation, review, and regression gate

- [ ] Document nonsecret environment variables, fixed SSH prerequisites,
  disabled-by-default behavior, API schemas, ownership, cancellation, stable
  errors, and the EMR-61/62/63 boundaries.
- [ ] Security-review the complete EMR-60 diff. Critical/Important findings
  block push; confirm no key, known-host content, secret, personal path, SQLite
  state, SSH output, or generated artifact is tracked.
- [ ] Run Simulation, full Python/chat, frontend, plugin, shell syntax, compile,
  and `git diff --check` gates. Record any sandbox-only loopback limitation
  without misreporting it as a product failure or a pass.
- [ ] Commit docs and push `codex/librenms-ai-assistant`; leave the isolated
  worktree intact for EMR-61/62/63.

## Acceptance evidence

- Non-admin and disabled/misconfigured callers cannot enumerate or mutate Lab.
- Browser input cannot alter SSH/process/filesystem/SNMP control material.
- Local/deployed manifest drift fails before a mutation run is admitted.
- Concurrent admins cannot overlap shared-lab mutations.
- Fake-transport SSE proves real event mapping, failure, cancellation, ownership,
  and refresh behavior without touching UTM.
- Existing chat API/history/SSE and LibreNMS Assistant behavior remain green.
