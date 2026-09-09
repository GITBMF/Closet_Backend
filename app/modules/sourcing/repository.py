"""Sourcing repository — profiles, submissions, media, history, payouts.

Writes flush but do not commit; the service owns the transaction boundary so a
decision AND its status-history row (and any cross-module call) commit together.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.sourcing.constants import SourcerStatus, SubmissionStatus
from app.modules.sourcing.models import (
    Payout,
    SourcerProfile,
    Submission,
    SubmissionMedia,
    SubmissionStatusHistory,
)


class SourcingRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ----------------------------------------------------- profiles
    async def add_profile(self, profile: SourcerProfile) -> SourcerProfile:
        self.db.add(profile)
        await self.db.flush()
        return profile

    async def get_profile(self, profile_id: uuid.UUID) -> SourcerProfile | None:
        return await self.db.get(SourcerProfile, profile_id)

    async def get_profile_for_user(self, user_id: uuid.UUID) -> SourcerProfile | None:
        return (
            await self.db.execute(
                select(SourcerProfile).where(SourcerProfile.user_id == user_id)
            )
        ).scalar_one_or_none()

    async def list_profiles(
        self, *, status: SourcerStatus | None, limit: int, offset: int
    ) -> tuple[list[SourcerProfile], int]:
        base = select(SourcerProfile)
        if status is not None:
            base = base.where(SourcerProfile.status == status)
        total = (
            await self.db.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()
        rows = (
            await self.db.execute(
                base.order_by(SourcerProfile.created_at.desc()).limit(limit).offset(offset)
            )
        ).scalars().all()
        return list(rows), int(total)

    async def count_profiles_by_status(self) -> dict[SourcerStatus, int]:
        """One grouped query: {status: count}. Absent statuses are simply missing."""
        rows = (
            await self.db.execute(
                select(SourcerProfile.status, func.count())
                .group_by(SourcerProfile.status)
            )
        ).all()
        return {status: int(n) for status, n in rows}

    # --------------------------------------------------- submissions
    async def add_submission(self, submission: Submission) -> Submission:
        self.db.add(submission)
        await self.db.flush()
        return submission

    async def get_submission(
        self, submission_id: uuid.UUID, *, with_media: bool = False
    ) -> Submission | None:
        stmt = select(Submission).where(Submission.id == submission_id)
        if with_media:
            stmt = stmt.options(selectinload(Submission.media))
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def list_submissions_for_sourcer(
        self, sourcer_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[list[Submission], int]:
        base = select(Submission).where(Submission.sourcer_id == sourcer_id)
        total = (
            await self.db.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()
        rows = (
            await self.db.execute(
                base.order_by(Submission.created_at.desc()).limit(limit).offset(offset)
            )
        ).scalars().all()
        return list(rows), int(total)

    async def list_submissions_for_review(
        self, *, status: SubmissionStatus | None, limit: int, offset: int
    ) -> tuple[list[Submission], int]:
        base = select(Submission)
        if status is not None:
            base = base.where(Submission.status == status)
        total = (
            await self.db.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()
        rows = (
            await self.db.execute(
                base.order_by(Submission.created_at.asc()).limit(limit).offset(offset)
            )
        ).scalars().all()
        return list(rows), int(total)

    # -------------------------------------------------------- media
    async def add_media(self, media: SubmissionMedia) -> SubmissionMedia:
        self.db.add(media)
        await self.db.flush()
        return media

    async def media_for(self, submission_id: uuid.UUID) -> list[SubmissionMedia]:
        stmt = (
            select(SubmissionMedia)
            .where(SubmissionMedia.submission_id == submission_id)
            .order_by(SubmissionMedia.position)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    # ------------------------------------------------------ history
    async def add_history(self, row: SubmissionStatusHistory) -> None:
        self.db.add(row)
        await self.db.flush()

    # ------------------------------------------------------ payouts
    async def list_payouts_for_sourcer(self, sourcer_id: uuid.UUID) -> list[Payout]:
        stmt = (
            select(Payout)
            .where(Payout.sourcer_id == sourcer_id)
            .order_by(Payout.created_at.desc())
        )
        return list((await self.db.execute(stmt)).scalars().all())