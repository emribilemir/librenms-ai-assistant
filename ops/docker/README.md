# Docker migration lab

This Compose stack replaces the manually managed Debian/UTM LibreNMS lab. It
keeps the migrated database in a Compose-managed volume, keeps the RRD history
and SNMPSim fixtures under `ops/docker/state/`, routes distributed poller writes
through RRDcached, and builds the AI Assistant plugin into a local LibreNMS
image.

The first migration remains intentionally two-phase: the LibreNMS stack runs
in Docker, while the existing AI backend continues to run on the Mac at port
8765. The `gateway` service proxies `/ai-api/` to that host service and all
other traffic to LibreNMS.

## Verified status

The stack was acceptance-tested on 17 September 2026 with OrbStack on Apple
Silicon. LibreNMS validation passed, the migrated database contained 11 devices,
15 ports, 1 user, and 133 alert rows, 346 RRD files were mounted, the synthetic
baseline settled at 8 devices up and 3 down, and the AI gateway health endpoint
returned HTTP 200. LibreNMS validation confirmed the active dispatcher and
RRDcached connection. The native AI Assistant page also restored the existing
chat history and completed a live Ollama-backed query through a signed LibreNMS
session in the Codex in-app browser. Historical availability graphs rendered
from the migrated RRD files.

This repository does not contain the tested database, RRD files, SNMPSim
recordings, credentials, or application key. Those files remain local under the
ignored `ops/docker/state/` and `ops/docker/.env` paths.

## Prerequisites

- Docker Engine with Compose v2, such as OrbStack or Docker Desktop
- A checksum-verified migration directory containing `SHA256SUMS`,
  `librenms.sql.gz`, and `librenms-files.tar.gz`
- The source LibreNMS `APP_KEY`
- A running host AI backend when the native Assistant is required

## Stage the verified backup

From the repository root:

```sh
./scripts/docker-migration-stage \
  /path/to/verified/LibreNMS-Migration-Backup \
  ops/docker/state
```

The staging command verifies `SHA256SUMS`, rejects unsafe archive members, and
copies only the SQL dump, RRD history, current SNMPSim lab, and legacy
configuration/plugin evidence needed for comparison. It refuses to overwrite
an existing state directory.

## Configure and start

```sh
cd ops/docker
cp .env.example .env
# Set PUID/PGID from `id -u` and `id -g`, replace MYSQL_PASSWORD, copy
# LIBRENMS_APP_KEY from the archived source `/opt/librenms/.env`, and set
# AI_BACKEND_HOST if the Mac backend is bound to a specific host address.
# RRDCACHED_PGID may use a non-conflicting numeric group inside the container;
# on macOS, matching PUID is sufficient for the owner-writable bind mounts.
chmod 600 .env
docker compose config
docker compose build
docker compose up -d
docker compose exec -T librenms lnms config:set distributed_poller true
docker compose logs -f
```

Open `http://localhost:8080` unless `LIBRENMS_HTTP_PORT` was changed.

The `distributed_poller` command is required after importing a native/UTM
database because that source does not contain the Docker dispatcher setting.
RRDcached keeps its database in the migrated `state/librenms/rrd` tree and its
journal in the ignored `state/rrdcached-journal` directory.

## Reconnect the host AI backend

The host backend must use the Docker gateway after the migration. Replace any
retired VM address in its private runtime environment with the published
LibreNMS API URL:

```sh
LIBRENMS_BASE_URL=http://127.0.0.1:8080/api/v0
```

For the repository's macOS launchd setup, this value lives in
`$AI_RUNTIME_ROOT/runtime.env` (or, when `AI_RUNTIME_ROOT` is unset,
`~/Library/Application Support/LibreNMSAiAssistant/runtime.env`). Restart the
service after changing it:

```sh
launchctl kickstart -k "gui/$(id -u)/com.emirbilici.librenms-ai-assistant"
```

Leaving `LIBRENMS_BASE_URL` pointed at the stopped UTM guest makes live device
and suggestion requests wait for network timeouts. Because the chat service
handles those requests alongside history loading, the Assistant can appear to
have an empty history until the timeouts finish even though its persistent
SQLite database is intact.

The SQL dump is imported only when the Compose-managed `db-data` volume is
empty. Do not remove that volume after the first successful start unless you
intend to perform a fresh database import. MariaDB uses a named volume because
its case-sensitive table mode is incompatible with a normal macOS bind mount.

## Repeatable checks

Run these commands from `ops/docker/` after startup:

```sh
docker compose ps
docker compose exec -T --user librenms librenms php validate.php
curl --fail http://localhost:8080/ai-api/healthz
```

The Compose contract and migration staging behavior are covered by the offline
Python suite. GitHub Actions also renders the Compose model with `.env.example`
on every push and pull request.

## Migration acceptance

Before retiring the UTM VM, verify all of the following in the Docker stack:

- 11 devices, 15 ports, 1 user, and 133 alert rows are present.
- Historical graphs render from the migrated RRD files.
- Eight baseline-up and three baseline-down SNMPSim devices retain their state.
- The AI Assistant plugin loads, signed identity works, and `/ai-api/v1`
  streaming reaches the Mac backend.
- LibreNMS validation passes inside the container.

Keep the UTM VM stopped but undeleted until this acceptance passes and a second
copy of the migration backup has been checksum-verified.

For the currently verified machine, the historical graph check and a second
checksum-verified migration backup were completed before retiring the UTM VM.
Containerizing the AI backend is optional and does not block retirement because
the backend and persistent chat database already run on the Mac.
