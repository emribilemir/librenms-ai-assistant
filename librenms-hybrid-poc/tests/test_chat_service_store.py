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
            self.assertEqual(connection.execute("SELECT version FROM schema_version").fetchone()[0], 1)

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
