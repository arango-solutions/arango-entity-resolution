"""WebSocket endpoint for live pipeline progress."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/pipeline/{run_id}")
async def pipeline_progress(websocket: WebSocket, run_id: str) -> None:
    """Stream pipeline progress events for a given run_id."""
    await websocket.accept()

    db = websocket.app.state.db
    runs_coll = "_er_pipeline_runs"

    try:
        last_status = None
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

            current_status = doc.get("status")
            if current_status != last_status:
                await websocket.send_json({
                    "type": "status_change",
                    "run_id": run_id,
                    "status": current_status,
                    "started_at": doc.get("started_at"),
                    "completed_at": doc.get("completed_at"),
                })
                last_status = current_status

            if current_status in ("completed", "failed"):
                summary: Dict[str, Any] = {
                    "type": "pipeline_complete" if current_status == "completed" else "pipeline_failed",
                    "run_id": run_id,
                }
                if current_status == "completed":
                    summary["result"] = doc.get("result")
                else:
                    summary["error"] = doc.get("error")
                await websocket.send_json(summary)
                break

            await asyncio.sleep(1.0)

    except WebSocketDisconnect:
        pass
