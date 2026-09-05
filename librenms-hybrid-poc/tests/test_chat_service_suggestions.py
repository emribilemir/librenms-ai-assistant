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
from chat_service.suggestions import build_suggestions


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
                "a-up açık mı?",
                "b-up port 2 ne durumda?",
                "lab-j9772a-01'in down portları hangileri?",
                "z-up üzerinde aktif alarm var mı?",
            ],
        )
        self.assertEqual(
            [item["title"] for item in result],
            [item["prompt"] for item in result],
        )
        self.assertTrue(all(item["prompt"] and item["label"] for item in result))
        self.assertTrue(all("z-down" not in item["prompt"] for item in result))

    def test_is_deterministic_and_bounded(self):
        devices = [
            {"hostname": f"sw-{index:02d}", "status": 1}
            for index in range(10, 0, -1)
        ]

        first = build_suggestions(devices, limit=4)
        second = build_suggestions(reversed(devices), limit=4)

        self.assertEqual(first, second)
        self.assertEqual(len(first), 4)


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
            "lab-j9775a-01 açık mı?",
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
