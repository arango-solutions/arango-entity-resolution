"""Cluster export endpoints."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from entity_resolution.ui.models.schemas import ExportRequest

router = APIRouter(prefix="/api/export", tags=["export"])


def _db(request: Request):
    return request.app.state.db


@router.post("/{collection}")
async def export_clusters(
    request: Request,
    collection: str,
    body: ExportRequest,
) -> Dict[str, Any]:
    """Export clusters to JSON and CSV files."""
    from entity_resolution.services.cluster_export_service import ClusterExportService
    from entity_resolution.utils.validation import validate_collection_name

    if request.app.state.readonly:
        raise HTTPException(status_code=403, detail="Read-only mode")

    validate_collection_name(collection)
    db = _db(request)

    service = ClusterExportService(
        db=db,
        source_collection=collection,
        edge_collection=body.edge_collection,
        cluster_collection=body.cluster_collection,
    )

    output_dir = body.output_dir or tempfile.mkdtemp(prefix="er_export_")
    result = service.export(
        output_dir=output_dir,
        filename_prefix=body.filename_prefix,
        limit=body.limit,
    )

    return {
        "collection": collection,
        "output_files": {
            "json": result["json"],
            "csv": result["csv"],
        },
        "clusters_exported": result["clusters_exported"],
    }


@router.get("/{collection}/download/{filename}")
async def download_export(
    request: Request,
    collection: str,
    filename: str,
) -> FileResponse:
    """Serve an exported file for download."""
    safe_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.")
    if not all(c in safe_chars for c in filename):
        raise HTTPException(status_code=400, detail="Invalid filename")

    search_dirs = [
        Path(tempfile.gettempdir()),
        Path.cwd() / "exports",
    ]

    for directory in search_dirs:
        candidate = directory / filename
        if candidate.is_file():
            media_type = "application/json" if filename.endswith(".json") else "text/csv"
            return FileResponse(
                path=str(candidate),
                filename=filename,
                media_type=media_type,
            )

    raise HTTPException(status_code=404, detail="File not found")
