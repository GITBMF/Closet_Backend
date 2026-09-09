"""Sourcing service — the supplier workflow (submissions + review).

Cross-module rule honoured: sourcing reaches identity and catalogue only through
their SERVICES, on the same session, so an approval (grant role) or a catalogue
(create piece + link) commits as one transaction.

Two state machines, both enforced here:
  sourcer:     pending -> approved | rejected
  submission:  submitted -> in_review -> accepted -> catalogued
                                      -> refused
Every submission transition writes a submission_status_history row.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from app.modules.catalogue.service import CatalogueService
from app.modules.identity.service import IdentityService
from app.modules.identity.constants import UserRole
from app.modules.notifications.constants import NotificationChannel
from app.modules.notifications.hook import send_notification
from app.modules.sourcing.constants import (
    CollaborationType,
    SourcerStatus,
    SubmissionStatus,
)
from app.modules.sourcing.models import (
    SourcerProfile,
    Submission,
    SubmissionMedia,
    SubmissionStatusHistory,
)
from app.modules.sourcing.repository import SourcingRepository
from app.modules.sourcing.schemas import (
    ApplyIn,
    CatalogueIn,
    DecisionIn,
    MediaIn,
    SubmissionCreate,
)

# a sourcer can create submissions only once approved
_ACTIVE = {SourcerStatus.APPROVED}

_SUBMISSION_TRANSITIONS: dict[SubmissionStatus, set[SubmissionStatus]] = {
    SubmissionStatus.SUBMITTED: {SubmissionStatus.IN_REVIEW, SubmissionStatus.ACCEPTED, SubmissionStatus.REFUSED},
    SubmissionStatus.IN_REVIEW: {SubmissionStatus.ACCEPTED, SubmissionStatus.REFUSED},
    SubmissionStatus.ACCEPTED: {SubmissionStatus.CATALOGUED},
    SubmissionStatus.REFUSED: set(),
    SubmissionStatus.CATALOGUED: set(),
}


class SourcingService:
    def __init__(
        self,
        repo: SourcingRepository,
        identity: IdentityService,
        catalogue: CatalogueService,
    ) -> None:
        self.repo = repo
        self.identity = identity
        self.catalogue = catalogue

    @property
    def db(self):
        return self.repo.db

    # ============================================ customer: application
    async def apply(self, user_id: uuid.UUID, payload: ApplyIn) -> SourcerProfile:
        existing = await self.repo.get_profile_for_user(user_id)
        if existing is not None and existing.status in (
            SourcerStatus.PENDING, SourcerStatus.APPROVED
        ):
            raise ConflictError(
                "Une demande est déjà en cours ou approuvée.",
                code="application_exists",
            )
        if existing is not None:
            # re-apply after a rejection: reset to pending
            existing.status = SourcerStatus.PENDING
            existing.rejection_reason = None
            existing.display_name = payload.display_name or existing.display_name
            existing.phone = payload.phone or existing.phone
            existing.collaboration_type = payload.collaboration_type or existing.collaboration_type
            existing.payout_method = payload.payout_method or existing.payout_method
            existing.payout_phone = payload.payout_phone or existing.payout_phone
            await self.db.commit()
            await self._alert_admins_of_application(existing.display_name)
            return await self.repo.get_profile(existing.id)

        profile = SourcerProfile(
            user_id=user_id,
            display_name=payload.display_name,
            phone=payload.phone,
            collaboration_type=payload.collaboration_type,
            payout_method=payload.payout_method,
            payout_phone=payload.payout_phone,
            status=SourcerStatus.PENDING,
        )
        await self.repo.add_profile(profile)
        await self.db.commit()
        await self._alert_admins_of_application(profile.display_name)
        return await self.repo.get_profile(profile.id)

    async def _alert_admins_of_application(self, applicant_name: str | None) -> None:
        """Best-effort: e-mail active admins that a new sourcer application
        arrived, so requests aren't missed.

        Runs after the application is committed. The notification hook sends on
        its own session and never raises, so a mail hiccup can't affect the
        application; any lookup error is swallowed too.
        """
        try:
            admins, _ = await self.identity.repo.list_users(
                role=UserRole.ADMIN, is_active=True, page_size=100
            )
        except Exception:  # noqa: BLE001
            return
        for admin in admins:
            if not getattr(admin, "email", None):
                continue
            await send_notification(
                "sourcing.application_received",
                channel=NotificationChannel.EMAIL,
                to_email=admin.email,
                context={"applicant_name": applicant_name or "Un utilisateur"},
            )

    async def my_profile(self, user_id: uuid.UUID) -> SourcerProfile:
        profile = await self.repo.get_profile_for_user(user_id)
        if profile is None:
            raise NotFoundError(
                "Aucun profil de sourcer. Postulez d'abord.", code="no_sourcer_profile"
            )
        return profile

    async def _require_active_profile(self, user_id: uuid.UUID) -> SourcerProfile:
        profile = await self.repo.get_profile_for_user(user_id)
        if profile is None:
            raise NotFoundError("Aucun profil de sourcer.", code="no_sourcer_profile")
        if profile.status not in _ACTIVE:
            raise PermissionDeniedError(
                "Votre profil de sourcer n'est pas encore approuvé.",
                code="sourcer_not_approved",
            )
        return profile

    # ============================================ customer: submissions
    async def create_submission(
        self, user_id: uuid.UUID, payload: SubmissionCreate
    ) -> Submission:
        profile = await self._require_active_profile(user_id)
        submission = Submission(
            sourcer_id=profile.id,
            item_type=payload.item_type,
            brand=payload.brand,
            size_label=payload.size_label,
            condition_claimed=payload.condition_claimed,
            desired_price=payload.desired_price,
            story=payload.story,
            share_permission=payload.share_permission,
            collection_method=payload.collection_method,
            status=SubmissionStatus.SUBMITTED,
        )
        await self.repo.add_submission(submission)
        await self.repo.add_history(
            SubmissionStatusHistory(
                submission_id=submission.id, from_status=None,
                to_status=SubmissionStatus.SUBMITTED, actor_id=user_id,
                reason="submitted",
            )
        )
        await self.db.commit()
        return await self.repo.get_submission(submission.id, with_media=True)

    async def my_submissions(self, user_id: uuid.UUID, *, limit: int, offset: int):
        profile = await self._require_active_profile(user_id)
        return await self.repo.list_submissions_for_sourcer(
            profile.id, limit=limit, offset=offset
        )

    async def my_submission(
        self, user_id: uuid.UUID, submission_id: uuid.UUID
    ) -> Submission:
        profile = await self.my_profile(user_id)
        submission = await self.repo.get_submission(submission_id, with_media=True)
        if submission is None or submission.sourcer_id != profile.id:
            raise NotFoundError("Soumission introuvable.", code="submission_not_found")
        return submission

    async def add_media(
        self, user_id: uuid.UUID, submission_id: uuid.UUID, payload: MediaIn
    ) -> SubmissionMedia:
        submission = await self.my_submission(user_id, submission_id)
        if submission.status not in (
            SubmissionStatus.SUBMITTED, SubmissionStatus.IN_REVIEW
        ):
            raise ConflictError(
                "On ne peut plus ajouter de photos à cette soumission.",
                code="submission_locked",
            )
        media = SubmissionMedia(
            submission_id=submission.id, url=payload.url, position=payload.position
        )
        await self.repo.add_media(media)
        await self.db.commit()
        return media

    async def my_payouts(self, user_id: uuid.UUID):
        profile = await self.my_profile(user_id)
        return await self.repo.list_payouts_for_sourcer(profile.id)

    # ================================================ admin: applications
    async def list_applications(self, *, status, limit, offset):
        return await self.repo.list_profiles(status=status, limit=limit, offset=offset)

    async def approve_application(
        self, profile_id: uuid.UUID, *, admin_id: uuid.UUID
    ) -> SourcerProfile:
        profile = await self.repo.get_profile(profile_id)
        if profile is None:
            raise NotFoundError("Demande introuvable.", code="application_not_found")
        if profile.status is SourcerStatus.APPROVED:
            return profile
        if profile.status is not SourcerStatus.PENDING:
            raise ConflictError(
                "Seule une demande en attente peut être approuvée.",
                code="not_pending",
            )
        profile.status = SourcerStatus.APPROVED
        profile.approved_at = datetime.now(UTC)
        profile.rejection_reason = None
        # grant the SOURCER role via identity (same session -> one commit)
        await self.identity.grant_sourcer_role(
            user_id=profile.user_id, approved_by=admin_id
        )
        await self.db.commit()
        return await self.repo.get_profile(profile_id)

    async def reject_application(
        self, profile_id: uuid.UUID, *, reason: str, admin_id: uuid.UUID
    ) -> SourcerProfile:
        profile = await self.repo.get_profile(profile_id)
        if profile is None:
            raise NotFoundError("Demande introuvable.", code="application_not_found")
        if profile.status is not SourcerStatus.PENDING:
            raise ConflictError(
                "Seule une demande en attente peut être rejetée.", code="not_pending"
            )
        profile.status = SourcerStatus.REJECTED
        profile.rejection_reason = reason
        await self.db.commit()
        return await self.repo.get_profile(profile_id)

    # ================================================== admin: review
    async def list_review_queue(self, *, status, limit, offset):
        return await self.repo.list_submissions_for_review(
            status=status, limit=limit, offset=offset
        )

    async def get_for_review(self, submission_id: uuid.UUID) -> Submission:
        submission = await self.repo.get_submission(submission_id, with_media=True)
        if submission is None:
            raise NotFoundError("Soumission introuvable.", code="submission_not_found")
        return submission

    async def decide(
        self, submission_id: uuid.UUID, payload: DecisionIn, *, admin_id: uuid.UUID
    ) -> Submission:
        submission = await self.get_for_review(submission_id)
        target = SubmissionStatus.ACCEPTED if payload.accept else SubmissionStatus.REFUSED
        if not payload.accept and not payload.reason:
            raise ValidationError(
                "Un motif est requis pour refuser.", code="reason_required"
            )
        self._guard_transition(submission.status, target)
        prev = submission.status
        submission.status = target
        if target is SubmissionStatus.REFUSED:
            submission.refusal_reason = payload.reason
        submission.decided_by = admin_id
        await self.repo.add_history(
            SubmissionStatusHistory(
                submission_id=submission.id, from_status=prev, to_status=target,
                actor_id=admin_id, reason=payload.reason or target.value,
            )
        )
        await self.db.commit()
        return await self.repo.get_submission(submission_id, with_media=True)

    async def catalogue_submission(
        self, submission_id: uuid.UUID, payload: CatalogueIn, *, admin_id: uuid.UUID
    ) -> Submission:
        """Turn an ACCEPTED submission into a catalogue piece (via catalogue
        service), link it back, and mark the submission CATALOGUED."""
        submission = await self.get_for_review(submission_id)
        if submission.status is not SubmissionStatus.ACCEPTED:
            raise ConflictError(
                "Seule une soumission acceptée peut être cataloguée.",
                code="not_accepted",
            )
        self._guard_transition(submission.status, SubmissionStatus.CATALOGUED)

        acquisition = (
            "consignment"
            if await self._is_consignment(submission.sourcer_id)
            else "direct_buy"
        )
        piece = await self.catalogue.create_from_submission(
            title=payload.title,
            condition=payload.condition,
            price=payload.price,
            sourcer_id=submission.sourcer_id,
            house_id=payload.house_id,
            universe_id=payload.universe_id,
            size_label=payload.size_label or submission.size_label,
            story=submission.story,
            acquisition_type=acquisition,
        )
        submission.piece_id = piece.id
        submission.status = SubmissionStatus.CATALOGUED
        await self.repo.add_history(
            SubmissionStatusHistory(
                submission_id=submission.id,
                from_status=SubmissionStatus.ACCEPTED,
                to_status=SubmissionStatus.CATALOGUED,
                actor_id=admin_id, reason="catalogued",
            )
        )
        await self.db.commit()
        return await self.repo.get_submission(submission_id, with_media=True)

    # ------------------------------------------------------- helpers
    async def _is_consignment(self, sourcer_id: uuid.UUID) -> bool:
        profile = await self.repo.get_profile(sourcer_id)
        return (
            profile is not None
            and profile.collaboration_type is CollaborationType.CONSIGNMENT
        )

    @staticmethod
    def _guard_transition(current: SubmissionStatus, target: SubmissionStatus) -> None:
        if target not in _SUBMISSION_TRANSITIONS[current]:
            raise ConflictError(
                f"Transition invalide: {current.value} → {target.value}.",
                code="invalid_submission_transition",
            )