"""Write the FastAPI OpenAPI document to a file (ABB-29 contract check, ABB-02 A7).

Usage (from backend/, so that the locked environment is used):
    uv run --locked python ../scripts/export_openapi.py ../frontend/.openapi.json

No database, no network: the document is generated from the route and model definitions only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: export_openapi.py <output.json>", file=sys.stderr)
        return 2
    from agroblackbox.app import app

    out = Path(argv[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"OpenAPI {app.openapi()['info']['version']}: {len(app.openapi()['paths'])} paths -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
