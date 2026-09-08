import os
import stat
import unittest
from pathlib import Path
from unittest.mock import patch

from chat_service.app import default_database_path


ROOT = Path(__file__).resolve().parents[2]


class RepositoryOperationsContractTests(unittest.TestCase):
    def test_example_environment_is_non_secret_and_has_no_personal_network_default(self):
        example = (ROOT / ".env.example").read_text(encoding="utf-8")

        for name in (
            "LAB_SSH_HOST",
            "LAB_SSH_USER",
            "LAB_SSH_KEY",
            "LIBRENMS_BASE_URL",
            "LIBRENMS_WEB_URL",
            "AI_BACKEND_HOST",
            "AI_BACKEND_PORT",
            "AI_CHAT_DB",
            "LAB_UTM_VM_ID",
        ):
            self.assertIn(f"{name}=", example)
        self.assertNotIn("192.168.64.", example)
        self.assertNotIn("emir", example.lower())
        self.assertNotIn("codex_utm", example)

    def test_default_chat_database_lives_outside_the_repository(self):
        with patch.dict(os.environ, {}, clear=True):
            path = default_database_path()

        self.assertFalse(path.is_relative_to(ROOT))
        self.assertEqual(path.name, "chat.sqlite3")

    def test_canonical_lab_commands_and_service_unit_are_committed(self):
        for name in ("lab-up", "lab-status", "lab-down"):
            path = ROOT / "scripts" / name
            self.assertTrue(path.is_file(), name)
            self.assertTrue(path.stat().st_mode & stat.S_IXUSR, name)

        up = (ROOT / "scripts" / "lab-up").read_text(encoding="utf-8")
        common = (ROOT / "scripts" / "lab-common").read_text(encoding="utf-8")
        status = (ROOT / "scripts" / "lab-status").read_text(encoding="utf-8")
        down = (ROOT / "scripts" / "lab-down").read_text(encoding="utf-8")
        unit = (ROOT / "ops" / "systemd" / "librenms-snmpsim.service").read_text(encoding="utf-8")
        responder = (ROOT / "ops" / "systemd" / "run-snmpsim").read_text(encoding="utf-8")

        self.assertIn("ConnectTimeout", common)
        self.assertIn("systemctl enable --now", up)
        self.assertIn("clock_skew", up)
        self.assertIn("launchctl bootstrap", up)
        self.assertIn("Application Support", up)
        self.assertIn("rsync -a --delete", up)
        self.assertIn("baseline-up", status)
        self.assertIn("baseline-down", status)
        self.assertIn("health", status)
        self.assertIn("clock skew", status)
        self.assertIn("launchctl bootout", down)
        self.assertIn("User=librenms", unit)
        self.assertIn("Group=librenms", unit)
        self.assertIn("WantedBy=multi-user.target", unit)
        self.assertIn("run-systemd.sh", unit)
        self.assertNotIn("--process-user", responder)

    def test_gitignore_excludes_runtime_database_families(self):
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for pattern in ("*.sqlite3", "*.sqlite3-wal", "*.sqlite3-shm", "*.db"):
            self.assertIn(pattern, ignored)

    def test_ci_runs_offline_python_frontend_build_and_plugin_contract(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

        self.assertIn("python3 -m unittest discover -s librenms-hybrid-poc -p 'test_*.py' -v", workflow)
        self.assertIn("npm test -- --runInBand", workflow)
        self.assertIn("npm run build", workflow)
        self.assertIn("integrations/librenms/AiAssistant/tests", workflow)


if __name__ == "__main__":
    unittest.main()
