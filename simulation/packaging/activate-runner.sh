#!/bin/bash
set -euo pipefail

[[ ${EUID} -eq 0 ]] || { echo "activate-runner.sh must run as root" >&2; exit 2; }
INSTALL_ROOT=/opt/librenms-ai-lab
LAB_ROOT=/opt/snmpsim-lab
STATE_ROOT=/var/lib/librenms-ai-lab
LEGACY_LOG="$STATE_ROOT/legacy-responder.log"
LEGACY_LAUNCHER=/opt/snmpsim-lab/run-up-only.sh

is_responder_command() {
  local command_file="$1"
  local -a process_argv=()
  mapfile -d '' -t process_argv < "$command_file" || true
  [[ ${#process_argv[@]} -ge 1 ]] || return 1
  [[ "${process_argv[0]}" == /opt/snmpsim-venv/bin/snmpsim-command-responder ]] && return 0
  [[ ${#process_argv[@]} -ge 2 && "${process_argv[1]}" == /opt/snmpsim-venv/bin/snmpsim-command-responder ]]
}

legacy_running() {
  local command_file
  for command_file in /proc/[0-9]*/cmdline; do
    [[ -r "$command_file" ]] || continue
    if is_responder_command "$command_file"; then
      return 0
    fi
  done
  return 1
}

start_legacy() {
  if ! legacy_running; then
    /usr/sbin/runuser -u librenms -- /usr/bin/nohup "$LEGACY_LAUNCHER" >> "$LEGACY_LOG" 2>&1 &
  fi
}

rollback_legacy() {
  /usr/bin/systemctl disable --now snmpsim-lab.service >/dev/null 2>&1 || true
  start_legacy
}

stop_legacy() {
  local command_file pid owner attempt
  local -a responder_pids=()
  for command_file in /proc/[0-9]*/cmdline; do
    [[ -r "$command_file" ]] || continue
    if is_responder_command "$command_file"; then
      pid=${command_file#/proc/}
      pid=${pid%/cmdline}
      owner=$(/usr/bin/stat -c %U "/proc/$pid")
      [[ "$owner" == librenms ]] || { echo "unexpected responder owner" >&2; exit 3; }
      responder_pids+=("$pid")
      /bin/kill -TERM "$pid"
    fi
  done
  for attempt in {1..20}; do
    local any_running=false
    for pid in "${responder_pids[@]}"; do
      [[ -d "/proc/$pid" ]] && any_running=true
    done
    [[ "$any_running" == false ]] && return 0
    /bin/sleep 0.25
  done
  for pid in "${responder_pids[@]}"; do
    [[ -d "/proc/$pid" ]] && /bin/kill -KILL "$pid"
  done
}

[[ -x "$INSTALL_ROOT/runner-entry.py" && -x "$LEGACY_LAUNCHER" ]] || {
  echo "runner or legacy launcher missing" >&2
  exit 3
}
trap rollback_legacy ERR
stop_legacy
/usr/bin/systemctl enable --now snmpsim-lab.service
"$INSTALL_ROOT/runner/simulation/packaging/verify-runner.sh"
trap - ERR
echo "snmpsim-lab.service activated"
