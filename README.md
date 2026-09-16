# LibreNMS AI Assistant — Natural-Language Hybrid PoC

[![CI](https://github.com/emribilemir/librenms-ai-assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/emribilemir/librenms-ai-assistant/actions/workflows/ci.yml)

A read-only proof of concept investigating whether LibreNMS data can be accessed
safely and verifiably through natural language.

The project tests the boundaries between natural-language planning with a local
Qwen model, deterministic device resolution, LibreNMS `/api/v0` queries, a
native LibreNMS plugin, and evidence-grounded answer generation. All access to
LibreNMS remains read-only.

## Current status

The repository is public and the complete offline test suite is reproducible
without LibreNMS, UTM, Docker, Ollama, or production credentials. An optional
Docker migration lab is also available for users who already have a verified
LibreNMS backup and want to replace the native Debian/UTM lab.

The Docker path was acceptance-tested on 17 September 2026 with OrbStack on
Apple Silicon:

| Check | Verified result |
|---|---|
| LibreNMS stack | LibreNMS, MariaDB, Redis, dispatcher, SNMPSim, and gateway running |
| Migrated state | 11 devices, 15 ports, 1 user, 133 alert rows, and 346 RRD files |
| Synthetic network baseline | 8 devices up and 3 intentionally down |
| LibreNMS validator | Database, schema, poller, dispatcher, Redis, and RRD checks pass |
| AI integration | Native plugin loads in a signed LibreNMS session and `/ai-api/healthz` returns `200` |
| Frontend dependency audit | 0 known npm vulnerabilities with Vite 8.3.0 |

Migration backups, database dumps, RRD data, SNMPSim runtime state, API tokens,
application keys, and local `.env` files are deliberately excluded from Git.
The checked-in Docker files are infrastructure and migration tooling only.

## Core approach

> Qwen structures the request; the resolver establishes identity; LibreNMS
> provides operational truth; Python validates critical decisions.

```text
User query
        |
        v
Qwen semantic planner
(route + intent + raw reference + structured filters)
        |
        v
Strict plan validation
        |
        v
Resolver v5
(unique / ambiguous / no_match)
        |
        v
Read-only LibreNMS backend
        |
        +--> Direct read: deterministic answer
        |
        +--> Investigation: typed findings -> Qwen claims -> validation/judge
                                               |
                                               +--> safe fallback
```

### Responsibility boundaries

| Layer | Responsibility | What it does not do |
|---|---|---|
| Qwen planner | Convert natural language into a verifiable structured plan | Select a device or claim operational state without backend evidence |
| Plan validator | Check schema, types, route–intent alignment, and field consistency | Reinterpret the user's sentence with regex rules |
| Resolver v5 | Resolve hostnames, SKUs, models, and catalog filters | Pick a random device when a match is ambiguous |
| LibreNMS backend | Provide device, port, alert, and event facts | Call write endpoints or guess data |
| Grounding layer | Package findings with stable references and validate claims | Invent a root cause that is absent from the evidence |

## Native Assistant UI

The PoC is more than a CLI. The chat experience under
[`chat-ui/`](chat-ui/), built with React 19, Vite 8, and
[assistant-ui](https://www.assistant-ui.com/) primitives, is embedded in
LibreNMS's own session and page shell through
[`integrations/librenms/AiAssistant/`](integrations/librenms/AiAssistant/).

The main features currently available in the interface are:

- A native plugin page opened with signed user identity from the LibreNMS session
- Persistent chat history, search, new-chat creation, and a safe deletion flow
- Streaming responses, cancel/retry controls, and a sequential message queue
  within each conversation
- A device picker backed by live inventory and query-ready starter suggestions
- Readable tables for device and port results, plus summary cards for alerts
- A compact timeline for event queries that separates timestamps, severity,
  messages, and `up -> down` transitions
- Verified LibreNMS deep links for `device`, `port`, `alerts`, and `events`
- Processing status for planner, resolver, tool, and finding stages during an
  investigation, plus a detailed inspector in Demo Mode
- A right-side Demo Controls drawer using the backend manifest's 11 targets and
  target-specific support matrix, with direct actions, reset, and the
  **Bu durumu AI'a sor** (“Ask AI about this state”) CTA
- Keyboard focus handling, accessible names, empty and single-event states, and
  safe error states

```text
LibreNMS plugin page
        |
        v
React + assistant-ui ExternalStoreRuntime
        |
        v
Signed /v1 chat API + SSE
        |
        v
Hybrid planner / resolver / read-only LibreNMS backend
```

Normal chat and LibreNMS reads are read-only. Demo Controls that modify lab
fixtures additionally require `AI_DEMO_MODE_ALLOWED=1` and a signed
`demo_control` capability. Setting only `AI_DEV_AUTH=1` does not grant this
permission in the deployed application.

## Supported query scope

- Live status for a single device or a set of devices
- Device model, hostname, uptime, location, and operating system
- Port administrative/operational state, speed, and description
- A specific port or structured port filters
- Active alert and event lists
- Latest state change and time-windowed event queries
- Current or historical investigations over a fixed evidence set
- Device-set resolution with catalog filters such as brand, family, port count,
  and PoE capability

Example Turkish queries:

```text
lab-j9772a-01 açık mı?
lab-j9772a-01'in modeli ne?
lab-j9772a-01 ne kadar süredir açık?
lab-j9772a-01 port 2'nin hızı ne?
lab-j9772a-01'in down portları hangileri?
lab-j9772a-01 son 30 dakikada status değiştirdi mi?
lab-j9772a-01'de ne sorun var?
```

## Repository structure

| Path | Contents |
|---|---|
| [`chat-ui/`](chat-ui/) | React + assistant-ui native chat, structured results, and demo interface |
| [`integrations/librenms/AiAssistant/`](integrations/librenms/AiAssistant/) | LibreNMS plugin page, signed identity bridge, and deployment contract |
| [`librenms-hybrid-poc/`](librenms-hybrid-poc/) | Current planner, orchestration, and backend adapter entry points |
| [`librenms-hybrid-poc/tests/`](librenms-hybrid-poc/tests/) | Offline hybrid, chat, security, and operations regression suite |
| [`librenms-hybrid-poc/fixtures/`](librenms-hybrid-poc/fixtures/) | PoC inventory, prompt, and acceptance inputs |
| [`librenms-hybrid-poc/hybrid-gold-v3/`](librenms-hybrid-poc/hybrid-gold-v3/) | Frozen Gold/Generated evaluation assets and compatibility entry points |
| [`simulation/`](simulation/) | Allowlisted, target-selectable demo scenarios |
| [`scripts/`](scripts/) | Single-command lab startup, health, and shutdown entry points |
| [`ops/docker/`](ops/docker/) | Docker Compose migration stack, image builds, and UTM backup staging guide |
| [`ops/systemd/`](ops/systemd/) | Unprivileged, boot-persistent SNMPSim service inside the guest |
| [`docs/history/`](docs/history/) | Historical review and remediation reports |
| [`docs/INSTALLATION.md`](docs/INSTALLATION.md) | Optional Debian, SSH, sudo, and SNMPSim installation guide |
| [`docs/lab/`](docs/lab/) | Detailed historical LibreNMS and SNMPSim lab notes |

### Important files

- [`hybrid_poc.py`](librenms-hybrid-poc/hybrid_poc.py): planner, resolver,
  backend, and synthesis orchestration
- [`live_query.py`](librenms-hybrid-poc/live_query.py): command-line entry point
  for the real LibreNMS API
- [`planner_v2.py`](librenms-hybrid-poc/planner_v2.py): structured plan schema,
  normalization, and strict validation
- [`librenms_backend.py`](librenms-hybrid-poc/librenms_backend.py): read-only
  LibreNMS `/api/v0` adapter
- [`investigation_grounding.py`](librenms-hybrid-poc/investigation_grounding.py):
  typed findings, claim validation, judge, and safe-fallback contracts
- [`utility_facts.py`](librenms-hybrid-poc/utility_facts.py): deterministic
  device, port, and event fact selectors
- [`resolver_v5.py`](librenms-hybrid-poc/resolver_v5.py): active structured
  catalog filtering and identity resolution
- [`catalog_ingest.py`](librenms-hybrid-poc/catalog_ingest.py): active catalog
  ingestion and identity-index helper
- [`emr52_acceptance_queries.json`](librenms-hybrid-poc/fixtures/emr52_acceptance_queries.json):
  current live acceptance queries

## Quick start

Install the chat service's test dependencies, then run the offline suite:

```bash
git clone https://github.com/emribilemir/librenms-ai-assistant.git
cd librenms-ai-assistant
python3 -m venv .venv
.venv/bin/python -m pip install -r librenms-hybrid-poc/requirements-chat-service.txt
.venv/bin/python -m unittest discover -s librenms-hybrid-poc -p 'test_*.py' -v
```

The offline suite does not require an external LibreNMS or Ollama connection.
Backend adapter tests use only an in-process localhost test server.

To test and build the Assistant UI for production:

```bash
cd chat-ui
npm ci
npm test -- --runInBand
npm run build
```

Build output is generated under `chat-ui/dist/` and deployed to the static
assets loaded by the native plugin. See
[`integrations/librenms/AiAssistant/docs/deployment.md`](integrations/librenms/AiAssistant/docs/deployment.md)
for detailed plugin deployment steps.

## Optional end-to-end lab setup

The offline tests do not require Debian, UTM, macOS, LibreNMS, or SNMPSim.
Anyone who wants to exercise the real LibreNMS discovery/poller/API chain
without physical devices can set up the optional lab environment:

```text
SNMPSim -> LibreNMS discovery/poller -> LibreNMS API -> Hybrid PoC
```

- [Installation guide](docs/INSTALLATION.md): Debian/Linux preparation, SSH,
  sudo, firewall, native service checks, and SNMPSim installation
- [Detailed lab journal](docs/lab/librenms_native_lab_kurulum_ve_snmpsim_notlari_v2.md):
  historical steps and issues from the verified UTM + Debian 13 ARM64 setup

macOS/UTM is only the verified reference environment; it is not required. An
equivalent Linux server or VM and any SSH client can be used.

For migration away from the native UTM guest, use the checksum-verifying
staging command and Compose runbook in
[`ops/docker/README.md`](ops/docker/README.md). The Docker stack preserves the
MariaDB import, RRD history, and loopback-addressed SNMPSim lab while keeping
runtime data and credentials outside Git.

The current migration is intentionally two-phase: LibreNMS and its supporting
services run in containers, while the Python AI backend continues to run on the
host and is reached through the gateway. Containerizing that backend is a
future portability improvement, not a blocker for the verified local stack.

Lab configuration is machine-specific and is not committed to the repository.
First copy `.env.example` to `.env` and fill in the SSH, LibreNMS, and backend
fields. Then use the canonical lifecycle:

```bash
./scripts/lab-up
./scripts/lab-status
./scripts/lab-down
```

`lab-up` coordinates optional UTM startup, bounded SSH waiting, LibreNMS
services, boot-persistent SNMPSim, and the launchd backend installation.
`lab-status` verifies the services, the single unprivileged responder process,
the 8-up/3-down baseline inventory, LibreNMS API/web access, and the backend
health endpoint. SQLite runtime data is stored in the user's state directory by
default. Demo mutation endpoints are available only to an operator identity
with a signed `demo_control` capability; normal chat access for global-read
users remains unchanged.

### Short demo flow

1. Run `./scripts/lab-status` to show the services and the 8-up/3-down baseline.
2. Run a model or status query on the **AI Assistant** page in LibreNMS.
3. Open the structured results for down-port, active-alert, and latest-event
   queries.
4. Run an investigation and show the processing stages and verified deep links.
5. In authorized Demo Mode, select another target, run a supported action, use
   **Bu durumu AI'a sor** (“Ask AI about this state”), and return that target to
   its own baseline with **Laboratuvarı sıfırla** (“Reset lab”).

## PoC harness with local Ollama

If a compatible model is running locally at `http://localhost:11434`:

```bash
python3 librenms-hybrid-poc/hybrid_poc.py \
  --model librenms-qwen \
  --cases librenms-hybrid-poc/fixtures/t46_v2_cases.json \
  --temps 0.0 \
  --out /tmp/librenms-hybrid-results.json
```

## Live queries against the real LibreNMS API

For read-only use, provide a legacy `/api/v0` token through the environment.
Never write a real token to the repository or shell history.

```bash
export LIBRENMS_TOKEN="<read-only-token>"
export LIBRENMS_BASE_URL="http://<librenms-host>/api/v0"

python3 librenms-hybrid-poc/live_query.py "lab-j9775a-01 açık mı?"
python3 librenms-hybrid-poc/live_query.py "lab-j9772a-01 port 2 ne durumda?"
python3 librenms-hybrid-poc/live_query.py "lab-j9772a-01'de ne sorun var?"
```

`live_query.py` uses the Gold planner contract, runtime `resolver_v5`, and the
real `LibreNMSBackend` adapter. The real LibreNMS `device_id` returned by the
first device query is passed to subsequent port, alert, and event calls; fixture
identity is never treated as backend truth.

## Security and correctness rules

- The backend is restricted to read-only endpoints.
- The token is read from the environment and never written to sanitized traces.
- Atomic state and utility-fact answers are not reinterpreted by the LLM.
- Ambiguous references produce a clarification; no random device is selected.
- Values are never guessed when there is no match or backend data.
- Device-set status answers make a separate live backend call for each hostname.
- Investigations use only the retrieved `device + ports + alerts + events`
  evidence.
- If mechanical or semantic validation fails, the generated answer is discarded
  and a deterministic fallback is used.
- Invalid planner output never reaches the resolver or backend.

The source spreadsheet provides only brand and model information. The
`lab-<sku>-NN` hostnames, device IDs, and operational states are synthetic
fixtures and must not be interpreted as real ISBAK operational data.

## Verification

On every push and pull request, CI runs the complete offline Python suite,
frontend unit tests, the production build, LibreNMS plugin contract tests,
Docker Compose configuration validation, and a narrow secret-pattern check.
Live LibreNMS acceptance is performed only through the Codex in-app browser.

The current verified scope consists of **213 Python tests**, **103 Assistant UI
tests**, **9 LibreNMS plugin contract tests**, a valid Docker Compose model, and
a successful Vite production build. Live acceptance verified the native plugin,
AI backend health path, migrated LibreNMS state, and the 8-up/3-down lab
baseline.

Live Ollama/LibreNMS acceptance runs are not part of the offline suite because
they require a model, a token, and an accessible lab environment.

## Local experiment outputs

Harness results, logs, comparison reports, and external-judge exports are
reproducible runtime outputs and are not tracked by Git. By default, PoC results
are written to the operating system's temporary directory. When persistent
experiment evidence is required, it should be stored as a separate release
artifact with model, runtime, and commit information.

## Known limitations

- The project does not include production deployment, write operations, or
  authorization management.
- The Docker migration currently keeps the Python AI backend on the host; the
  LibreNMS, database, Redis, dispatcher, SNMPSim, and gateway services are
  containerized.
- The Docker lab requires a user-provided, checksum-verified migration backup;
  no database, RRD, device recording, credential, or application-key material
  is distributed in this repository.
- RAG has not been implemented; it remains a possible fallback for catalog and
  documentation context.
- The generator and judge use the same Qwen model in separate calls, so the
  judge is not an independent source of truth.
- Investigation quality is limited by the data and event-window coverage
  provided by the backend.
- When no root cause is supported by evidence, the result remains bounded at
  `root_cause unknown`.

## Next direction

The next portability step is to containerize the Python AI backend, add an
explicit container health check, and remove the remaining host-network
dependency. After that, release builds can pin tested image digests and measure
latency across the planner, backend, and two-stage investigation chain.

## Design documents

- [Planner/catalog/resolver ownership review](docs/history/LIBRENMS_PLANNER_CATALOG_RESOLVER_OWNERSHIP_REVIEW.md)
- [Planner v2 remediation report](docs/history/PLANNER_V2_FIX_REPORT.md)

## UI foundation

The chat surface is built on
[assistant-ui](https://www.assistant-ui.com/) primitives. LibreNMS-specific data
safety, visual language, and controls are implemented in this repository.
