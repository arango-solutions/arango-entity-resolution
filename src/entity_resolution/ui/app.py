"""FastAPI application factory for the Entity Resolution UI."""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from entity_resolution.utils.constants import __version__
from .auth import extract_request_token, tokens_match

from .routes import (
    collections,
    clusters,
    config,
    export,
    golden,
    metrics,
    pipeline,
    resolve,
    review,
    ws,
)

_STATIC_DIR = Path(__file__).parent / "static"


def create_app(
    db: Any,
    *,
    readonly: bool = False,
    allowed_origins: Optional[List[str]] = None,
    connection_params: Optional[dict[str, Any]] = None,
    collection_aliases: Optional[dict[str, str]] = None,
    auth_token: Optional[str] = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Parameters
    ----------
    db:
        A python-arango database handle.
    readonly:
        When ``True``, mutation endpoints (verdicts, pipeline runs, merges)
        return 403.
    allowed_origins:
        CORS allowed origins.  Defaults to same-origin only (empty list).
    connection_params:
        Explicit ``{"host", "port", "username", "password", "database"}``
        dict so UI routes can create secondary clients without introspecting
        the opaque ``db`` handle (python-arango v8 no longer exposes
        credentials as instance attributes).
        collection_aliases:
        Optional mapping from the library's derived collection names to actual
        collection names in the database.  For example::

            {"duns_clusters": "entity_clusters",
             "duns_similarity_edges": "similarTo"}
    auth_token:
        Optional shared secret.  When set, every ``/api/*`` request (except
        ``/api/health``) and every WebSocket connection must present the token
        via ``Authorization: Bearer <token>`` / ``X-API-Key`` header (or a
        ``token`` query parameter for WebSockets).  When ``None`` the API is
        unauthenticated (intended for trusted localhost use only).
    """
    app = FastAPI(
        title="Entity Resolution UI",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    app.state.db = db
    app.state.readonly = readonly
    app.state.connection_params = connection_params or {}
    app.state.collection_aliases = collection_aliases or {}
    app.state.auth_token = auth_token or None
    app.state.pipeline_runs: dict[str, dict[str, Any]] = {}

    origins = allowed_origins or []
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def check_db_connection(request: Request, call_next):
        """Return 503 for API calls when no database is connected."""
        path = request.url.path
        if path.startswith("/api/") and path != "/api/health" and app.state.db is None:
            return JSONResponse(
                {"detail": "No database connection. Start ArangoDB and restart with connection options."},
                status_code=503,
            )
        return await call_next(request)

    # Registered last so it runs first (outermost): authentication must be
    # enforced before any other request handling.
    @app.middleware("http")
    async def require_auth(request: Request, call_next):
        """Require a valid token for API routes when auth is enabled.

        Health checks, CORS preflight, and non-API (SPA/static) routes are
        exempt so the app remains usable behind the SPA fallback.
        """
        token = app.state.auth_token
        if token and request.method != "OPTIONS":
            path = request.url.path
            if path.startswith("/api/") and path != "/api/health":
                provided = extract_request_token(request.headers)
                if not tokens_match(provided, token):
                    return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        connected = app.state.db is not None
        return {
            "status": "ok" if connected else "no_database",
            "version": __version__,
            "database_connected": connected,
        }

    app.include_router(collections.router)
    app.include_router(clusters.router)
    app.include_router(review.router)
    app.include_router(pipeline.router)
    app.include_router(golden.router)
    app.include_router(config.router)
    app.include_router(resolve.router)
    app.include_router(export.router)
    app.include_router(metrics.router)
    app.include_router(ws.router)

    if _STATIC_DIR.is_dir():
        app.mount("/assets", StaticFiles(directory=_STATIC_DIR / "assets"), name="assets")

        @app.get("/{full_path:path}")
        async def spa_fallback(request: Request, full_path: str) -> FileResponse:
            """Serve the SPA index for any non-API path."""
            file_path = _STATIC_DIR / full_path
            if file_path.is_file():
                return FileResponse(file_path)
            index = _STATIC_DIR / "index.html"
            if index.is_file():
                return FileResponse(index)
            return JSONResponse({"detail": "Not found"}, status_code=404)

    return app
