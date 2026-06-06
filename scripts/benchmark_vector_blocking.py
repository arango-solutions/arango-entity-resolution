#!/usr/bin/env python3
"""
Benchmark brute-force vs native vector-index (APPROX_NEAR_COSINE) blocking.

Requires ArangoDB 3.12+ (vector index) and a collection whose documents already
have embeddings in ``--embedding-field`` (use EmbeddingService to populate them).

Reports wall-clock time for each backend and the recall of the ANN result set
relative to the brute-force result set (treated as ground truth).

Usage:
    python scripts/benchmark_vector_blocking.py \
        --collection customers --embedding-field embedding_vector \
        --threshold 0.8 --limit 20
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Set, Tuple


def _connect():
    from arango import ArangoClient

    host = os.getenv("ARANGO_HOST", "localhost")
    port = os.getenv("ARANGO_PORT", "8529")
    endpoint = os.getenv("ARANGO_ENDPOINT", f"http://{host}:{port}")
    username = os.getenv("ARANGO_USERNAME", "root")
    password = os.getenv("ARANGO_PASSWORD", os.getenv("ARANGO_ROOT_PASSWORD", ""))
    database = os.getenv("ARANGO_DATABASE", "_system")
    client = ArangoClient(hosts=endpoint)
    return client.db(database, username=username, password=password)


def _pair_set(pairs) -> Set[Tuple[str, str]]:
    out: Set[Tuple[str, str]] = set()
    for p in pairs:
        a, b = p["doc1_key"], p["doc2_key"]
        out.add((a, b) if a < b else (b, a))
    return out


def _brute_force_all_pairs(db, collection, field, threshold, limit):
    """Ground-truth O(n^2) cosine self-join. Benchmark-only; not a product path."""
    query = f"""
        FOR doc1 IN @@col
            FILTER doc1.{field} != null
            FOR doc2 IN @@col
                FILTER doc2.{field} != null
                FILTER doc1._key < doc2._key
                LET dp = SUM(FOR i IN 0..LENGTH(doc1.{field})-1
                    RETURN doc1.{field}[i] * doc2.{field}[i])
                LET m1 = SQRT(SUM(FOR x IN doc1.{field} RETURN x*x))
                LET m2 = SQRT(SUM(FOR x IN doc2.{field} RETURN x*x))
                LET sim = (m1 > 0 AND m2 > 0) ? dp / (m1 * m2) : 0.0
                FILTER sim >= @threshold
                SORT sim DESC
                LIMIT @limit
                RETURN {{doc1_key: doc1._key, doc2_key: doc2._key, similarity: sim}}
    """
    return list(db.aql.execute(
        query, bind_vars={"@col": collection, "threshold": threshold, "limit": limit}
    ))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", required=True)
    parser.add_argument("--embedding-field", default="embedding_vector")
    parser.add_argument("--threshold", type=float, default=0.8)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--n-lists", type=int, default=None)
    args = parser.parse_args()

    from entity_resolution.similarity.ann_adapter import ANNAdapter

    db = _connect()

    # Brute-force baseline (ground truth) -- benchmark-only, not a product path.
    t0 = time.perf_counter()
    brute_pairs = _brute_force_all_pairs(
        db, args.collection, args.embedding_field, args.threshold, args.limit
    )
    brute_time = time.perf_counter() - t0

    # Native vector index (build if needed).
    ann = ANNAdapter(
        db=db, collection=args.collection, embedding_field=args.embedding_field,
    )
    index_info = ann.ensure_vector_index(n_lists=args.n_lists)
    if ann.method != "arango_vector_index":
        print("ERROR: vector index path not active; check ArangoDB version/index.", file=sys.stderr)
        return 1

    t0 = time.perf_counter()
    ann_pairs = ann.find_all_pairs(
        similarity_threshold=args.threshold, limit_per_entity=args.limit
    )
    ann_time = time.perf_counter() - t0

    brute_set = _pair_set(brute_pairs)
    ann_set = _pair_set(ann_pairs)
    recall = (len(brute_set & ann_set) / len(brute_set)) if brute_set else 1.0
    speedup = (brute_time / ann_time) if ann_time > 0 else float("inf")

    print("=" * 60)
    print(f"Collection:        {args.collection}")
    print(f"Index:             {index_info}")
    print(f"Brute force:       {len(brute_set):>8} pairs  {brute_time:8.3f}s")
    print(f"Vector index:      {len(ann_set):>8} pairs  {ann_time:8.3f}s")
    print(f"Speedup:           {speedup:8.1f}x")
    print(f"Recall (vs brute): {recall*100:7.1f}%")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
