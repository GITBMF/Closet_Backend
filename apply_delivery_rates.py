#!/usr/bin/env python3
"""
Wire the delivery-rate seed into config + startup.

Adds a SEED_DELIVERY_RATES_ON_STARTUP flag (default True, mirroring geo) and
calls ensure_delivery_rates_seeded() in the app lifespan right after the geo
seed. With region rates present, checkout resolves an instant total instead of
falling into quote_required.

Pairs with the new file app/modules/delivery_pricing/seed.py.

USAGE (from repo root):
    python apply_delivery_rates.py [--dry-run]
Idempotent.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

CONFIG = "app/core/config.py"
MAIN = "app/main.py"

EDITS = [
    (CONFIG, "SEED_DELIVERY_RATES_ON_STARTUP",
     "    SEED_GEO_ON_STARTUP: bool = True\n",
     "    SEED_GEO_ON_STARTUP: bool = True\n"
     "    SEED_DELIVERY_RATES_ON_STARTUP: bool = True\n"),
    (MAIN, "from app.modules.delivery_pricing.seed import ensure_delivery_rates_seeded",
     "from app.modules.geo.seed import ensure_geo_seeded\n",
     "from app.modules.geo.seed import ensure_geo_seeded\n"
     "from app.modules.delivery_pricing.seed import ensure_delivery_rates_seeded\n"),
    (MAIN, "await ensure_delivery_rates_seeded()",
     "await ensure_geo_seeded()\n",
     "await ensure_geo_seeded()\n    await ensure_delivery_rates_seeded()\n"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    root = Path(args.root).resolve()

    by_file: dict[str, list[tuple[str, str, str]]] = {}
    for f, marker, anchor, new in EDITS:
        by_file.setdefault(f, []).append((marker, anchor, new))

    applied = skipped = failed = 0
    for rel, edits in by_file.items():
        path = root / rel
        if not path.exists():
            print(f"[MISS] {rel}")
            failed += len(edits)
            continue
        text = original = path.read_text(encoding="utf-8")
        for marker, anchor, new in edits:
            if marker in text:
                print(f"[skip] {rel}: already applied")
                skipped += 1
                continue
            if text.count(anchor) != 1:
                print(f"[FAIL] {rel}: anchor found {text.count(anchor)}x (need 1)")
                failed += 1
                continue
            text = text.replace(anchor, new, 1)
            print(f"[ok]   {rel}: applied")
            applied += 1
        if text != original and not args.dry_run:
            path.write_text(text, encoding="utf-8")

    print(f"\nDone. applied={applied} skipped={skipped} failed={failed}"
          + ("  (dry-run)" if args.dry_run else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
