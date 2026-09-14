# AI Assistant plugin deployment and rollback

This runbook is a command reference, not authorization to touch the UTM guest,
Nginx, or `/opt/librenms`. Execute it only after an operator approves the
named target and has a rollback window.

## Preconditions

1. Confirm the guest runs LibreNMS 26.8.1 and the core is clean. This is a
   core-clean deployment: it changes only
   `/opt/librenms/app/Plugins/AiAssistant/`,
   `/opt/librenms/html/plugins/ai-assistant/`, an opt-in Nginx location
   include, and timestamped backups under `/opt/librenms/.ai-assistant-backups/`.
   Never edit LibreNMS application source, package metadata, or Vite files.
2. Create an exact 32-character ASCII secret and keep it out of shell history,
   the repository, browser configuration, and logs:

   ```sh
   python3 -c 'import secrets; print(secrets.token_urlsafe(24))'
   ```

3. Save that exact value verbatim in the plugin setting and set the same exact
   value in the Mac service environment. The current backend reads raw bytes
   from `AI_ASSISTANT_SHARED_SECRET` and exposes the `create_app` factory:

   ```sh
   export AI_ASSISTANT_SHARED_SECRET='replace-with-exactly-32-ASCII-characters'
   cd /path/to/librenms-ai-assistant
   cp .env.example .env
   # Fill the placeholders, then use the reproducible launchd entrypoint:
   ./scripts/lab-up
   ```

   The launcher resolves the configured Python runtime and executes
   `uvicorn chat_service.app:create_app --factory`; bind host, port and state
   database come from `.env`.

   Before a live rollout, run `php -l` on the three deployed PHP hook files;
   PHP CLI was not available for the offline repository check.

   `AI_DEV_AUTH=1` is intentionally insufficient in the deployed app factory.
   The standalone frontend harness opts into development auth explicitly;
   production plugin requests must carry a valid signed identity. Demo mutation
   additionally requires the signed `demo_control` operator capability.

## Authorized installation sequence

The script builds and stages the frontend before it writes `/opt/librenms`.
It backs up existing plugin/assets to a timestamped directory, uses
`rsync --delete-delay` so stale files are removed after replacement files are
ready, and restores the backup if either deployment copy fails.

```sh
cd /path/to/librenms-ai-assistant
sudo integrations/librenms/AiAssistant/scripts/deploy-plugin.sh /opt/librenms
```

Record the printed backup path. Do not supply a different root: the script
accepts only an existing `/opt/librenms` target.

## Nginx server-context include

`nginx/ai-assistant.conf` contains a `location` block, which is valid only
inside a `server {}` block. It must **not** be copied directly to an ordinary
top-level `/etc/nginx/conf.d/*.conf` include, because those files are normally
read in the `http {}` context.

First inspect the live configuration and identify the `server {}` block that
serves LibreNMS:

```sh
sudo nginx -T
```

For the common Debian/Ubuntu LibreNMS layout, edit the active
`/etc/nginx/sites-available/librenms` (or its enabled symlink target) and add
this include *inside that existing `server {}` block*:

```nginx
include /opt/librenms/nginx/ai-assistant.location.conf;
```

Copy the repository fragment to that exact path, then test before reload:

```sh
sudo install -d -m 0755 /opt/librenms/nginx
sudo install -m 0644 integrations/librenms/AiAssistant/nginx/ai-assistant.conf \
  /opt/librenms/nginx/ai-assistant.location.conf
sudo nginx -t
sudo systemctl reload nginx
```

Do not reload if `nginx -t` fails. The trailing slash in `proxy_pass` maps
`/ai-api/v1/...` to upstream `/v1/...`; HTTP/1.1, disabled buffering/cache,
the 360-second read timeout, and `X-Accel-Buffering: no` preserve SSE.

Then enable **AiAssistant** under LibreNMS Plugins. A global-read user should
see its menu entry and `/plugin/AiAssistant` should mount the static client.

## Rollback

1. Disable **AiAssistant** in LibreNMS Plugins and stop the Mac API service.
2. Remove the server-block include line and
   `/opt/librenms/nginx/ai-assistant.location.conf`; run `sudo nginx -t` and
   reload only on success.
3. Use the recorded backup timestamp. If a component was present before
   installation, restore it with the narrow, exact destination commands:

   ```sh
   sudo rsync -a --delete-delay /opt/librenms/.ai-assistant-backups/<timestamp>/plugin/ \
     /opt/librenms/app/Plugins/AiAssistant/
   sudo rsync -a --delete-delay /opt/librenms/.ai-assistant-backups/<timestamp>/assets/ \
     /opt/librenms/html/plugins/ai-assistant/
   ```

   If `plugin-present` or `assets-present` is absent in that backup, the
   corresponding destination did not exist before deployment; remove only that
   exact destination after confirming the path and backup marker.

No rollback step edits LibreNMS core source, package files, or Vite setup.
