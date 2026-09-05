#!/usr/bin/env python3
"""Minimal live scenario runner for the existing EMR-55 UTM lab."""

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POC_DIR = ROOT / "librenms-hybrid-poc"
sys.path.insert(0, str(POC_DIR))

from librenms_backend import LibreNMSBackend  # noqa: E402


SSH_HOST = "emir@192.168.64.3"
SSH_KEY = Path.home() / ".ssh" / "codex_utm"
DEVICE_ID = 1
HOSTNAME = "lab-j9772a-01"
FIXTURE = "/opt/snmpsim-lab/data/lab-j9772a-01/public.snmprec"
OFFLINE_FIXTURE = "/opt/snmpsim-lab/data/lab-j9772a-01/offline.snmprec"
RESPONDER = "/opt/snmpsim-venv/bin/snmpsim-command-responder"
RESPONDER_PATTERN = (
    "^/opt/snmpsim-venv/bin/python3 "
    "/opt/snmpsim-venv/bin/snmpsim-command-responder"
)
DEVICES_UP = "/opt/snmpsim-lab/devices-up.txt"
SNMP_ENDPOINT = "udp:127.0.0.11:1611"
LOCATION_OID = "1.3.6.1.2.1.1.6.0"
PORT2_ADMIN_OID = "1.3.6.1.2.1.2.2.1.7.2"
PORT2_OPER_OID = "1.3.6.1.2.1.2.2.1.8.2"
BASELINE_LOCATION = "Test Lab"
DEMO_LOCATION = "EMR-55 Demo Lab"


def ssh(command, *, input_text=None, check=True, timeout=180):
    result = subprocess.run(
        [
            "ssh",
            "-i",
            os.fspath(SSH_KEY),
            "-o",
            "BatchMode=yes",
            SSH_HOST,
            command,
        ],
        input=input_text,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"UTM command failed ({result.returncode}): {detail}")
    return result


def replace_record(text, oid, value_type, value):
    prefix = f"{oid}|{value_type}|"
    lines = text.splitlines(keepends=True)
    matches = [index for index, line in enumerate(lines) if line.startswith(prefix)]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one record for {oid}, found {len(matches)}")
    index = matches[0]
    newline = "\n" if lines[index].endswith("\n") else ""
    lines[index] = f"{prefix}{value}{newline}"
    return "".join(lines)


def read_fixture():
    return ssh(f"cat {shlex.quote(FIXTURE)}").stdout


def write_fixture(text):
    temporary = FIXTURE + ".emr55-tmp"
    command = (
        "set -eu; "
        f"tmp={shlex.quote(temporary)}; "
        "trap 'rm -f \"$tmp\"' EXIT; "
        "cat >\"$tmp\"; "
        f"mv \"$tmp\" {shlex.quote(FIXTURE)}; "
        "trap - EXIT"
    )
    ssh(command, input_text=text)


def set_record(oid, value_type, value):
    before = read_fixture()
    after = replace_record(before, oid, value_type, value)
    if after != before:
        write_fixture(after)
        return True
    return False


def single_responder_pid(output):
    values = [line.strip() for line in output.splitlines() if line.strip()]
    if len(values) != 1 or not values[0].isdigit():
        raise RuntimeError(f"expected exactly one responder PID, found {values}")
    return int(values[0])


def responder_pid(*, required=True):
    result = ssh(
        "pgrep -u librenms -f " + shlex.quote(RESPONDER_PATTERN), check=False
    )
    if result.returncode == 1 and not result.stdout.strip():
        if required:
            raise RuntimeError("expected exactly one responder PID, found none")
        return None
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return single_responder_pid(result.stdout)


def stop_responder():
    pid = responder_pid()
    ssh(f"sudo -n -u librenms kill {pid}")
    for _ in range(30):
        if responder_pid(required=False) is None:
            return pid
        time.sleep(0.2)
    raise RuntimeError(f"responder PID {pid} did not stop")


def start_responder(*, target_online):
    if responder_pid(required=False) is not None:
        raise RuntimeError("refusing to start a second responder")
    start_script = f"""
cmd=({shlex.quote(RESPONDER)} --cache-dir=/opt/snmpsim-lab/cache)
while IFS='|' read -r ip host model; do
  cmd+=(--v3-engine-id auto "--data-dir=/opt/snmpsim-lab/data/$host" "--agent-udpv4-endpoint=$ip:1611")
done < {shlex.quote(DEVICES_UP)}
nohup "${{cmd[@]}}" >/tmp/emr55-snmpsim.log 2>&1 &
""".strip()
    ssh("sudo -n -u librenms bash -c " + shlex.quote(start_script))
    for _ in range(30):
        pid = responder_pid(required=False)
        if pid is not None:
            break
        time.sleep(0.2)
    else:
        log = ssh("tail -n 50 /tmp/emr55-snmpsim.log", check=False).stdout
        raise RuntimeError(f"responder did not start: {log.strip()}")

    if target_online:
        for _ in range(10):
            if snmp_available():
                return pid
            time.sleep(0.5)
        raise RuntimeError("responder started but target SNMP endpoint is unavailable")
    return pid


def restart_responder(*, target_online):
    stop_responder()
    return start_responder(target_online=target_online)


def snmp_available():
    command = (
        "snmpget -v2c -c public -t 1 -r 0 -On "
        f"{shlex.quote(SNMP_ENDPOINT)} 1.3.6.1.2.1.1.5.0"
    )
    return ssh(command, check=False, timeout=10).returncode == 0


def poll_device(*, expect_down=False):
    result = ssh(
        "cd /opt/librenms && "
        f"sudo -n -u librenms ./poller.php -h {shlex.quote(HOSTNAME)}",
        check=False,
        timeout=180,
    )
    accepted = {0, 6} if expect_down else {0}
    if result.returncode not in accepted:
        detail = (result.stderr or result.stdout)[-2000:].strip()
        raise RuntimeError(f"LibreNMS poller failed ({result.returncode}): {detail}")
    return True


def discover_device():
    ssh(
        "cd /opt/librenms && "
        f"sudo -n -u librenms ./discovery.php -h {shlex.quote(HOSTNAME)}",
        timeout=180,
    )
    return True


def api_backend():
    return LibreNMSBackend(event_limit=100)


def current_port2(backend):
    ports = backend.get_ports(device_id=DEVICE_ID)
    return next((port for port in ports if int(port.get("ifIndex")) == 2), None)


def current_events(backend):
    return list(backend.get_events(device_id=DEVICE_ID))


def newest_event_id(events):
    return max((int(event.get("event_id") or 0) for event in events), default=0)


def find_new_event(
    events, *, after_id, event_type, reference, message_fragment
):
    matches = []
    for event in events:
        event_id = int(event.get("event_id") or 0)
        if event_id <= after_id or event.get("type") != event_type:
            continue
        if reference is not None and str(event.get("reference")) != str(reference):
            continue
        if message_fragment not in (event.get("message") or ""):
            continue
        matches.append(event)
    return max(matches, key=lambda event: int(event["event_id"]), default=None)


def require_port(backend, *, oper_status):
    port = current_port2(backend)
    if not port:
        raise RuntimeError("LibreNMS API did not return port 2")
    if port.get("ifAdminStatus") != "up" or port.get("ifOperStatus") != oper_status:
        raise RuntimeError(f"unexpected LibreNMS port 2 state: {port}")
    return port


def require_device_status(backend, status):
    device = backend.get_device(device_id=DEVICE_ID)
    if not device or device.get("status") != status:
        raise RuntimeError(f"unexpected LibreNMS device state: {device}")
    return device


def fixture_state():
    result = ssh(
        f"if [ -f {shlex.quote(FIXTURE)} ] && [ ! -e {shlex.quote(OFFLINE_FIXTURE)} ]; then echo online; "
        f"elif [ -f {shlex.quote(OFFLINE_FIXTURE)} ] && [ ! -e {shlex.quote(FIXTURE)} ]; then echo offline; "
        "else echo invalid; fi"
    )
    return result.stdout.strip()


def take_device_offline():
    if fixture_state() != "online":
        raise RuntimeError("target fixture is not in the online state")
    ssh(f"mv {shlex.quote(FIXTURE)} {shlex.quote(OFFLINE_FIXTURE)}")


def restore_online_fixture():
    state = fixture_state()
    if state == "online":
        return False
    if state != "offline":
        raise RuntimeError("target fixture state is ambiguous")
    ssh(f"mv {shlex.quote(OFFLINE_FIXTURE)} {shlex.quote(FIXTURE)}")
    return True


def set_baseline_records():
    changed = False
    changed |= set_record(LOCATION_OID, "4", BASELINE_LOCATION)
    changed |= set_record(PORT2_ADMIN_OID, "2", "1")
    changed |= set_record(PORT2_OPER_OID, "2", "2")
    return changed


def preflight():
    if not SSH_KEY.is_file():
        raise RuntimeError(f"SSH key not found: {SSH_KEY}")
    ssh(
        "set -eu; "
        "sudo -n -u librenms true; "
        f"test -x {shlex.quote(RESPONDER)}; "
        f"test -r {shlex.quote(DEVICES_UP)}"
    )
    if fixture_state() == "online":
        ssh(f"test -w {shlex.quote(FIXTURE)}")
    api_backend().get_device(device_id=DEVICE_ID)


def event_line(event):
    return (
        f"event id={event.get('event_id')} "
        f"timestamp={event.get('timestamp')} message={event.get('message')}"
    )


def run_port_down(backend):
    set_record(PORT2_OPER_OID, "2", "1")
    poll_device()
    changed = set_record(PORT2_OPER_OID, "2", "2")
    poll_device()
    port = require_port(backend, oper_status="down")
    return changed, f"Port 2 admin={port['ifAdminStatus']} oper={port['ifOperStatus']}", []


def run_port_up(backend):
    set_record(PORT2_OPER_OID, "2", "2")
    poll_device()
    changed = set_record(PORT2_OPER_OID, "2", "1")
    poll_device()
    port = require_port(backend, oper_status="up")
    return changed, f"Port 2 admin={port['ifAdminStatus']} oper={port['ifOperStatus']}", []


def run_location_change(backend):
    set_record(LOCATION_OID, "4", BASELINE_LOCATION)
    discover_device()
    changed = set_record(LOCATION_OID, "4", DEMO_LOCATION)
    discover_device()
    device = backend.get_device(device_id=DEVICE_ID)
    location = (device.get("location") or {}).get("location") if device else None
    if location != DEMO_LOCATION:
        raise RuntimeError(f"unexpected LibreNMS location: {location}")
    return changed, f"Device location={location}", []


def run_device_down_up(backend):
    restored = restore_online_fixture()
    if responder_pid(required=False) is None:
        start_responder(target_online=True)
    elif restored:
        restart_responder(target_online=True)
    poll_device()
    before_id = newest_event_id(current_events(backend))
    down_event = None
    try:
        take_device_offline()
        restart_responder(target_online=False)
        poll_device(expect_down=True)
        require_device_status(backend, 0)
        down_event = find_new_event(
            current_events(backend),
            after_id=before_id,
            event_type="down",
            reference=None,
            message_fragment="Device status changed to Down",
        )
        if not down_event:
            raise RuntimeError("LibreNMS did not record a new device down event")
    finally:
        if fixture_state() == "offline":
            restore_online_fixture()
            if responder_pid(required=False) is not None:
                restart_responder(target_online=True)
            else:
                start_responder(target_online=True)
            poll_device()
    require_device_status(backend, 1)
    up_event = find_new_event(
        current_events(backend),
        after_id=int(down_event["event_id"]),
        event_type="up",
        reference=None,
        message_fragment="Device status changed to Up",
    )
    if not up_event:
        raise RuntimeError("LibreNMS did not record a new device up event")
    return True, "Device transitioned down and returned up", [down_event, up_event]


def run_port_down_up_event(backend):
    set_record(PORT2_OPER_OID, "2", "2")
    poll_device()
    before_id = newest_event_id(current_events(backend))
    set_record(PORT2_OPER_OID, "2", "1")
    poll_device()
    set_record(PORT2_OPER_OID, "2", "2")
    poll_device()
    event = find_new_event(
        current_events(backend),
        after_id=before_id,
        event_type="interface",
        reference="2",
        message_fragment="ifOperStatus: up -> down",
    )
    if not event:
        raise RuntimeError("LibreNMS did not record a new port down event")
    set_record(PORT2_OPER_OID, "2", "1")
    poll_device()
    require_port(backend, oper_status="up")
    return True, "Port 2 transition event recorded", [event]


SCENARIO_RUNNERS = {
    "port-down": run_port_down,
    "port-up": run_port_up,
    "location-change": run_location_change,
    "device-down-up": run_device_down_up,
    "port-down-up-event": run_port_down_up_event,
}


def reset_baseline():
    restored = restore_online_fixture()
    pid = responder_pid(required=False)
    if pid is None:
        start_responder(target_online=True)
    elif restored:
        restart_responder(target_online=True)
    changed = set_baseline_records()
    discover_device()
    poll_device()
    backend = api_backend()
    device = require_device_status(backend, 1)
    port = require_port(backend, oper_status="down")
    location = (device.get("location") or {}).get("location")
    if location != BASELINE_LOCATION:
        raise RuntimeError(f"reset location verification failed: {location}")
    return {
        "changed": changed or restored,
        "location": location,
        "admin": port["ifAdminStatus"],
        "oper": port["ifOperStatus"],
    }


def load_scenarios():
    return json.loads(
        (Path(__file__).with_name("scenarios.json")).read_text(encoding="utf-8")
    )


def execute_scenario(scenario_id):
    scenarios = load_scenarios()
    if scenario_id not in SCENARIO_RUNNERS or scenario_id not in scenarios:
        raise ValueError(f"unsupported scenario: {scenario_id}")
    preflight()
    changed, verified, events = SCENARIO_RUNNERS[scenario_id](api_backend())
    return {
        "scenario_id": scenario_id,
        "snmp_state_changed": bool(changed),
        "librenms_completed": True,
        "verified": verified,
        "events": [
            {
                "event_id": event.get("event_id"),
                "timestamp": event.get("timestamp"),
                "message": event.get("message"),
            }
            for event in events
        ],
        "example_question": scenarios[scenario_id]["example_ai_question"],
    }


def main(argv=None):
    scenarios = load_scenarios()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=scenarios)
    args = parser.parse_args(argv)
    result = execute_scenario(args.scenario)
    metadata = scenarios[args.scenario]
    print(f"Scenario: {args.scenario}")
    print(f"SNMP state changed: {'yes' if result['snmp_state_changed'] else 'no'}")
    print("LibreNMS poll/discovery completed: yes")
    print(f"Verified: {result['verified']}")
    for event in result["events"]:
        print(f"Event: {event_line(event)}")
    print(f"Example AI question: {metadata['example_ai_question']}")
    print("Reset: available (python3 simulation/reset.py)")


if __name__ == "__main__":
    main()
