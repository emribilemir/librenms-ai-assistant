#!/usr/bin/env python3

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import investigation_grounding as grounding


ISTANBUL = ZoneInfo("Europe/Istanbul")


class EventWindowTests(unittest.TestCase):
    def test_default_window_is_the_previous_24_hours(self):
        now = datetime(2026, 8, 28, 12, 0, tzinfo=ISTANBUL)

        window = grounding.resolve_event_window(None, now)

        self.assertEqual(window["mode"], "default_24h")
        self.assertEqual(window["from"], "2026-08-27T12:00:00+03:00")
        self.assertEqual(window["to"], "2026-08-28T12:00:00+03:00")

    def test_relative_window_is_anchored_to_the_request_time(self):
        now = datetime(2026, 8, 28, 12, 0, tzinfo=ISTANBUL)

        window = grounding.resolve_event_window(
            {"mode": "relative", "amount": 7, "unit": "day"}, now
        )

        self.assertEqual(window["from"], "2026-08-21T12:00:00+03:00")
        self.assertEqual(window["to"], "2026-08-28T12:00:00+03:00")

    def test_date_only_absolute_window_expands_to_the_local_day(self):
        now = datetime(2026, 8, 28, 12, 0, tzinfo=ISTANBUL)

        window = grounding.resolve_event_window(
            {"mode": "absolute", "from": "2026-08-20", "to": "2026-08-20"},
            now,
        )

        self.assertEqual(window["from"], "2026-08-20T00:00:00+03:00")
        self.assertEqual(window["to"], "2026-08-20T23:59:59+03:00")


class AuthoritativeIdTests(unittest.TestCase):
    def test_only_positive_integers_and_digit_strings_are_ids(self):
        self.assertEqual(grounding._positive_int(1), 1)
        self.assertEqual(grounding._positive_int("104"), 104)
        for value in (True, 0, -1, 1.0, 1.9, "-", "1.0", " 1"):
            with self.subTest(value=value):
                self.assertIsNone(grounding._positive_int(value))


class EvidenceBuilderTests(unittest.TestCase):
    def setUp(self):
        self.window = {
            "mode": "default_24h",
            "from": "2026-08-27T12:00:00+03:00",
            "to": "2026-08-28T12:00:00+03:00",
        }

    def test_builds_only_authoritative_current_findings_and_stable_refs(self):
        raw = {
            "device": {"device_id": 1, "hostname": "lab-j9772a-01", "status": 1},
            "ports": [
                {
                    "port_id": 21,
                    "ifIndex": "2",
                    "ifName": "2",
                    "ifAdminStatus": "up",
                    "ifOperStatus": "down",
                    "ifAlias": "Uplink",
                },
                {
                    "port_id": 22,
                    "ifIndex": "3",
                    "ifName": "3",
                    "ifAdminStatus": "down",
                    "ifOperStatus": "down",
                    "ifAlias": "Disabled",
                },
            ],
            "alerts": [
                {"alert_id": 133, "severity": "warning", "name": "LAB - Port admin up oper down"},
                {"alert_id": 88, "severity": "critical", "name": "Port status up/down"},
            ],
            "events": [],
        }

        package = grounding.build_investigation_evidence(raw, self.window)
        findings = {item["id"]: item for item in package["findings"]}

        self.assertEqual(package["schema_version"], 1)
        self.assertEqual(package["device"], {"device_id": 1, "hostname": "lab-j9772a-01"})
        self.assertIsNone(package["root_cause"])
        self.assertEqual(findings["device:1:current-status"]["value"], "up")
        port = findings["port:21:admin-up-oper-down"]
        self.assertEqual(port["ifIndex"], "2")
        self.assertEqual(
            port["evidence_refs"],
            [
                "ports[port_id=21].ifAdminStatus",
                "ports[port_id=21].ifOperStatus",
            ],
        )
        self.assertNotIn("port:22:admin-up-oper-down", findings)
        self.assertEqual(findings["alert:88:active"]["severity"], "critical")
        self.assertEqual(findings["alert:133:active"]["severity"], "warning")
        self.assertIn("root-cause:unknown", findings)

    def test_parses_only_allowlisted_status_messages_and_builds_chronological_transition(self):
        raw = {
            "device": {"device_id": 1, "hostname": "lab-j9772a-01", "status": 1},
            "ports": [],
            "alerts": [],
            "events": [
                {
                    "event_id": 107,
                    "timestamp": "2026-08-28 10:30:00",
                    "message": "Device status changed to Up from check.",
                },
                {
                    "event_id": 105,
                    "timestamp": "2026-08-28 10:00:00",
                    "message": "SNMP may be broken; probably Down.",
                },
                {
                    "event_id": 104,
                    "timestamp": "2026-08-28 09:00:00",
                    "message": "Device status changed to Down from check.",
                },
            ],
        }

        package = grounding.build_investigation_evidence(raw, self.window)
        findings = {item["id"]: item for item in package["findings"]}

        transition = findings["event-transition:104:107"]
        self.assertEqual((transition["from"], transition["to"]), ("down", "up"))
        self.assertEqual(
            transition["evidence_refs"],
            ["events[event_id=104].message", "events[event_id=107].message"],
        )
        self.assertFalse(any("105" in key for key in findings))

    def test_empty_retrieved_sources_produce_absence_findings(self):
        class CompleteEvents(list):
            complete = True

        raw = {
            "device": {"device_id": 1, "hostname": "lab-j9772a-01", "status": 1},
            "ports": [],
            "alerts": [],
            "events": CompleteEvents(),
        }

        package = grounding.build_investigation_evidence(raw, self.window)
        finding_ids = {item["id"] for item in package["findings"]}

        self.assertIn("ports:no-actionable-contradiction", finding_ids)
        self.assertIn("alerts:none-active", finding_ids)
        self.assertIn("events:no-recent-transition", finding_ids)

    def test_unretrieved_sources_never_produce_absence_findings(self):
        raw = {
            "device": None,
            "ports": None,
            "alerts": None,
            "events": None,
        }

        package = grounding.build_investigation_evidence(raw, self.window)
        finding_ids = {item["id"] for item in package["findings"]}

        self.assertFalse(package["coverage"]["device"]["retrieved"])
        self.assertFalse(package["coverage"]["ports"]["retrieved"])
        self.assertFalse(package["coverage"]["alerts"]["retrieved"])
        self.assertFalse(package["coverage"]["events"]["retrieved"])
        self.assertNotIn("ports:no-actionable-contradiction", finding_ids)
        self.assertNotIn("alerts:none-active", finding_ids)
        self.assertNotIn("events:no-recent-transition", finding_ids)

    def test_incomplete_event_coverage_never_claims_no_transition(self):
        class IncompleteEvents(list):
            complete = False

        raw = {
            "device": {"device_id": 1, "hostname": "lab-j9772a-01", "status": 1},
            "ports": [],
            "alerts": [],
            "events": IncompleteEvents(),
        }

        package = grounding.build_investigation_evidence(raw, self.window)
        finding_ids = {item["id"] for item in package["findings"]}

        self.assertFalse(package["coverage"]["events"]["complete"])
        self.assertNotIn("events:no-recent-transition", finding_ids)

    def test_plain_event_list_is_not_proof_of_complete_window_coverage(self):
        raw = {
            "device": {"device_id": 1, "hostname": "lab-j9772a-01", "status": 1},
            "ports": [],
            "alerts": [],
            "events": [],
        }

        package = grounding.build_investigation_evidence(raw, self.window)
        finding_ids = {item["id"] for item in package["findings"]}

        self.assertFalse(package["coverage"]["events"]["complete"])
        self.assertNotIn("events:no-recent-transition", finding_ids)

    def test_truthy_non_boolean_complete_marker_is_rejected(self):
        class AmbiguousEvents(list):
            complete = "false"

        raw = {
            "device": {"device_id": 1, "hostname": "lab-j9772a-01", "status": 1},
            "ports": [],
            "alerts": [],
            "events": AmbiguousEvents(),
        }

        package = grounding.build_investigation_evidence(raw, self.window)

        self.assertFalse(package["coverage"]["events"]["complete"])

    def test_missing_and_duplicate_authoritative_ids_mark_coverage_incomplete(self):
        raw = {
            "device": {"hostname": "missing-id", "status": 1},
            "ports": [
                {"port_id": "21", "ifIndex": "2", "ifAdminStatus": "up", "ifOperStatus": "down"},
                {"port_id": 21, "ifIndex": "2", "ifAdminStatus": "up", "ifOperStatus": "down"},
            ],
            "alerts": [
                {"alert_id": "88", "severity": "critical"},
                {"alert_id": 88, "severity": "critical"},
                {"severity": "warning"},
            ],
            "events": [
                {"event_id": 104, "timestamp": "2026-08-28 09:00:00", "message": "Device status changed to Down from check."},
                {"event_id": "104", "timestamp": "2026-08-28 09:30:00", "message": "Device status changed to Up from check."},
                {"timestamp": "2026-08-28 10:00:00", "message": "Device status changed to Up from check."},
            ],
        }

        package = grounding.build_investigation_evidence(raw, self.window)
        finding_ids = [item["id"] for item in package["findings"]]

        self.assertNotIn("device:None:current-status", finding_ids)
        self.assertEqual(finding_ids.count("port:21:admin-up-oper-down"), 1)
        self.assertEqual(finding_ids.count("alert:88:active"), 1)
        self.assertFalse(package["coverage"]["device"]["complete"])
        self.assertFalse(package["coverage"]["ports"]["complete"])
        self.assertFalse(package["coverage"]["alerts"]["complete"])
        self.assertFalse(package["coverage"]["events"]["complete"])

    def test_caps_categories_and_reports_omitted_counts(self):
        raw = {
            "device": {"device_id": 1, "hostname": "lab-j9772a-01", "status": 1},
            "ports": [
                {
                    "port_id": index,
                    "ifIndex": str(index),
                    "ifAdminStatus": "up",
                    "ifOperStatus": "down",
                }
                for index in range(1, 13)
            ],
            "alerts": [
                {"alert_id": index, "severity": "warning", "name": f"Alert {index}"}
                for index in range(1, 13)
            ],
            "events": [],
        }

        package = grounding.build_investigation_evidence(raw, self.window)

        self.assertEqual(package["truncation"]["ports"], {"total": 12, "included": 10, "omitted": 2})
        self.assertEqual(package["truncation"]["alerts"], {"total": 12, "included": 10, "omitted": 2})


if __name__ == "__main__":
    unittest.main()
