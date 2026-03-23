from __future__ import annotations

import json
from pathlib import Path

from entity_resolution.services.runtime_quality_gate_service import RuntimeQualityGateService


def _load_quality_policy() -> dict:
    path = Path("ci/runtime-quality/quality_gate_policy.json")
    return json.loads(path.read_text(encoding="utf-8"))


def test_quality_policy_profiles_are_well_formed() -> None:
    policy = _load_quality_policy()
    profiles = policy.get("profiles", {})

    for profile in ("linux-cpu", "apple-silicon", "linux-gpu"):
        assert profile in profiles
        cfg = profiles[profile]
        assert cfg["quality_corpus"].endswith("runtime_quality_corpus.json")
        assert cfg["quality_baseline_metrics"].endswith(f"{profile}.json")
        assert cfg["quality_batch_size"] > 0
        assert 0 <= cfg["quality_cosine_drift_max"] <= 1
        assert 0 <= cfg["quality_topk_overlap_min"] <= 1


def test_quality_policy_thresholds_drive_regression_decision() -> None:
    policy = _load_quality_policy()
    cfg = policy["profiles"]["linux-cpu"]
    baseline_path = Path(cfg["quality_baseline_metrics"])
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))

    clean_current = {
        "cosine_drift": cfg["quality_cosine_drift_max"] - 0.01,
        "topk_overlap": cfg["quality_topk_overlap_min"] + 0.05,
    }
    regressed_current = {
        "cosine_drift": cfg["quality_cosine_drift_max"] + 0.05,
        "topk_overlap": cfg["quality_topk_overlap_min"] - 0.2,
    }

    clean = RuntimeQualityGateService.compare_metrics(
        current=clean_current,
        baseline=baseline,
        cosine_drift_max=cfg["quality_cosine_drift_max"],
        topk_overlap_min=cfg["quality_topk_overlap_min"],
    )
    regressed = RuntimeQualityGateService.compare_metrics(
        current=regressed_current,
        baseline=baseline,
        cosine_drift_max=cfg["quality_cosine_drift_max"],
        topk_overlap_min=cfg["quality_topk_overlap_min"],
    )

    assert clean["regressions"]["quality_regression"] is False
    assert regressed["regressions"]["quality_regression"] is True
