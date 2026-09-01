"""In-memory coordination for the one-active-run-per-thread rule."""

from __future__ import annotations

import threading


class RunConflictError(RuntimeError):
    pass


class ActiveRunRegistry:
    def __init__(self):
        self._runs = {}
        self._lock = threading.Lock()

    def start(self, thread_id, run_id, on_cancel=None):
        with self._lock:
            if thread_id in self._runs:
                raise RunConflictError()
            self._runs[thread_id] = (run_id, on_cancel)

    def finish(self, thread_id, run_id):
        with self._lock:
            active = self._runs.get(thread_id)
            if active is not None and active[0] == run_id:
                del self._runs[thread_id]

    def cancel(self, thread_id):
        with self._lock:
            active = self._runs.get(thread_id)
            if active is None:
                return None
            if active[1] is not None:
                active[1]()
            return active[0]
