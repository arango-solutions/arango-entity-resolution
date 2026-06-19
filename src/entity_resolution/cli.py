"""
Command Line Interface for ArangoDB Entity Resolution.
"""

from __future__ import annotations

import click
from click.core import ParameterSource
import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List

from arango import ArangoClient

from .core.configurable_pipeline import ConfigurableERPipeline
from .mcp.tools.cluster import run_get_clusters
from .mcp.tools.pipeline import run_pipeline_status
from .services.ab_evaluation_runner import run_blocking_benchmark
from .services.runtime_benchmark_service import RuntimeBenchmarkService
from .services.cluster_export_service import ClusterExportService
from .services.embedding_service import EmbeddingService
from .services.runtime_compare_report_service import RuntimeCompareReportService
from .services.runtime_profile_registry import RuntimeProfileRegistry
from .services.runtime_activation_evidence_service import RuntimeActivationEvidenceService
from .services.runtime_quality_benchmark_service import RuntimeQualityBenchmarkService
from .services.runtime_quality_gate_service import RuntimeQualityGateService
from .services.runtime_quality_policy_service import RuntimeQualityPolicyService
from .services.runtime_telemetry_service import RuntimeTelemetryService
from .utils.config import DatabaseConfig
from .utils.constants import get_version_string
from .utils.database import get_connection_args, get_database

@click.group()
@click.version_option(version=get_version_string())
def main():
    """ArangoDB Entity Resolution CLI."""
    pass


def connection_options(func: Callable[..., Any]) -> Callable[..., Any]:
    """Shared database connection options for CLI commands."""
    options = [
        click.option("--password", "-p", help="Password."),
        click.option("--username", "-u", help="Username."),
        click.option("--port", type=int, help="ArangoDB port."),
        click.option("--host", help="ArangoDB host."),
        click.option("--database", "-d", help="Database name (overrides config)."),
    ]
    for option in options:
        func = option(func)
    return func


def _resolve_connection_args(
    database: str | None,
    host: str | None,
    port: int | None,
    username: str | None,
    password: str | None,
) -> Dict[str, Any]:
    """Merge CLI overrides onto configured connection defaults."""
    try:
        args = get_connection_args()
    except Exception:
        defaults = DatabaseConfig()
        args = {
            "host": defaults.host,
            "port": defaults.port,
            "username": defaults.username,
            "password": defaults.password,
            "database": defaults.database,
        }
    if database is not None:
        args["database"] = database
    if host is not None:
        args["host"] = host
    if port is not None:
        args["port"] = port
    if username is not None:
        args["username"] = username
    if password is not None:
        args["password"] = password
    return args


def _get_db_from_options(
    database: str | None,
    host: str | None,
    port: int | None,
    username: str | None,
    password: str | None,
):
    """Connect using config defaults unless CLI overrides require a direct client."""
    args = _resolve_connection_args(database, host, port, username, password)
    if host is None and port is None and username is None and password is None:
        return get_database(args["database"])

    from entity_resolution.mcp.connection import get_arango_hosts
    client = ArangoClient(hosts=get_arango_hosts(args["host"], args["port"]))
    db = client.db(args["database"], username=args["username"], password=args["password"])
    db.properties()
    return db


def _emit_json(payload: Any) -> None:
    """Write JSON to stdout with stable formatting."""
    click.echo(json.dumps(payload, indent=2))


def _build_runtime_quality_metrics(
    corpus: str,
    model_name: str,
    device: str,
    batch_size: int,
) -> Dict[str, Any]:
    """Compute quality metrics from benchmark corpus using embedding service."""
    corpus_payload = RuntimeQualityBenchmarkService.load_corpus(corpus)
    embedding_service = EmbeddingService(
        model_name=model_name,
        device=device,
        batch_size=batch_size,
    )

    def _embed_texts(texts: List[str]) -> Any:
        records = [{"text": text} for text in texts]
        vectors = embedding_service.generate_embeddings_batch(
            records=records,
            text_fields=["text"],
            batch_size=batch_size,
            show_progress=False,
        )
        return vectors.tolist()

    metrics = RuntimeQualityBenchmarkService.run_benchmark(
        corpus=corpus_payload,
        embed_texts=_embed_texts,
    )
    metrics.setdefault("metadata", {})
    metrics["metadata"]["model_name"] = model_name
    metrics["metadata"]["requested_device"] = device
    metrics["metadata"]["resolved_device"] = embedding_service.device
    metrics["metadata"]["batch_size"] = batch_size
    return metrics


@main.command()
@click.option('--config', '-c', type=click.Path(exists=True), required=True, help='Path to YAML/JSON configuration file.')
@connection_options
def run(config, database, host, port, username, password):
    """Run an entity resolution pipeline from a configuration file."""
    try:
        db = _get_db_from_options(database, host, port, username, password)
        # Initialize and run pipeline
        pipeline = ConfigurableERPipeline(db=db, config_path=config)
        results = pipeline.run()
        
        click.echo(click.style("\nPipeline execution successful!", fg="green", bold=True))
        _emit_json(results)
        
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)


@main.command("runtime-health")
@click.option('--config', '-c', type=click.Path(exists=True), required=True, help='Path to YAML/JSON configuration file.')
@click.option(
    "--startup-mode",
    type=click.Choice(["permissive", "strict"], case_sensitive=False),
    help="Optional override for embedding startup policy.",
)
@connection_options
def runtime_health(config, startup_mode, database, host, port, username, password):
    """Show embedding runtime/provider diagnostics from configuration."""
    try:
        db = _get_db_from_options(database, host, port, username, password)
        pipeline = ConfigurableERPipeline(db=db, config_path=config)
        _emit_json(pipeline.get_embedding_runtime_health(startup_mode=startup_mode))
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)


@main.command("runtime-health-export")
@click.option('--config', '-c', type=click.Path(exists=True), required=True, help='Path to YAML/JSON configuration file.')
@click.option(
    "--output-dir",
    required=True,
    type=click.Path(file_okay=False),
    help="Directory where runtime health JSON artifacts will be written.",
)
@click.option(
    "--filename-prefix",
    default="runtime_health",
    show_default=True,
    help="Filename prefix for runtime health artifacts.",
)
@click.option(
    "--startup-mode",
    type=click.Choice(["permissive", "strict"], case_sensitive=False),
    help="Optional override for embedding startup policy.",
)
@connection_options
def runtime_health_export(
    config,
    output_dir,
    filename_prefix,
    startup_mode,
    database,
    host,
    port,
    username,
    password,
):
    """Export embedding runtime diagnostics to a timestamped JSON artifact."""
    try:
        db = _get_db_from_options(database, host, port, username, password)
        pipeline = ConfigurableERPipeline(db=db, config_path=config)
        snapshot = pipeline.get_embedding_runtime_health(startup_mode=startup_mode)
        output_file = RuntimeTelemetryService.export_snapshot(
            snapshot=snapshot,
            output_dir=output_dir,
            filename_prefix=filename_prefix,
        )
        _emit_json(
            {
                "output_file": output_file,
                "snapshot": snapshot,
            }
        )
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)


@main.command("runtime-health-benchmark")
@click.option('--config', '-c', type=click.Path(exists=True), required=True, help='Path to YAML/JSON configuration file.')
@click.option("--repeats", type=int, default=5, show_default=True, help="Number of repeated runtime-health probes.")
@click.option(
    "--warmup-runs",
    type=int,
    default=0,
    show_default=True,
    help="Warmup probes to run before measured benchmark repeats.",
)
@click.option(
    "--profile",
    default="default",
    show_default=True,
    help="Benchmark profile label included in output metadata.",
)
@click.option(
    "--startup-mode",
    type=click.Choice(["permissive", "strict"], case_sensitive=False),
    help="Optional override for embedding startup policy.",
)
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False),
    help="Optional output directory to persist benchmark JSON artifact.",
)
@click.option(
    "--filename-prefix",
    default="runtime_benchmark",
    show_default=True,
    help="Filename prefix for persisted benchmark artifacts.",
)
@connection_options
def runtime_health_benchmark(
    config,
    repeats,
    warmup_runs,
    profile,
    startup_mode,
    output_dir,
    filename_prefix,
    database,
    host,
    port,
    username,
    password,
):
    """Benchmark repeated runtime-health checks and summarize setup latency."""
    try:
        db = _get_db_from_options(database, host, port, username, password)
        pipeline = ConfigurableERPipeline(db=db, config_path=config)
        result = RuntimeBenchmarkService.run_benchmark(
            probe=lambda: pipeline.get_embedding_runtime_health(startup_mode=startup_mode),
            repeats=repeats,
            warmup_runs=warmup_runs,
            profile=profile,
        )
        result.setdefault("metadata", {})
        result["metadata"]["startup_mode"] = startup_mode or "default"
        result["metadata"]["config"] = {
            "config_path": str(config),
        }
        if output_dir:
            result["output_file"] = RuntimeBenchmarkService.export_benchmark(
                benchmark_result=result,
                output_dir=output_dir,
                filename_prefix=filename_prefix,
            )
        _emit_json(result)
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)


@main.command("runtime-quality-compare")
@click.option(
    "--current-metrics",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to current quality metrics JSON.",
)
@click.option(
    "--baseline-metrics",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to baseline quality metrics JSON.",
)
@click.option(
    "--cosine-drift-max",
    type=float,
    default=0.01,
    show_default=True,
    help="Maximum allowed cosine drift.",
)
@click.option(
    "--topk-overlap-min",
    type=float,
    default=0.95,
    show_default=True,
    help="Minimum allowed top-k overlap.",
)
@click.option(
    "--fail-on-regression/--no-fail-on-regression",
    default=False,
    show_default=True,
    help="Exit with code 2 when a quality regression is detected.",
)
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False),
    help="Optional output directory for JSON/Markdown/CSV quality comparison artifacts.",
)
@click.option(
    "--filename-prefix",
    default="runtime_quality_compare",
    show_default=True,
    help="Filename prefix for quality comparison artifacts when --output-dir is provided.",
)
def runtime_quality_compare(
    current_metrics,
    baseline_metrics,
    cosine_drift_max,
    topk_overlap_min,
    fail_on_regression,
    output_dir,
    filename_prefix,
):
    """Compare quality metrics against baseline thresholds."""
    try:
        current = RuntimeQualityGateService.load_metrics(current_metrics)
        baseline = RuntimeQualityGateService.load_metrics(baseline_metrics)
        comparison = RuntimeQualityGateService.compare_metrics(
            current=current,
            baseline=baseline,
            cosine_drift_max=cosine_drift_max,
            topk_overlap_min=topk_overlap_min,
        )
        if output_dir:
            comparison["output_files"] = RuntimeCompareReportService.export_report(
                comparison=comparison,
                output_dir=output_dir,
                filename_prefix=filename_prefix,
            )
        _emit_json(comparison)
        if fail_on_regression and comparison["regressions"]["quality_regression"]:
            sys.exit(2)
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)


@main.command("runtime-quality-corpus-init")
@click.option(
    "--output",
    "output_path",
    required=True,
    type=click.Path(dir_okay=False),
    help="Output path for benchmark corpus JSON scaffold.",
)
@click.option(
    "--overwrite/--no-overwrite",
    default=False,
    show_default=True,
    help="Overwrite output file if it already exists.",
)
def runtime_quality_corpus_init(output_path, overwrite):
    """Create a scaffold benchmark corpus for runtime quality checks."""
    try:
        corpus_file = RuntimeQualityBenchmarkService.scaffold_corpus(
            path=output_path,
            overwrite=overwrite,
        )
        _emit_json({"corpus_file": corpus_file})
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)


@main.command("runtime-quality-benchmark")
@click.option(
    "--corpus",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Benchmark corpus JSON path.",
)
@click.option(
    "--model-name",
    default="all-MiniLM-L6-v2",
    show_default=True,
    help="Sentence-transformers model used for corpus embedding.",
)
@click.option(
    "--device",
    default="cpu",
    show_default=True,
    help="Embedding device ('cpu', 'cuda', 'mps', or 'auto').",
)
@click.option(
    "--batch-size",
    type=int,
    default=32,
    show_default=True,
    help="Batch size for embedding generation.",
)
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False),
    help="Optional output directory for metrics JSON artifact.",
)
@click.option(
    "--filename-prefix",
    default="runtime_quality_metrics",
    show_default=True,
    help="Filename prefix for metrics artifacts when --output-dir is provided.",
)
def runtime_quality_benchmark(
    corpus,
    model_name,
    device,
    batch_size,
    output_dir,
    filename_prefix,
):
    """Run corpus-driven embedding quality benchmark and emit metrics."""
    try:
        metrics = _build_runtime_quality_metrics(
            corpus=corpus,
            model_name=model_name,
            device=device,
            batch_size=batch_size,
        )

        if output_dir:
            metrics["output_file"] = RuntimeQualityBenchmarkService.export_metrics(
                metrics=metrics,
                output_dir=output_dir,
                filename_prefix=filename_prefix,
            )

        _emit_json(metrics)
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)


@main.command("runtime-quality-policy-validate")
@click.option(
    "--policy-file",
    default="ci/runtime-quality/quality_gate_policy.json",
    show_default=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Quality gate policy JSON path to validate.",
)
def runtime_quality_policy_validate(policy_file):
    """Validate runtime quality policy file and referenced artifacts."""
    try:
        RuntimeQualityPolicyService.validate_policy_file(policy_file)
        _emit_json({"ok": True, "policy_file": policy_file})
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)


@main.command("runtime-quality-baseline")
@click.option(
    "--corpus",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Benchmark corpus JSON path.",
)
@click.option(
    "--model-name",
    default="all-MiniLM-L6-v2",
    show_default=True,
    help="Sentence-transformers model used for corpus embedding.",
)
@click.option(
    "--device",
    default="cpu",
    show_default=True,
    help="Embedding device ('cpu', 'cuda', 'mps', or 'auto').",
)
@click.option(
    "--batch-size",
    type=int,
    default=32,
    show_default=True,
    help="Batch size for embedding generation.",
)
@click.option(
    "--output-dir",
    default="artifacts/quality",
    show_default=True,
    type=click.Path(file_okay=False),
    help="Directory where stable baseline metrics file will be written.",
)
@click.option(
    "--baseline-filename",
    default="baseline_metrics.json",
    show_default=True,
    help="Stable baseline metrics filename.",
)
@click.option(
    "--overwrite/--no-overwrite",
    default=True,
    show_default=True,
    help="Overwrite baseline file if it already exists.",
)
def runtime_quality_baseline(
    corpus,
    model_name,
    device,
    batch_size,
    output_dir,
    baseline_filename,
    overwrite,
):
    """Generate and persist stable baseline quality metrics in one command."""
    try:
        metrics = _build_runtime_quality_metrics(
            corpus=corpus,
            model_name=model_name,
            device=device,
            batch_size=batch_size,
        )
        baseline_path = str(Path(output_dir) / baseline_filename)
        output_file = RuntimeQualityBenchmarkService.write_metrics_file(
            metrics=metrics,
            output_path=baseline_path,
            overwrite=overwrite,
        )
        _emit_json(
            {
                "output_file": output_file,
                "metrics": metrics,
            }
        )
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)


@main.command("runtime-health-baseline")
@click.option('--config', '-c', type=click.Path(exists=True), required=True, help='Path to YAML/JSON configuration file.')
@click.option(
    "--registry-file",
    required=True,
    type=click.Path(dir_okay=False),
    help="JSON registry file for runtime baselines.",
)
@click.option("--label", help="Optional baseline label (e.g., host or model profile).")
@click.option(
    "--startup-mode",
    type=click.Choice(["permissive", "strict"], case_sensitive=False),
    help="Optional override for embedding startup policy.",
)
@connection_options
def runtime_health_baseline(
    config,
    registry_file,
    label,
    startup_mode,
    database,
    host,
    port,
    username,
    password,
):
    """Capture and store a runtime health baseline entry."""
    try:
        db = _get_db_from_options(database, host, port, username, password)
        pipeline = ConfigurableERPipeline(db=db, config_path=config)
        snapshot = pipeline.get_embedding_runtime_health(startup_mode=startup_mode)
        baseline = RuntimeProfileRegistry.upsert_baseline(
            registry_file=registry_file,
            snapshot=snapshot,
            label=label,
        )
        _emit_json({"registry_file": registry_file, "baseline": baseline})
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)


@main.command("runtime-health-compare")
@click.option('--config', '-c', type=click.Path(exists=True), required=True, help='Path to YAML/JSON configuration file.')
@click.option(
    "--registry-file",
    required=True,
    type=click.Path(dir_okay=False, exists=True),
    help="JSON registry file containing runtime baselines.",
)
@click.option("--label", help="Optional baseline label (must match stored label).")
@click.option(
    "--startup-mode",
    type=click.Choice(["permissive", "strict"], case_sensitive=False),
    help="Optional override for embedding startup policy.",
)
@click.option(
    "--latency-regression-pct",
    type=float,
    default=20.0,
    show_default=True,
    help="Percent latency increase threshold to flag regression.",
)
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False),
    help="Optional output directory for JSON/Markdown/CSV comparison artifacts.",
)
@click.option(
    "--filename-prefix",
    default="runtime_compare",
    show_default=True,
    help="Filename prefix for comparison artifacts when --output-dir is provided.",
)
@connection_options
def runtime_health_compare(
    config,
    registry_file,
    label,
    startup_mode,
    latency_regression_pct,
    output_dir,
    filename_prefix,
    database,
    host,
    port,
    username,
    password,
):
    """Compare current runtime health against a stored baseline."""
    try:
        db = _get_db_from_options(database, host, port, username, password)
        pipeline = ConfigurableERPipeline(db=db, config_path=config)
        snapshot = pipeline.get_embedding_runtime_health(startup_mode=startup_mode)
        comparison = RuntimeProfileRegistry.compare_snapshot(
            registry_file=registry_file,
            snapshot=snapshot,
            label=label,
            latency_regression_pct=latency_regression_pct,
        )
        if output_dir:
            comparison["output_files"] = RuntimeCompareReportService.export_report(
                comparison=comparison,
                output_dir=output_dir,
                filename_prefix=filename_prefix,
            )
        _emit_json(comparison)
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)


@main.command("runtime-health-gate")
@click.option('--config', '-c', type=click.Path(exists=True), required=True, help='Path to YAML/JSON configuration file.')
@click.option(
    "--registry-file",
    required=True,
    type=click.Path(dir_okay=False),
    help="JSON registry file containing runtime baselines.",
)
@click.option("--label", help="Optional baseline label (must match stored label).")
@click.option(
    "--startup-mode",
    type=click.Choice(["permissive", "strict"], case_sensitive=False),
    help="Optional override for embedding startup policy.",
)
@click.option(
    "--latency-regression-pct",
    type=float,
    default=20.0,
    show_default=True,
    help="Percent latency increase threshold to flag regression.",
)
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False),
    help="Optional output directory for JSON/Markdown/CSV comparison artifacts.",
)
@click.option(
    "--filename-prefix",
    default="runtime_gate",
    show_default=True,
    help="Filename prefix for comparison artifacts when --output-dir is provided.",
)
@click.option(
    "--fail-on-regression/--no-fail-on-regression",
    default=False,
    show_default=True,
    help="Exit with code 2 when a regression is detected.",
)
@click.option(
    "--bootstrap-baseline/--no-bootstrap-baseline",
    default=False,
    show_default=True,
    help="Create/update baseline automatically when none exists for the current key.",
)
@click.option(
    "--quality-current-metrics",
    type=click.Path(exists=True, dir_okay=False),
    help="Optional current quality metrics JSON path for combined health+quality gating.",
)
@click.option(
    "--quality-baseline-metrics",
    type=click.Path(exists=True, dir_okay=False),
    help="Optional baseline quality metrics JSON path for combined health+quality gating.",
)
@click.option(
    "--quality-corpus",
    type=click.Path(exists=True, dir_okay=False),
    help="Optional benchmark corpus path to compute current quality metrics on the fly.",
)
@click.option(
    "--quality-model-name",
    default="all-MiniLM-L6-v2",
    show_default=True,
    help="Model name used when --quality-corpus is provided.",
)
@click.option(
    "--quality-device",
    default="cpu",
    show_default=True,
    help="Embedding device used when --quality-corpus is provided.",
)
@click.option(
    "--quality-batch-size",
    type=int,
    default=32,
    show_default=True,
    help="Batch size used when --quality-corpus is provided.",
)
@click.option(
    "--quality-cosine-drift-max",
    type=float,
    default=0.01,
    show_default=True,
    help="Quality gate max cosine drift threshold.",
)
@click.option(
    "--quality-topk-overlap-min",
    type=float,
    default=0.95,
    show_default=True,
    help="Quality gate min top-k overlap threshold.",
)
@connection_options
def runtime_health_gate(
    config,
    registry_file,
    label,
    startup_mode,
    latency_regression_pct,
    output_dir,
    filename_prefix,
    fail_on_regression,
    bootstrap_baseline,
    quality_current_metrics,
    quality_corpus,
    quality_model_name,
    quality_device,
    quality_batch_size,
    quality_baseline_metrics,
    quality_cosine_drift_max,
    quality_topk_overlap_min,
    database,
    host,
    port,
    username,
    password,
):
    """
    Run runtime health, compare against baseline, optionally export artifacts.

    This is the CI-friendly one-shot command for runtime readiness gates.
    """
    try:
        db = _get_db_from_options(database, host, port, username, password)
        pipeline = ConfigurableERPipeline(db=db, config_path=config)
        snapshot = pipeline.get_embedding_runtime_health(startup_mode=startup_mode)
        comparison = RuntimeProfileRegistry.compare_snapshot(
            registry_file=registry_file,
            snapshot=snapshot,
            label=label,
            latency_regression_pct=latency_regression_pct,
        )
        if not comparison.get("baseline_found", False) and bootstrap_baseline:
            baseline = RuntimeProfileRegistry.upsert_baseline(
                registry_file=registry_file,
                snapshot=snapshot,
                label=label,
            )
            comparison["baseline_bootstrapped"] = True
            comparison["baseline"] = baseline.get("snapshot")
            comparison["baseline_entry"] = baseline
        else:
            comparison["baseline_bootstrapped"] = False

        if output_dir:
            comparison["output_files"] = RuntimeCompareReportService.export_report(
                comparison=comparison,
                output_dir=output_dir,
                filename_prefix=filename_prefix,
            )

        ctx = click.get_current_context()

        quality_inputs_provided = any(
            [quality_current_metrics, quality_corpus, quality_baseline_metrics]
        )
        corpus_option_explicitly_set = any(
            ctx.get_parameter_source(param_name) != ParameterSource.DEFAULT
            for param_name in ("quality_model_name", "quality_device", "quality_batch_size")
        )
        if corpus_option_explicitly_set and not quality_corpus:
            raise click.ClickException(
                "Options --quality-model-name/--quality-device/--quality-batch-size require --quality-corpus."
            )
        if quality_inputs_provided:
            if not quality_baseline_metrics:
                raise click.ClickException(
                    "Quality gate requires --quality-baseline-metrics when quality inputs are provided."
                )
            if quality_current_metrics and quality_corpus:
                raise click.ClickException(
                    "Specify only one of --quality-current-metrics or --quality-corpus."
                )
            if not quality_current_metrics and not quality_corpus:
                raise click.ClickException(
                    "Quality gate requires either --quality-current-metrics or --quality-corpus."
                )

        if quality_baseline_metrics and (quality_current_metrics or quality_corpus):
            if quality_current_metrics:
                quality_current = RuntimeQualityGateService.load_metrics(quality_current_metrics)
                quality_current_source = "metrics_file"
            else:
                quality_current = _build_runtime_quality_metrics(
                    corpus=quality_corpus,
                    model_name=quality_model_name,
                    device=quality_device,
                    batch_size=quality_batch_size,
                )
                quality_current_source = "corpus_benchmark"
            quality_baseline = RuntimeQualityGateService.load_metrics(quality_baseline_metrics)
            quality_comparison = RuntimeQualityGateService.compare_metrics(
                current=quality_current,
                baseline=quality_baseline,
                cosine_drift_max=quality_cosine_drift_max,
                topk_overlap_min=quality_topk_overlap_min,
            )
            comparison["quality_gate"] = quality_comparison
            comparison["quality_gate"]["current_source"] = quality_current_source

        _emit_json(comparison)

        regressions = comparison.get("regressions", {})
        has_regression = bool(
            regressions.get("latency_regression") or regressions.get("fallback_regression")
        )
        if comparison.get("quality_gate"):
            has_regression = has_regression or bool(
                comparison["quality_gate"]["regressions"]["quality_regression"]
            )
        if fail_on_regression and has_regression:
            sys.exit(2)
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)


@main.command("runtime-activation-summary")
@click.option(
    "--artifacts-root",
    default="artifacts",
    show_default=True,
    help="Root artifact directory containing runtime/ and quality/ subdirectories.",
)
@click.option(
    "--output-json",
    default="artifacts/runtime/activation_summary.json",
    show_default=True,
    type=click.Path(dir_okay=False),
    help="Path to write machine-readable activation summary JSON.",
)
@click.option(
    "--output-md",
    default="artifacts/runtime/activation_summary.md",
    show_default=True,
    type=click.Path(dir_okay=False),
    help="Path to write markdown activation checklist summary.",
)
def runtime_activation_summary(artifacts_root, output_json, output_md):
    """Summarize runtime matrix artifacts into activation evidence files."""
    try:
        summary = RuntimeActivationEvidenceService.summarize(artifacts_root=artifacts_root)
        markdown = RuntimeActivationEvidenceService.to_markdown(summary)

        output_json_path = Path(output_json)
        output_json_path.parent.mkdir(parents=True, exist_ok=True)
        output_json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

        output_md_path = Path(output_md)
        output_md_path.parent.mkdir(parents=True, exist_ok=True)
        output_md_path.write_text(markdown + "\n", encoding="utf-8")

        _emit_json(
            {
                "artifacts_root": artifacts_root,
                "output_files": {
                    "json": str(output_json_path),
                    "markdown": str(output_md_path),
                },
                "checklist": summary.get("checklist", {}),
            }
        )
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)


@main.command()
@click.option("--collection", required=True, help="Source collection name.")
@click.option("--edge-collection", help="Similarity edge collection override.")
@click.option(
    "--include-runtime-health",
    is_flag=True,
    help="Include embedding runtime diagnostics (requires --config).",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True),
    help="Pipeline YAML/JSON config used for runtime diagnostics.",
)
@click.option(
    "--startup-mode",
    type=click.Choice(["permissive", "strict"], case_sensitive=False),
    help="Optional startup-mode override for runtime diagnostics.",
)
@connection_options
def status(
    collection,
    edge_collection,
    include_runtime_health,
    config_path,
    startup_mode,
    database,
    host,
    port,
    username,
    password,
):
    """Show pipeline status for a collection."""
    try:
        conn = _resolve_connection_args(database, host, port, username, password)
        result = run_pipeline_status(
            **conn,
            collection=collection,
            edge_collection=edge_collection,
        )
        if include_runtime_health:
            if not config_path:
                raise click.ClickException(
                    "--include-runtime-health requires --config <path>"
                )
            db = _get_db_from_options(database, host, port, username, password)
            pipeline = ConfigurableERPipeline(db=db, config_path=config_path)
            result["runtime_health"] = pipeline.get_embedding_runtime_health(
                startup_mode=startup_mode
            )
        _emit_json(result)
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)


@main.command()
@click.option("--collection", required=True, help="Source collection name.")
@click.option("--limit", type=int, default=50, show_default=True, help="Maximum clusters to return.")
@click.option("--min-size", type=int, default=2, show_default=True, help="Minimum cluster size.")
@connection_options
def clusters(collection, limit, min_size, database, host, port, username, password):
    """List stored clusters and quality signals."""
    try:
        conn = _resolve_connection_args(database, host, port, username, password)
        result = run_get_clusters(
            **conn,
            collection=collection,
            limit=limit,
            min_size=min_size,
        )
        _emit_json(result)
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)


@main.command()
@click.option("--collection", required=True, help="Source collection name.")
@click.option("--cluster-collection", help="Stored cluster collection override.")
@click.option("--edge-collection", help="Similarity edge collection override.")
@click.option("--output-dir", required=True, type=click.Path(file_okay=False), help="Directory for JSON/CSV export artifacts.")
@click.option("--filename-prefix", default="cluster_export", show_default=True, help="Filename prefix for exported artifacts.")
@click.option("--limit", type=int, help="Optional maximum number of clusters to export.")
@connection_options
def export(
    collection,
    cluster_collection,
    edge_collection,
    output_dir,
    filename_prefix,
    limit,
    database,
    host,
    port,
    username,
    password,
):
    """Export cluster results to JSON and CSV."""
    try:
        db = _get_db_from_options(database, host, port, username, password)
        service = ClusterExportService(
            db=db,
            source_collection=collection,
            edge_collection=edge_collection,
            cluster_collection=cluster_collection,
        )
        exported = service.export(
            output_dir=output_dir,
            filename_prefix=filename_prefix,
            limit=limit,
        )
        click.echo(click.style("\nExport complete!", fg="green", bold=True))
        _emit_json(
            {
                "collection": collection,
                "cluster_collection": service.cluster_collection,
                "output_files": {
                    "json": exported["json"],
                    "csv": exported["csv"],
                },
                "clusters_exported": exported["clusters_exported"],
            }
        )
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)


@main.command()
@click.option("--collection", required=True, help="Source collection name.")
@click.option("--ground-truth", "ground_truth", required=True, type=click.Path(exists=True), help="Ground-truth pairs file (.json or .csv).")
@click.option("--baseline-field", "baseline_fields", multiple=True, required=True, help="Exact blocking field(s) for the baseline strategy.")
@click.option("--search-view", required=True, help="ArangoSearch view name for BM25 comparison.")
@click.option("--search-field", required=True, help="Field searched by the BM25 strategy.")
@click.option("--blocking-field", help="Optional field used to constrain BM25 comparisons.")
@click.option("--output-dir", required=True, type=click.Path(file_okay=False), help="Directory for benchmark artifacts.")
@click.option("--filename-prefix", default="blocking_benchmark", show_default=True, help="Filename prefix for benchmark artifacts.")
@click.option("--baseline-max-block-size", type=int, default=100, show_default=True, help="Maximum exact-block size.")
@click.option("--hybrid-bm25-threshold", type=float, default=2.0, show_default=True, help="Minimum BM25 score for the comparison strategy.")
@click.option("--hybrid-limit-per-entity", type=int, default=20, show_default=True, help="Maximum BM25 candidates per source record.")
@connection_options
def benchmark(
    collection,
    ground_truth,
    baseline_fields,
    search_view,
    search_field,
    blocking_field,
    output_dir,
    filename_prefix,
    baseline_max_block_size,
    hybrid_bm25_threshold,
    hybrid_limit_per_entity,
    database,
    host,
    port,
    username,
    password,
):
    """Run the supported exact-vs-BM25 blocking benchmark workflow."""
    try:
        db = _get_db_from_options(database, host, port, username, password)
        results = run_blocking_benchmark(
            db=db,
            collection_name=collection,
            ground_truth_path=ground_truth,
            baseline_fields=baseline_fields,
            search_view=search_view,
            search_field=search_field,
            blocking_field=blocking_field,
            output_dir=output_dir,
            filename_prefix=filename_prefix,
            baseline_max_block_size=baseline_max_block_size,
            hybrid_bm25_threshold=hybrid_bm25_threshold,
            hybrid_limit_per_entity=hybrid_limit_per_entity,
        )
        click.echo(click.style("\nBenchmark complete!", fg="green", bold=True))
        _emit_json(results)
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)

@main.command()
@click.option("--input", "-i", "input_path", required=True, type=click.Path(exists=True), help="Input TSV/CSV file.")
@click.option("--config", "-c", "config_path", type=click.Path(exists=True), help="YAML/JSON config with etl.canonical section.")
@click.option("--output-dir", "-o", required=True, type=click.Path(file_okay=False), help="Directory for output JSONL files.")
@click.option("--header", type=click.Path(exists=True), help="Separate header file (TSV/CSV).")
@click.option("--delimiter", default="\t", show_default=True, help="Column delimiter.")
@click.option("--hub-threshold", type=int, default=50, show_default=True, help="In-degree threshold for hub classification.")
@click.option("--from-collection", default="regs", show_default=True, help="Source vertex collection name.")
@click.option("--to-collection", default="canonical_addresses", show_default=True, help="Target canonical node collection name.")
def canonicalize(input_path, config_path, output_dir, header, delimiter, hub_threshold, from_collection, to_collection):
    """Canonicalize addresses at ETL time (pre-load deduplication)."""
    from pathlib import Path
    from .etl import CanonicalResolver, AddressNormalizer
    from .config.er_config import CanonicalETLConfig, ERPipelineConfig

    try:
        etl_cfg = None
        if config_path:
            suffix = Path(config_path).suffix.lower()
            if suffix in (".yaml", ".yml"):
                pipeline_cfg = ERPipelineConfig.from_yaml(config_path)
            else:
                pipeline_cfg = ERPipelineConfig.from_json(config_path)
            etl_cfg = pipeline_cfg.canonical_etl

        if etl_cfg is not None:
            resolver = CanonicalResolver(
                normalizer=AddressNormalizer(locale=etl_cfg.locale),
                signature_fields=etl_cfg.signature_fields,
                field_mapping=etl_cfg.field_mapping,
                shard_key_field=etl_cfg.shard_key_field,
                shard_key_length=etl_cfg.shard_key_length,
                hub_threshold=etl_cfg.hub_threshold,
                hub_markers=etl_cfg.hub_markers,
                provenance=etl_cfg.provenance,
                max_variants=etl_cfg.max_variants,
            )
        else:
            resolver = CanonicalResolver(
                normalizer=AddressNormalizer(),
                hub_threshold=hub_threshold,
            )

        resolver.process_file(
            input_path,
            delimiter=delimiter,
            header_path=header,
        )

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        nodes_written = resolver.write_nodes(str(out / "canonical_addresses.jsonl"))
        edges_written = resolver.write_edges(
            str(out / "hasAddress.jsonl"),
            from_collection=from_collection,
            to_collection=to_collection,
        )

        stats = resolver.stats
        stats["nodes_written"] = nodes_written
        stats["edges_written"] = edges_written

        click.echo(click.style("\nCanonicalization complete!", fg="green", bold=True))
        _emit_json(stats)

    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)


@main.command("estimate")
@click.option('--config', '-c', type=click.Path(exists=True), required=True, help='Pipeline YAML/JSON config.')
@click.option('--sample-size', type=int, default=100_000, show_default=True, help='Candidate pairs to sample for EM.')
@click.option('--max-iterations', type=int, default=50, show_default=True, help='Max EM iterations.')
@click.option('--no-term-frequencies', is_flag=True, help='Skip term-frequency table computation.')
@connection_options
def estimate(config, sample_size, max_iterations, no_term_frequencies, database, host, port, username, password):
    """Estimate Fellegi-Sunter m/u parameters via EM and persist them."""
    try:
        from entity_resolution.learning import ModelParameterEstimator

        db = _get_db_from_options(database, host, port, username, password)
        pipeline = ConfigurableERPipeline(db=db, config_path=config)
        sim_service = pipeline.build_similarity_service()
        field_names = list(pipeline._effective_field_weights().keys())
        if not field_names:
            raise click.ClickException("No similarity fields configured; cannot estimate parameters.")

        estimator = ModelParameterEstimator(
            db=db,
            similarity_service=sim_service,
            edge_collection=pipeline.config.edge_collection,
            field_names=field_names,
        )
        result = estimator.run(
            source_collection=pipeline.config.collection_name,
            sample_size=sample_size,
            with_term_frequencies=not no_term_frequencies,
        )
        click.echo(click.style("\nParameter estimation complete!", fg="green", bold=True))
        _emit_json(result)
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)


@main.command("profile")
@click.option("--collection", required=True, help="Collection to profile.")
@click.option("--sample-size", type=int, default=1000, show_default=True, help="Documents to sample.")
@click.option("--emit-config", is_flag=True, help="Emit a generated similarity config instead of the raw profile.")
@connection_options
def profile(collection, sample_size, emit_config, database, host, port, username, password):
    """Profile a collection's fields and suggest comparators (plan 1.4)."""
    try:
        from entity_resolution.learning import FieldProfiler

        db = _get_db_from_options(database, host, port, username, password)
        profiler = FieldProfiler(db=db, collection=collection, sample_size=sample_size)
        prof = profiler.profile()
        if emit_config:
            _emit_json(profiler.emit_similarity_config(prof))
        else:
            _emit_json(prof)
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)


@main.command("repair-clusters")
@click.option("--collection", required=True, help="Source (vertex) collection name.")
@click.option("--edge-collection", default="similarTo", show_default=True, help="Similarity edge collection.")
@click.option("--cluster-collection", help="Cluster collection (default: <collection>_clusters).")
@click.option("--min-coherence", type=float, default=0.5, show_default=True, help="Mean intra-cluster score below which a cluster is flagged.")
@click.option("--auto-split/--queue-only", default=False, help="Auto-split safe bridges (else queue all flagged clusters).")
@connection_options
def repair_clusters(collection, edge_collection, cluster_collection, min_coherence, auto_split, database, host, port, username, password):
    """Flag low-coherence clusters and split bridge-joined ones (plan 1.3)."""
    try:
        from entity_resolution.services.cluster_repair_service import ClusterRepairService

        db = _get_db_from_options(database, host, port, username, password)
        service = ClusterRepairService(
            db=db,
            edge_collection=edge_collection,
            vertex_collection=collection,
            cluster_collection=cluster_collection or f"{collection}_clusters",
            min_coherence=min_coherence,
        )
        result = service.repair(auto_split=auto_split)
        click.echo(click.style("\nCluster repair complete!", fg="green", bold=True))
        _emit_json(result)
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)


@main.command("migrate")
@click.option(
    "--status",
    "status_only",
    is_flag=True,
    help="Show current/pending schema version without applying anything.",
)
@click.option(
    "--target",
    type=int,
    default=None,
    help="Apply migrations only up to this version (default: latest).",
)
@connection_options
def migrate(status_only, target, database, host, port, username, password):
    """Apply pending ER schema migrations (or show status with --status)."""
    try:
        from entity_resolution.migrations import MigrationRunner

        db = _get_db_from_options(database, host, port, username, password)
        runner = MigrationRunner(db)
        if status_only:
            _emit_json(runner.status())
            return
        result = runner.migrate(target=target)
        click.echo(click.style("\nSchema migration complete!", fg="green", bold=True))
        _emit_json(result)
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)


@main.command("address-resolve")
@connection_options
@click.option("--collection", "-c", required=True, help="Address collection name.")
@click.option("--edge-collection", default="address_sameAs", help="Edge collection for matches.")
@click.option("--config", "config_path", type=click.Path(exists=True), help="YAML config file for field mapping.")
@click.option("--max-block-size", type=int, default=100, help="Max block size for blocking.")
@click.option("--cluster/--no-cluster", default=True, help="Run WCC clustering after edge creation.")
def address_resolve(collection, edge_collection, config_path, max_block_size, cluster, **conn_kwargs):
    """Run address entity resolution pipeline."""
    try:
        conn_args = _resolve_connection_args(**conn_kwargs)
        db = get_database(**conn_args)

        if config_path:
            from .core.address_pipeline import AddressERPipeline
            pipeline = AddressERPipeline.from_yaml(db, config_path)
        else:
            from .core.address_pipeline import AddressERPipeline
            config = {
                "collection": collection,
                "field_mapping": {
                    "street": "street",
                    "city": "city",
                    "state": "state",
                    "postal_code": "postal_code",
                },
                "edge_collection": edge_collection,
                "max_block_size": max_block_size,
                "cluster": cluster,
                "create_edges": True,
            }
            pipeline = AddressERPipeline(db, config)

        results = pipeline.run()
        click.echo(click.style("Address resolution complete!", fg="green", bold=True))
        _emit_json(results)

    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)


@main.command("onnx-export")
@click.argument("model_name")
@click.option("--output-dir", "-o", required=True, help="Directory to write the ONNX model and tokenizer.")
@click.option("--quantize/--no-quantize", default=False, help="Apply INT8 dynamic quantization.")
def onnx_export(model_name, output_dir, quantize):
    """Export a sentence-transformers model to ONNX format."""
    try:
        from .services.onnx_model_exporter import export_model

        click.echo(f"Exporting {model_name} to {output_dir} ...")
        result = export_model(model_name, output_dir, quantize=quantize)
        click.echo(click.style("Export complete!", fg="green", bold=True))
        _emit_json(result)
    except ImportError as e:
        click.echo(click.style(f"Missing dependency: {e}", fg="red"), err=True)
        click.echo("Install with: pip install optimum[onnxruntime] onnx", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)


@main.command("embedding-benchmark")
@connection_options
@click.option("--collection", "-c", required=True, help="Collection to embed.")
@click.option("--fields", required=True, help="Comma-separated fields to concatenate for embedding.")
@click.option("--model", default="all-MiniLM-L6-v2", help="Sentence-transformer model name.")
@click.option("--limit", type=int, default=100, help="Number of records to benchmark.")
@click.option("--batch-size", type=int, default=64, help="Batch size for embedding.")
def embedding_benchmark(collection, fields, model, limit, batch_size, **conn_kwargs):
    """Benchmark embedding generation speed."""
    import time as _time

    try:
        conn_args = _resolve_connection_args(**conn_kwargs)
        db = get_database(**conn_args)

        field_list = [f.strip() for f in fields.split(",")]
        cursor = db.aql.execute(
            "FOR doc IN @@col LIMIT @lim RETURN doc",
            bind_vars={"@col": collection, "lim": limit},
        )
        docs = list(cursor)
        if not docs:
            click.echo(click.style("No documents found.", fg="yellow"))
            return

        texts = [
            " ".join(str(doc.get(f, "")) for f in field_list).strip()
            for doc in docs
        ]
        texts = [t for t in texts if t]

        click.echo(f"Benchmarking {len(texts)} texts with {model} ...")

        svc = EmbeddingService(
            db=db,
            collection=collection,
            model_name=model,
            batch_size=batch_size,
            device="auto",
        )

        start = _time.time()
        embeddings = svc.model.encode(texts, batch_size=batch_size, show_progress_bar=False)
        elapsed = _time.time() - start

        result = {
            "model": model,
            "device": svc.resolved_device,
            "records": len(texts),
            "batch_size": batch_size,
            "embedding_dim": embeddings.shape[1] if hasattr(embeddings, "shape") else "?",
            "elapsed_seconds": round(elapsed, 3),
            "records_per_second": round(len(texts) / elapsed, 1),
        }
        click.echo(click.style("Benchmark complete!", fg="green", bold=True))
        _emit_json(result)

    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)


@main.command()
@connection_options
@click.option("--serve-port", type=int, default=8787, show_default=True, help="Port for the UI server.")
@click.option("--serve-host", default="127.0.0.1", show_default=True, help="Host for the UI server.")
@click.option("--open", "auto_open", is_flag=True, help="Open browser after startup.")
@click.option("--dev", is_flag=True, help="Enable CORS for localhost:5173 (Vite dev server).")
@click.option("--readonly", is_flag=True, help="Disable mutation endpoints.")
@click.option(
    "--auth-token",
    default=None,
    help="Shared secret required on all /api and /ws requests. "
    "Falls back to the ER_UI_AUTH_TOKEN environment variable.",
)
@click.option(
    "--insecure",
    is_flag=True,
    help="Allow binding to a non-loopback host without an auth token (NOT recommended).",
)
def ui(database, host, port, username, password, serve_port, serve_host, auto_open, dev, readonly, auth_token, insecure):
    """Launch the Entity Resolution web UI."""
    import os as _os_auth
    auth_token = (auth_token or _os_auth.getenv("ER_UI_AUTH_TOKEN") or "").strip() or None

    loopback_hosts = {"127.0.0.1", "localhost", "::1", "::ffff:127.0.0.1"}
    is_public_bind = serve_host not in loopback_hosts
    if is_public_bind and not auth_token:
        if not insecure:
            click.echo(
                click.style(
                    f"Refusing to bind the UI to non-loopback host '{serve_host}' without "
                    "authentication.\n\nProvide --auth-token / ER_UI_AUTH_TOKEN, bind to "
                    "127.0.0.1, or pass --insecure to override (NOT recommended).",
                    fg="red",
                ),
                err=True,
            )
            sys.exit(1)
        click.echo(
            click.style(
                f"WARNING: UI is bound to non-loopback host '{serve_host}' with NO "
                "authentication. Anyone who can reach this host has full database access.",
                fg="yellow",
                bold=True,
            ),
            err=True,
        )
    try:
        from entity_resolution.ui.app import create_app
        import uvicorn
    except ImportError:
        click.echo(
            click.style(
                'The UI extra is not installed. Install it with:\n\n'
                '  pip install "arango-entity-resolution[ui]"\n',
                fg="red",
            ),
            err=True,
        )
        sys.exit(1)

    args = _resolve_connection_args(database, host, port, username, password)
    conn_params = {
        "host": args["host"],
        "port": args["port"],
        "username": args["username"],
        "password": args["password"],
        "database": args["database"],
    }

    db = None
    try:
        db = _get_db_from_options(database, host, port, username, password)
    except Exception as e:
        click.echo(click.style(f"Warning: Could not connect to ArangoDB: {e}", fg="yellow"), err=True)
        click.echo(click.style("Starting UI without database — API calls will return errors until a connection is available.", fg="yellow"))

    import os as _os
    alias_env = _os.getenv("ARANGO_COLLECTION_ALIASES", "").strip()
    collection_aliases: dict[str, str] = {}
    if alias_env:
        for pair in alias_env.split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                collection_aliases[k.strip()] = v.strip()

    allowed_origins = ["http://localhost:5173"] if dev else None
    app = create_app(
        db,
        readonly=readonly,
        allowed_origins=allowed_origins,
        connection_params=conn_params,
        collection_aliases=collection_aliases,
        auth_token=auth_token,
    )

    if auto_open:
        import threading
        import time
        import webbrowser

        def _open_browser():
            time.sleep(1.5)
            webbrowser.open(f"http://{serve_host}:{serve_port}")

        threading.Thread(target=_open_browser, daemon=True).start()

    click.echo(click.style(f"Starting Entity Resolution UI on http://{serve_host}:{serve_port}", fg="green", bold=True))
    uvicorn.run(app, host=serve_host, port=serve_port)


if __name__ == '__main__':
    main()
