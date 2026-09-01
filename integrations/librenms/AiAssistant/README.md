# LibreNMS AI Assistant local plugin

This is a LibreNMS 26.8.1 local v2 plugin package. It is intentionally a
small presentation/authentication boundary: `Menu` and `Page` require
`global-read`; `Page` emits the frontend mount, the relative `/ai-api/v1`
configuration, and a short-lived HMAC identity. It contains no planner,
resolver, model, or LibreNMS-adapter orchestration.

LibreNMS discovers local PHP hooks by scanning
`app/Plugins/<PluginName>/*.php`. The package therefore has no invented core
manifest format: `deployment-manifest.json` records only this repository's
copy destinations and stable frontend asset names.

## Secret setting

An administrator opens **Plugins → AI Assistant settings** and saves a
base64-encoded value that decodes to exactly 32 bytes. Generate it with
`openssl rand -base64 32`. The settings view never renders the stored value;
the value must be entered again when rotating it. Configure the same value in
the Mac service as `AI_ASSISTANT_SHARED_SECRET_BASE64`.

The signed browser token is exactly
`v1.<base64url-json>.<base64url-hmac-sha256>`. Its signed JSON claims are
`sub`, `name`, `iss=librenms`, `aud=ai-assistant`, `iat`, and `exp=iat+3600`.
Only the token reaches JavaScript; the secret stays in the LibreNMS plugin
settings and the Mac service environment.

## Packaging and deployment

Read [deployment.md](docs/deployment.md) before executing either script.
`scripts/package-assets.sh` builds `chat-ui/dist` and copies only the Vite
entry CSS/JS to fixed `ai-assistant.css` and `ai-assistant.js` names. The
deployment script copies this local plugin to the documented plugin path and
then runs the asset package step. Neither script changes LibreNMS core source,
core `package.json`, or core Vite configuration.
