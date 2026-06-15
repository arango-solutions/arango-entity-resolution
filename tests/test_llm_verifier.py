"""
Unit tests for LLMMatchVerifier.

LLM calls are mocked — no API key or network required.
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import MagicMock, patch


RECORD_A = {"name": "Acme Corp", "city": "Boston", "state": "MA"}
RECORD_B = {"name": "Acme Corporation", "city": "Boston", "state": "Massachusetts"}
FIELD_SCORES = {
    "name": {"score": 0.84, "method": "jaro_winkler"},
    "city": {"score": 1.0, "method": "exact"},
    "state": {"score": 0.72, "method": "jaro_winkler"},
}


class TestLLMMatchVerifier:
    def _verifier(self, **kwargs):
        from entity_resolution.reasoning.llm_verifier import LLMMatchVerifier
        return LLMMatchVerifier(model="test/model", api_key="test-key", **kwargs)

    def test_needs_verification_in_range(self):
        v = self._verifier(low_threshold=0.55, high_threshold=0.80)
        assert v.needs_verification(0.70) is True

    def test_needs_verification_above_range(self):
        v = self._verifier(low_threshold=0.55, high_threshold=0.80)
        assert v.needs_verification(0.85) is False

    def test_needs_verification_below_range(self):
        v = self._verifier(low_threshold=0.55, high_threshold=0.80)
        assert v.needs_verification(0.40) is False

    def test_fast_path_high_score_no_llm(self):
        v = self._verifier()
        result = v.verify(RECORD_A, RECORD_B, score=0.95, field_scores=FIELD_SCORES)
        assert result["decision"] == "match"
        assert result["llm_called"] is False

    def test_fast_path_low_score_no_llm(self):
        v = self._verifier()
        result = v.verify(RECORD_A, RECORD_B, score=0.30, field_scores=FIELD_SCORES)
        assert result["decision"] == "no_match"
        assert result["llm_called"] is False

    @patch("entity_resolution.reasoning.llm_verifier.litellm")
    def test_llm_called_for_uncertain_score(self, mock_litellm):
        llm_response = MagicMock()
        llm_response.choices[0].message.content = json.dumps({
            "decision": "match",
            "confidence": 0.88,
            "reasoning": "Abbreviation difference only.",
        })
        mock_litellm.completion.return_value = llm_response

        v = self._verifier(low_threshold=0.55, high_threshold=0.80)
        result = v.verify(RECORD_A, RECORD_B, score=0.70, field_scores=FIELD_SCORES)

        assert result["llm_called"] is True
        assert result["decision"] == "match"
        assert result["confidence"] == pytest.approx(0.88)
        assert result["score_override"] is not None  # pushed above high threshold

    @patch("entity_resolution.reasoning.llm_verifier.litellm")
    def test_llm_no_match_decision(self, mock_litellm):
        llm_response = MagicMock()
        llm_response.choices[0].message.content = json.dumps({
            "decision": "no_match",
            "confidence": 0.92,
            "reasoning": "Same name, completely different businesses.",
        })
        mock_litellm.completion.return_value = llm_response

        v = self._verifier()
        result = v.verify(RECORD_A, RECORD_B, score=0.70, field_scores=FIELD_SCORES)

        assert result["decision"] == "no_match"
        assert result["score_override"] is not None
        assert result["score_override"] < 0.55  # pushed below low threshold

    @patch("entity_resolution.reasoning.llm_verifier.litellm")
    def test_fallback_on_llm_error(self, mock_litellm):
        mock_litellm.completion.side_effect = RuntimeError("API timeout")

        v = self._verifier()
        result = v.verify(RECORD_A, RECORD_B, score=0.70)

        # Should not raise; falls back gracefully
        assert result["decision"] in {"match", "no_match"}
        assert result["llm_called"] is False
        assert "error" in result

    @patch("entity_resolution.reasoning.llm_verifier.litellm")
    def test_handles_markdown_fenced_json(self, mock_litellm):
        llm_response = MagicMock()
        llm_response.choices[0].message.content = (
            "```json\n{\"decision\": \"match\", \"confidence\": 0.9, \"reasoning\": \"test\"}\n```"
        )
        mock_litellm.completion.return_value = llm_response

        v = self._verifier()
        result = v.verify(RECORD_A, RECORD_B, score=0.70)
        assert result["decision"] == "match"

    @patch("entity_resolution.reasoning.llm_verifier.litellm")
    def test_verify_batch(self, mock_litellm):
        llm_response = MagicMock()
        llm_response.choices[0].message.content = json.dumps({
            "decision": "match", "confidence": 0.9, "reasoning": "ok"
        })
        mock_litellm.completion.return_value = llm_response

        v = self._verifier()
        pairs = [
            (RECORD_A, RECORD_B, 0.95),   # fast path — no LLM
            (RECORD_A, RECORD_B, 0.70),   # LLM called
            (RECORD_A, RECORD_B, 0.30),   # fast path — no LLM
        ]
        results = v.verify_batch(pairs)
        assert len(results) == 3
        assert results[0]["llm_called"] is False
        assert results[1]["llm_called"] is True
        assert results[2]["llm_called"] is False


class TestLLMHardening:
    def _verifier(self, **kwargs):
        from entity_resolution.reasoning.llm_verifier import LLMMatchVerifier
        return LLMMatchVerifier(model="test/model", api_key="test-key", **kwargs)

    def _resp(self, content):
        r = MagicMock()
        r.choices[0].message.content = content
        return r

    @patch("entity_resolution.reasoning.llm_verifier.litellm")
    def test_parse_failure_retries_then_routes_to_review(self, mock_litellm):
        mock_litellm.completion.return_value = self._resp("not json at all")
        v = self._verifier()
        result = v.verify(RECORD_A, RECORD_B, score=0.70)
        assert result["decision"] == "error"
        assert result["needs_review"] is True
        # never fabricates match/no_match from the raw score
        assert v.stats()["parse_failures"] == 1
        assert mock_litellm.completion.call_count == 2  # initial + one retry

    @patch("entity_resolution.reasoning.llm_verifier.litellm")
    def test_parse_failure_recovers_on_retry(self, mock_litellm):
        good = json.dumps({"decision": "match", "confidence": 0.9, "reasoning": "ok"})
        mock_litellm.completion.side_effect = [self._resp("garbage"), self._resp(good)]
        v = self._verifier()
        result = v.verify(RECORD_A, RECORD_B, score=0.70)
        assert result["decision"] == "match"
        assert v.stats()["parse_failures"] == 0

    @patch("entity_resolution.reasoning.llm_verifier.litellm")
    def test_empty_fenced_block_does_not_crash(self, mock_litellm):
        mock_litellm.completion.return_value = self._resp("```\n\n```")
        v = self._verifier()
        result = v.verify(RECORD_A, RECORD_B, score=0.70)  # must not raise
        assert result["decision"] == "error"

    @patch("entity_resolution.reasoning.llm_verifier.litellm")
    def test_max_calls_budget_routes_remaining_to_review(self, mock_litellm):
        good = json.dumps({"decision": "match", "confidence": 0.9, "reasoning": "ok"})
        mock_litellm.completion.return_value = self._resp(good)
        v = self._verifier(max_calls=1)
        first = v.verify(RECORD_A, RECORD_B, score=0.70)
        second = v.verify(RECORD_A, RECORD_B, score=0.70)
        assert first["llm_called"] is True
        assert second["decision"] == "pending_review"
        assert second["llm_called"] is False
        assert v.stats()["budget_stops"] == 1
        assert mock_litellm.completion.call_count == 1  # second never called the LLM

    @patch("entity_resolution.reasoning.llm_verifier.litellm")
    def test_stats_count_calls(self, mock_litellm):
        good = json.dumps({"decision": "no_match", "confidence": 0.8, "reasoning": "x"})
        mock_litellm.completion.return_value = self._resp(good)
        v = self._verifier()
        v.verify(RECORD_A, RECORD_B, score=0.70)
        v.verify(RECORD_A, RECORD_B, score=0.72)
        assert v.stats()["calls"] == 2

    @patch("entity_resolution.reasoning.llm_verifier.litellm")
    def test_mask_fields_hides_pii_from_prompt(self, mock_litellm):
        good = json.dumps({"decision": "match", "confidence": 0.9, "reasoning": "ok"})
        mock_litellm.completion.return_value = self._resp(good)
        a = {"name": "Acme", "ssn": "123-45-6789"}
        b = {"name": "Acme", "ssn": "123-45-6789"}
        v = self._verifier(mask_fields=["ssn"])
        v.verify(a, b, score=0.70)
        prompt = mock_litellm.completion.call_args.kwargs["messages"][0]["content"]
        assert "123-45-6789" not in prompt
        assert "masked:" in prompt

    def test_estimate_cost_returns_structure(self):
        v = self._verifier()
        est = v.estimate_cost(num_pairs=100)
        assert est["num_pairs"] == 100
        assert "cost_usd" in est
