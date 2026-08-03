"""Integration tests for the sourcing module (submissions + review).

Covers the supplier lifecycle against real tables: apply, the approval gate on
submitting, admin approve/reject (approve grants the sourcer role via identity),
submit + media, the review decision (accept/refuse, reason required to refuse),
cataloguing an accepted submission (calls the catalogue service and links the
piece), and the status-history timeline.

Identity and catalogue are exercised through lightweight fakes with the real
method signatures, so the sourcing workflow and its DB writes are covered without
importing those modules' internals.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.core.exceptions import (
    ConflictError,
    PermissionDeniedError,
    ValidationError,
)
from app.modules.sourcing.constants import CollaborationType, SourcerStatus, SubmissionStatus
from app.modules.sourcing.repository import SourcingRepository
from app.modules.sourcing.schemas import (
    ApplyIn,
    CatalogueIn,
    DecisionIn,
    MediaIn,
    SubmissionCreate,
)
from app.modules.sourcing.service import SourcingService


class _FakeIdentity:
    def __init__(self) -> None:
        self.granted: list[tuple] = []

    async def grant_sourcer_role(self, *, user_id, approved_by):
        self.granted.append((user_id, approved_by))
        return None


class _FakePiece:
    def __init__(self, pid) -> None:
        self.id = pid


class _FakeCatalogue:
    def __init__(self) -> None:
        self.created: list[dict] = []

    async def create_from_submission(self, *, title, condition, price, sourcer_id, **kw):
        self.created.append({"title": title, "sourcer_id": sourcer_id, **kw})
        pid = uuid.uuid4()
        async with AsyncSessionLocal() as s:
            await s.execute(
                text(
                    "INSERT INTO piece (id,title,slug,price,status,sku,condition,currency) "
                    "VALUES (:i,:t,:sl,:p,'draft',:sk,'good','XAF')"
                ),
                {"i": pid, "t": title, "sl": f"p-{pid.hex[:6]}", "p": price, "sk": f"CLO-{pid.hex[:6]}"},
            )
            await s.commit()
        return _FakePiece(pid)


def _svc(db, identity=None, catalogue=None) -> SourcingService:
    return SourcingService(
        SourcingRepository(db), identity or _FakeIdentity(), catalogue or _FakeCatalogue()
    )


async def _mk_user() -> uuid.UUID:
    uid = uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO users (id,email,full_name,role,is_active) "
                "VALUES (:i,:e,'U','customer',true)"
            ),
            {"i": uid, "e": f"u{uid.hex[:6]}@c.cm"},
        )
        await s.commit()
    return uid


async def _approved_sourcer(collaboration=None) -> uuid.UUID:
    uid = await _mk_user()
    async with AsyncSessionLocal() as db:
        await _svc(db).apply(uid, ApplyIn(display_name="S", collaboration_type=collaboration))
        prof = await _svc(db).repo.get_profile_for_user(uid)
    admin = await _mk_user()
    async with AsyncSessionLocal() as db:
        await _svc(db).approve_application(prof.id, admin_id=admin)
    return uid


@pytest_asyncio.fixture(autouse=True)
async def _clean() -> AsyncGenerator[None, None]:
    yield
    async with AsyncSessionLocal() as s:
        await s.execute(
            text(
                "TRUNCATE payout_item, payout, submission_status_history, submission_media, "
                "submission, sourcer_profile, piece, users RESTART IDENTITY CASCADE"
            )
        )
        await s.commit()


class TestApplication:
    async def test_apply_creates_pending_profile(self):
        uid = await _mk_user()
        async with AsyncSessionLocal() as db:
            p = await _svc(db).apply(uid, ApplyIn(display_name="Ada Store"))
        assert p.status is SourcerStatus.PENDING

    async def test_reapply_while_pending_rejected(self):
        uid = await _mk_user()
        async with AsyncSessionLocal() as db:
            await _svc(db).apply(uid, ApplyIn(display_name="A"))
        with pytest.raises(ConflictError):
            async with AsyncSessionLocal() as db:
                await _svc(db).apply(uid, ApplyIn(display_name="A"))

    async def test_approve_grants_role_and_sets_approved(self):
        uid = await _mk_user()
        async with AsyncSessionLocal() as db:
            await _svc(db).apply(uid, ApplyIn(display_name="A"))
            prof = await _svc(db).repo.get_profile_for_user(uid)
        admin = await _mk_user()
        identity = _FakeIdentity()
        async with AsyncSessionLocal() as db:
            p = await _svc(db, identity=identity).approve_application(prof.id, admin_id=admin)
        assert p.status is SourcerStatus.APPROVED
        assert p.approved_at is not None
        assert len(identity.granted) == 1

    async def test_reject_requires_pending(self):
        uid = await _mk_user()
        async with AsyncSessionLocal() as db:
            await _svc(db).apply(uid, ApplyIn(display_name="A"))
            prof = await _svc(db).repo.get_profile_for_user(uid)
        admin = await _mk_user()
        async with AsyncSessionLocal() as db:
            p = await _svc(db).reject_application(prof.id, reason="incomplete", admin_id=admin)
        assert p.status is SourcerStatus.REJECTED


class TestSubmissions:
    async def test_cannot_submit_before_approval(self):
        uid = await _mk_user()
        async with AsyncSessionLocal() as db:
            await _svc(db).apply(uid, ApplyIn(display_name="A"))
        with pytest.raises(PermissionDeniedError):
            async with AsyncSessionLocal() as db:
                await _svc(db).create_submission(uid, SubmissionCreate(brand="X"))

    async def test_submit_and_add_media(self):
        uid = await _approved_sourcer()
        async with AsyncSessionLocal() as db:
            sub = await _svc(db).create_submission(
                uid, SubmissionCreate(brand="Gucci", desired_price=Decimal("75000"))
            )
            sid = sub.id
        assert sub.status is SubmissionStatus.SUBMITTED
        async with AsyncSessionLocal() as db:
            await _svc(db).add_media(uid, sid, MediaIn(url="https://x/1.jpg"))
        async with AsyncSessionLocal() as db:
            sub = await _svc(db).my_submission(uid, sid)
        assert len(sub.media) == 1


class TestReview:
    async def test_accept_then_catalogue_links_piece(self):
        uid = await _approved_sourcer(CollaborationType.CONSIGNMENT)
        admin = await _mk_user()
        async with AsyncSessionLocal() as db:
            sub = await _svc(db).create_submission(uid, SubmissionCreate(brand="Gucci"))
            sid = sub.id
        async with AsyncSessionLocal() as db:
            await _svc(db).decide(sid, DecisionIn(accept=True), admin_id=admin)
        catalogue = _FakeCatalogue()
        async with AsyncSessionLocal() as db:
            sub = await _svc(db, catalogue=catalogue).catalogue_submission(
                sid, CatalogueIn(title="Gucci Bag", price=Decimal("75000"), condition="good"),
                admin_id=admin,
            )
        assert sub.status is SubmissionStatus.CATALOGUED
        assert sub.piece_id is not None
        assert len(catalogue.created) == 1
        assert catalogue.created[0]["acquisition_type"] == "consignment"

    async def test_refuse_requires_reason(self):
        uid = await _approved_sourcer()
        admin = await _mk_user()
        async with AsyncSessionLocal() as db:
            sub = await _svc(db).create_submission(uid, SubmissionCreate(brand="Fake"))
            sid = sub.id
        with pytest.raises(ValidationError):
            async with AsyncSessionLocal() as db:
                await _svc(db).decide(sid, DecisionIn(accept=False), admin_id=admin)
        async with AsyncSessionLocal() as db:
            sub = await _svc(db).decide(
                sid, DecisionIn(accept=False, reason="counterfeit"), admin_id=admin
            )
        assert sub.status is SubmissionStatus.REFUSED
        assert sub.refusal_reason == "counterfeit"

    async def test_cannot_catalogue_non_accepted(self):
        uid = await _approved_sourcer()
        admin = await _mk_user()
        async with AsyncSessionLocal() as db:
            sub = await _svc(db).create_submission(uid, SubmissionCreate(brand="X"))
            sid = sub.id
            await _svc(db).decide(sid, DecisionIn(accept=False, reason="no"), admin_id=admin)
        with pytest.raises(ConflictError):
            async with AsyncSessionLocal() as db:
                await _svc(db).catalogue_submission(
                    sid, CatalogueIn(title="x", price=Decimal("1"), condition="good"),
                    admin_id=admin,
                )

    async def test_history_timeline(self):
        uid = await _approved_sourcer()
        admin = await _mk_user()
        async with AsyncSessionLocal() as db:
            sub = await _svc(db).create_submission(uid, SubmissionCreate(brand="G"))
            sid = sub.id
            await _svc(db).decide(sid, DecisionIn(accept=True), admin_id=admin)
        async with AsyncSessionLocal() as db:
            await _svc(db).catalogue_submission(
                sid, CatalogueIn(title="G", price=Decimal("1000"), condition="good"),
                admin_id=admin,
            )
        async with AsyncSessionLocal() as s:
            rows = (
                await s.execute(
                    text(
                        "SELECT to_status FROM submission_status_history "
                        "WHERE submission_id=:i ORDER BY id"
                    ),
                    {"i": sid},
                )
            ).fetchall()
        assert [r[0] for r in rows] == ["submitted", "accepted", "catalogued"]
