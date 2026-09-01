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


SECRET = b"0123456789abcdef0123456789abcdef"


def bearer(sub="alice"):
    now = int(time.time())
    payload = {"sub": sub, "name": sub, "iss": "librenms", "aud": "ai-assistant", "iat": now, "exp": now + 3600}
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).rstrip(b"=")
    sig = base64.urlsafe_b64encode(hmac.new(SECRET, body, hashlib.sha256).digest()).rstrip(b"=")
    return {"Authorization": "Bearer v1." + body.decode() + "." + sig.decode()}


class CompletedAdapter:
    def run(self, content, observer, is_cancelled):
        for stage, duration in (("planner", 3), ("resolver", 4), ("librenms", 5)):
            observer(stage, "started", None)
            observer(stage, "completed", duration)
        return {"answer": "Güvenli yanıt", "used_fallback": False, "metrics": {"planner_ms": 3, "resolver_ms": 4, "backend_ms": 5, "synthesis_ms": None, "time_to_first_token_ms": None, "total_ms": 12}}


class HeartbeatAdapter:
    def run(self, content, observer, is_cancelled):
        time.sleep(0.02)
        return {"answer": "yanıt", "used_fallback": False, "metrics": {"planner_ms": None, "resolver_ms": None, "backend_ms": None, "synthesis_ms": None, "time_to_first_token_ms": None, "total_ms": 20}}


class SseServiceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.client = TestClient(create_app(os.path.join(self.directory.name, "chat.sqlite3"), secret=SECRET, adapter=CompletedAdapter()))

    def tearDown(self):
        self.directory.cleanup()

    def test_stream_has_ordered_stage_events_safe_metrics_and_persists_answer(self):
        headers = bearer()
        thread = self.client.post("/v1/threads", headers=headers, json={}).json()
        response = self.client.post(f"/v1/threads/{thread['id']}/runs", headers=headers, json={"client_message_id": "c1", "content": "durum nedir?"})
        self.assertEqual(response.status_code, 200)
        events = [line[7:] for line in response.text.splitlines() if line.startswith("event:")]
        self.assertEqual(events, ["run.started", "planner.started", "planner.completed", "resolver.started", "resolver.completed", "librenms.started", "librenms.completed", "answer.delta", "completed"])
        completed = json.loads([line[6:] for line in response.text.splitlines() if line.startswith("data:")][-1])
        self.assertEqual(completed["metrics"]["backend_ms"], 5)
        self.assertEqual(completed["metrics"]["time_to_first_visible_chunk_ms"], 12)
        detail = self.client.get(f"/v1/threads/{thread['id']}", headers=headers).json()
        self.assertEqual(detail["messages"][-1]["content"], "Güvenli yanıt")

    def test_duplicate_id_returns_conflict_without_stream(self):
        headers = bearer()
        thread = self.client.post("/v1/threads", headers=headers, json={}).json()
        url = f"/v1/threads/{thread['id']}/runs"
        self.client.post(url, headers=headers, json={"client_message_id": "c1", "content": "ilk"})
        duplicate = self.client.post(url, headers=headers, json={"client_message_id": "c1", "content": "tekrar"})
        self.assertEqual(duplicate.status_code, 409)
        self.assertNotIn("text/event-stream", duplicate.headers.get("content-type", ""))
        detail = self.client.get(f"/v1/threads/{thread['id']}", headers=headers).json()
        self.assertEqual(len(detail["messages"]), 2)
        self.assertEqual(len(detail["runs"]), 1)

    def test_foreign_user_gets_not_found(self):
        thread = self.client.post("/v1/threads", headers=bearer("alice"), json={}).json()
        self.assertEqual(self.client.get(f"/v1/threads/{thread['id']}", headers=bearer("bob")).status_code, 404)

    def test_open_stream_sends_heartbeat_before_the_interval_elapses(self):
        client = TestClient(create_app(os.path.join(self.directory.name, "heartbeat.sqlite3"), secret=SECRET, adapter=HeartbeatAdapter(), heartbeat_seconds=0.001))
        thread = client.post("/v1/threads", headers=bearer(), json={}).json()
        response = client.post(f"/v1/threads/{thread['id']}/runs", headers=bearer(), json={"client_message_id": "heartbeat", "content": "bekle"})
        self.assertIn(": heartbeat\n\n", response.text)
