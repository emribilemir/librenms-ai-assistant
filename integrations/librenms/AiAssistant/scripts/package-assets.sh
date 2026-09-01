#!/usr/bin/env bash
set -euo pipefail

# Build the reusable chat-ui bundle, then normalize Vite's hashed entry names
# to the two stable filenames referenced by the native LibreNMS plugin view.
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PLUGIN_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
REPOSITORY_ROOT=$(CDPATH= cd -- "$PLUGIN_DIR/../../.." && pwd)
LIBRENMS_ROOT=${1:-/opt/librenms}
CHAT_UI_DIR="$REPOSITORY_ROOT/chat-ui"
ASSET_DESTINATION="$LIBRENMS_ROOT/html/plugins/ai-assistant"

cd "$CHAT_UI_DIR"
npm run build

js_entry=$(find dist/assets -maxdepth 1 -type f -name 'index-*.js' -print -quit)
css_entry=$(find dist/assets -maxdepth 1 -type f -name 'index-*.css' -print -quit)

test -n "$js_entry"
test -n "$css_entry"

install -d -m 0755 "$ASSET_DESTINATION"
install -m 0644 "$js_entry" "$ASSET_DESTINATION/ai-assistant.js"
install -m 0644 "$css_entry" "$ASSET_DESTINATION/ai-assistant.css"
