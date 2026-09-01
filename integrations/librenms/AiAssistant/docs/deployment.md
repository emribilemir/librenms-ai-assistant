# AI Assistant plugin deployment and rollback

This runbook is deliberately a command reference, not authorization to touch
the UTM guest, Nginx, or `/opt/librenms`. Execute it only after an operator
approves the named target and has a rollback window.

## Preconditions

1. Confirm the guest runs LibreNMS 26.8.1 and has no local core changes that
   this integration would overwrite. The strategy is core-clean: deploy only
   `/opt/librenms/app/Plugins/AiAssistant/`,
   `/opt/librenms/html/plugins/ai-assistant/`, and one Nginx include; do not
   alter LibreNMS application source, package metadata, or Vite files.
2. Generate one secret locally: `openssl rand -base64 32`. Keep it out of the
   repository, shell history, browser configuration, and logs.
3. On the Mac host, configure the service environment with the generated value
   as `AI_ASSISTANT_SHARED_SECRET_BASE64`, then start it bound specifically to
   `192.168.64.1:8765` (not a public interface):

   ```sh
   export AI_ASSISTANT_SHARED_SECRET_BASE64='replace-with-32-byte-base64-secret'
   cd /path/to/isbaklibrenms/librenms-hybrid-poc
   uvicorn chat_service.app:app --host 192.168.64.1 --port 8765
   ```

## Authorized installation sequence

Run the version-controlled script on the approved guest checkout only after
reviewing its source and preserving the previous plugin/asset directories:

```sh
cd /path/to/isbaklibrenms
sudo integrations/librenms/AiAssistant/scripts/deploy-plugin.sh /opt/librenms
```

Install the proxy snippet into the *active LibreNMS server block's include
location*. The exact include path is distribution-specific; inspect the active
Nginx configuration first and then copy the file, for example:

```sh
sudo install -m 0644 integrations/librenms/AiAssistant/nginx/ai-assistant.conf \
  /etc/nginx/conf.d/ai-assistant.conf
sudo nginx -t
sudo systemctl reload nginx
```

Do not reload if `nginx -t` fails. The include forwards `/ai-api/v1/...` to
the Mac service as `/v1/...`, uses HTTP/1.1, disables proxy buffering/cache,
sets the 360-second read timeout, and sends SSE-safe `X-Accel-Buffering: no`.

In LibreNMS, enable **AiAssistant** under Plugins. Then open its plugin
settings as an administrator and save the same base64 secret from the Mac
environment. A global-read user should then see **AI Assistant** in the plugin
menu and `/plugin/AiAssistant` should render the static client.

## Rollback

1. Disable **AiAssistant** in LibreNMS Plugins.
2. Remove only the installed proxy include, then run `sudo nginx -t`; reload
   Nginx only after that succeeds.
3. Stop the Mac API service.
4. Restore or remove only
   `/opt/librenms/app/Plugins/AiAssistant/` and
   `/opt/librenms/html/plugins/ai-assistant/` from the backup made before
   installation.

No rollback step edits LibreNMS core source, its package files, or Vite setup.
