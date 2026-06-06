"""WebSocket endpoint for live pipeline progress."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from entity_resolution.ui.auth import extract_request_token, tokens_match

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/pipeline/{run_id}")
async def pipeline_progress(websocket: WebSocket, run_id: str) -> None:
    """Stream pipeline progress events for a given run_id."""
    token = getattr(websocket.app.state, "auth_token", None)
    if token:
        # Accept the token via header (Authorization/X-API-Key) or a `token`
        # query parameter (browsers cannot set headers on WebSocket handshakes).
        provided = extract_request_token(websocket.headers) or websocket.query_params.get("token")
        if not tokens_match(provided, token):
            await websocket.close(code=1008)  # policy violation
            return
    await websocket.accept()

    db = websocket.app.state.db
    runs_coll = "_er_pipeline_runs"

    _STAGE_EVENTS = {"stage_start", "stage_progress", "stage_complete", "stage_error"}

    try:
        sent = 0  # number of progress_events already forwarded
        while True:
            if not db.has_collection(runs_coll):
                await websocket.send_json({"type": "error", "detail": "No pipeline runs collection"})
                break

            try:
                doc = db.collection(runs_coll).get(run_id)
            except Exception:
                doc = None

            if doc is None:
                await websocket.send_json({"type": "error", "detail": f"Run {run_id} not found"})
                break

            # Forward any new stage events emitted by the pipeline's on_progress
            # callback (persisted to the run document by the pipeline route).
            events = doc.get("progress_events") or []
            for event in events[sent:]:
                if event.get("type") in _STAGE_EVENTS:
                    await websocket.send_json(event)
            sent = len(events)

            current_status = doc.get("status")
            if current_status in ("completed", "failed"):
                if current_status == "completed":
                    await websocket.send_json({
                        "type": "pipeline_complete",
                        "run_id": run_id,
                        "summary": doc.get("result"),
                        "result": doc.get("result"),
                    })
                else:
                    await websocket.send_json({
                        "type": "pipeline_failed",
                        "run_id": run_id,
                        "error": doc.get("error"),
                    })
                break

            await asyncio.sleep(0.5)

    except WebSocketDisconnect:
        pass
