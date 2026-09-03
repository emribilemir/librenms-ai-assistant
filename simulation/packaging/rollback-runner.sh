#!/bin/bash
set -euo pipefail

[[ ${EUID} -eq 0 ]] || { echo "rollback-runner.sh must run as root" >&2; exit 2; }
INSTALL_ROOT=/opt/librenms-ai-lab
LAB_ROOT=/opt/snmpsim-lab
STATE_ROOT=/var/lib/librenms-ai-lab

/usr/bin/python3 -I "$INSTALL_ROOT/local-reset-entry.py"
/usr/bin/systemctl disable --now snmpsim-lab.service
/usr/sbin/runuser -u librenms -- /usr/bin/nohup "$LAB_ROOT/run-up-only.sh" >> "$STATE_ROOT/legacy-responder.log" 2>&1 &
echo "Managed service disabled; captured baseline restored; legacy run-up-only.sh started."
