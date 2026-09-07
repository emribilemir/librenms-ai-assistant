import base64
import hashlib
import hmac
import json
import os
import tempfile
import time
import unittest

from fastapi.testclient import TestClient

from chat_service.app import create_app
from chat_service.pipeline_adapter import PipelineAdapter
from chat_service.suggestions import CAPABILITIES, build_contextual_examples, build_suggestions


SECRET = b"0123456789abcdef0123456789abcdef"


def bearer(sub="alice"):
    now = int(time.time())
    payload = {
        "sub": sub,
        "name": sub,
        "iss": "librenms",
        "aud": "ai-assistant",
        "iat": now,
        "exp": now + 3600,
    }
    body = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).rstrip(b"=")
    signature = base64.urlsafe_b64encode(
        hmac.new(SECRET, body, hashlib.sha256).digest()
    ).rstrip(b"=")
    return {
        "Authorization": "Bearer v1."
        + body.decode()
        + "."
        + signature.decode()
    }


class SuggestionGenerationTests(unittest.TestCase):
    def test_single_live_device_covers_multiple_capabilities(self):
        result = build_suggestions(
            [{"hostname": "lab-j9772a-01", "status": 1, "port_count": 4}],
            limit=4,
        )

        self.assertEqual(
            [item["label"] for item in result],
            [
                "Model bilgisi",
                "Bağlantısı düşmüş aktif portlar",
                "Son 24 saat incelemesi",
                "Cihaz incelemesi",
            ],
        )
        self.assertTrue(
            all("lab-j9772a-01" in item["prompt"] for item in result)
        )

    def test_rotation_changes_recent_capability_window_without_unsupported_prompts(self):
        devices = [
            {"hostname": "lab-j9772a-01", "status": 1, "port_count": 4}
        ]

        first = build_suggestions(devices, limit=4, rotation=0)
        second = build_suggestions(devices, limit=4, rotation=1)

        self.assertNotEqual(
            {item["prompt"] for item in first},
            {item["prompt"] for item in second},
        )
        self.assertTrue(
            {item["prompt"] for item in first}.isdisjoint(
                {item["prompt"] for item in second}
            )
        )
        self.assertIn("İşletim sistemi", [item["label"] for item in second])
        self.assertTrue(
            all(
                item["label"]
                in {
                    "Model bilgisi",
                    "Bağlantısı düşmüş aktif portlar",
                    "Son 24 saat incelemesi",
                    "Cihaz incelemesi",
                    "İşletim sistemi",
                    "Çalışma süresi",
                    "Konum",
                    "Port hızı",
                    "Port açıklaması",
                    "Down portlar",
                    "Disabled portlar",
                    "Port en son ne zaman down oldu?",
                    "Aktif alarmlar",
                    "Son olaylar",
                    "Cihaz durumu",
                    "Port durumu",
                }
                for item in first + second
            )
        )

    def test_uses_only_sorted_up_devices(self):
        devices = [
            {"hostname": "z-down", "status": 0},
            {"hostname": "b-up", "status": "up"},
            {"hostname": "a-up", "status": 1},
            {"hostname": "lab-j9772a-01", "status": True},
            {"hostname": "z-up", "status": "1"},
            {"hostname": "", "status": 1},
        ]

        result = build_suggestions(devices)

        self.assertEqual(
            [item["prompt"] for item in result],
            [
                "a-up modeli ne?",
                "b-up son 24 saatte neler olmuş?",
                "lab-j9772a-01'de ne sorun var?",
                "z-up işletim sistemi ne?",
            ],
        )
        self.assertEqual(
            [item["title"] for item in result],
            [item["prompt"] for item in result],
        )
        self.assertTrue(all(item["prompt"] and item["label"] for item in result))
        self.assertTrue(all("z-down" not in item["prompt"] for item in result))

    def test_live_adapter_validates_only_port_prompt_candidates(self):
        calls = []

        def ports_source(*, device_id):
            calls.append(device_id)
            return [{"port_id": 10}, {"port_id": 11}] if device_id == 2 else []

        adapter = PipelineAdapter(
            device_source=lambda: [
                {"device_id": 1, "hostname": "a-status-only", "status": 1},
                {"device_id": 2, "hostname": "b-has-ports", "status": 1},
                {"device_id": 3, "hostname": "c-down", "status": 0},
            ],
            ports_source=ports_source,
        )

        devices = adapter.list_suggestion_devices()

        self.assertEqual(devices[0]["port_count"], 0)
        self.assertEqual(devices[1]["port_count"], 2)
        self.assertNotIn("port_count", devices[2])
        self.assertEqual(calls, [1, 2])

    def test_is_deterministic_and_bounded(self):
        devices = [
            {"hostname": f"sw-{index:02d}", "status": 1}
            for index in range(10, 0, -1)
        ]

        first = build_suggestions(devices, limit=4)
        second = build_suggestions(reversed(devices), limit=4)

        self.assertEqual(first, second)
        self.assertEqual(len(first), 4)

    def test_port_prompts_only_use_devices_with_live_port_rows(self):
        devices = [
            {"hostname": "a-status-only", "status": 1, "port_count": 0},
            {"hostname": "b-has-ports", "status": 1, "port_count": 4},
            {"hostname": "c-status-only", "status": 1, "port_count": 0},
            {"hostname": "d-status-only", "status": 1, "port_count": 0},
        ]

        result = build_suggestions(devices, limit=4)

        self.assertEqual(
            [item["prompt"] for item in result],
            [
                "a-status-only modeli ne?",
                "b-has-ports'ta admin up olup oper down portlar hangileri?",
                "c-status-only son 24 saatte neler olmuş?",
                "d-status-only'de ne sorun var?",
            ],
        )

    def test_contextual_examples_rotate_verified_windows_without_repeating_recent_examples(self):
        first = build_contextual_examples("lab-j9772a-01", has_ports=True, rotation=0)
        second = build_contextual_examples("lab-j9772a-01", has_ports=True, rotation=1)

        self.assertEqual(first, [
            "lab-j9772a-01 modeli ne?",
            "lab-j9772a-01'ta admin up olup oper down portlar hangileri?",
            "lab-j9772a-01 son 24 saatte neler olmuş?",
        ])
        self.assertEqual(len(first), 3)
        self.assertEqual(len(second), 3)
        self.assertTrue(set(first).isdisjoint(second))

    def test_contextual_examples_exclude_port_families_without_live_port_rows(self):
        examples = build_contextual_examples("status-only", has_ports=False)

        self.assertEqual(examples[:3], [
            "status-only modeli ne?",
            "status-only son 24 saatte neler olmuş?",
            "status-only'de ne sorun var?",
        ])
        self.assertFalse(any("port" in example.lower() for example in examples))

    def test_capability_catalog_matches_the_established_planner_contract(self):
        self.assertEqual({capability["id"] for capability in CAPABILITIES}, {
            "model", "active_down_ports", "recent_history", "investigation",
            "os", "uptime", "location", "port_speed", "port_description",
            "down_ports", "disabled_ports", "port_last_down", "alerts", "events",
            "status", "specific_port",
        })


class SuggestionAdapter:
    def __init__(self, devices=None, error=None):
        self.devices = devices or []
        self.error = error

    def list_devices(self):
        if self.error is not None:
            raise self.error
        return self.devices

    def run(self, content, observer, is_cancelled):
        raise AssertionError("suggestion endpoint must not start a pipeline run")


class SuggestionRouteTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.directory.cleanup()

    def make_client(self, adapter):
        return TestClient(
            create_app(
                os.path.join(self.directory.name, "chat.sqlite3"),
                secret=SECRET,
                adapter=adapter,
            )
        )

    def test_requires_auth_and_returns_live_prompts(self):
        client = self.make_client(
            SuggestionAdapter(
                [
                    {"hostname": "lab-j9775a-01", "status": 1},
                    {"hostname": "offline", "status": 0},
                ]
            )
        )

        self.assertEqual(client.get("/v1/suggestions").status_code, 401)
        response = client.get("/v1/suggestions", headers=bearer())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["suggestions"][0]["prompt"],
            "lab-j9775a-01 modeli ne?",
        )

    def test_devices_route_returns_only_bounded_live_inventory_with_semantic_status(self):
        client = self.make_client(
            SuggestionAdapter(
                [
                    {"device_id": 3, "hostname": "z-unknown", "status": None},
                    {"device_id": 2, "hostname": "lab-down", "status": "0"},
                    {"device_id": 1, "hostname": "lab-up", "status": 1},
                    {"device_id": 4, "hostname": "", "status": 1},
                ]
            )
        )

        self.assertEqual(client.get("/v1/devices").status_code, 401)
        response = client.get("/v1/devices", headers=bearer())

        self.assertEqual(response.status_code, 200)
        devices = response.json()["devices"]
        self.assertEqual(
            [(device["hostname"], device["status"]) for device in devices],
            [("lab-down", "down"), ("lab-up", "up"), ("z-unknown", "unknown")],
        )
        self.assertEqual(devices[1]["examples"][:3], [
            "lab-up modeli ne?",
            "lab-up son 24 saatte neler olmuş?",
            "lab-up'de ne sorun var?",
        ])
        self.assertFalse(any("port" in example.lower() for device in devices for example in device["examples"]))
        self.assertNotIn("fixture", response.text)

    def test_suggestion_route_accepts_deterministic_rotation(self):
        client = self.make_client(
            SuggestionAdapter(
                [{"hostname": "lab-j9772a-01", "status": 1}]
            )
        )

        first = client.get("/v1/suggestions?rotation=0", headers=bearer())
        second = client.get("/v1/suggestions?rotation=1", headers=bearer())

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertNotEqual(
            {item["prompt"] for item in first.json()["suggestions"]},
            {item["prompt"] for item in second.json()["suggestions"]},
        )

    def test_returns_safe_503_without_upstream_details(self):
        client = self.make_client(
            SuggestionAdapter(error=RuntimeError("secret upstream body"))
        )

        response = client.get("/v1/suggestions", headers=bearer())

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()["detail"],
            {
                "code": "librenms_unavailable",
                "message": "Canlı cihaz önerileri şu anda alınamıyor.",
            },
        )
        self.assertNotIn("secret upstream body", response.text)


if __name__ == "__main__":
    unittest.main()
