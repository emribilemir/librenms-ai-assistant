#!/usr/bin/env python3
"""Offline regression tests for the real LibreNMS backend adapter.

These tests never contact the user's VM. A tiny local HTTP server exercises the
same HTTP/header/JSON path that the live adapter will use.
"""

import importlib.util
import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

import hybrid_poc
import planner_v2

ROOT = Path(__file__).resolve().parent.parent
POC = ROOT / "librenms-hybrid-poc"
GOLD = ROOT / "hybrid-gold-v3"
BACKEND_PATH = POC / "librenms_backend.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_live_backend_module():
    if not BACKEND_PATH.exists():
        raise AssertionError(
            "librenms_backend.py is missing; add the real LibreNMS backend adapter"
        )
    return load_module("librenms_backend_test", BACKEND_PATH)


resolver_v5 = load_module("resolver_v5_live_test", GOLD / "resolver_candidate_v5.py")
with (GOLD / "dummy_inventory.json").open(encoding="utf-8") as stream:
    INVENTORY = json.load(stream)


class _ApiHandler(BaseHTTPRequestHandler):
    requests = []
    expected_token = "test-token"

    def do_GET(self):
        type(self).requests.append(
            {
                "path": self.path,
                "token": self.headers.get("X-Auth-Token"),
                "accept": self.headers.get("Accept"),
            }
        )

        if self.headers.get("X-Auth-Token") != self.expected_token:
            return self._json(401, {"message": "Unauthenticated."})

        if self.path == "/api/v0/devices/lab-j9775a-01":
            return self._json(
                200,
                {
                    "status": "ok",
                    "devices": [
                        {
                            "device_id": "3",
                            "hostname": "lab-j9775a-01",
                            "status": "0",
                            "hardware": "J9775A 2530-48G",
                            "os": "procurve",
                        }
                    ],
                    "count": 1,
                },
            )

        if self.path == "/api/v0/devices/3/ports":
            return self._json(
                200,
                {
                    "status": "ok",
                    "ports": [
                        {
                            "port_id": "31",
                            "device_id": "3",
                            "ifIndex": "1",
                            "ifName": "1",
                            "ifAdminStatus": "up",
                            "ifOperStatus": "down",
                        }
                    ],
                    "count": 1,
                },
            )

        if self.path == "/api/v0/alerts?state=1":
            return self._json(
                200,
                {
                    "status": "ok",
                    "alerts": [
                        {"id": "8", "device_id": "3", "state": "1", "severity": "critical"},
                        {"id": "9", "device_id": "7", "state": "1", "severity": "warning"},
                    ],
                    "count": 2,
                },
            )

        if self.path == "/api/v0/logs/eventlog/3?limit=20&sortorder=DESC":
            return self._json(
                200,
                {
                    "status": "ok",
                    "logs": [
                        {
                            "event_id": "100",
                            "device_id": "3",
                            "datetime": "2026-08-26 11:41:36",
                            "message": "Device status changed to Down from check.",
                            "severity": "5",
                        }
                    ],
                    "count": 1,
                },
            )

        return self._json(404, {"status": "error", "message": "not found"})

    def log_message(self, format, *args):
        return

    def _json(self, code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class LocalApiServer:
    def __enter__(self):
        _ApiHandler.requests = []
        self.server = HTTPServer(("127.0.0.1", 0), _ApiHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.base_url = f"http://{host}:{port}/api/v0"
        return self

    def __exit__(self, exc_type, exc, tb):
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()


class LibreNMSBackendContractTests(unittest.TestCase):
    def test_live_backend_uses_auth_header_and_normalizes_read_only_results(self):
        backend_mod = load_live_backend_module()

        with LocalApiServer() as api:
            backend = backend_mod.LibreNMSBackend(
                base_url=api.base_url,
                token="test-token",
                timeout=2,
            )
            device = backend.get_device(hostname="lab-j9775a-01")
            ports = backend.get_ports(device_id=device["device_id"])
            alerts = backend.get_alerts(device_id=device["device_id"])
            events = backend.get_events(device_id=device["device_id"])

        self.assertEqual(device["device_id"], 3)
        self.assertEqual(device["status"], 0)
        self.assertEqual(ports[0]["ifOperStatus"], "down")
        self.assertEqual([a["alert_id"] for a in alerts], [8])
        self.assertEqual(events[0]["timestamp"], "2026-08-26 11:41:36")
        self.assertEqual(
            [c["tool"] for c in backend.trace()],
            ["get_device", "get_ports", "get_alerts", "get_events"],
        )
        self.assertTrue(all(r["token"] == "test-token" for r in _ApiHandler.requests))
        self.assertTrue(all(r["accept"] == "application/json" for r in _ApiHandler.requests))


class BackendIdentityRegressionTests(unittest.TestCase):
    class BackendWithRealIds:
        def __init__(self):
            self.calls = []

        def reset_trace(self):
            self.calls = []

        def _record(self, tool, args, result):
            self.calls.append({"tool": tool, "args": args, "result": result})
            return result

        def get_device(self, *, hostname=None, device_id=None):
            return self._record(
                "get_device",
                {"hostname": hostname} if hostname is not None else {"device_id": device_id},
                {"device_id": 3, "hostname": "lab-j9775a-01", "status": 0},
            )

        def get_ports(self, *, device_id):
            return self._record("get_ports", {"device_id": device_id}, [])

        def get_alerts(self, *, device_id):
            return self._record("get_alerts", {"device_id": device_id}, [])

        def get_events(self, *, device_id):
            return self._record("get_events", {"device_id": device_id}, [])

        def trace(self):
            return list(self.calls)

    def test_downstream_calls_use_device_id_returned_by_backend_not_fixture_id(self):
        plans = {
            "ports": ("ports", "device_ports", ["get_ports"]),
            "alerts": ("alerts", "device_alerts", ["get_alerts"]),
            "events": ("events", "device_events", ["get_events"]),
            "investigation": (
                "investigation",
                "investigation",
                ["get_ports", "get_alerts", "get_events"],
            ),
            "historical_investigation": (
                "historical_investigation",
                "historical_status",
                ["get_events"],
            ),
        }
        for route, (request_type, intent, downstream_tools) in plans.items():
            with self.subTest(route=route):
                plan = {
                    "request_type": request_type,
                    "intent": intent,
                    "device_query": "lab-j9775a-01",
                    "device_filters": dict(planner_v2.EMPTY_FILTERS),
                }
                backend = self.BackendWithRealIds()
                with patch.object(
                    hybrid_poc,
                    "ollama_chat",
                    return_value=(json.dumps(plan), "stop", 1.0),
                ):
                    trace = hybrid_poc.orchestrate(
                        "test query",
                        inventory=INVENTORY,
                        backend=backend,
                        planner_schema="gold",
                        resolver_module=resolver_v5,
                    )

                resolver_id = trace["resolver_output"]["device"]["device_id"]
                self.assertEqual(resolver_id, 102)
                self.assertEqual(trace["tool_calls"][0]["args"], {"hostname": "lab-j9775a-01"})
                observed = {
                    call["tool"]: call["args"]["device_id"]
                    for call in trace["tool_calls"][1:]
                    if call["tool"] in downstream_tools
                }
                self.assertEqual(observed, {tool: 3 for tool in downstream_tools})


if __name__ == "__main__":
    unittest.main()

class LiveQueryEntrypointTests(unittest.TestCase):
    def test_live_query_runs_gold_pipeline_with_real_backend_contract(self):
        live_query_path = POC / "live_query.py"
        if not live_query_path.exists():
            self.fail("live_query.py is missing; add the live PoC entrypoint")
        live_query = load_module("live_query_test", live_query_path)

        plan = {
            "request_type": "atomic_fact",
            "intent": "device_status",
            "device_query": "lab-j9775a-01",
            "device_filters": dict(planner_v2.EMPTY_FILTERS),
        }
        backend = BackendIdentityRegressionTests.BackendWithRealIds()
        with patch.object(
            hybrid_poc,
            "ollama_chat",
            return_value=(json.dumps(plan), "stop", 1.0),
        ):
            trace = live_query.run_live_query(
                "lab-j9775a-01 açık mı?",
                backend=backend,
            )

        self.assertEqual(trace["route"], "atomic")
        self.assertEqual(trace["tool_calls"][0]["result"]["device_id"], 3)
        self.assertIn("çalışmıyor", trace["final_answer"])
