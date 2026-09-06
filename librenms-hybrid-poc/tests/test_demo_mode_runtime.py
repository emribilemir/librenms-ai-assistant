import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import chat_service.app as app_module
from tests.test_demo_controls import SECRET, bearer


class DemoModeRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.directory.cleanup()

    def client(self, allowed):
        with patch.dict(os.environ, {"AI_DEMO_MODE_ALLOWED": "1" if allowed else "0"}, clear=False):
            app = app_module.create_app(
                os.path.join(self.directory.name, "chat.sqlite3"), secret=SECRET
            )
        return TestClient(app)

    def test_hard_gate_hides_runtime_state_and_rejects_enable(self):
        client = self.client(allowed=False)

        self.assertEqual(client.get("/v1/demo-mode", headers=bearer()).status_code, 404)
        self.assertEqual(
            client.post("/v1/demo-mode", headers=bearer(), json={"enabled": True}).status_code,
            404,
        )

    def test_allowed_instance_starts_off_and_accepts_only_boolean_enablement(self):
        client = self.client(allowed=True)

        self.assertEqual(client.get("/v1/demo-mode", headers=bearer()).json(), {"allowed": True, "enabled": False})
        self.assertEqual(client.post("/v1/demo-mode", headers=bearer(), json={"enabled": True}).json(), {"allowed": True, "enabled": True})
        self.assertEqual(client.post("/v1/demo-mode", headers=bearer(), json={"enabled": "true"}).status_code, 422)
        self.assertEqual(client.post("/v1/demo-mode", headers=bearer(), json={"enabled": True, "path": "/tmp"}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
