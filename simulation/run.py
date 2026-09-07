#!/usr/bin/env python3
"""Minimal live scenario runner for the existing EMR-55 UTM lab."""

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POC_DIR = ROOT / "librenms-hybrid-poc"
sys.path.insert(0, str(POC_DIR))

from librenms_backend import LibreNMSBackend  # noqa: E402


SSH_HOST = "emir@192.168.64.3"
SSH_KEY = Path.home() / ".ssh" / "codex_utm"
RESPONDER = "/opt/snmpsim-venv/bin/snmpsim-command-responder"
RESPONDER_PATTERN = (
    "^/opt/snmpsim-venv/bin/python3 "
    "/opt/snmpsim-venv/bin/snmpsim-command-responder"
)
DEVICES_UP = "/opt/snmpsim-lab/devices-up.txt"
LOCATION_OID = "1.3.6.1.2.1.1.6.0"
PORT2_ADMIN_OID = "1.3.6.1.2.1.2.2.1.7.2"
PORT2_OPER_OID = "1.3.6.1.2.1.2.2.1.8.2"
BASELINE_LOCATION = "Test Lab"
DEMO_LOCATION = "EMR-55 Demo Lab"

SCENARIO_IDS = (
    "port-down",
    "port-up",
    "location-change",
    "device-down-up",
    "port-down-up-event",
    "investigation-incident",
)


@dataclass(frozen=True)
class DemoTarget:
    target_id: str
    hostname: str
    device_id: int
    fixture: str
    offline_fixture: str
    snmp_endpoint: str
    supported_scenarios: tuple[str, ...]
    alert_rule_id: int | None = None


# Only targets whose fixture ownership and required Port 2 OIDs were verified
# on the UTM lab are exposed here. Inventory membership alone is insufficient.
TARGETS = {
    "lab-j9772a-01": DemoTarget(
        target_id="lab-j9772a-01",
        hostname="lab-j9772a-01",
        device_id=1,
        fixture="/opt/snmpsim-lab/data/lab-j9772a-01/public.snmprec",
        offline_fixture="/opt/snmpsim-lab/data/lab-j9772a-01/offline.snmprec",
        snmp_endpoint="udp:127.0.0.11:1611",
        supported_scenarios=SCENARIO_IDS,
        alert_rule_id=13,
    ),
}


def resolve_target(target_id, targets=None):
    target = (targets or TARGETS).get(target_id)
    if target is None:
        raise ValueError(f"unsupported target: {target_id}")
    return target


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


def read_fixture(target):
    return ssh(f"cat {shlex.quote(target.fixture)}").stdout


def write_fixture(target, text):
    temporary = target.fixture + ".emr55-tmp"
    command = (
        "set -eu; "
        f"tmp={shlex.quote(temporary)}; "
        "trap 'rm -f \"$tmp\"' EXIT; "
        "cat >\"$tmp\"; "
        f"mv \"$tmp\" {shlex.quote(target.fixture)}; "
        "trap - EXIT"
    )
    ssh(command, input_text=text)


def set_record(target, oid, value_type, value):
    before = read_fixture(target)
    after = replace_record(before, oid, value_type, value)
    if after != before:
        write_fixture(target, after)
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


def start_responder(target, *, target_online):
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
            if snmp_available(target):
                return pid
            time.sleep(0.5)
        raise RuntimeError("responder started but target SNMP endpoint is unavailable")
    return pid


def restart_responder(target, *, target_online):
    stop_responder()
    return start_responder(target, target_online=target_online)


def snmp_available(target):
    command = (
        "snmpget -v2c -c public -t 1 -r 0 -On "
        f"{shlex.quote(target.snmp_endpoint)} 1.3.6.1.2.1.1.5.0"
    )
    return ssh(command, check=False, timeout=10).returncode == 0


def poll_device(target, *, expect_down=False):
    result = ssh(
        "cd /opt/librenms && "
        f"sudo -n -u librenms ./poller.php -h {shlex.quote(target.hostname)}",
        check=False,
        timeout=180,
    )
    accepted = {0, 6} if expect_down else {0}
    if result.returncode not in accepted:
        detail = (result.stderr or result.stdout)[-2000:].strip()
        raise RuntimeError(f"LibreNMS poller failed ({result.returncode}): {detail}")
    return True


def discover_device(target):
    ssh(
        "cd /opt/librenms && "
        f"sudo -n -u librenms ./discovery.php -h {shlex.quote(target.hostname)}",
        timeout=180,
    )
    return True


def api_backend():
    return LibreNMSBackend(event_limit=100)


def current_port2(backend, target):
    ports = backend.get_ports(device_id=target.device_id)
    return next((port for port in ports if int(port.get("ifIndex")) == 2), None)


def current_events(backend, target):
    return list(backend.get_events(device_id=target.device_id))


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


def require_port(backend, target, *, oper_status):
    port = current_port2(backend, target)
    if not port:
        raise RuntimeError("LibreNMS API did not return port 2")
    if port.get("ifAdminStatus") != "up" or port.get("ifOperStatus") != oper_status:
        raise RuntimeError(f"unexpected LibreNMS port 2 state: {port}")
    return port


def require_device_status(backend, target, status):
    device = backend.get_device(device_id=target.device_id)
    if not device or device.get("status") != status:
        raise RuntimeError(f"unexpected LibreNMS device state: {device}")
    return device


def fixture_state(target):
    result = ssh(
        f"if [ -f {shlex.quote(target.fixture)} ] && [ ! -e {shlex.quote(target.offline_fixture)} ]; then echo online; "
        f"elif [ -f {shlex.quote(target.offline_fixture)} ] && [ ! -e {shlex.quote(target.fixture)} ]; then echo offline; "
        "else echo invalid; fi"
    )
    return result.stdout.strip()


def take_device_offline(target):
    if fixture_state(target) != "online":
        raise RuntimeError("target fixture is not in the online state")
    ssh(f"mv {shlex.quote(target.fixture)} {shlex.quote(target.offline_fixture)}")


def restore_online_fixture(target):
    state = fixture_state(target)
    if state == "online":
        return False
    if state != "offline":
        raise RuntimeError("target fixture state is ambiguous")
    ssh(f"mv {shlex.quote(target.offline_fixture)} {shlex.quote(target.fixture)}")
    return True


def set_baseline_records(target):
    changed = False
    changed |= set_record(target, LOCATION_OID, "4", BASELINE_LOCATION)
    changed |= set_record(target, PORT2_ADMIN_OID, "2", "1")
    changed |= set_record(target, PORT2_OPER_OID, "2", "2")
    return changed


def preflight(target):
    if not SSH_KEY.is_file():
        raise RuntimeError(f"SSH key not found: {SSH_KEY}")
    ssh(
        "set -eu; "
        "sudo -n -u librenms true; "
        f"test -x {shlex.quote(RESPONDER)}; "
        f"test -r {shlex.quote(DEVICES_UP)}"
    )
    if fixture_state(target) == "online":
        ssh(f"test -w {shlex.quote(target.fixture)}")
    api_backend().get_device(device_id=target.device_id)


def ensure_online(target):
    restored = restore_online_fixture(target)
    pid = responder_pid(required=False)
    if pid is None:
        start_responder(target, target_online=True)
    elif restored:
        restart_responder(target, target_online=True)
    return restored


def event_line(event):
    return (
        f"event id={event.get('event_id')} "
        f"timestamp={event.get('timestamp')} message={event.get('message')}"
    )


def run_port_down(backend, target):
    set_record(target, PORT2_OPER_OID, "2", "1")
    poll_device(target)
    changed = set_record(target, PORT2_OPER_OID, "2", "2")
    poll_device(target)
    port = require_port(backend, target, oper_status="down")
    return changed, f"Port 2: admin={port['ifAdminStatus']} / oper={port['ifOperStatus']}", []


def run_port_up(backend, target):
    set_record(target, PORT2_OPER_OID, "2", "2")
    poll_device(target)
    changed = set_record(target, PORT2_OPER_OID, "2", "1")
    poll_device(target)
    port = require_port(backend, target, oper_status="up")
    return changed, f"Port 2: admin={port['ifAdminStatus']} / oper={port['ifOperStatus']}", []


def run_location_change(backend, target):
    set_record(target, LOCATION_OID, "4", BASELINE_LOCATION)
    discover_device(target)
    changed = set_record(target, LOCATION_OID, "4", DEMO_LOCATION)
    discover_device(target)
    device = backend.get_device(device_id=target.device_id)
    location = (device.get("location") or {}).get("location") if device else None
    if location != DEMO_LOCATION:
        raise RuntimeError(f"unexpected LibreNMS location: {location}")
    return changed, f"Cihaz konumu={location}", []


def run_device_down_up(backend, target):
    ensure_online(target)
    poll_device(target)
    before_id = newest_event_id(current_events(backend, target))
    down_event = None
    try:
        take_device_offline(target)
        restart_responder(target, target_online=False)
        poll_device(target, expect_down=True)
        require_device_status(backend, target, 0)
        down_event = find_new_event(
            current_events(backend, target),
            after_id=before_id,
            event_type="down",
            reference=None,
            message_fragment="Device status changed to Down",
        )
        if not down_event:
            raise RuntimeError("LibreNMS did not record a new device down event")
    finally:
        if fixture_state(target) == "offline":
            restore_online_fixture(target)
            if responder_pid(required=False) is not None:
                restart_responder(target, target_online=True)
            else:
                start_responder(target, target_online=True)
            poll_device(target)
    require_device_status(backend, target, 1)
    up_event = find_new_event(
        current_events(backend, target),
        after_id=int(down_event["event_id"]),
        event_type="up",
        reference=None,
        message_fragment="Device status changed to Up",
    )
    if not up_event:
        raise RuntimeError("LibreNMS did not record a new device up event")
    return True, "Cihaz down durumuna geçti ve yeniden up oldu", [down_event, up_event]


def run_port_down_up_event(backend, target):
    set_record(target, PORT2_OPER_OID, "2", "2")
    poll_device(target)
    before_id = newest_event_id(current_events(backend, target))
    set_record(target, PORT2_OPER_OID, "2", "1")
    poll_device(target)
    set_record(target, PORT2_OPER_OID, "2", "2")
    poll_device(target)
    event = find_new_event(
        current_events(backend, target),
        after_id=before_id,
        event_type="interface",
        reference="2",
        message_fragment="ifOperStatus: up -> down",
    )
    if not event:
        raise RuntimeError("LibreNMS did not record a new port down event")
    set_record(target, PORT2_OPER_OID, "2", "1")
    poll_device(target)
    require_port(backend, target, oper_status="up")
    return True, "Port 2 geçiş eventi kaydedildi", [event]


def _active_target_alert(backend, target):
    if target.alert_rule_id is None:
        return None
    return next(
        (
            alert
            for alert in backend.get_alerts(device_id=target.device_id)
            if int(alert.get("rule_id") or 0) == target.alert_rule_id
        ),
        None,
    )


def run_investigation_incident(backend, target):
    ensure_online(target)
    changed = set_record(target, PORT2_ADMIN_OID, "2", "1")
    changed |= set_record(target, PORT2_OPER_OID, "2", "1")
    poll_device(target)
    before_id = newest_event_id(current_events(backend, target))

    device_changed, _, device_events = run_device_down_up(backend, target)
    changed |= device_changed
    after_device_id = max(before_id, newest_event_id(device_events))

    changed |= set_record(target, PORT2_OPER_OID, "2", "2")
    poll_device(target)
    port = require_port(backend, target, oper_status="down")
    port_event = find_new_event(
        current_events(backend, target),
        after_id=after_device_id,
        event_type="interface",
        reference="2",
        message_fragment="ifOperStatus: up -> down",
    )
    if not port_event:
        raise RuntimeError("LibreNMS did not record the investigation port event")

    alert = _active_target_alert(backend, target)
    proof = [
        {
            "id": "device",
            "status": "passed",
            "label": f"Cihaz: {target.hostname} / device_id={target.device_id}",
        },
        {
            "id": "port",
            "status": "passed",
            "label": (
                f"Port 2: admin {port['ifAdminStatus']} / oper {port['ifOperStatus']}"
            ),
        },
        {
            "id": "event",
            "status": "passed",
            "label": f"Event #{port_event['event_id']}: ifOperStatus up -> down",
            "event_id": int(port_event["event_id"]),
        },
    ]
    required_findings = [
        "device_current_status",
        "port_admin_up_oper_down",
    ]
    if alert:
        proof.append(
            {
                "id": "alert",
                "status": "passed",
                "label": (
                    f"Aktif alarm #{alert['alert_id']}: {alert.get('severity') or 'unknown'}"
                ),
                "alert_id": int(alert["alert_id"]),
            }
        )
        required_findings.append("active_alert")
    else:
        proof.append(
            {
                "id": "alert",
                "status": "unavailable",
                "label": "Aktif alarm doğrulaması kullanılamıyor",
            }
        )
    required_findings.append("historical_status_transition")
    proof.append(
        {"id": "poll", "status": "passed", "label": "LibreNMS poll tamamlandı"}
    )
    history_event_ids = [int(event["event_id"]) for event in device_events]
    return (
        bool(changed),
        "İnceleme olayı hazır",
        [*device_events, port_event],
        {
            "proof": proof,
            "expected_investigation": {
                "target_id": target.target_id,
                "hostname": target.hostname,
                "device_id": target.device_id,
                "required_route": "investigation",
                "required_tools": [
                    "get_device",
                    "get_ports",
                    "get_alerts",
                    "get_events",
                ],
                "required_finding_types": required_findings,
                "required_event_ids": history_event_ids,
                "required_synthesis_llm_called": True,
            },
        },
    )


SCENARIO_RUNNERS = {
    "port-down": run_port_down,
    "port-up": run_port_up,
    "location-change": run_location_change,
    "device-down-up": run_device_down_up,
    "port-down-up-event": run_port_down_up_event,
    "investigation-incident": run_investigation_incident,
}


def reset_baseline(target_id="lab-j9772a-01"):
    target = resolve_target(target_id) if isinstance(target_id, str) else target_id
    restored = ensure_online(target)
    changed = set_baseline_records(target)
    discover_device(target)
    poll_device(target)
    backend = api_backend()
    device = require_device_status(backend, target, 1)
    port = require_port(backend, target, oper_status="down")
    location = (device.get("location") or {}).get("location")
    if location != BASELINE_LOCATION:
        raise RuntimeError(f"reset location verification failed: {location}")
    return {
        "changed": changed or restored,
        "target_id": target.target_id,
        "location": location,
        "admin": port["ifAdminStatus"],
        "oper": port["ifOperStatus"],
    }


def load_scenarios():
    return json.loads(
        (Path(__file__).with_name("scenarios.json")).read_text(encoding="utf-8")
    )


def demo_metadata():
    scenarios = load_scenarios()
    targets = list(TARGETS.values())
    return {
        "supported_targets": [
            {
                "id": target.target_id,
                "hostname": target.hostname,
                "device_id": target.device_id,
                "supported_scenarios": list(target.supported_scenarios),
            }
            for target in targets
        ],
        "scenarios": [
            {
                "id": scenario_id,
                "label": scenarios[scenario_id]["label"],
                "example_question": scenarios[scenario_id]["example_ai_question"].format(
                    hostname=next(
                        target.hostname
                        for target in targets
                        if scenario_id in target.supported_scenarios
                    )
                ),
                "supported_target_ids": [
                    target.target_id
                    for target in targets
                    if scenario_id in target.supported_scenarios
                ],
            }
            for scenario_id in SCENARIO_IDS
        ],
    }


def execute_scenario(scenario_id, target_id):
    scenarios = load_scenarios()
    if scenario_id not in SCENARIO_RUNNERS or scenario_id not in scenarios:
        raise ValueError(f"unsupported scenario: {scenario_id}")
    target = resolve_target(target_id)
    if scenario_id not in target.supported_scenarios:
        raise ValueError(f"scenario {scenario_id} is unavailable for target {target_id}")
    preflight(target)
    try:
        ensure_online(target)
        outcome = SCENARIO_RUNNERS[scenario_id](api_backend(), target)
    except Exception:
        try:
            reset_baseline(target)
        except Exception:
            pass
        raise
    changed, verified, events = outcome[:3]
    details = outcome[3] if len(outcome) == 4 else {}
    return {
        "scenario_id": scenario_id,
        "target_id": target.target_id,
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
        "proof": details.get("proof", []),
        "expected_investigation": details.get("expected_investigation"),
        "example_question": scenarios[scenario_id]["example_ai_question"].format(
            hostname=target.hostname
        ),
    }


def main(argv=None):
    scenarios = load_scenarios()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=scenarios)
    parser.add_argument("--target", choices=TARGETS, default="lab-j9772a-01")
    args = parser.parse_args(argv)
    result = execute_scenario(args.scenario, args.target)
    metadata = scenarios[args.scenario]
    print(f"Scenario: {args.scenario}")
    print(f"SNMP state changed: {'yes' if result['snmp_state_changed'] else 'no'}")
    print("LibreNMS poll/discovery completed: yes")
    print(f"Verified: {result['verified']}")
    for event in result["events"]:
        print(f"Event: {event_line(event)}")
    print(
        "Example AI question: "
        + metadata["example_ai_question"].format(hostname=resolve_target(args.target).hostname)
    )
    print("Reset: available (python3 simulation/reset.py)")


if __name__ == "__main__":
    main()
