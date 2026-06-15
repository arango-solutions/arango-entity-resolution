#!/usr/bin/env python3
"""
Migration 001: repair GraphRAG self-loop provenance edges.

GraphRAGLinker used to write extraction-link edges with _from == _to
(both pointing at the matched entity), storing the source document only
as a string attribute. Edges must run document -> entity so the graph
can be traversed from documents to extracted entities.

The self-loops are recoverable: each carries `source_doc` (the document
key). This script rewrites every self-loop edge of type "extracted_link"
to `_from = <document-collection>/<source_doc>`. Self-loops without a
`source_doc` cannot be repaired and are reported (and removed only with
--delete-unrepairable).

Idempotent: already-repaired edges (_from != _to) are never touched.

Usage:
    python scripts/migrations/001_fix_graphrag_self_loop_edges.py \
        --database er_db \
        --edge-collection extraction_links \
        --document-collection documents [--dry-run]

Connection settings come from --host/--port/--username/--password or the
ARANGO_HOST / ARANGO_PORT / ARANGO_USERNAME / ARANGO_PASSWORD env vars.
"""

from __future__ import annotations

import argparse
import os
import sys

from arango import ArangoClient


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1].strip())
    p.add_argument("--host", default=os.environ.get("ARANGO_HOST", "localhost"))
    p.add_argument("--port", type=int, default=int(os.environ.get("ARANGO_PORT", "8529")))
    p.add_argument("--username", default=os.environ.get("ARANGO_USERNAME", "root"))
    p.add_argument("--password", default=os.environ.get("ARANGO_PASSWORD"))
    p.add_argument("--database", required=True)
    p.add_argument("--edge-collection", required=True,
                   help="Edge collection containing extraction_link edges")
    p.add_argument("--document-collection", required=True,
                   help="Collection the source documents live in (new _from side)")
    p.add_argument("--dry-run", action="store_true",
                   help="Report what would change without writing")
    p.add_argument("--delete-unrepairable", action="store_true",
                   help="Delete self-loop edges that have no source_doc")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.password is None:
        print("error: no password (use --password or ARANGO_PASSWORD)", file=sys.stderr)
        return 2

    client = ArangoClient(hosts=f"http://{args.host}:{args.port}")
    db = client.db(args.database, username=args.username, password=args.password)

    if not db.has_collection(args.edge_collection):
        print(f"error: edge collection '{args.edge_collection}' not found", file=sys.stderr)
        return 2
    if not db.has_collection(args.document_collection):
        print(f"error: document collection '{args.document_collection}' not found",
              file=sys.stderr)
        return 2

    self_loops = list(db.aql.execute(
        """
        FOR e IN @@edges
            FILTER e._from == e._to AND e.type == "extracted_link"
            RETURN {_key: e._key, _to: e._to, source_doc: e.source_doc}
        """,
        bind_vars={"@edges": args.edge_collection},
    ))

    repairable = [e for e in self_loops if e.get("source_doc")]
    unrepairable = [e for e in self_loops if not e.get("source_doc")]

    print(f"self-loop extraction_link edges: {len(self_loops)} "
          f"({len(repairable)} repairable, {len(unrepairable)} without source_doc)")

    if args.dry_run:
        for e in repairable[:10]:
            print(f"  would repair {e['_key']}: "
                  f"_from -> {args.document_collection}/{e['source_doc']}")
        if len(repairable) > 10:
            print(f"  ... and {len(repairable) - 10} more")
        return 0

    edges = db.collection(args.edge_collection)
    repaired = 0
    for e in repairable:
        edges.update({
            "_key": e["_key"],
            "_from": f"{args.document_collection}/{e['source_doc']}",
        })
        repaired += 1
    print(f"repaired: {repaired}")

    if unrepairable:
        if args.delete_unrepairable:
            for e in unrepairable:
                edges.delete(e["_key"])
            print(f"deleted unrepairable self-loops: {len(unrepairable)}")
        else:
            keys = ", ".join(e["_key"] for e in unrepairable[:10])
            print(f"WARNING: {len(unrepairable)} self-loops have no source_doc and "
                  f"were left in place (first keys: {keys}). "
                  f"Re-run with --delete-unrepairable to remove them.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
