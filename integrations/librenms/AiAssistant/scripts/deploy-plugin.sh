#!/usr/bin/env bash
set -euo pipefail

# Intended only for an explicitly authorized guest. Stage/build everything
# before changing /opt/librenms, then retain a timestamped recoverable backup.
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PLUGIN_SOURCE=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
LIBRENMS_ROOT=${1:-/opt/librenms}

if [ "$LIBRENMS_ROOT" != "/opt/librenms" ] || [ ! -d "$LIBRENMS_ROOT" ]; then
    printf '%s\n' 'Refusing to deploy outside the existing /opt/librenms target.' >&2
    exit 64
fi

PLUGIN_DESTINATION="$LIBRENMS_ROOT/app/Plugins/AiAssistant"
ASSET_DESTINATION="$LIBRENMS_ROOT/html/plugins/ai-assistant"
TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
BACKUP_ROOT="$LIBRENMS_ROOT/.ai-assistant-backups/$TIMESTAMP"
STAGE_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/ai-assistant-stage.XXXXXX")
ROLLBACK_NEEDED=0

cleanup_stage() {
    rm -rf "$STAGE_ROOT"
}

restore_backup() {
    if [ "$ROLLBACK_NEEDED" -ne 1 ]; then
        return
    fi
    if [ -f "$BACKUP_ROOT/plugin-present" ]; then
        rsync -a --delete-delay "$BACKUP_ROOT/plugin/" "$PLUGIN_DESTINATION/"
    else
        rm -rf "$PLUGIN_DESTINATION"
    fi
    if [ -f "$BACKUP_ROOT/assets-present" ]; then
        rsync -a --delete-delay "$BACKUP_ROOT/assets/" "$ASSET_DESTINATION/"
    else
        rm -rf "$ASSET_DESTINATION"
    fi
}

on_failure() {
    restore_backup
    exit 1
}

trap cleanup_stage EXIT
trap on_failure ERR INT TERM

STAGED_PLUGIN="$STAGE_ROOT/plugin"
rsync -a \
  --exclude '.git/' \
  --exclude 'docs/' \
  --exclude 'nginx/' \
  --exclude 'scripts/' \
  --exclude 'tests/' \
  --exclude 'README.md' \
  --exclude 'deployment-manifest.json' \
  "$PLUGIN_SOURCE/" "$STAGED_PLUGIN/"
"$SCRIPT_DIR/package-assets.sh" "$STAGE_ROOT"

test -f "$STAGED_PLUGIN/Page.php"
test -f "$STAGED_PLUGIN/resources/views/page.blade.php"
test -f "$STAGE_ROOT/html/plugins/ai-assistant/ai-assistant.js"
test -f "$STAGE_ROOT/html/plugins/ai-assistant/ai-assistant.css"

install -d -m 0700 "$BACKUP_ROOT"
if [ -d "$PLUGIN_DESTINATION" ]; then
    rsync -a "$PLUGIN_DESTINATION/" "$BACKUP_ROOT/plugin/"
    : > "$BACKUP_ROOT/plugin-present"
fi
if [ -d "$ASSET_DESTINATION" ]; then
    rsync -a "$ASSET_DESTINATION/" "$BACKUP_ROOT/assets/"
    : > "$BACKUP_ROOT/assets-present"
fi

install -d -m 0755 "$PLUGIN_DESTINATION" "$ASSET_DESTINATION"
ROLLBACK_NEEDED=1
rsync -a --delete-delay "$STAGED_PLUGIN/" "$PLUGIN_DESTINATION/"
rsync -a --delete-delay "$STAGE_ROOT/html/plugins/ai-assistant/" "$ASSET_DESTINATION/"
ROLLBACK_NEEDED=0

printf 'Installed AI Assistant plugin. Recoverable backup: %s\n' "$BACKUP_ROOT"
