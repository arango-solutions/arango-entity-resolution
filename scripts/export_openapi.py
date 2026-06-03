#!/usr/bin/env python3
"""Export the Entity Resolution UI FastAPI OpenAPI schema to a JSON file.

This is the source of truth for the frontend's generated TypeScript types
(``ui/src/api/schema.ts``).  Run it whenever UI routes or Pydantic models
change, then regenerate the TS types::

    python scripts/export_openapi.py            # writes ui/openapi.json
    cd ui && npm run gen:types                  # writes ui/src/api/schema.ts

CI runs both steps and fails if the committed artifacts are stale (see
.github/workflows/ui-contract.yml), preventing frontend/backend contract drift.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_OUTPUT = _REPO_ROOT / "ui" / "openapi.json"


def build_openapi() -> dict:
    """Build the OpenAPI schema from the UI app with no database connection."""
    try:
        from entity_resolution.ui.app import create_app
    except ImportError as exc:  # pragma: no cover - dependency guidance
        raise SystemExit(
            "The UI extra is required to export the OpenAPI schema. Install it "
            'with: pip install -e ".[ui]"'
        ) from exc

    # db=None is fine: OpenAPI generation only introspects routes/models.
    app = create_app(db=None)
    return app.openapi()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=_DEFAULT_OUTPUT,
        help=f"Output path for the OpenAPI JSON (default: {_DEFAULT_OUTPUT}).",
    )
    args = parser.parse_args(argv)

    schema = build_openapi()
    # Stable, deterministic output so the CI diff check is reliable.
    text = json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    print(f"Wrote OpenAPI schema to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
