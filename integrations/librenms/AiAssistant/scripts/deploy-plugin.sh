#!/usr/bin/env bash
set -euo pipefail

# Intended for an explicitly authorized LibreNMS guest. It does not edit any
# LibreNMS core source, package metadata, or Vite configuration.
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PLUGIN_SOURCE=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
LIBRENMS_ROOT=${1:-/opt/librenms}
PLUGIN_DESTINATION="$LIBRENMS_ROOT/app/Plugins/AiAssistant"

install -d -m 0755 "$PLUGIN_DESTINATION"
rsync -a \
  --exclude '.git/' \
  --exclude 'docs/' \
  --exclude 'nginx/' \
  --exclude 'scripts/' \
  --exclude 'tests/' \
  --exclude 'README.md' \
  --exclude 'deployment-manifest.json' \
  "$PLUGIN_SOURCE/" "$PLUGIN_DESTINATION/"

"$SCRIPT_DIR/package-assets.sh" "$LIBRENMS_ROOT"
