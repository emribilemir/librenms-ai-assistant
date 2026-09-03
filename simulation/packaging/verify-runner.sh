#!/bin/bash
set -euo pipefail

[[ ${EUID} -eq 0 ]] || { echo "verify-runner.sh must run as root" >&2; exit 2; }
INSTALL_ROOT=/opt/librenms-ai-lab
STATE_ROOT=/var/lib/librenms-ai-lab
SERVICE_FILE=/etc/systemd/system/snmpsim-lab.service
SUDOERS_FILE=/etc/sudoers.d/librenms-ai-lab

/usr/bin/sha256sum -c "$INSTALL_ROOT/manifest/manifest.sha256"
/usr/sbin/visudo -cf "$SUDOERS_FILE"
/usr/sbin/sshd -t
/usr/bin/systemd-analyze verify "$SERVICE_FILE"
/usr/bin/systemctl is-active --quiet snmpsim-lab.service
[[ $(/usr/bin/stat -c '%U:%G:%a' "$SUDOERS_FILE") == root:root:440 ]]
[[ $(/usr/bin/stat -c '%U:%G:%a' "$STATE_ROOT/state.json") == root:root:600 ]]
STATUS_OUTPUT=$(/usr/bin/python3 -I "$INSTALL_ROOT/local-status-entry.py")
if [[ "$STATUS_OUTPUT" == *'"phase":"manual_recovery_required"'* ]]; then
  echo "manual_recovery_required" >&2
  exit 4
fi
echo "$STATUS_OUTPUT"
