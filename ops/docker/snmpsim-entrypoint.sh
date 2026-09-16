#!/usr/bin/env bash
set -euo pipefail

lab_root=/opt/snmpsim-lab
devices_up="$lab_root/devices-up.txt"
test -r "$devices_up"

mkdir -p /tmp/snmpsim-cache
command=(snmpsim-command-responder --cache-dir=/tmp/snmpsim-cache)

while IFS='|' read -r ip host _model; do
    [ -n "$ip" ] && [ -n "$host" ] || continue
    case "$ip" in
        127.0.0.*) ;;
        *) printf 'Refusing non-loopback SNMPSim endpoint: %s\n' "$ip" >&2; exit 64 ;;
    esac
    data_dir="$lab_root/data/$host"
    test -d "$data_dir"
    command+=(--v3-engine-id auto "--data-dir=$data_dir" "--agent-udpv4-endpoint=$ip:1611")
done < "$devices_up"

[ "${#command[@]}" -gt 2 ]
exec "${command[@]}"
