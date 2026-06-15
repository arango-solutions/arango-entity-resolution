"""
GraphRAG: Document entity extraction and linking.

Uses an LLM to extract structured entities from unstructured text and
links them to existing entities in an ArangoDB graph.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """\
You are an expert in Named Entity Recognition and data extraction.

Extract all entities from the following text. For each entity, provide:
- name: the entity's canonical name
- type: one of {entity_types}
- attributes: a dict of any additional attributes mentioned

Return a JSON array of objects. Example:
[{{"name": "Acme Corp", "type": "company", "attributes": {{"city": "New York"}}}}]

If no entities are found, return an empty array [].
Do NOT add any text outside the JSON array.

## Text
{text}
"""


class DocumentEntityExtractor:
    """Extract structured entities from unstructured text using an LLM.

    Parameters
    ----------
    llm_config:
        An :class:`LLMProviderConfig` (or None to use env defaults).
    entity_types:
        List of valid entity types to extract (e.g. ``["company", "person", "address"]``).
    """

    def __init__(
        self,
        llm_config: Optional[Any] = None,
        entity_types: Optional[List[str]] = None,
    ) -> None:
        self.entity_types = entity_types or ["company", "person", "address", "organization"]
        self._verifier = self._build_verifier(llm_config)

    @staticmethod
    def _build_verifier(llm_config):
        import litellm  # noqa: F401
        from ..reasoning.llm_verifier import LLMMatchVerifier

        if llm_config is not None:
            return LLMMatchVerifier.from_provider_config(llm_config)
        return LLMMatchVerifier()

    def extract(self, text: str) -> List[Dict[str, Any]]:
        """Extract entities from a text document.

        Parameters
        ----------
        text:
            Unstructured text to extract entities from.

        Returns
        -------
        list[dict]
            Each dict has ``name``, ``type``, ``attributes``, and
            ``extraction_metadata`` keys.
        """
        import litellm

        prompt = EXTRACTION_PROMPT.format(
            text=text,
            entity_types=", ".join(self.entity_types),
        )

        start = time.time()
        kwargs: Dict[str, Any] = {
            "model": self._verifier.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2048,
            "temperature": 0.1,
            "timeout": self._verifier.timeout_seconds,
        }
        if self._verifier.api_key:
            kwargs["api_key"] = self._verifier.api_key
        if self._verifier.base_url:
            kwargs["api_base"] = self._verifier.base_url

        response = litellm.completion(**kwargs)
        raw = response.choices[0].message.content.strip()
        elapsed = time.time() - start

        entities = self._parse_response(raw)
        for ent in entities:
            ent["extraction_metadata"] = {
                "model": self._verifier.model,
                "latency_seconds": round(elapsed, 3),
            }

        logger.info("Extracted %d entities in %.2fs", len(entities), elapsed)
        return entities

    def extract_batch(self, texts: List[str]) -> List[List[Dict[str, Any]]]:
        """Extract entities from multiple documents."""
        return [self.extract(t) for t in texts]

    @staticmethod
    def _parse_response(raw: str) -> List[Dict[str, Any]]:
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return parsed
            return [parsed]
        except json.JSONDecodeError:
            logger.warning("LLM returned non-JSON: %s", raw[:200])
            return []


class GraphRAGLinker:
    """Link extracted entities to existing ArangoDB graph entities.

    Uses similarity matching to find the best existing entity for each
    extracted entity and creates edges with provenance metadata.

    Parameters
    ----------
    db:
        ArangoDB database connection.
    entity_collection:
        Collection containing existing entities to link against.
    edge_collection:
        Edge collection for storing extraction links.
    similarity_threshold:
        Minimum similarity score to create a link (0.0–1.0).
    name_field:
        Field name in the entity collection that contains the entity name.
    document_collection:
        Collection containing the source documents. Provenance edges run
        document -> entity, so this (together with ``source_doc_key`` at
        link time) is required for edges to be created; matches found
        without document context are returned with ``edge_key: None``.
    """

    def __init__(
        self,
        db: Any,
        entity_collection: str,
        edge_collection: str,
        similarity_threshold: float = 0.70,
        name_field: str = "name",
        document_collection: Optional[str] = None,
    ) -> None:
        self.db = db
        self.entity_collection = entity_collection
        self.edge_collection = edge_collection
        self.similarity_threshold = similarity_threshold
        self.name_field = name_field
        self.document_collection = document_collection

    def link(
        self,
        extracted_entities: List[Dict[str, Any]],
        source_doc_key: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Match extracted entities to existing graph entities.

        Parameters
        ----------
        extracted_entities:
            Output from :meth:`DocumentEntityExtractor.extract`.
        source_doc_key:
            Optional key of the source document (for provenance).

        Returns
        -------
        list[dict]
            Each dict has ``extracted``, ``matched_key``, ``score``,
            ``linked`` (bool), and ``edge_key`` fields. ``edge_key`` is
            None when no provenance edge was created (requires both
            ``document_collection`` and ``source_doc_key``).
        """
        import jellyfish

        results = []
        for entity in extracted_entities:
            name = entity.get("name", "")
            if not name:
                results.append(self._no_match(entity))
                continue

            best = self._find_best_match(name, jellyfish)
            if best and best["score"] >= self.similarity_threshold:
                edge_key = self._create_edge(
                    best["key"], entity, source_doc_key
                )
                results.append({
                    "extracted": entity,
                    "matched_key": best["key"],
                    "matched_name": best["name"],
                    "score": best["score"],
                    "linked": True,
                    "edge_key": edge_key,
                })
            else:
                results.append(self._no_match(entity))

        logger.info(
            "Linked %d / %d entities (threshold=%.2f)",
            sum(1 for r in results if r["linked"]),
            len(results),
            self.similarity_threshold,
        )
        return results

    def _find_best_match(self, name: str, jellyfish_mod) -> Optional[Dict[str, Any]]:
        cursor = self.db.aql.execute(
            "FOR doc IN @@col RETURN {key: doc._key, name: doc.@field}",
            bind_vars={
                "@col": self.entity_collection,
                "field": self.name_field,
            },
        )
        best: Optional[Dict[str, Any]] = None
        for row in cursor:
            if not row.get("name"):
                continue
            score = jellyfish_mod.jaro_winkler_similarity(
                name.lower(), row["name"].lower()
            )
            if best is None or score > best["score"]:
                best = {"key": row["key"], "name": row["name"], "score": round(score, 4)}
        return best

    def _create_edge(
        self,
        matched_key: str,
        entity: Dict[str, Any],
        source_doc_key: Optional[str],
    ) -> Optional[str]:
        if not (self.document_collection and source_doc_key):
            logger.warning(
                "No document context (document_collection=%r, source_doc_key=%r); "
                "skipping provenance edge for entity %r",
                self.document_collection, source_doc_key, matched_key,
            )
            return None

        edge = {
            "_from": f"{self.document_collection}/{source_doc_key}",
            "_to": f"{self.entity_collection}/{matched_key}",
            "type": "extracted_link",
            "extracted_name": entity.get("name"),
            "extracted_type": entity.get("type"),
            "source_doc": source_doc_key,
        }
        if not self.db.has_collection(self.edge_collection):
            self.db.create_collection(self.edge_collection, edge=True)
        result = self.db.collection(self.edge_collection).insert(edge)
        return result["_key"]

    @staticmethod
    def _no_match(entity: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "extracted": entity,
            "matched_key": None,
            "matched_name": None,
            "score": 0.0,
            "linked": False,
            "edge_key": None,
        }
