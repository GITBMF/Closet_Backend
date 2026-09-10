#!/usr/bin/env python3
"""
Make delivery prices editable per town / region from the ops panel.

Pairs with the updated app/modules/delivery_pricing/models.py (which adds the
`region` / `city` relationships on DeliveryRate).

  * geo/models.py  — Region and FixedRateCity get an __admin_repr__ so they show
                     by NAME in the rate pickers (instead of a raw id).
  * ops/admin.py   — DeliveryRateView lists scope / region / city / amount /
                     currency, lets an admin CREATE a rate by picking a region or
                     town by name, and EDIT the amount of an existing rate.
                     (scope + target are fixed on edit; to retarget, add a rate.)

USAGE (from repo root):
    python apply_delivery_rate_admin.py [--dry-run]
Idempotent (re-running skips already-applied edits).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

GEO = "app/modules/geo/models.py"
OPS = "app/ops/admin.py"

_REPR = (
    "\n"
    "    async def __admin_repr__(self, request) -> str:  # noqa: ANN001\n"
    "        return self.name\n"
)

REGION_ANCHOR = (
    "    divisions: Mapped[list[Division]] = relationship(\n"
    '        back_populates="region", cascade="all, delete-orphan"\n'
    "    )\n"
)
REGION_NEW = REGION_ANCHOR + _REPR

CITY_ANCHOR = (
    "    neighbourhoods: Mapped[list[Neighbourhood]] = relationship(\n"
    '        back_populates="city", cascade="all, delete-orphan"\n'
    "    )\n"
)
CITY_NEW = CITY_ANCHOR + _REPR

VIEW_ANCHOR = (
    'class DeliveryRateView(_Reference):\n'
    '    identity = "delivery-rate"\n'
    '    name = "Tarif"\n'
    '    label = "Tarifs de livraison"\n'
    '    icon = "fa fa-money-bill-wave"\n'
)
VIEW_NEW = VIEW_ANCHOR + (
    "    fields = [\n"
    '        "scope", "region", "city", "amount", "currency",\n'
    '        "effective_from", "effective_to",\n'
    "    ]\n"
    '    exclude_fields_from_list = ["effective_from", "effective_to"]\n'
    "    # effective dates default in the DB; set them only for a scheduled change\n"
    '    exclude_fields_from_create = ["effective_from", "effective_to"]\n'
    "    # change a price by editing its amount; scope/target are fixed once set\n"
    '    exclude_fields_from_edit = ["scope", "region", "city", "effective_from", "effective_to"]\n'
)

# (file, applied_when_present, anchor, replacement)
EDITS = [
    (GEO, REGION_NEW, REGION_ANCHOR, REGION_NEW),
    (GEO, CITY_NEW, CITY_ANCHOR, CITY_NEW),
    (OPS, VIEW_NEW, VIEW_ANCHOR, VIEW_NEW),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    root = Path(args.root).resolve()

    by_file: dict[str, list[tuple[str, str, str]]] = {}
    for f, present, anchor, new in EDITS:
        by_file.setdefault(f, []).append((present, anchor, new))

    applied = skipped = failed = 0
    for rel, es in by_file.items():
        path = root / rel
        if not path.exists():
            print(f"[MISS] {rel}")
            failed += len(es)
            continue
        text = original = path.read_text(encoding="utf-8")
        for present, anchor, new in es:
            if present in text:                      # already applied
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
