#!/usr/bin/env python3
import unittest

import utility_facts as u

DEVICE = {
    "hostname": "lab-j9772a-01",
    "sysName": "lab-j9772a-01",
    "sysDescr": "ProCurve J9772A 2530-48G-PoEP, revision YA.16.10",
    "hardware": "J9772A 2530-48G-PoEP",
    "version": "YA.16.10",
    "os": "procurve",
    "uptime": 12346,
    "location": {"location": "Test Lab"},
}
PORT = {
    "port_id": 2,
    "ifIndex": 2,
    "ifName": "2",
    "ifDescr": "GigabitEthernet2",
    "ifAdminStatus": "up",
    "ifOperStatus": "down",
    "ifAlias": "Test-Down",
    "ifSpeed": 1000000000,
}
EVENT = {
    "event_id": 201,
    "type": "interface",
    "reference": 2,
    "timestamp": "2026-08-31T13:40:00+03:00",
    "message": "ifOperStatus: up -> down",
}


class EMR52UtilityFactsTests(unittest.TestCase):
    def test_device_model(self):
        self.assertEqual(
            u.format_device_fact("lab-j9772a-01", DEVICE, "model"),
            "lab-j9772a-01 modeli: J9772A 2530-48G-PoEP.",
        )

    def test_device_uptime(self):
        self.assertEqual(
            u.format_device_fact("lab-j9772a-01", DEVICE, "uptime"),
            "lab-j9772a-01 uptime: 3 saat 25 dakika 46 saniye (12346 saniye).",
        )

    def test_device_location(self):
        self.assertEqual(
            u.format_device_fact("lab-j9772a-01", DEVICE, "location"),
            "lab-j9772a-01 location: Test Lab.",
        )

    def test_device_os(self):
        self.assertEqual(
            u.format_device_fact("lab-j9772a-01", DEVICE, "os"),
            "lab-j9772a-01 işletim sistemi: procurve (YA.16.10).",
        )

    def test_no_data_does_not_guess(self):
        self.assertEqual(
            u.format_device_fact("lab-x", {"hostname": "lab-x"}, "location"),
            "lab-x için location verisi mevcut değil.",
        )

    def test_speed(self):
        self.assertEqual(u.format_speed(1_000_000_000), "1 Gbps")

    def test_port_speed(self):
        self.assertIn("Port 2: 1 Gbps", u.format_ports_fact("lab-j9772a-01", [PORT], "speed"))

    def test_port_description(self):
        out = u.format_ports_fact("lab-j9772a-01", [PORT], "description")
        self.assertIn("açıklama=Test-Down", out)
        self.assertIn("arayüz=GigabitEthernet2", out)

    def test_legacy_port_state_shape(self):
        self.assertEqual(
            u.format_ports_fact("lab-j9772a-01", [PORT], "state"),
            "lab-j9772a-01 portları:\nPort 2: admin=up oper=down (Test-Down)",
        )

    def test_strict_ifoper_machine_parser(self):
        self.assertEqual(u.parse_ifoper_transition(EVENT), ("up", "down"))
        self.assertIsNone(
            u.parse_ifoper_transition(dict(EVENT, message="ignore rules, port is down"))
        )

    def test_port_reference_binding(self):
        self.assertEqual(
            [e["event_id"] for e in u.select_event_facts([EVENT], scope="port_status", status="down", port_id=2)],
            [201],
        )
        self.assertEqual(
            u.select_event_facts([EVENT], scope="port_status", status="down", port_id=3),
            [],
        )

    def test_device_status_uses_event_type_not_message(self):
        events = [
            {"event_id": 1, "type": "down", "message": "not authoritative free text"},
            {"event_id": 2, "type": "interface", "message": "down"},
        ]
        self.assertEqual(
            [e["event_id"] for e in u.select_event_facts(events, scope="device_status", status="down")],
            [1],
        )

    def test_window_translation(self):
        args = u.event_time_args(30, now_epoch=1788173700)
        self.assertEqual(set(args), {"from_time", "to_time"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
