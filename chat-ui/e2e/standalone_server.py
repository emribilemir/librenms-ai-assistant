"""Local-only FastAPI host for browser acceptance tests.

The server deliberately uses the production Task 1 routes, SSE response, run
registry and SQLite store.  Its only replacement is a deterministic pipeline
adapter: it emits the same observer boundaries as the production adapter while
never connecting to LibreNMS, Qwen, UTM, or another external service.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import os
from pathlib import Path
import sys
import threading
import time

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY / "librenms-hybrid-poc"))

import uvicorn
from fastapi import Response

from chat_service.app import create_app


def metrics(*, planner=None, resolver=None, backend=None, synthesis=None):
    """Build coherent component timings without ever summing total_ms twice."""
    values = {
        "planner_ms": planner,
        "resolver_ms": resolver,
        "backend_ms": backend,
        "synthesis_ms": synthesis,
        "time_to_first_token_ms": None,
        "time_to_first_visible_chunk_ms": None,
    }
    values["total_ms"] = sum(value for key, value in values.items() if key.endswith("_ms") and isinstance(value, int))
    return values


class DeterministicPipelineAdapter:
    """A controlled adapter seam, never a frontend or HTTP mock."""

    def __init__(self):
        self._attempts = defaultdict(int)
        self._retry_failure_release = threading.Event()
        self._queue_release = threading.Event()

    def release_retryable_failure(self):
        self._retry_failure_release.set()

    def release_queue_barrier(self):
        self._queue_release.set()

    @staticmethod
    def list_devices():
        """Expose a stable live-inventory shape through the production route."""
        return [
            {"hostname": "lab-j9775a-01", "status": 1},
            {"hostname": "lab-j9776a-01", "status": 1},
            {"hostname": "lab-offline-01", "status": 0},
        ]

    @staticmethod
    def _stage(observer, is_cancelled, stage, duration):
        if is_cancelled():
            return False
        observer(stage, "started", None)
        # This small service-side yield lets the browser observe a genuine SSE
        # stage before the next real service boundary is entered.
        time.sleep(0.08)
        if is_cancelled():
            return False
        observer(stage, "completed", duration)
        return True

    @staticmethod
    def _result(answer, *, fallback=False, planner=7, resolver=11, backend=None, synthesis=None):
        return {
            "answer": answer,
            "used_fallback": fallback,
            "metrics": metrics(planner=planner, resolver=resolver, backend=backend, synthesis=synthesis),
        }

    def run(self, content, observer, is_cancelled):
        question = content.casefold()
        if not self._stage(observer, is_cancelled, "planner", 7):
            return {"cancelled": True, "metrics": metrics()}

        if "cancel after planner" in question:
            # The browser cancellation closes the actual fetch stream.  The
            # Task 1 disconnect predicate is repeatedly consulted here, so no
            # resolver boundary or answer can be produced after cancellation.
            while not is_cancelled():
                time.sleep(0.01)
            return {"cancelled": True, "metrics": metrics(planner=7)}

        if "queue barrier" in question:
            self._queue_release.clear()
            while not self._queue_release.wait(0.02):
                if is_cancelled():
                    return {"cancelled": True, "metrics": metrics(planner=7)}

        if not self._stage(observer, is_cancelled, "resolver", 11):
            return {"cancelled": True, "metrics": metrics(planner=7)}
        if "no-match" in question:
            return self._result("No monitored device matches that name.")
        if "ambiguous" in question:
            return self._result("Several matching devices need clarification.")
        if "retryable" in question:
            self._attempts[content] += 1
            if self._attempts[content] == 1:
                # A backend outage starts the real LibreNMS boundary but never
                # completes it. The service then emits its librenms-scoped
                # terminal error, matching the production failure contract.
                self._retry_failure_release.clear()
                observer("librenms", "started", None)
                while not self._retry_failure_release.wait(0.02):
                    if is_cancelled():
                        return {"cancelled": True, "metrics": metrics(planner=7, resolver=11)}
                return {
                    "error": {
                        "stage": "librenms",
                        "code": "backend_unavailable",
                        "retryable": True,
                        "message": "LibreNMS is temporarily unavailable.",
                    },
                    "metrics": metrics(planner=7, resolver=11, backend=13),
                }
        if not self._stage(observer, is_cancelled, "librenms", 13):
            return {"cancelled": True, "metrics": metrics(planner=7, resolver=11)}
        if "fallback" in question:
            if not self._stage(observer, is_cancelled, "synthesis", 17):
                return {"cancelled": True, "metrics": metrics(planner=7, resolver=11, backend=13)}
            return self._result("Safe evidence fallback summary.", fallback=True, backend=13, synthesis=17)
        if "retryable" in question:
            return self._result("Backend recovered on retry.", backend=13)
        if "streaming cadence" in question:
            lines = [
                f"Port grubu {index:02d}: canlı telemetri incelendi; durum normal ve gözlenen sayaçlar tutarlı."
                for index in range(1, 25)
            ]
            return self._result("\n\n".join(lines), backend=13)
        if "navigation persistence" in question:
            result = self._result("Validated device result.", backend=13)
            result["navigation_targets"] = [{
                "kind": "device",
                "label": "LibreNMS'te cihazı aç",
                "entity_id": 1,
                "href": "/device/1",
            }]
            return result
        if "structured port list" in question:
            result = self._result(
                "Port 2: admin=up oper=down (Test-Down)\nPort 3: admin=down oper=down (Disabled)",
                backend=13,
            )
            result["navigation_targets"] = [
                {"kind": "port", "label": "Port detayını aç", "entity_id": 41, "href": "/device/7/port/port=41"},
                {"kind": "port", "label": "Port detayını aç", "entity_id": 42, "href": "/device/7/port/port=42"},
            ]
            result["structured_result"] = {
                "kind": "ports",
                "device": {"device_id": 7, "hostname": "lab-j9772a-02"},
                "ports": [
                    {"device_id": 7, "port_id": 41, "ifIndex": 2, "ifName": "2", "ifAlias": "Test-Down", "admin_status": "up", "oper_status": "down"},
                    {"device_id": 7, "port_id": 42, "ifIndex": 3, "ifName": "3", "ifAlias": "Disabled", "admin_status": "down", "oper_status": "down"},
                ],
            }
            return result
        if "malformed navigation" in question:
            result = self._result("Validated result without an action.", backend=13)
            result["navigation_targets"] = [{
                "kind": "device",
                "label": "Unsafe",
                "entity_id": 1,
                "href": "https://example.invalid/write",
            }]
            return result
        return self._result("Deterministic standalone result.", backend=13)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument("--database", required=True)
    args = parser.parse_args()
    database = Path(args.database)
    database.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-shm", "-wal"):
        database.with_name(database.name + suffix).unlink(missing_ok=True)
    os.environ["AI_DEV_AUTH"] = "1"
    adapter = DeterministicPipelineAdapter()
    app = create_app(
        str(database),
        # The standalone dev-identity gate never verifies a signed token, but the
        # application factory still requires a valid-sized verifier secret. Keep
        # it ephemeral so the fixture does not embed a reusable credential.
        secret=os.urandom(32),
        adapter=adapter,
    )

    @app.middleware("http")
    async def standalone_development_identity(request, call_next):
        """Route the fixture-only placeholder through the service's dev gate."""
        if request.headers.get("authorization") == "Bearer standalone-development":
            request.scope["headers"] = [
                (key, value)
                for key, value in request.scope["headers"]
                if key.lower() != b"authorization"
            ]
        return await call_next(request)

    @app.post("/__test__/release-retryable-failure", status_code=204)
    def release_retryable_failure():
        """Test-only deterministic barrier; no production route is changed."""
        adapter.release_retryable_failure()
        return Response(status_code=204)

    @app.post("/__test__/release-queue-barrier", status_code=204)
    def release_queue_barrier():
        """Release the first request so browser tests can observe FIFO drain."""
        adapter.release_queue_barrier()
        return Response(status_code=204)

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
