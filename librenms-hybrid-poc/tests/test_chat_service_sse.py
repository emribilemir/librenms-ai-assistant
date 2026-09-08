import base64
import hashlib
import hmac
import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from chat_service.app import create_app


SECRET = b"0123456789abcdef0123456789abcdef"


def bearer(sub="alice", *, demo_control=False):
    now = int(time.time())
    payload = {"sub": sub, "name": sub, "iss": "librenms", "aud": "ai-assistant", "iat": now, "exp": now + 3600}
    if demo_control:
        payload["demo_control"] = True
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
        self.assertNotEqual(completed["metrics"]["time_to_first_visible_chunk_ms"], 12)
        self.assertGreaterEqual(completed["metrics"]["time_to_first_visible_chunk_ms"], 0)
        detail = self.client.get(f"/v1/threads/{thread['id']}", headers=headers).json()
        self.assertEqual(detail["messages"][-1]["content"], "Güvenli yanıt")

    def test_completed_event_carries_and_persists_optional_navigation_targets(self):
        class NavigationAdapter(CompletedAdapter):
            def run(self, content, observer, is_cancelled):
                result = super().run(content, observer, is_cancelled)
                result["navigation_targets"] = [{
                    "kind": "device",
                    "label": "LibreNMS'te cihazı aç",
                    "entity_id": 1,
                    "href": "/device/1",
                }]
                return result

        client = TestClient(create_app(
            os.path.join(self.directory.name, "navigation.sqlite3"),
            secret=SECRET,
            adapter=NavigationAdapter(),
        ))
        headers = bearer()
        thread = client.post("/v1/threads", headers=headers, json={}).json()
        response = client.post(
            f"/v1/threads/{thread['id']}/runs",
            headers=headers,
            json={"client_message_id": "navigation", "content": "durum nedir?"},
        )
        completed = json.loads([
            line[6:] for line in response.text.splitlines() if line.startswith("data:")
        ][-1])

        self.assertEqual(completed["navigation_targets"], [{
            "kind": "device",
            "label": "LibreNMS'te cihazı aç",
            "entity_id": 1,
            "href": "/device/1",
        }])
        detail = client.get(f"/v1/threads/{thread['id']}", headers=headers).json()
        self.assertEqual(detail["messages"][-1]["navigation_targets"], completed["navigation_targets"])

    def test_completed_event_carries_and_persists_structured_result(self):
        structured_result = {
            "kind": "ports",
            "device": {"device_id": 1, "hostname": "lab-j9772a-02"},
            "ports": [{"device_id": 1, "port_id": 2, "ifIndex": 2, "admin_status": "up", "oper_status": "down"}],
        }

        class StructuredAdapter(CompletedAdapter):
            def run(self, content, observer, is_cancelled):
                result = super().run(content, observer, is_cancelled)
                result["structured_result"] = structured_result
                return result

        client = TestClient(create_app(
            os.path.join(self.directory.name, "structured.sqlite3"),
            secret=SECRET,
            adapter=StructuredAdapter(),
        ))
        headers = bearer()
        thread = client.post("/v1/threads", headers=headers, json={}).json()
        response = client.post(
            f"/v1/threads/{thread['id']}/runs",
            headers=headers,
            json={"client_message_id": "structured", "content": "down portlar?"},
        )
        completed = json.loads([
            line[6:] for line in response.text.splitlines() if line.startswith("data:")
        ][-1])

        self.assertEqual(completed["structured_result"], structured_result)
        detail = client.get(f"/v1/threads/{thread['id']}", headers=headers).json()
        self.assertEqual(detail["messages"][-1]["structured_result"], structured_result)

    def test_demo_mode_off_drops_adapter_inspection_from_completed_transport(self):
        class InspectionAdapter(CompletedAdapter):
            def run(self, content, observer, is_cancelled):
                result = super().run(content, observer, is_cancelled)
                result["inspection"] = {"route": "ports"}
                return result

        with patch.dict(os.environ, {"AI_DEMO_MODE_ALLOWED": "0"}):
            client = TestClient(create_app(
                os.path.join(self.directory.name, "inspection-off.sqlite3"),
                secret=SECRET,
                adapter=InspectionAdapter(),
            ))
        headers = bearer()
        thread = client.post("/v1/threads", headers=headers, json={}).json()
        response = client.post(
            f"/v1/threads/{thread['id']}/runs",
            headers=headers,
            json={"client_message_id": "inspection-off", "content": "durum nedir?"},
        )
        completed = json.loads([
            line[6:] for line in response.text.splitlines() if line.startswith("data:")
        ][-1])

        self.assertNotIn("inspection", completed)

    def test_demo_mode_on_carries_adapter_inspection_without_persisting_it(self):
        inspection = {"route": "ports", "synthesis_llm_called": False}

        class InspectionAdapter(CompletedAdapter):
            def run(self, content, observer, is_cancelled):
                result = super().run(content, observer, is_cancelled)
                result["inspection"] = inspection
                return result

        with patch.dict(os.environ, {"AI_DEMO_MODE_ALLOWED": "1"}):
            client = TestClient(create_app(
                os.path.join(self.directory.name, "inspection-on.sqlite3"),
                secret=SECRET,
                adapter=InspectionAdapter(),
            ))
        headers = bearer(demo_control=True)
        self.assertEqual(
            client.post("/v1/demo-mode", headers=headers, json={"enabled": True}).status_code,
            200,
        )
        thread = client.post("/v1/threads", headers=headers, json={}).json()
        response = client.post(
            f"/v1/threads/{thread['id']}/runs",
            headers=headers,
            json={"client_message_id": "inspection-on", "content": "durum nedir?"},
        )
        completed = json.loads([
            line[6:] for line in response.text.splitlines() if line.startswith("data:")
        ][-1])

        self.assertIn("inspection", completed)
        self.assertEqual(completed["inspection"], inspection)
        detail = client.get(f"/v1/threads/{thread['id']}", headers=headers).json()
        self.assertNotIn("inspection", detail["messages"][-1])

    def test_approved_answer_uses_multiple_lossless_delta_frames(self):
        answer = (
            "Cihaz erişilebilir durumda. İki yönetimsel olarak açık port bağlantı "
            "durumunda down görünüyor. Aktif kritik alarm bulunmuyor."
        )

        class LongAnswerAdapter(CompletedAdapter):
            def run(self, content, observer, is_cancelled):
                result = super().run(content, observer, is_cancelled)
                result["answer"] = answer
                return result

        client = TestClient(
            create_app(
                os.path.join(self.directory.name, "chunks.sqlite3"),
                secret=SECRET,
                adapter=LongAnswerAdapter(),
            )
        )
        headers = bearer()
        thread = client.post("/v1/threads", headers=headers, json={}).json()

        response = client.post(
            f"/v1/threads/{thread['id']}/runs",
            headers=headers,
            json={"client_message_id": "chunks", "content": "durum nedir?"},
        )
        frames = [frame for frame in response.text.split("\n\n") if frame]
        deltas = [
            json.loads(frame.split("data: ", 1)[1])["delta"]
            for frame in frames
            if frame.startswith("event: answer.delta\n")
        ]

        self.assertGreater(len(deltas), 1)
        self.assertEqual("".join(deltas), answer)
        self.assertTrue(frames[-1].startswith("event: completed\n"))
        detail = client.get(f"/v1/threads/{thread['id']}", headers=headers).json()
        self.assertEqual(detail["messages"][-1]["content"], answer)

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

    def test_stage_error_keeps_the_pipeline_classification(self):
        class PlannerFailureAdapter:
            def run(self, content, observer, is_cancelled):
                return {"error": {"stage": "planner", "code": "planner_invalid_output", "retryable": True, "message": "Plan oluşturulamadı."}, "metrics": {}}
        client = TestClient(create_app(os.path.join(self.directory.name, "failure.sqlite3"), secret=SECRET, adapter=PlannerFailureAdapter()))
        thread = client.post("/v1/threads", headers=bearer(), json={}).json()
        response = client.post(f"/v1/threads/{thread['id']}/runs", headers=bearer(), json={"client_message_id": "failure", "content": "bekle"})
        payload = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data:")]
        self.assertIn({"run_id": payload[0]["run_id"], "stage": "planner", "code": "planner_invalid_output", "retryable": True, "message": "Plan oluşturulamadı."}, payload)

    def test_visible_metric_includes_required_persistence_before_delta(self):
        original = __import__("chat_service.store", fromlist=["ChatStore"]).ChatStore.complete_run
        def delayed(store, *args, **kwargs):
            time.sleep(0.02)
            return original(store, *args, **kwargs)
        with patch("chat_service.app.ChatStore.complete_run", delayed):
            headers = bearer()
            thread = self.client.post("/v1/threads", headers=headers, json={}).json()
            response = self.client.post(f"/v1/threads/{thread['id']}/runs", headers=headers, json={"client_message_id": "delay", "content": "durum"})
        completed = json.loads([line[6:] for line in response.text.splitlines() if line.startswith("data:")][-1])
        self.assertGreaterEqual(completed["metrics"]["time_to_first_visible_chunk_ms"], 20)
        self.assertGreaterEqual(
            completed["metrics"]["total_ms"],
            completed["metrics"]["time_to_first_visible_chunk_ms"],
        )
        detail = self.client.get(f"/v1/threads/{thread['id']}", headers=headers).json()
        self.assertEqual(detail["runs"][0]["total_ms"], completed["metrics"]["total_ms"])

    def test_storage_failure_after_pipeline_stage_still_emits_terminal_storage_error(self):
        original = __import__("chat_service.store", fromlist=["ChatStore"]).ChatStore.complete_run
        calls = [0]
        def reject_once(store, *args, **kwargs):
            calls[0] += 1
            if calls[0] == 1:
                raise RuntimeError("disk full")
            return original(store, *args, **kwargs)
        with patch("chat_service.app.ChatStore.complete_run", reject_once):
            headers = bearer()
            thread = self.client.post("/v1/threads", headers=headers, json={}).json()
            response = self.client.post(f"/v1/threads/{thread['id']}/runs", headers=headers, json={"client_message_id": "storage", "content": "durum"})
        data = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data:")]
        self.assertIn({"run_id": data[0]["run_id"], "stage": "storage", "code": "storage_failed", "retryable": True, "message": "Sonuç kaydedilemedi."}, data)

    def test_visible_metric_update_failure_keeps_accepted_run_and_message_completed(self):
        with patch("chat_service.app.ChatStore.update_visible_time", side_effect=RuntimeError("metric disk error")):
            headers = bearer()
            thread = self.client.post("/v1/threads", headers=headers, json={}).json()
            response = self.client.post(f"/v1/threads/{thread['id']}/runs", headers=headers, json={"client_message_id": "metric-failure", "content": "durum"})
        events = [line[7:] for line in response.text.splitlines() if line.startswith("event:")]
        self.assertEqual(events[-2:], ["answer.delta", "completed"])
        detail = self.client.get(f"/v1/threads/{thread['id']}", headers=headers).json()
        self.assertEqual(detail["runs"][0]["status"], "completed")
        self.assertEqual([message["role"] for message in detail["messages"]], ["user", "assistant"])

    def test_first_delta_is_yielded_before_visible_metric_update(self):
        from chat_service.app import _sse as original_sse
        from chat_service.store import ChatStore
        order = []
        def traced_sse(event, data):
            if event == "answer.delta":
                order.append("delta")
            return original_sse(event, data)
        original_update = ChatStore.update_visible_time
        def traced_update(store, *args):
            order.append("metric")
            return original_update(store, *args)
        with patch("chat_service.app._sse", traced_sse), patch("chat_service.app.ChatStore.update_visible_time", traced_update):
            headers = bearer()
            thread = self.client.post("/v1/threads", headers=headers, json={}).json()
            self.client.post(f"/v1/threads/{thread['id']}/runs", headers=headers, json={"client_message_id": "ordering", "content": "durum"})
        self.assertLess(order.index("delta"), order.index("metric"))

    def test_empty_adapter_answer_uses_safe_persisted_fallback(self):
        class EmptyAdapter:
            def run(self, content, observer, is_cancelled):
                return {"answer": "", "used_fallback": True, "metrics": {}}
        client = TestClient(create_app(os.path.join(self.directory.name, "empty.sqlite3"), secret=SECRET, adapter=EmptyAdapter()))
        headers = bearer()
        thread = client.post("/v1/threads", headers=headers, json={}).json()
        client.post(f"/v1/threads/{thread['id']}/runs", headers=headers, json={"client_message_id": "empty", "content": "durum"})
        detail = client.get(f"/v1/threads/{thread['id']}", headers=headers).json()
        self.assertEqual(detail["messages"][-1]["content"], "İşlem desteklenmiyor.")
