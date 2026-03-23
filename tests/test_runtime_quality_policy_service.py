from __future__ import annotations

import json
from pathlib import Path

import pytest

from entity_resolution.services.runtime_quality_policy_service import (
    RuntimeQualityPolicyService,
)


def test_validate_policy_file_accepts_repo_policy() -> None:
    RuntimeQualityPolicyService.validate_policy_file(
        "ci/runtime-quality/quality_gate_policy.json"
    )


def test_validate_policy_file_rejects_missing_profile(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.json"
    baseline = tmp_path / "baseline.json"
    corpus.write_text("{}", encoding="utf-8")
    baseline.write_text('{"cosine_drift":0.1,"topk_overlap":0.7}', encoding="utf-8")

    policy = {
        "version": 1,
        "profiles": {
            "linux-cpu": {
                "quality_corpus": str(corpus),
                "quality_baseline_metrics": str(baseline),
                "quality_batch_size": 16,
                "quality_cosine_drift_max": 0.2,
                "quality_topk_overlap_min": 0.5,
            }
        },
    }
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")

    with pytest.raises(ValueError, match="Missing profile"):
        RuntimeQualityPolicyService.validate_policy_file(str(policy_path))


def test_validate_policy_file_rejects_missing_referenced_file(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.json"
    corpus.write_text("{}", encoding="utf-8")
    missing_baseline = tmp_path / "missing_baseline.json"

    profile_cfg = {
        "quality_corpus": str(corpus),
        "quality_baseline_metrics": str(missing_baseline),
        "quality_batch_size": 16,
        "quality_cosine_drift_max": 0.2,
        "quality_topk_overlap_min": 0.5,
    }
    policy = {
        "version": 1,
        "profiles": {
            "linux-cpu": profile_cfg,
            "apple-silicon": profile_cfg,
            "linux-gpu": profile_cfg,
        },
    }
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")

    with pytest.raises(ValueError, match="references missing file"):
        RuntimeQualityPolicyService.validate_policy_file(str(policy_path))


def test_validate_policy_file_rejects_invalid_threshold_range(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.json"
    baseline = tmp_path / "baseline.json"
    corpus.write_text("{}", encoding="utf-8")
    baseline.write_text('{"cosine_drift":0.1,"topk_overlap":0.7}', encoding="utf-8")

    profile_cfg = {
        "quality_corpus": str(corpus),
        "quality_baseline_metrics": str(baseline),
        "quality_batch_size": 16,
        "quality_cosine_drift_max": 1.5,
        "quality_topk_overlap_min": 0.5,
    }
    policy = {
        "version": 1,
        "profiles": {
            "linux-cpu": profile_cfg,
            "apple-silicon": profile_cfg,
            "linux-gpu": profile_cfg,
        },
    }
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")

    with pytest.raises(ValueError, match="must be between 0 and 1"):
        RuntimeQualityPolicyService.validate_policy_file(str(policy_path))


def test_validate_policy_file_rejects_non_positive_batch_size(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.json"
    baseline = tmp_path / "baseline.json"
    corpus.write_text("{}", encoding="utf-8")
    baseline.write_text('{"cosine_drift":0.1,"topk_overlap":0.7}', encoding="utf-8")

    profile_cfg = {
        "quality_corpus": str(corpus),
        "quality_baseline_metrics": str(baseline),
        "quality_batch_size": 0,
        "quality_cosine_drift_max": 0.2,
        "quality_topk_overlap_min": 0.5,
    }
    policy = {
        "version": 1,
        "profiles": {
            "linux-cpu": profile_cfg,
            "apple-silicon": profile_cfg,
            "linux-gpu": profile_cfg,
        },
    }
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")

    with pytest.raises(ValueError, match="positive int quality_batch_size"):
        RuntimeQualityPolicyService.validate_policy_file(str(policy_path))
