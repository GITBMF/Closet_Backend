#!/usr/bin/env python3
"""
Wire discount (privilege) codes into the app.

The privileges module ships new files (repository / schemas / service /
dependencies / router). This patcher connects them:

  * orders/service.py      — OrderService takes a PrivilegeService; checkout
                             validates payload.privilege_code, applies the
                             discount to the total, and records a redemption.
  * orders/dependencies.py — build the PrivilegeService and pass it in.
  * app/api/router.py      — mount the admin + public privilege routers.
  * app/ops/admin.py       — add a "Codes promo" view under Commerce.

The privilege_code / privilege_redemption tables already exist (0003_full_schema),
so NO migration is needed.

USAGE (from repo root):
    python apply_privilege_codes.py [--dry-run]
Idempotent.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SERVICE = "app/modules/orders/service.py"
DEPS = "app/modules/orders/dependencies.py"
API = "app/api/router.py"
OPS = "app/ops/admin.py"

# ---- orders/service.py -------------------------------------------------------
SVC_IMPORT_ANCHOR = (
    "from app.modules.delivery_pricing.service import DeliveryPricingService\n"
)
SVC_IMPORT_NEW = (
    "from app.modules.delivery_pricing.service import DeliveryPricingService\n"
    "from app.modules.privileges.service import PrivilegeService\n"
)

SVC_INIT_ANCHOR = (
    "        repo: OrderRepository,\n"
    "        catalogue: CatalogueService,\n"
    "        pricing: DeliveryPricingService,\n"
    "    ) -> None:\n"
    "        self.repo = repo\n"
    "        self.catalogue = catalogue\n"
    "        self.pricing = pricing\n"
)
SVC_INIT_NEW = (
    "        repo: OrderRepository,\n"
    "        catalogue: CatalogueService,\n"
    "        pricing: DeliveryPricingService,\n"
    "        privileges: PrivilegeService,\n"
    "    ) -> None:\n"
    "        self.repo = repo\n"
    "        self.catalogue = catalogue\n"
    "        self.pricing = pricing\n"
    "        self.privileges = privileges\n"
)

SVC_DISCOUNT_ANCHOR = (
    "        subtotal = sum((Decimal(p.price) for p in pieces), Decimal(0))\n"
    "        discount = Decimal(0)  # privilege codes applied by the privileges module later\n"
    "        total = subtotal + delivery_fee - discount\n"
)
SVC_DISCOUNT_NEW = (
    "        subtotal = sum((Decimal(p.price) for p in pieces), Decimal(0))\n"
    "        discount = Decimal(0)\n"
    "        applied_code = None\n"
    "        if payload.privilege_code:\n"
    "            applied_code, discount = await self.privileges.apply(\n"
    "                payload.privilege_code, subtotal\n"
    "            )\n"
    "        total = subtotal + delivery_fee - discount\n"
)

SVC_REDEEM_ANCHOR = "        await self.repo.add_purchase(purchase)\n"
SVC_REDEEM_NEW = (
    "        await self.repo.add_purchase(purchase)\n"
    "        if applied_code is not None:\n"
    "            await self.privileges.redeem(\n"
    "                applied_code,\n"
    "                purchase_id=order_id,\n"
    "                user_id=user_id,\n"
    "                amount=discount,\n"
    "            )\n"
)

# ---- orders/dependencies.py --------------------------------------------------
DEPS_IMPORT_ANCHOR = (
    "from app.modules.delivery_pricing.service import DeliveryPricingService\n"
)
DEPS_IMPORT_NEW = (
    "from app.modules.delivery_pricing.service import DeliveryPricingService\n"
    "from app.modules.privileges.repository import PrivilegeRepository\n"
    "from app.modules.privileges.service import PrivilegeService\n"
)

DEPS_BUILD_ANCHOR = (
    "    pricing = DeliveryPricingService(\n"
    "        DeliveryPricingRepository(db), GeoRepository(db)\n"
    "    )\n"
    "    return OrderService(OrderRepository(db), catalogue, pricing)\n"
)
DEPS_BUILD_NEW = (
    "    pricing = DeliveryPricingService(\n"
    "        DeliveryPricingRepository(db), GeoRepository(db)\n"
    "    )\n"
    "    privileges = PrivilegeService(PrivilegeRepository(db))\n"
    "    return OrderService(OrderRepository(db), catalogue, pricing, privileges)\n"
)

# ---- app/api/router.py -------------------------------------------------------
API_IMPORT_ANCHOR = (
    "from app.modules.orders.router import router as orders_router\n"
)
API_IMPORT_NEW = (
    "from app.modules.orders.router import router as orders_router\n"
    "from app.modules.privileges.router import admin_router as privileges_admin_router\n"
    "from app.modules.privileges.router import router as privileges_router\n"
)

API_INCLUDE_ANCHOR = (
    "api_router.include_router(orders_router)\n"
    "api_router.include_router(orders_admin_router)\n"
)
API_INCLUDE_NEW = (
    "api_router.include_router(orders_router)\n"
    "api_router.include_router(orders_admin_router)\n"
    "api_router.include_router(privileges_router)\n"
    "api_router.include_router(privileges_admin_router)\n"
)

# ---- app/ops/admin.py --------------------------------------------------------
OPS_IMPORT_ANCHOR = (
    "from app.modules.delivery_pricing.models import DeliveryRate\n"
)
OPS_IMPORT_NEW = (
    "from app.modules.delivery_pricing.models import DeliveryRate\n"
    "from app.modules.privileges.models import PrivilegeCode\n"
)

OPS_VIEW_ANCHOR = "class DeliveryRateView(_Reference):\n"
OPS_VIEW_NEW = (
    "class PrivilegeCodeView(_Reference):\n"
    '    identity = "privilege-code"\n'
    '    name = "Code promo"\n'
    '    label = "Codes promo"\n'
    '    icon = "fa fa-ticket"\n'
    "    fields = [\n"
    '        "code", "type", "value", "min_order_amount", "max_uses", "times_used",\n'
    '        "valid_from", "valid_until", "is_active", "created_at",\n'
    "    ]\n"
    '    exclude_fields_from_list = ["min_order_amount", "valid_from", "valid_until", "created_at"]\n'
    '    exclude_fields_from_create = ["times_used", "created_at"]\n'
    "    # code / type are fixed after creation; times_used is a read-only counter\n"
    '    exclude_fields_from_edit = ["code", "type", "times_used", "created_at"]\n'
    '    searchable_fields = ["code"]\n'
    "\n\n"
    "class DeliveryRateView(_Reference):\n"
)

OPS_REG_ANCHOR = (
    "            DeliveryView(Delivery),\n"
    "            DeliveryEventView(DeliveryEvent),\n"
    "            ReturnView(ReturnTicket),\n"
    "        ],\n"
)
OPS_REG_NEW = (
    "            DeliveryView(Delivery),\n"
    "            DeliveryEventView(DeliveryEvent),\n"
    "            ReturnView(ReturnTicket),\n"
    "            PrivilegeCodeView(PrivilegeCode),\n"
    "        ],\n"
)

EDITS = [
    (SERVICE, "from app.modules.privileges.service import PrivilegeService", SVC_IMPORT_ANCHOR, SVC_IMPORT_NEW),
    (SERVICE, "self.privileges = privileges", SVC_INIT_ANCHOR, SVC_INIT_NEW),
    (SERVICE, "applied_code, discount = await self.privileges.apply", SVC_DISCOUNT_ANCHOR, SVC_DISCOUNT_NEW),
    (SERVICE, "await self.privileges.redeem(", SVC_REDEEM_ANCHOR, SVC_REDEEM_NEW),
    (DEPS, "from app.modules.privileges.service import PrivilegeService", DEPS_IMPORT_ANCHOR, DEPS_IMPORT_NEW),
    (DEPS, "privileges = PrivilegeService(PrivilegeRepository(db))", DEPS_BUILD_ANCHOR, DEPS_BUILD_NEW),
    (API, "from app.modules.privileges.router import router as privileges_router", API_IMPORT_ANCHOR, API_IMPORT_NEW),
    (API, "api_router.include_router(privileges_router)", API_INCLUDE_ANCHOR, API_INCLUDE_NEW),
    (OPS, "from app.modules.privileges.models import PrivilegeCode", OPS_IMPORT_ANCHOR, OPS_IMPORT_NEW),
    (OPS, "class PrivilegeCodeView(_Reference):", OPS_VIEW_ANCHOR, OPS_VIEW_NEW),
    (OPS, "PrivilegeCodeView(PrivilegeCode),", OPS_REG_ANCHOR, OPS_REG_NEW),
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
