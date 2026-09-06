"""FastAPI REST and SSE surface for the read-only AI assistant."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys
import threading
import time

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from .auth import AuthError, Identity, IdentityVerifier
from .logging import RestrictedJsonLogger
from .pipeline_adapter import PipelineAdapter
from .runs import ActiveRunRegistry, RunConflictError
from .store import ChatStore, ConflictError, NotFoundError
from .suggestions import build_suggestions


DEMO_SCENARIO_IDS = (
    "port-down",
    "port-up",
    "location-change",
    "device-down-up",
    "port-down-up-event",
)


def load_simulation_runner():
    path = Path(__file__).resolve().parents[2] / "simulation" / "run.py"
    spec = importlib.util.spec_from_file_location("emr55_simulation_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("simulation runner is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def bounded_demo_result(result, scenario_id):
    events = []
    for event in (result.get("events") or [])[:4]:
        events.append(
            {
                "event_id": event.get("event_id"),
                "timestamp": event.get("timestamp"),
                "message": str(event.get("message") or "")[:500],
            }
        )
    return {
        "scenario_id": scenario_id,
        "snmp_state_changed": bool(result.get("snmp_state_changed")),
        "librenms_completed": bool(result.get("librenms_completed")),
        "verified": str(result.get("verified") or "")[:500],
        "events": events,
        "example_question": str(result.get("example_question") or "")[:500],
    }


def _sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n"


def iter_answer_chunks(answer, max_chars=72):
    """Split accepted text without changing the text reconstructed by clients."""
    start = 0
    while start < len(answer):
        end = min(len(answer), start + max_chars)
        if end < len(answer):
            boundary = max(
                answer.rfind(" ", start + 1, end + 1),
                answer.rfind("\n", start + 1, end + 1),
            )
            if boundary > start:
                end = boundary + 1
        yield answer[start:end]
        start = end


def create_app(database_path=None, *, secret=None, adapter=None, logger=None,
               heartbeat_seconds=15):
    secret = secret if secret is not None else os.environ.get("AI_ASSISTANT_SHARED_SECRET", "").encode()
    verifier = IdentityVerifier(secret)
    store = ChatStore(database_path or os.environ.get("AI_CHAT_DB", "ai-chat.sqlite3"))
    demo_mode = os.environ.get("AI_DEMO_MODE") == "1"
    adapter = adapter or PipelineAdapter(include_inspection=demo_mode)
    registry = ActiveRunRegistry()
    logger = logger or RestrictedJsonLogger(sys.stderr)
    app = FastAPI()
    demo_runner = load_simulation_runner() if demo_mode else None
    demo_lock = threading.Lock()

    def identity(authorization: str | None):
        if authorization is None and os.environ.get("AI_DEV_AUTH") == "1":
            return Identity("development", "Development")
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "authentication required")
        try:
            return verifier.verify(authorization[7:])
        except AuthError:
            raise HTTPException(401, "authentication required") from None

    def owned(thread_id, user):
        try:
            return store.get_thread(thread_id, user.sub)
        except NotFoundError:
            raise HTTPException(404, "thread not found") from None

    @app.post("/v1/threads", status_code=201)
    async def create_thread(request: Request, authorization: str | None = Header(default=None)):
        user = identity(authorization)
        try:
            body = await request.json()
        except json.JSONDecodeError:
            raise HTTPException(400, "malformed JSON") from None
        if body != {}:
            raise HTTPException(400, "request must be an empty object")
        return store.create_thread(user.sub)

    @app.get("/v1/threads")
    async def list_threads(authorization: str | None = Header(default=None)):
        user = identity(authorization)
        return store.list_threads(user.sub)

    @app.get("/v1/suggestions")
    async def list_suggestions(authorization: str | None = Header(default=None)):
        identity(authorization)
        try:
            suggestion_source = getattr(
                adapter, "list_suggestion_devices", adapter.list_devices
            )
            devices = suggestion_source()
        except Exception:
            raise HTTPException(
                503,
                {
                    "code": "librenms_unavailable",
                    "message": "Canlı cihaz önerileri şu anda alınamıyor.",
                },
            ) from None
        return {"suggestions": build_suggestions(devices)}

    if demo_mode:
        @app.get("/v1/demo/scenarios")
        async def list_demo_scenarios(authorization: str | None = Header(default=None)):
            identity(authorization)
            metadata = demo_runner.load_scenarios()
            return {
                "scenarios": [
                    {
                        "id": scenario_id,
                        "label": metadata[scenario_id]["label"],
                        "example_question": metadata[scenario_id]["example_ai_question"],
                    }
                    for scenario_id in DEMO_SCENARIO_IDS
                ]
            }

        @app.post("/v1/demo/scenarios")
        async def run_demo_scenario(request: Request, authorization: str | None = Header(default=None)):
            identity(authorization)
            try:
                body = await request.json()
            except json.JSONDecodeError:
                raise HTTPException(400, "malformed JSON") from None
            if not isinstance(body, dict) or set(body) != {"scenario_id"}:
                raise HTTPException(400, "request must contain only scenario_id")
            scenario_id = body.get("scenario_id")
            if not isinstance(scenario_id, str) or scenario_id not in DEMO_SCENARIO_IDS:
                raise HTTPException(422, "unsupported scenario_id")
            if not demo_lock.acquire(blocking=False):
                raise HTTPException(409, "a demo action is already running")
            try:
                result = await asyncio.to_thread(demo_runner.execute_scenario, scenario_id)
                return bounded_demo_result(result, scenario_id)
            except Exception:
                raise HTTPException(
                    503,
                    {"code": "demo_scenario_failed", "message": "Scenario could not be completed."},
                ) from None
            finally:
                demo_lock.release()

        @app.post("/v1/demo/reset")
        async def reset_demo(authorization: str | None = Header(default=None)):
            identity(authorization)
            if not demo_lock.acquire(blocking=False):
                raise HTTPException(409, "a demo action is already running")
            try:
                result = await asyncio.to_thread(demo_runner.reset_baseline)
                return {
                    "scenario_id": "reset",
                    "snmp_state_changed": bool(result.get("changed")),
                    "librenms_completed": True,
                    "verified": "Baseline restored",
                    "events": [],
                    "example_question": "",
                }
            except Exception:
                raise HTTPException(
                    503,
                    {"code": "demo_reset_failed", "message": "Lab reset could not be completed."},
                ) from None
            finally:
                demo_lock.release()

    @app.get("/v1/threads/{thread_id}")
    async def get_thread(thread_id: str, authorization: str | None = Header(default=None)):
        return owned(thread_id, identity(authorization))

    @app.delete("/v1/threads/{thread_id}", status_code=204)
    async def delete_thread(thread_id: str, authorization: str | None = Header(default=None)):
        user = identity(authorization)
        owned(thread_id, user)
        registry.cancel(thread_id)
        store.delete_thread(thread_id, user.sub)
        return Response(status_code=204)

    @app.post("/v1/threads/{thread_id}/runs")
    async def create_run(thread_id: str, request: Request, authorization: str | None = Header(default=None)):
        user = identity(authorization)
        owned(thread_id, user)
        try:
            body = await request.json()
        except json.JSONDecodeError:
            raise HTTPException(400, "malformed JSON") from None
        if not isinstance(body, dict) or not isinstance(body.get("client_message_id"), str) or not body["client_message_id"].strip():
            raise HTTPException(422, "client_message_id is required")
        content = body.get("content")
        if not isinstance(content, str) or not content.strip() or len(content) > 8000:
            raise HTTPException(422, "content must be 1 to 8000 non-whitespace characters")
        try:
            started = store.start_run(thread_id, user.sub, body["client_message_id"], content)
            cancelled = threading.Event()
            registry.start(thread_id, started["id"], cancelled.set)
        except (ConflictError, RunConflictError):
            raise HTTPException(409, "run already exists") from None

        async def stream():
            queue = asyncio.Queue()
            loop = asyncio.get_running_loop()
            stream_started = time.perf_counter()
            task = None
            event_waiter = None
            terminal = False
            last_stage = "internal"
            work = "pipeline"
            metrics = {key: None for key in ("planner_ms", "resolver_ms", "backend_ms", "synthesis_ms", "time_to_first_token_ms", "time_to_first_visible_chunk_ms", "total_ms")}

            def persist_failure(stage, code, failure_metrics):
                try:
                    store.complete_run(started["id"], "failed", failure_metrics, error_stage=stage, error_code=code)
                except Exception:
                    pass
                try:
                    logger.write(user_id=user.sub, thread_id=thread_id, run_id=started["id"], route="/v1/threads/{id}/runs", stage=stage, error_code=code)
                except Exception:
                    pass

            def observer(stage, state, duration):
                nonlocal last_stage
                last_stage = stage
                if cancelled.is_set():
                    return
                payload = {"run_id": started["id"], "stage": stage}
                if state == "completed":
                    payload["duration_ms"] = max(0, int(duration or 0))
                loop.call_soon_threadsafe(queue.put_nowait, (f"{stage}.{state}", payload))

            try:
                yield _sse("run.started", {"run_id": started["id"], "thread_id": thread_id, "client_message_id": body["client_message_id"]})
                if await request.is_disconnected():
                    cancelled.set()
                task = asyncio.create_task(asyncio.to_thread(adapter.run, content, observer, cancelled.is_set))
                while not task.done():
                    if await request.is_disconnected():
                        cancelled.set()
                    event_waiter = asyncio.create_task(queue.get())
                    done, _ = await asyncio.wait(
                        (task, event_waiter), timeout=heartbeat_seconds,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if event_waiter in done:
                        event, payload = event_waiter.result()
                        yield _sse(event, payload)
                    else:
                        event_waiter.cancel()
                        try:
                            await event_waiter
                        except asyncio.CancelledError:
                            pass
                        if not task.done():
                            if await request.is_disconnected():
                                cancelled.set()
                            yield ": heartbeat\n\n"
                while not queue.empty():
                    event, payload = queue.get_nowait()
                    yield _sse(event, payload)
                result = task.result()
                metrics = result.get("metrics", {})
                if result.get("cancelled") or cancelled.is_set():
                    work = "storage"
                    store.complete_run(started["id"], "cancelled", metrics, error_stage="cancellation", error_code="cancelled")
                    yield _sse("completed", {"run_id": started["id"], "status": "cancelled", "used_fallback": False, "metrics": metrics})
                    terminal = True
                    return
                if result.get("error"):
                    error = result["error"]
                    work = "storage"
                    persist_failure(error["stage"], error["code"], metrics)
                    yield _sse("error", {"run_id": started["id"], **error})
                    yield _sse("completed", {"run_id": started["id"], "status": "failed", "used_fallback": False, "metrics": metrics})
                    terminal = True
                    return
                answer = result.get("answer") or "İşlem desteklenmiyor."
                work = "storage"
                message_id = store.complete_run(
                    started["id"],
                    "completed",
                    metrics,
                    used_fallback=result["used_fallback"],
                    answer=answer,
                    navigation_targets=result.get("navigation_targets"),
                )
                terminal = True
                chunks = iter(iter_answer_chunks(answer))
                first_chunk = next(chunks)
                yield _sse("answer.delta", {"run_id": started["id"], "message_id": message_id, "delta": first_chunk})
                metrics["time_to_first_visible_chunk_ms"] = max(0, int((time.perf_counter() - stream_started) * 1000))
                for chunk in chunks:
                    yield _sse("answer.delta", {"run_id": started["id"], "message_id": message_id, "delta": chunk})
                delivery_total_ms = max(0, int((time.perf_counter() - stream_started) * 1000))
                metrics["total_ms"] = max(
                    metrics.get("total_ms") or 0,
                    metrics["time_to_first_visible_chunk_ms"],
                    delivery_total_ms,
                )
                try:
                    store.update_visible_time(
                        started["id"],
                        metrics["time_to_first_visible_chunk_ms"],
                        metrics["total_ms"],
                    )
                except Exception:
                    try:
                        logger.write(user_id=user.sub, thread_id=thread_id, run_id=started["id"], route="/v1/threads/{id}/runs", stage="storage", error_code="visible_metric_unavailable")
                    except Exception:
                        pass
                completed = {"run_id": started["id"], "status": "completed", "message_id": message_id, "used_fallback": result["used_fallback"], "metrics": metrics}
                if result.get("navigation_targets"):
                    completed["navigation_targets"] = result["navigation_targets"]
                if demo_mode and isinstance(result.get("inspection"), dict):
                    completed["inspection"] = result["inspection"]
                yield _sse("completed", completed)
            except Exception:
                if work == "storage":
                    stage, code, message = "storage", "storage_failed", "Sonuç kaydedilemedi."
                elif work == "pipeline" and last_stage in {"planner", "resolver", "librenms", "synthesis"}:
                    stage, code, message = last_stage, f"{last_stage}_failed", "İşlem tamamlanamadı."
                else:
                    stage, code, message = "internal", "internal_failure", "İşlem tamamlanamadı."
                persist_failure(stage, code, metrics)
                yield _sse("error", {"run_id": started["id"], "stage": stage, "code": code, "retryable": True, "message": message})
                yield _sse("completed", {"run_id": started["id"], "status": "failed", "used_fallback": False, "metrics": metrics})
                terminal = True
            finally:
                if event_waiter is not None and not event_waiter.done():
                    event_waiter.cancel()
                    try:
                        await event_waiter
                    except asyncio.CancelledError:
                        pass
                if not terminal:
                    cancelled.set()
                    try:
                        store.complete_run(started["id"], "cancelled", {}, error_stage="cancellation", error_code="cancelled")
                    except NotFoundError:
                        pass
                registry.finish(thread_id, started["id"])

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return app
