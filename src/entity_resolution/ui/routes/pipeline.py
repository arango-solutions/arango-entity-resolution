"""Pipeline execution and status endpoints."""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from entity_resolution.ui.models.schemas import PipelineRunRequest, PipelineRunResponse

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

_RUNS_COLLECTION = "_er_pipeline_runs"


def _db(request: Request):
    return request.app.state.db


@router.get("/status/{collection}")
async def pipeline_status(
    request: Request,
    collection: str,
    edge_collection: str | None = None,
) -> Dict[str, Any]:
    """Collection status: document count, edges, clusters."""
    from entity_resolution.utils.pipeline_utils import count_inferred_edges
    from entity_resolution.utils.validation import validate_collection_name

    validate_collection_name(collection)
    db = _db(request)

    edge_coll = edge_collection or f"{collection}_similarity_edges"
    total_docs = db.collection(collection).count() if db.has_collection(collection) else 0

    edge_stats: Dict[str, Any] = {}
    if db.has_collection(edge_coll):
        try:
            edge_stats = count_inferred_edges(db, edge_collection=edge_coll)
        except Exception as exc:
            edge_stats = {"error": str(exc)}

    cluster_coll = f"{collection}_clusters"
    cluster_count = 0
    if db.has_collection(cluster_coll):
        try:
            cluster_count = db.collection(cluster_coll).count()
        except Exception:
            pass

    return {
        "collection": collection,
        "total_documents": total_docs,
        "edge_collection": edge_coll,
        "edge_stats": edge_stats,
        "cluster_collection": cluster_coll,
        "cluster_count": cluster_count,
    }


@router.get("/history")
async def pipeline_history(
    request: Request,
    limit: int = 20,
    offset: int = 0,
) -> Dict[str, Any]:
    """Query pipeline run history from _er_pipeline_runs collection."""
    db = _db(request)

    if not db.has_collection(_RUNS_COLLECTION):
        return {"runs": [], "total": 0}

    count_cursor = db.aql.execute(
        "FOR r IN @@coll COLLECT WITH COUNT INTO n RETURN n",
        bind_vars={"@coll": _RUNS_COLLECTION},
    )
    total = list(count_cursor)[0]

    cursor = db.aql.execute(
        """
        FOR r IN @@coll
            SORT r.started_at DESC
            LIMIT @offset, @limit
            RETURN r
        """,
        bind_vars={"@coll": _RUNS_COLLECTION, "offset": offset, "limit": limit},
    )
    return {"runs": list(cursor), "total": total}


@router.post("/run")
async def run_pipeline(
    request: Request,
    body: PipelineRunRequest,
    background_tasks: BackgroundTasks,
) -> PipelineRunResponse:
    """Start a pipeline run in the background. Returns a run_id."""
    if request.app.state.readonly:
        raise HTTPException(status_code=403, detail="Read-only mode")

    run_id = str(uuid.uuid4())
    db = _db(request)

    run_meta: Dict[str, Any] = {
        "_key": run_id,
        "status": "running",
        "config": body.config,
        "started_at": time.time(),
        "completed_at": None,
        "result": None,
        "error": None,
        # Stage progress events appended during the run; streamed by the WS.
        "progress_events": [],
    }

    if not db.has_collection(_RUNS_COLLECTION):
        db.create_collection(_RUNS_COLLECTION)
    db.collection(_RUNS_COLLECTION).insert(run_meta)

    request.app.state.pipeline_runs[run_id] = run_meta

    background_tasks.add_task(_execute_pipeline, db, run_id, body.config)

    return PipelineRunResponse(run_id=run_id, status="running")


def _execute_pipeline(db, run_id: str, config_dict: Dict[str, Any]) -> None:
    """Run the pipeline in a background thread and update the run record."""
    from entity_resolution.config.er_config import ERPipelineConfig
    from entity_resolution.core.configurable_pipeline import ConfigurableERPipeline

    def on_progress(event: Dict[str, Any]) -> None:
        # Persist each stage event so the WebSocket can stream it to the UI.
        _append_event(db, run_id, event)

    try:
        er_config = ERPipelineConfig.from_dict(config_dict)
        pipeline = ConfigurableERPipeline(db=db, config=er_config)
        result = pipeline.run(on_progress=on_progress)

        _update_run(db, run_id, status="completed", result=result)
    except Exception as exc:
        _update_run(db, run_id, status="failed", error=str(exc))


def _append_event(db, run_id: str, event: Dict[str, Any]) -> None:
    """Atomically append a progress event to the run document."""
    if not db.has_collection(_RUNS_COLLECTION):
        return
    try:
        db.aql.execute(
            """
            FOR r IN @@coll
                FILTER r._key == @key
                UPDATE r WITH {
                    progress_events: PUSH(r.progress_events != null ? r.progress_events : [], @event)
                } IN @@coll
            """,
            bind_vars={"@coll": _RUNS_COLLECTION, "key": run_id, "event": event},
        )
    except Exception:
        pass


def _update_run(db, run_id: str, **fields: Any) -> None:
    """Patch a pipeline run document."""
    fields["completed_at"] = time.time()
    if db.has_collection(_RUNS_COLLECTION):
        try:
            db.collection(_RUNS_COLLECTION).update({"_key": run_id, **fields})
        except Exception:
            pass
