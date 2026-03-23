"""
Runtime quality policy validation helpers.

Validates CI quality gate policy shape and referenced artifact paths so matrix
jobs can fail fast on policy drift or missing files.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


class RuntimeQualityPolicyService:
    """Validate runtime quality policy files used by CI workflows."""

    REQUIRED_PROFILES = ("linux-cpu", "apple-silicon", "linux-gpu")
    REQUIRED_PATH_FIELDS = ("quality_corpus", "quality_baseline_metrics")
    REQUIRED_NUMERIC_FIELDS = (
        "quality_batch_size",
        "quality_cosine_drift_max",
        "quality_topk_overlap_min",
    )

    @classmethod
    def load_policy(cls, policy_path: str) -> Dict[str, Any]:
        path = Path(policy_path)
        if not path.exists():
            raise ValueError(f"Policy file does not exist: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    @classmethod
    def validate_policy_file(cls, policy_path: str) -> Dict[str, Any]:
        policy = cls.load_policy(policy_path)
        profiles = policy.get("profiles", {})
        if not isinstance(profiles, dict):
            raise ValueError("Policy 'profiles' must be an object.")

        for profile in cls.REQUIRED_PROFILES:
            if profile not in profiles:
                raise ValueError(f"Missing profile in quality gate policy: {profile}")
            cls._validate_profile(profile=profile, config=profiles[profile])

        return policy

    @classmethod
    def _validate_profile(cls, profile: str, config: Dict[str, Any]) -> None:
        if not isinstance(config, dict):
            raise ValueError(f"Profile {profile} must be an object.")

        for field in cls.REQUIRED_PATH_FIELDS:
            value = config.get(field)
            if not value:
                raise ValueError(f"Profile {profile} missing required field: {field}")
            target = Path(str(value))
            if not target.exists():
                raise ValueError(
                    f"Profile {profile} references missing file in {field}: {target}"
                )

        batch_size = config.get("quality_batch_size")
        if not isinstance(batch_size, int) or batch_size <= 0:
            raise ValueError(
                f"Profile {profile} must provide positive int quality_batch_size, got: {batch_size}"
            )

        for field in ("quality_cosine_drift_max", "quality_topk_overlap_min"):
            value = config.get(field)
            if value is None:
                raise ValueError(
                    f"Profile {profile} missing required numeric field: {field}"
                )
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                raise ValueError(
                    f"Profile {profile} field {field} must be numeric, got: {value}"
                ) from None
            if not 0 <= numeric <= 1:
                raise ValueError(
                    f"Profile {profile} field {field} must be between 0 and 1, got: {numeric}"
                )
