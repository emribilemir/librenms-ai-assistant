import os
import sqlite3
import tempfile
import unittest

from chat_service.store import ChatStore, ConflictError, NotFoundError


class ChatStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.directory.name, "chat.sqlite3")
        self.store = ChatStore(self.path)

    def tearDown(self):
        self.directory.cleanup()

    def test_database_enables_wal_foreign_keys_busy_timeout_and_schema_version(self):
        with self.store.connection() as connection:
            self.assertEqual(connection.execute("PRAGMA journal_mode").fetchone()[0].lower(), "wal")
            self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertGreaterEqual(connection.execute("PRAGMA busy_timeout").fetchone()[0], 5000)
            self.assertEqual(connection.execute("SELECT version FROM schema_version").fetchone()[0], 3)

    def test_create_thread_reuses_a_pristine_thread_but_allows_a_new_one_after_content(self):
        first = self.store.create_thread("owner")
        duplicate = self.store.create_thread("owner")

        self.assertEqual(duplicate["id"], first["id"])
        self.assertEqual(len(self.store.list_threads("owner")), 1)

        self.store.create_user_message(first["id"], "owner", "first question")
        second = self.store.create_thread("owner")

        self.assertNotEqual(second["id"], first["id"])
        self.assertEqual(len(self.store.list_threads("owner")), 2)

    def test_running_thread_is_not_reused_as_pristine(self):
        first = self.store.create_thread("owner")
        self.store.start_run(first["id"], "owner", "client-1", "first question")

        second = self.store.create_thread("owner")

        self.assertNotEqual(second["id"], first["id"])

    def test_titles_are_whitespace_normalized_and_limited_to_sixty_unicode_characters(self):
        thread = self.store.create_thread("owner")
        text = "  first\n question  " + ("x" * 80)
        self.store.create_user_message(thread["id"], "owner", text)
        self.assertEqual(self.store.get_thread(thread["id"], "owner")["title"], ("first question " + "x" * 80)[:60])

    def test_foreign_user_cannot_read_a_thread(self):
        thread = self.store.create_thread("owner")
        with self.assertRaises(NotFoundError):
            self.store.get_thread(thread["id"], "other")

    def test_duplicate_client_message_id_conflicts_before_creating_message_or_run(self):
        thread = self.store.create_thread("owner")
        self.store.start_run(thread["id"], "owner", "client-1", "first")
        with self.assertRaises(ConflictError):
            self.store.start_run(thread["id"], "owner", "client-1", "second")
        detail = self.store.get_thread(thread["id"], "owner")
        self.assertEqual(len(detail["messages"]), 1)
        self.assertEqual(len(detail["runs"]), 1)

    def test_failed_run_update_rolls_back_assistant_message(self):
        thread = self.store.create_thread("owner")
        run = self.store.start_run(thread["id"], "owner", "client-1", "first")
        with self.store.connection() as connection:
            connection.execute("CREATE TRIGGER reject_run_update BEFORE UPDATE ON runs BEGIN SELECT RAISE(ABORT, 'no update'); END")
        with self.assertRaises(sqlite3.DatabaseError):
            self.store.complete_run(run["id"], "completed", {}, answer="must not persist")
        detail = self.store.get_thread(thread["id"], "owner")
        self.assertEqual([message["role"] for message in detail["messages"]], ["user"])

    def test_completed_answer_persists_bounded_navigation_targets(self):
        thread = self.store.create_thread("owner")
        run = self.store.start_run(thread["id"], "owner", "client-1", "question")
        targets = [{
            "kind": "device",
            "label": "LibreNMS'te cihazı aç",
            "entity_id": 1,
            "href": "/device/1",
        }]

        self.store.complete_run(run["id"], "completed", {}, answer="answer", navigation_targets=targets)

        self.assertEqual(self.store.get_thread(thread["id"], "owner")["messages"][-1]["navigation_targets"], targets)

    def test_completed_answer_persists_bounded_structured_result(self):
        thread = self.store.create_thread("owner")
        run = self.store.start_run(thread["id"], "owner", "client-1", "question")
        structured_result = {
            "kind": "ports",
            "device": {"device_id": 1, "hostname": "lab-j9772a-02"},
            "ports": [{"device_id": 1, "port_id": 2, "ifIndex": 2, "admin_status": "up", "oper_status": "down"}],
        }

        self.store.complete_run(run["id"], "completed", {}, answer="answer", structured_result=structured_result)

        self.assertEqual(self.store.get_thread(thread["id"], "owner")["messages"][-1]["structured_result"], structured_result)

    def test_completed_answer_persists_structured_alert_rows_and_empty_state(self):
        for index, alerts in enumerate((
            [{"device_id": 1, "alert_id": 88, "severity": "critical", "name": "Port status"}],
            [],
        )):
            thread = self.store.create_thread("owner")
            run = self.store.start_run(thread["id"], "owner", f"client-{index}", "question")
            structured_result = {
                "kind": "alerts",
                "device": {"device_id": 1, "hostname": "lab-j9772a-01"},
                "alerts": alerts,
            }

            self.store.complete_run(run["id"], "completed", {}, answer="answer", structured_result=structured_result)

            self.assertEqual(self.store.get_thread(thread["id"], "owner")["messages"][-1]["structured_result"], structured_result)
