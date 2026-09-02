"""The service's deliberately small, ownership-scoped SQLite repository."""

from __future__ import annotations

from contextlib import contextmanager
import sqlite3
import time
import uuid


class ConflictError(RuntimeError):
    pass


class NotFoundError(RuntimeError):
    pass


METRIC_COLUMNS = (
    "planner_ms", "resolver_ms", "backend_ms", "synthesis_ms",
    "time_to_first_token_ms", "time_to_first_visible_chunk_ms", "total_ms",
)


class ChatStore:
    def __init__(self, path: str):
        self.path = path
        self._migrate()

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
        finally:
            connection.close()

    def _migrate(self):
        with self.connection() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER NOT NULL, applied_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS threads (
                    id TEXT PRIMARY KEY, user_sub TEXT NOT NULL, title TEXT NOT NULL,
                    created_at REAL NOT NULL, updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY, thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL, created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
                    client_message_id TEXT NOT NULL, status TEXT NOT NULL,
                    started_at REAL NOT NULL, completed_at REAL, used_fallback INTEGER,
                    planner_ms INTEGER, resolver_ms INTEGER, backend_ms INTEGER,
                    synthesis_ms INTEGER, time_to_first_token_ms INTEGER,
                    time_to_first_visible_chunk_ms INTEGER, total_ms INTEGER,
                    error_stage TEXT, error_code TEXT,
                    UNIQUE(thread_id, client_message_id)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_run_per_thread
                    ON runs(thread_id) WHERE status = 'running';
            """)
            row = connection.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
            if row is None:
                connection.execute("INSERT INTO schema_version(version, applied_at) VALUES(1, ?)", (time.time(),))

    @staticmethod
    def _row(row):
        return dict(row) if row is not None else None

    def create_thread(self, user_sub: str):
        now, thread_id = time.time(), str(uuid.uuid4())
        with self.connection() as connection:
            connection.execute("INSERT INTO threads VALUES(?, ?, '', ?, ?)", (thread_id, user_sub, now, now))
        return {"id": thread_id, "title": "", "created_at": now, "updated_at": now}

    def list_threads(self, user_sub: str):
        with self.connection() as connection:
            return [self._row(row) for row in connection.execute(
                "SELECT id, title, created_at, updated_at FROM threads WHERE user_sub=? ORDER BY updated_at DESC", (user_sub,)
            )]

    def _owned_thread(self, connection, thread_id, user_sub):
        row = connection.execute("SELECT * FROM threads WHERE id=? AND user_sub=?", (thread_id, user_sub)).fetchone()
        if row is None:
            raise NotFoundError()
        return row

    def get_thread(self, thread_id: str, user_sub: str):
        with self.connection() as connection:
            thread = self._owned_thread(connection, thread_id, user_sub)
            messages = [self._row(row) for row in connection.execute("SELECT id, role, content, created_at FROM messages WHERE thread_id=? ORDER BY created_at, rowid", (thread_id,))]
            runs = [self._row(row) for row in connection.execute("SELECT id, client_message_id, status, started_at, completed_at, used_fallback, planner_ms, resolver_ms, backend_ms, synthesis_ms, time_to_first_token_ms, time_to_first_visible_chunk_ms, total_ms, error_stage, error_code FROM runs WHERE thread_id=? ORDER BY started_at", (thread_id,))]
            out = self._row(thread)
            out["messages"], out["runs"] = messages, runs
            return out

    def create_user_message(self, thread_id: str, user_sub: str, content: str):
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            thread = self._owned_thread(connection, thread_id, user_sub)
            now, message_id = time.time(), str(uuid.uuid4())
            title = thread["title"] or " ".join(content.split())[:60]
            connection.execute("INSERT INTO messages VALUES(?, ?, 'user', ?, ?)", (message_id, thread_id, content, now))
            connection.execute("UPDATE threads SET title=?, updated_at=? WHERE id=?", (title, now, thread_id))
            connection.execute("COMMIT")
            return message_id

    def start_run(self, thread_id: str, user_sub: str, client_message_id: str, content: str):
        with self.connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                thread = self._owned_thread(connection, thread_id, user_sub)
                duplicate = connection.execute("SELECT 1 FROM runs WHERE thread_id=? AND client_message_id=?", (thread_id, client_message_id)).fetchone()
                if duplicate:
                    raise ConflictError("duplicate client message")
                active = connection.execute("SELECT 1 FROM runs WHERE thread_id=? AND status='running'", (thread_id,)).fetchone()
                if active:
                    raise ConflictError("active run")
                now, run_id, message_id = time.time(), str(uuid.uuid4()), str(uuid.uuid4())
                title = thread["title"] or " ".join(content.split())[:60]
                connection.execute("INSERT INTO messages VALUES(?, ?, 'user', ?, ?)", (message_id, thread_id, content, now))
                connection.execute("INSERT INTO runs(id, thread_id, client_message_id, status, started_at) VALUES(?, ?, ?, 'running', ?)", (run_id, thread_id, client_message_id, now))
                connection.execute("UPDATE threads SET title=?, updated_at=? WHERE id=?", (title, now, thread_id))
                connection.execute("COMMIT")
                return {"id": run_id, "message_id": message_id}
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise

    def complete_run(self, run_id, status, metrics, *, used_fallback=False, answer=None, error_stage=None, error_code=None):
        values = {key: (metrics or {}).get(key) for key in METRIC_COLUMNS}
        with self.connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute("SELECT thread_id FROM runs WHERE id=?", (run_id,)).fetchone()
                if row is None:
                    raise NotFoundError()
                now, message_id = time.time(), None
                if status == "completed" and answer:
                    message_id = str(uuid.uuid4())
                    connection.execute("INSERT INTO messages VALUES(?, ?, 'assistant', ?, ?)", (message_id, row["thread_id"], answer, now))
                assignments = ", ".join(["status=?", "completed_at=?", "used_fallback=?", *[f"{key}=?" for key in METRIC_COLUMNS], "error_stage=?", "error_code=?"])
                connection.execute(f"UPDATE runs SET {assignments} WHERE id=?", (status, now, int(bool(used_fallback)), *[values[key] for key in METRIC_COLUMNS], error_stage, error_code, run_id))
                connection.execute("COMMIT")
                return message_id
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise

    def update_visible_time(self, run_id, duration_ms, total_ms):
        with self.connection() as connection:
            connection.execute(
                "UPDATE runs SET time_to_first_visible_chunk_ms=?, total_ms=? WHERE id=?",
                (duration_ms, total_ms, run_id),
            )

    def delete_thread(self, thread_id, user_sub):
        with self.connection() as connection:
            self._owned_thread(connection, thread_id, user_sub)
            connection.execute("DELETE FROM threads WHERE id=?", (thread_id,))
