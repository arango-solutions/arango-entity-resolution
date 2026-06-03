"""
arango-entity-resolution MCP Server

Exposes entity resolution as MCP tools and resources so AI agents can
perform ER through natural language without writing any code.

Entry points:
    arango-er-mcp                  # stdio (Claude Desktop / Cursor)
    arango-er-mcp --transport sse  # HTTP SSE for remote MCP-capable clients
    arango-er-mcp --demo           # quickstart with sample data
"""
from __future__ import annotations

import hmac
import json
import logging
import os
from typing import Any, Dict, List, Optional, Union

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Server & connection config
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="arango-entity-resolution",
    instructions=(
        "You have access to an ArangoDB entity resolution system. "
        "Use the tools to find duplicate records, resolve entities, explain "
        "why two records match, and manage entity clusters. "
        "Always call `list_collections` first if you are unsure which "
        "collection to use."
    ),
)
logger = logging.getLogger(__name__)
ER_OPTIONS_SCHEMA_VERSION = "1.0"


def _attach_deprecation_warnings(result: Any, warnings: List[str]) -> Any:
    """Attach deprecation warnings when response shape allows additive metadata."""
    if warnings and isinstance(result, dict):
        result = dict(result)
        existing = result.get("deprecation_warnings")
        if isinstance(existing, list):
            result["deprecation_warnings"] = existing + warnings
        else:
            result["deprecation_warnings"] = list(warnings)
    return result


def _attach_schema_version(result: Any) -> Any:
    """Attach options schema version to dict-like responses."""
    if isinstance(result, dict) and "er_options_schema_version" not in result:
        out = dict(result)
        out["er_options_schema_version"] = ER_OPTIONS_SCHEMA_VERSION
        return out
    return result


def _wrap_response_envelope(*, result: Any, warnings: List[str], enabled: bool) -> Any:
    """Optionally wrap responses so metadata can be surfaced safely."""
    if not enabled:
        return result
    payload: Dict[str, Any] = {
        "status": "ok",
        "response_format": "envelope-v1",
        "er_options_schema_version": ER_OPTIONS_SCHEMA_VERSION,
        "result": result,
    }
    if warnings:
        payload["deprecation_warnings"] = list(warnings)
    return payload


def _extract_bearer_token(authorization: Optional[str]) -> Optional[str]:
    """Return the token from an ``Authorization`` header value."""
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return authorization.strip()


class _TokenAuthASGIMiddleware:
    """Minimal ASGI middleware enforcing a bearer token on HTTP requests.

    Wraps the FastMCP SSE app so both the event stream and the message
    endpoint require ``Authorization: Bearer <token>``.
    """

    def __init__(self, app: Any, token: str) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope: Dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") == "http":
            headers = {
                k.decode("latin-1").lower(): v.decode("latin-1")
                for k, v in scope.get("headers", [])
            }
            provided = _extract_bearer_token(headers.get("authorization"))
            if not provided or not hmac.compare_digest(provided, self.token):
                await send({
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [(b"content-type", b"application/json")],
                })
                await send({
                    "type": "http.response.body",
                    "body": b'{"detail": "Unauthorized"}',
                })
                return
        await self.app(scope, receive, send)


def run_sse_server(*, host: str, port: int, auth_token: Optional[str] = None) -> None:
    """Run the FastMCP server using its supported SSE transport.

    When ``auth_token`` is provided, every HTTP request to the SSE app must
    present ``Authorization: Bearer <token>``.
    """
    mcp.settings.host = host
    mcp.settings.port = port
    if not auth_token:
        mcp.run(transport="sse")
        return

    import uvicorn

    app = _TokenAuthASGIMiddleware(mcp.sse_app(), auth_token)
    uvicorn.run(app, host=host, port=port)

def _conn() -> Dict[str, Any]:
    """Read connection settings from environment variables."""
    return dict(
        host=os.getenv("ARANGO_HOST", "localhost"),
        port=int(os.getenv("ARANGO_PORT", "8529")),
        username=os.getenv("ARANGO_USERNAME", "root"),
        password=os.getenv("ARANGO_PASSWORD", os.getenv("ARANGO_ROOT_PASSWORD", "")),
        database=os.getenv("ARANGO_DATABASE", "_system"),
    )


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def list_collections(
    options: Optional[Dict[str, Any]] = None,
) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
    """
    List all document and edge collections in the ArangoDB database.

    Returns each collection's name, type ("document" or "edge"), and
    document count. Call this first to discover available collections.
    Set `options.diagnostics.response_envelope=true` for an object envelope.
    """
    from entity_resolution.mcp.tools.cluster import run_list_collections
    result = run_list_collections(**_conn())
    envelope_enabled = bool(
        isinstance(options, dict)
        and isinstance(options.get("diagnostics"), dict)
        and options["diagnostics"].get("response_envelope", False)
    )
    return _wrap_response_envelope(result=result, warnings=[], enabled=envelope_enabled)


@mcp.tool()
def find_duplicates(
    collection: str,
    fields: List[str],
    strategy: str = "exact",
    confidence_threshold: float = 0.85,
    max_block_size: int = 500,
    store_clusters: bool = True,
    edge_collection: Optional[str] = None,
    enable_active_learning: bool = False,
    feedback_collection: Optional[str] = None,
    active_learning_refresh_every: int = 100,
    active_learning_model: Optional[str] = None,
    active_learning_low_threshold: float = 0.55,
    active_learning_high_threshold: float = 0.80,
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Run the full entity resolution pipeline on a collection.

    Performs blocking → similarity computation → edge creation → clustering.
    Returns a metrics summary with counts and runtimes for each phase.

    Args:
        collection: Name of the ArangoDB document collection to deduplicate.
        fields: List of field names to use for blocking and similarity.
        strategy: Blocking strategy — "exact" (default) or "bm25".
        confidence_threshold: Minimum similarity score to create an edge (0–1).
        max_block_size: Maximum block size for blocking phase.
        store_clusters: Whether to persist cluster results to ArangoDB.
        edge_collection: Target edge collection name (default: {collection}_similarity_edges).
        enable_active_learning: Enable opt-in LLM verification for uncertain pairs.
        feedback_collection: Optional collection for persisted LLM feedback.
        active_learning_refresh_every: Calls between threshold refresh checks.
        active_learning_model: Optional litellm model override for active learning.
        active_learning_low_threshold: Lower bound of the uncertain-score band.
        active_learning_high_threshold: Upper bound of the uncertain-score band.
    """
    from entity_resolution.mcp.normalization import normalize_find_duplicates_args
    from entity_resolution.mcp.tools.pipeline import run_find_duplicates_request
    req = normalize_find_duplicates_args(
        collection=collection,
        fields=fields,
        strategy=strategy,
        confidence_threshold=confidence_threshold,
        max_block_size=max_block_size,
        store_clusters=store_clusters,
        edge_collection=edge_collection,
        enable_active_learning=enable_active_learning,
        feedback_collection=feedback_collection,
        active_learning_refresh_every=active_learning_refresh_every,
        active_learning_model=active_learning_model,
        active_learning_low_threshold=active_learning_low_threshold,
        active_learning_high_threshold=active_learning_high_threshold,
        options=options,
    )
    for warning in req.deprecation_warnings:
        logger.warning("find_duplicates normalization warning: %s", warning)

    result = run_find_duplicates_request(
        **_conn(),
        request=req,
    )
    result = _attach_deprecation_warnings(result, req.deprecation_warnings)
    return _attach_schema_version(result)


@mcp.tool()
def pipeline_status(
    collection: str,
    edge_collection: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get the current entity resolution status for a collection.

    Returns total document count, edge statistics (inferred vs direct,
    average confidence), and cluster count.

    Args:
        collection: Name of the document collection.
        edge_collection: Edge collection name (default: {collection}_similarity_edges).
    """
    from entity_resolution.mcp.tools.pipeline import run_pipeline_status
    result = run_pipeline_status(**_conn(), collection=collection, edge_collection=edge_collection)
    return _attach_schema_version(result)


@mcp.tool()
def resolve_entity(
    collection: str,
    record: Dict[str, Any],
    fields: List[str],
    confidence_threshold: float = 0.80,
    top_k: int = 10,
    options: Optional[Dict[str, Any]] = None,
) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Find existing records in a collection that match a given record.

    Does NOT modify the database — purely a read/search operation.
    Returns a ranked list of candidate matches with similarity scores.
    Set `options.diagnostics.response_envelope=true` for an object envelope.

    Args:
        collection: Collection to search for matches.
        record: The record to find matches for (a dict of field→value).
        fields: Fields to use for blocking and similarity comparison.
        confidence_threshold: Minimum score for a result to be included.
        top_k: Maximum number of matches to return.
    """
    from entity_resolution.mcp.normalization import normalize_resolve_entity_args
    from entity_resolution.mcp.tools.entity import run_resolve_entity_request
    req = normalize_resolve_entity_args(
        collection=collection,
        record=record,
        fields=fields,
        confidence_threshold=confidence_threshold,
        top_k=top_k,
        options=options,
    )
    for warning in req.deprecation_warnings:
        logger.warning("resolve_entity normalization warning: %s", warning)

    result = run_resolve_entity_request(
        **_conn(),
        request=req,
    )
    envelope_enabled = bool((req.options.diagnostics or {}).get("response_envelope", False))
    result = _wrap_response_envelope(
        result=result,
        warnings=req.deprecation_warnings,
        enabled=envelope_enabled,
    )
    return _attach_schema_version(result)


@mcp.tool()
def resolve_entity_cross_collection(
    source_collection: str,
    target_collection: str,
    source_fields: List[str],
    target_fields: List[str],
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Link entities across two collections with schema-mapping and guardrails.

    This C1 tool provides cross-collection resolution with explicit execution
    controls via `options`:
    - `retrieval.field_mapping` (logical -> {source,target})
    - `retrieval.target_filter`
    - `retrieval.source_skip_values`
    - `retrieval.candidate_limit`
    - `execution.batch_size`
    - `execution.max_runtime_ms`
    - `retrieval.deterministic_tiebreak`
    - `diagnostics.return_diagnostics`

    Args:
        source_collection: Collection containing the records to match from.
        target_collection: Collection containing the records to match against.
        source_fields: Positional source field names (used when field_mapping is absent).
        target_fields: Positional target field names (paired 1:1 with source_fields).
    """
    from entity_resolution.mcp.normalization import normalize_cross_collection_args
    from entity_resolution.mcp.tools.entity import run_resolve_cross_collection_request

    req = normalize_cross_collection_args(
        source_collection=source_collection,
        target_collection=target_collection,
        source_fields=source_fields,
        target_fields=target_fields,
        options=options,
    )
    for warning in req.deprecation_warnings:
        logger.warning("resolve_entity_cross_collection normalization warning: %s", warning)

    result = run_resolve_cross_collection_request(
        **_conn(),
        request=req,
    )
    result = _attach_deprecation_warnings(result, req.deprecation_warnings)
    return _attach_schema_version(result)


@mcp.tool()
def explain_match(
    collection: str,
    key_a: str,
    key_b: str,
    fields: Optional[List[str]] = None,
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Explain why (or why not) two entities in a collection match.

    Returns a field-level similarity breakdown showing individual scores
    for each field, the overall score, and an interpretation.

    Args:
        collection: Collection both documents belong to.
        key_a: _key of the first document.
        key_b: _key of the second document.
        fields: Specific fields to compare (default: all shared string fields).
        options: Optional diagnostics/gating options for explainability context.
    """
    from entity_resolution.mcp.tools.entity import run_explain_match
    result = run_explain_match(
        **_conn(),
        collection=collection,
        key_a=key_a,
        key_b=key_b,
        fields=fields,
        options=options,
    )
    return _attach_schema_version(result)


@mcp.tool()
def get_clusters(
    collection: str,
    limit: int = 50,
    min_size: int = 2,
    options: Optional[Dict[str, Any]] = None,
) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Return entity clusters found in the collection's similarity graph.

    Each cluster is a group of document keys that were resolved to
    represent the same real-world entity, sorted by cluster size descending.
    When available, includes quality metadata such as density and similarity
    summary statistics to help distinguish strong clusters from review candidates.
    Set `options.diagnostics.response_envelope=true` for an object envelope.

    Args:
        collection: Document collection name.
        limit: Maximum number of clusters to return.
        min_size: Minimum cluster size to include.
    """
    from entity_resolution.mcp.tools.cluster import run_get_clusters
    result = run_get_clusters(**_conn(), collection=collection, limit=limit, min_size=min_size)
    envelope_enabled = bool(
        isinstance(options, dict)
        and isinstance(options.get("diagnostics"), dict)
        and options["diagnostics"].get("response_envelope", False)
    )
    return _wrap_response_envelope(result=result, warnings=[], enabled=envelope_enabled)


@mcp.tool()
def merge_entities(
    collection: str,
    entity_keys: List[str],
    strategy: str = "most_complete",
) -> Dict[str, Any]:
    """
    Merge multiple entity records into a single deterministic golden-record preview.

    Args:
        collection: Collection containing the entities.
        entity_keys: List of document _keys to merge.
        strategy: Merge strategy — "most_complete" (default), "newest", or "first".
    """
    from entity_resolution.mcp.tools.cluster import run_merge_entities
    result = run_merge_entities(
        **_conn(),
        collection=collection,
        entity_keys=entity_keys,
        strategy=strategy,
    )
    return _attach_schema_version(result)


@mcp.tool()
def profile_dataset(
    source_type: str,
    dataset_id: str,
    request_id: Optional[str] = None,
    sample_limit: int = 10000,
    include_fields: Optional[List[str]] = None,
    exclude_fields: Optional[List[str]] = None,
    compute_pairwise_signals: bool = True,
) -> Dict[str, Any]:
    """
    Profile a dataset and return ER-relevant field statistics.

    Returns null rates, distinct counts, heavy hitters, token stats, and
    optional duplicate/hub risk signals to guide strategy selection.
    """
    from entity_resolution.mcp.tools.advisor import run_profile_dataset
    result = run_profile_dataset(
        **_conn(),
        source_type=source_type,
        dataset_id=dataset_id,
        request_id=request_id,
        sample_limit=sample_limit,
        include_fields=include_fields,
        exclude_fields=exclude_fields,
        compute_pairwise_signals=compute_pairwise_signals,
    )
    return _attach_schema_version(result)


@mcp.tool()
def recommend_resolution_strategy(
    profile: Dict[str, Any],
    objective_profile: Dict[str, Any],
    request_id: Optional[str] = None,
    allow_embedding_models: bool = True,
    allow_graph_clustering: bool = True,
) -> Dict[str, Any]:
    """
    Recommend ranked ER strategy families from profile + objective constraints.

    Produces explicit strategy recommendations with fit scores, expected
    tradeoffs, rationale, and confidence factors for client-side planning.
    """
    from entity_resolution.mcp.tools.advisor import run_recommend_resolution_strategy
    result = run_recommend_resolution_strategy(
        profile=profile,
        objective_profile=objective_profile,
        request_id=request_id,
        allow_embedding_models=allow_embedding_models,
        allow_graph_clustering=allow_graph_clustering,
    )
    return _attach_schema_version(result)


@mcp.tool()
def estimate_feature_weights(
    feature_matrix_ref: Dict[str, Any],
    target_metric: str = "f1",
    min_samples: int = 1000,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Estimate initial feature weights and threshold hints from labeled pairs.

    Accepts a feature matrix reference with labeled samples and returns
    normalized feature weights, threshold recommendation, diagnostics, and
    confidence factors.
    """
    from entity_resolution.mcp.tools.advisor import run_estimate_feature_weights
    result = run_estimate_feature_weights(
        feature_matrix_ref=feature_matrix_ref,
        target_metric=target_metric,
        min_samples=min_samples,
        request_id=request_id,
    )
    return _attach_schema_version(result)


@mcp.tool()
def simulate_pipeline_variants(
    variants: List[Dict[str, Any]],
    objective_profile: Optional[Dict[str, Any]] = None,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Simulate and rank multiple candidate ER pipeline variants.

    Returns per-variant runtime/memory/quality estimates, a ranked list by
    objective fit, and a winner rationale to support pre-commit decisions.
    """
    from entity_resolution.mcp.tools.advisor import run_simulate_pipeline_variants
    result = run_simulate_pipeline_variants(
        variants=variants,
        objective_profile=objective_profile,
        request_id=request_id,
    )
    return _attach_schema_version(result)


@mcp.tool()
def export_recommended_config(
    recommendation: Dict[str, Any],
    format: str = "json",
    include_rationale: bool = True,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Export advisor recommendation into a normalized JSON/YAML config artifact.

    Returns serialized config text, deterministic SHA256 hash, and policy
    version for auditability across recommendation and deployment flows.
    """
    from entity_resolution.mcp.tools.advisor import run_export_recommended_config
    result = run_export_recommended_config(
        recommendation=recommendation,
        format=format,
        include_rationale=include_rationale,
        request_id=request_id,
    )
    return _attach_schema_version(result)


@mcp.tool()
def evaluate_blocking_plan(
    profile: Dict[str, Any],
    blocking_plan: Dict[str, Any],
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Evaluate a proposed blocking plan before pipeline execution.

    Estimates candidate-pair volume and block-size distribution, then returns
    risk flags plus recommended guardrails for safer execution.
    """
    from entity_resolution.mcp.tools.advisor import run_evaluate_blocking_plan
    result = run_evaluate_blocking_plan(
        profile=profile,
        blocking_plan=blocking_plan,
        request_id=request_id,
    )
    return _attach_schema_version(result)


@mcp.tool()
def recommend_blocking_candidates(
    profile: Dict[str, Any],
    request_id: Optional[str] = None,
    max_composite_size: int = 3,
    max_results: int = 20,
    must_include_fields: Optional[List[str]] = None,
    must_exclude_fields: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Rank blocking field candidates from a dataset profile.

    Produces single-field and composite key candidates with heuristic
    fit scores and estimated candidate-pair volume.
    """
    from entity_resolution.mcp.tools.advisor import run_recommend_blocking_candidates
    result = run_recommend_blocking_candidates(
        profile=profile,
        request_id=request_id,
        max_composite_size=max_composite_size,
        max_results=max_results,
        must_include_fields=must_include_fields,
        must_exclude_fields=must_exclude_fields,
    )
    return _attach_schema_version(result)


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

@mcp.resource("arango://collections/{collection_name}/summary")
def collection_summary(collection_name: str) -> str:
    """
    JSON summary of a collection: document count, inferred field schema,
    and sample documents.
    """
    from entity_resolution.mcp.resources.collections import get_collection_summary
    return get_collection_summary(**_conn(), collection_name=collection_name)


@mcp.resource("arango://clusters/{collection_name}/{representative_key}")
def cluster_detail(collection_name: str, representative_key: str) -> str:
    """
    Full details of the entity cluster containing *representative_key*,
    including all member documents.
    """
    from entity_resolution.mcp.resources.collections import get_cluster_detail
    return get_cluster_detail(
        **_conn(),
        collection_name=collection_name,
        representative_key=representative_key,
    )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="arango-er-mcp",
        description="Entity Resolution MCP Server for ArangoDB",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport mode (default: stdio)",
    )
    parser.add_argument("--port", type=int, default=8080, help="Port for SSE transport")
    parser.add_argument("--host", default="127.0.0.1", help="Host for SSE transport")
    parser.add_argument(
        "--auth-token",
        default=None,
        help="Bearer token required for SSE transport. Falls back to the "
        "ER_MCP_AUTH_TOKEN environment variable.",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Allow binding SSE to a non-loopback host without a token (NOT recommended).",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help=(
            "Run in demo mode: start ArangoDB (Docker if needed), load sample data, "
            "run the ER pipeline, print Claude Desktop config, then start the MCP server."
        ),
    )
    args = parser.parse_args()

    if args.demo:
        from entity_resolution.mcp.demo import run_demo
        run_demo()
        return

    if args.transport == "sse":
        auth_token = (args.auth_token or os.getenv("ER_MCP_AUTH_TOKEN") or "").strip() or None
        loopback_hosts = {"127.0.0.1", "localhost", "::1", "::ffff:127.0.0.1"}
        if args.host not in loopback_hosts and not auth_token:
            if not args.insecure:
                logger.error(
                    "Refusing to bind MCP SSE to non-loopback host '%s' without "
                    "authentication. Provide --auth-token / ER_MCP_AUTH_TOKEN, bind to "
                    "127.0.0.1, or pass --insecure to override (NOT recommended).",
                    args.host,
                )
                raise SystemExit(1)
            logger.warning(
                "MCP SSE is bound to non-loopback host '%s' with NO authentication. "
                "Anyone who can reach this host has full database access.",
                args.host,
            )
        run_sse_server(host=args.host, port=args.port, auth_token=auth_token)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
