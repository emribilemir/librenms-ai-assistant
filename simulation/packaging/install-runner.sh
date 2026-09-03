#!/bin/bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "install-runner.sh must run as root" >&2
  exit 2
fi
if [[ $# -ne 1 ]]; then
  echo "usage: install-runner.sh /absolute/path/to/public-key.pub" >&2
  exit 2
fi

PUBLIC_KEY_FILE="$1"
INSTALL_ROOT=/opt/librenms-ai-lab
STATE_ROOT=/var/lib/librenms-ai-lab
LAB_ROOT=/opt/snmpsim-lab
SERVICE_FILE=/etc/systemd/system/snmpsim-lab.service
SUDOERS_FILE=/etc/sudoers.d/librenms-ai-lab
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
SOURCE_ROOT=$(cd -- "$SCRIPT_DIR/.." && pwd -P)
BACKUP_ROOT="$STATE_ROOT/install-backup"
SSH_ROOT="$STATE_ROOT/ssh"
AUTHORIZED_KEYS="$SSH_ROOT/.ssh/authorized_keys"

[[ "$PUBLIC_KEY_FILE" = /* && -f "$PUBLIC_KEY_FILE" && ! -L "$PUBLIC_KEY_FILE" ]] || {
  echo "public key must be one regular absolute-path file" >&2
  exit 2
}
IFS= read -r PUBLIC_KEY < "$PUBLIC_KEY_FILE" || true
[[ "$PUBLIC_KEY" == ssh-ed25519\ * && "$PUBLIC_KEY" != *$'\n'* && "$PUBLIC_KEY" != *$'\r'* ]] || {
  echo "only one ssh-ed25519 public key is accepted" >&2
  exit 2
}
[[ $(wc -l < "$PUBLIC_KEY_FILE") -eq 1 ]] || {
  echo "public key file must contain exactly one line" >&2
  exit 2
}

for required in "$LAB_ROOT/devices.txt" "$LAB_ROOT/devices-up.txt" "$SOURCE_ROOT/scenarios.json"; do
  [[ -f "$required" && ! -L "$required" ]] || {
    echo "required file unavailable" >&2
    exit 3
  }
done

getent group librenms-ai-lab >/dev/null || /usr/sbin/groupadd --system librenms-ai-lab
id -u librenms-ai-lab >/dev/null 2>&1 || /usr/sbin/useradd \
  --system --gid librenms-ai-lab --home-dir "$SSH_ROOT" --shell /bin/sh librenms-ai-lab

/usr/bin/install -d -o root -g root -m 0755 "$INSTALL_ROOT" "$STATE_ROOT"
/usr/bin/install -d -o root -g root -m 0700 "$BACKUP_ROOT"
/usr/bin/install -d -o librenms-ai-lab -g librenms-ai-lab -m 0700 "$SSH_ROOT" "$SSH_ROOT/.ssh"

STAMP=$(/usr/bin/date -u +%Y%m%dT%H%M%SZ)
for existing in "$SERVICE_FILE" "$SUDOERS_FILE" "$AUTHORIZED_KEYS"; do
  if [[ -e "$existing" && ! -L "$existing" ]]; then
    /usr/bin/cp -a -- "$existing" "$BACKUP_ROOT/$(basename -- "$existing").$STAMP.backup"
  fi
done

STAGE=$(/usr/bin/mktemp -d "$INSTALL_ROOT/.stage.XXXXXX")
cleanup_stage() {
  if [[ "$STAGE" == "$INSTALL_ROOT"/.stage.* && -d "$STAGE" ]]; then
    /usr/bin/rm -r -- "$STAGE"
  fi
}
trap cleanup_stage EXIT
/usr/bin/install -d -m 0755 "$STAGE/simulation/runner" "$STAGE/simulation/packaging" "$STAGE/simulation/systemd"
for module in __init__.py catalog.py manifest.py state.py scenarios.json; do
  /usr/bin/install -m 0644 "$SOURCE_ROOT/$module" "$STAGE/simulation/$module"
done
for module in __init__.py core.py errors.py forced_command.py local_admin.py processes.py protocol.py snmprec.py snmpsim_service.py storage.py; do
  /usr/bin/install -m 0644 "$SOURCE_ROOT/runner/$module" "$STAGE/simulation/runner/$module"
done
for asset in activate-runner.sh baseline-capture-entry.py install-runner.sh librenms-ai-lab.sudoers local-reset-entry.py local-status-entry.py rollback-runner.sh runner-entry.py snmpsim-service-entry.py verify-runner.sh; do
  /usr/bin/install -m 0644 "$SOURCE_ROOT/packaging/$asset" "$STAGE/simulation/packaging/$asset"
done
/usr/bin/install -m 0644 "$SOURCE_ROOT/systemd/snmpsim-lab.service" "$STAGE/simulation/systemd/snmpsim-lab.service"
/usr/bin/chown -R root:root "$STAGE"
/usr/bin/chmod 0755 "$STAGE/simulation/packaging/"*.sh
/usr/bin/python3 -m compileall -q "$STAGE/simulation"

if [[ -d "$INSTALL_ROOT/runner" && ! -L "$INSTALL_ROOT/runner" ]]; then
  /usr/bin/mv -- "$INSTALL_ROOT/runner" "$BACKUP_ROOT/runner.$STAMP.backup"
fi
/usr/bin/mv -- "$STAGE" "$INSTALL_ROOT/runner"
STAGE="$INSTALL_ROOT/.stage.complete"

/usr/bin/install -d -o root -g root -m 0755 "$INSTALL_ROOT/manifest"
/usr/bin/install -o root -g root -m 0644 "$INSTALL_ROOT/runner/simulation/scenarios.json" "$INSTALL_ROOT/manifest/scenarios.json"
RAW_MANIFEST_SHA=$(/usr/bin/sha256sum "$INSTALL_ROOT/manifest/scenarios.json" | /usr/bin/cut -d' ' -f1)
echo "$RAW_MANIFEST_SHA  $INSTALL_ROOT/manifest/scenarios.json" > "$INSTALL_ROOT/manifest/manifest.sha256"
/usr/bin/chown root:root "$INSTALL_ROOT/manifest/manifest.sha256"
/usr/bin/chmod 0644 "$INSTALL_ROOT/manifest/manifest.sha256"

for entry in runner-entry.py snmpsim-service-entry.py baseline-capture-entry.py local-status-entry.py local-reset-entry.py; do
  /usr/bin/install -o root -g root -m 0755 "$INSTALL_ROOT/runner/simulation/packaging/$entry" "$INSTALL_ROOT/$entry"
done
/usr/bin/install -o root -g root -m 0644 "$INSTALL_ROOT/runner/simulation/systemd/snmpsim-lab.service" "$SERVICE_FILE"
/usr/bin/install -o root -g root -m 0440 "$INSTALL_ROOT/runner/simulation/packaging/librenms-ai-lab.sudoers" "$SUDOERS_FILE"
printf 'restrict,command="/usr/bin/sudo -n /usr/bin/python3 -I /opt/librenms-ai-lab/runner-entry.py" %s\n' "$PUBLIC_KEY" > "$AUTHORIZED_KEYS"
/usr/bin/chown librenms-ai-lab:librenms-ai-lab "$AUTHORIZED_KEYS"
/usr/bin/chmod 0600 "$AUTHORIZED_KEYS"

/usr/sbin/visudo -cf "$SUDOERS_FILE"
/usr/sbin/sshd -t
/usr/bin/systemctl daemon-reload
/usr/bin/python3 -I "$INSTALL_ROOT/baseline-capture-entry.py"

echo "Runner staged and baseline captured. No process was stopped or started."
echo "Activate explicitly with: sudo $INSTALL_ROOT/runner/simulation/packaging/activate-runner.sh"
