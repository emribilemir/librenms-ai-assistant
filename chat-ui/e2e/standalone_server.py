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
import time

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY / "librenms-hybrid-poc"))

import uvicorn

from chat_service.app import create_app


METRICS = {
    "planner_ms": 7,
    "resolver_ms": 11,
    "backend_ms": 13,
    "synthesis_ms": None,
    "time_to_first_token_ms": None,
    "time_to_first_visible_chunk_ms": None,
    "total_ms": 31,
}


class DeterministicPipelineAdapter:
    """A controlled adapter seam, never a frontend or HTTP mock."""

    def __init__(self):
        self._attempts = defaultdict(int)

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
    def _result(answer, *, fallback=False, synthesis=None):
        metrics = dict(METRICS)
        metrics["synthesis_ms"] = synthesis
        metrics["total_ms"] = sum(value for value in metrics.values() if isinstance(value, int))
        return {"answer": answer, "used_fallback": fallback, "metrics": metrics}

    def run(self, content, observer, is_cancelled):
        question = content.casefold()
        if not self._stage(observer, is_cancelled, "planner", 7):
            return {"cancelled": True, "metrics": dict(METRICS)}

        if "cancel after planner" in question:
            # The browser cancellation closes the actual fetch stream.  The
            # Task 1 disconnect predicate is repeatedly consulted here, so no
            # resolver boundary or answer can be produced after cancellation.
            while not is_cancelled():
                time.sleep(0.01)
            return {"cancelled": True, "metrics": dict(METRICS)}

        if "retryable" in question:
            self._attempts[content] += 1
            if self._attempts[content] == 1:
                return {
                    "error": {
                        "stage": "librenms",
                        "code": "backend_unavailable",
                        "retryable": True,
                        "message": "LibreNMS is temporarily unavailable.",
                    },
                    "metrics": dict(METRICS),
                }

        if not self._stage(observer, is_cancelled, "resolver", 11):
            return {"cancelled": True, "metrics": dict(METRICS)}
        if "no-match" in question:
            return self._result("No monitored device matches that name.")
        if "ambiguous" in question:
            return self._result("Several matching devices need clarification.")
        if not self._stage(observer, is_cancelled, "librenms", 13):
            return {"cancelled": True, "metrics": dict(METRICS)}
        if "fallback" in question:
            if not self._stage(observer, is_cancelled, "synthesis", 17):
                return {"cancelled": True, "metrics": dict(METRICS)}
            return self._result("Safe evidence fallback summary.", fallback=True, synthesis=17)
        if "retryable" in question:
            return self._result("Backend recovered on retry.")
        return self._result("Deterministic standalone result.")


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
    app = create_app(
        str(database),
        # The standalone dev-identity gate never verifies a signed token, but the
        # application factory still requires a valid-sized verifier secret. Keep
        # it ephemeral so the fixture does not embed a reusable credential.
        secret=os.urandom(32),
        adapter=DeterministicPipelineAdapter(),
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

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
