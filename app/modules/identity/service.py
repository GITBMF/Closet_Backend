"""Identity business rules.

Everything that decides *whether* something may happen lives here. The router
only parses and serialises; the repository only reads and writes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import settings
from app.core.storage import StorageError, StorageProvider
from app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitedError,
    ValidationError,
)
from app.modules.identity.constants import (
    ActorType,
    AuditAction,
    TokenType,
    UserRole,
    permissions_for,
)
from app.modules.identity.models import (
    EmailVerificationCode,
    PasswordResetToken,
    RefreshToken,
    User,
)
from app.modules.identity.repository import IdentityRepository


@dataclass(slots=True)
class RequestContext:
    """Who is calling and from where — used for the audit trail."""

    ip: str | None = None
    user_agent: str | None = None


@dataclass(slots=True)
class IssuedTokens:
    access_token: str
    refresh_token: str
    expires_in: int
    user: User


@dataclass(slots=True)
class MFAChallenge:
    challenge_token: str
    expires_in: int


LoginResult = IssuedTokens | MFAChallenge


def actor_type_for(role: UserRole) -> ActorType:
    return {
        UserRole.CUSTOMER: ActorType.CUSTOMER,
        UserRole.SOURCER: ActorType.SOURCER,
        UserRole.COURIER: ActorType.COURIER,
        UserRole.ADMIN: ActorType.ADMIN,
    }[role]


class IdentityService:
    def __init__(
        self, db: AsyncSession, storage: StorageProvider | None = None
    ) -> None:
        self.db = db
        self.repo = IdentityRepository(db)
        self._storage = storage

    # ==================================================== avatar
    _AVATAR_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}

    async def set_avatar(
        self, *, user: User, data: bytes, content_type: str
    ) -> User:
        """Validate + upload a profile picture, then point the user at it.

        Mirrors the catalogue media rules: same allowed types, same size cap,
        same object-storage backend. Replacing an avatar deletes the old object
        best-effort so we do not orphan files.
        """
        if content_type not in settings.MEDIA_ALLOWED_TYPES:
            raise ValidationError(
                f"Type de fichier non supporté: {content_type}.",
                code="unsupported_media_type",
            )
        if len(data) == 0:
            raise ValidationError("Fichier vide.", code="empty_file")
        if len(data) > settings.MEDIA_MAX_BYTES:
            raise ValidationError(
                "Fichier trop volumineux.", code="file_too_large"
            )
        if self._storage is None:
            raise ValidationError(
                "Stockage indisponible.", code="storage_unavailable"
            )

        ext = self._AVATAR_EXT.get(content_type, "bin")
        key = f"avatars/{user.id}/{uuid.uuid4().hex}.{ext}"
        try:
            stored = await self._storage.put(
                key=key, data=data, content_type=content_type
            )
        except StorageError as exc:
            raise ValidationError(
                "Échec du téléversement.", code="upload_failed"
            ) from exc

        old_key = user.avatar_key
        user.avatar_url = stored.url
        user.avatar_key = key
        await self.db.commit()
        await self.db.refresh(user)

        if old_key and old_key != key:
            try:
                await self._storage.delete(key=old_key)
            except StorageError:
                pass
        return user

    async def remove_avatar(self, *, user: User) -> User:
        """Clear a user's profile picture (best-effort delete of the object)."""
        old_key = user.avatar_key
        user.avatar_url = None
        user.avatar_key = None
        await self.db.commit()
        await self.db.refresh(user)
        if old_key and self._storage is not None:
            try:
                await self._storage.delete(key=old_key)
            except StorageError:
                pass
        return user

    # =================================================== registration
    async def register(
        self,
        *,
        email: str,
        password: str,
        full_name: str,
        phone: str | None,
        city: str | None,
        ctx: RequestContext,
    ) -> User:
        """Create a customer account."""
        if await self.repo.email_exists(email):
            # The e-mail is the login identifier, so we cannot pretend success
            # here without breaking the client. Keep the message neutral.
            raise ConflictError(
                "Un compte existe déjà avec cette adresse e-mail.",
                code="email_taken",
            )

        user = User(
            email=email.lower().strip(),
            password_hash=security.hash_password(password),
            full_name=full_name.strip(),
            phone=phone,
            city=city,
            role=UserRole.CUSTOMER,
            is_active=True,
        )
        await self.repo.add_user(user)

        await self.repo.add_audit(
            action=AuditAction.USER_REGISTERED,
            entity_type="user",
            entity_id=str(user.id),
            actor_type=ActorType.CUSTOMER,
            actor_id=user.id,
            ip_address=ctx.ip,
            user_agent=ctx.user_agent,
        )
        await self.db.commit()
        await self.db.refresh(user)
        # Issue + e-mail a verification code (best-effort: a mail hiccup must not
        # fail the registration — the user can request a resend).
        await self._issue_email_verification(user)
        return user

    # ========================================================== login
    async def login(
        self, *, email: str, password: str, ctx: RequestContext
    ) -> LoginResult:
        user = await self.repo.get_by_email(email)

        # Uniform failure: never reveal whether the e-mail exists.
        if user is None:
            security.verify_password(password, None)  # keep timing comparable
            await self._audit_failed_login(None, email, ctx)
            raise AuthenticationError(
                "Identifiants incorrects.", code="invalid_credentials"
            )

        self._assert_not_locked(user)

        if not security.verify_password(password, user.password_hash):
            await self._register_failed_attempt(user, ctx)
            raise AuthenticationError(
                "Identifiants incorrects.", code="invalid_credentials"
            )

        if not user.is_active:
            raise PermissionDeniedError(
                "Ce compte est désactivé.", code="account_disabled"
            )

        if (
            settings.REQUIRE_EMAIL_VERIFICATION
            and user.email is not None
            and user.email_verified_at is None
        ):
            raise PermissionDeniedError(
                "Veuillez vérifier votre adresse e-mail avant de vous connecter.",
                code="email_not_verified",
            )

        # Password is correct — reset the counter before any 2FA step.
        user.failed_login_count = 0
        user.locked_until = None

        # Upgrade the hash transparently if the cost factor changed.
        if user.password_hash and security.needs_rehash(user.password_hash):
            user.password_hash = security.hash_password(password)

        if user.mfa_enabled:
            await self.db.commit()
            return MFAChallenge(
                challenge_token=security.create_mfa_challenge_token(user_id=user.id),
                expires_in=settings.MFA_CHALLENGE_MINUTES * 60,
            )

        if settings.ADMIN_REQUIRES_2FA and user.role is UserRole.ADMIN:
            # Admin without 2FA: allow the session but the router surfaces a
            # setup requirement; blocking here would lock the only admin out.
            pass

        tokens = await self._issue_tokens(user, ctx=ctx)
        await self.repo.add_audit(
            action=AuditAction.USER_LOGGED_IN,
            entity_type="user",
            entity_id=str(user.id),
            actor_type=actor_type_for(user.role),
            actor_id=user.id,
            ip_address=ctx.ip,
            user_agent=ctx.user_agent,
        )
        await self.db.commit()
        return tokens

    async def complete_mfa(
        self, *, challenge_token: str, code: str, ctx: RequestContext
    ) -> IssuedTokens:
        payload = security.decode_token(
            challenge_token, expected_type=TokenType.MFA_CHALLENGE
        )
        if payload is None:
            raise AuthenticationError(
                "Défi d'authentification invalide ou expiré.", code="invalid_challenge"
            )

        user = await self.repo.get_user(uuid.UUID(payload["sub"]))
        if user is None or not user.is_active:
            raise AuthenticationError("Compte indisponible.", code="account_unavailable")

        self._assert_not_locked(user)

        if not security.verify_totp(secret=user.totp_secret or "", code=code):
            await self._register_failed_attempt(user, ctx, action=AuditAction.MFA_CHALLENGE_FAILED)
            raise AuthenticationError("Code de vérification invalide.", code="invalid_code")

        user.failed_login_count = 0
        user.locked_until = None
        tokens = await self._issue_tokens(user, ctx=ctx)
        await self.repo.add_audit(
            action=AuditAction.USER_LOGGED_IN,
            entity_type="user",
            entity_id=str(user.id),
            actor_type=actor_type_for(user.role),
            actor_id=user.id,
            payload={"mfa": True},
            ip_address=ctx.ip,
            user_agent=ctx.user_agent,
        )
        await self.db.commit()
        return tokens

    # ================================================ token lifecycle
    async def _issue_tokens(
        self,
        user: User,
        *,
        ctx: RequestContext,
        family_id: uuid.UUID | None = None,
        parent: RefreshToken | None = None,
    ) -> IssuedTokens:
        perms = sorted(p.value for p in permissions_for(user.role))
        access = security.create_access_token(
            user_id=user.id, role=user.role.value, permissions=perms
        )
        raw_refresh = security.generate_opaque_token()
        record = RefreshToken(
            user_id=user.id,
            token_hash=security.hash_opaque_token(raw_refresh),
            family_id=family_id or uuid.uuid4(),
            parent_id=parent.id if parent else None,
            user_agent=(ctx.user_agent or "")[:255] or None,
            ip_address=ctx.ip,
            expires_at=datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_DAYS),
        )
        await self.repo.add_refresh_token(record)
        user.last_login_at = datetime.now(UTC)
        return IssuedTokens(
            access_token=access,
            refresh_token=raw_refresh,
            expires_in=settings.ACCESS_TOKEN_MINUTES * 60,
            user=user,
        )

    async def refresh(self, *, raw_token: str, ctx: RequestContext) -> IssuedTokens:
        record = await self.repo.get_refresh_by_hash(
            security.hash_opaque_token(raw_token)
        )
        if record is None:
            raise AuthenticationError("Session invalide.", code="invalid_refresh_token")

        if record.revoked_at is not None or record.rotated_at is not None:
            # Reuse of a rotated/revoked token => treat the family as stolen.
            await self.repo.revoke_family(record.family_id)
            await self.repo.add_audit(
                action=AuditAction.USER_TOKEN_REUSE_DETECTED,
                entity_type="user",
                entity_id=str(record.user_id),
                actor_type=ActorType.SYSTEM,
                actor_id=record.user_id,
                payload={"family_id": str(record.family_id)},
                ip_address=ctx.ip,
            )
            await self.db.commit()
            raise AuthenticationError(
                "Session révoquée. Reconnectez-vous.", code="token_reuse_detected"
            )

        if record.expires_at <= datetime.now(UTC):
            raise AuthenticationError("Session expirée.", code="expired_refresh_token")

        user = await self.repo.get_user(record.user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("Compte indisponible.", code="account_unavailable")

        record.rotated_at = datetime.now(UTC)
        tokens = await self._issue_tokens(
            user, ctx=ctx, family_id=record.family_id, parent=record
        )
        await self.repo.add_audit(
            action=AuditAction.USER_TOKEN_REFRESHED,
            entity_type="user",
            entity_id=str(user.id),
            actor_type=actor_type_for(user.role),
            actor_id=user.id,
            ip_address=ctx.ip,
        )
        await self.db.commit()
        return tokens

    async def logout(
        self,
        *,
        user: User,
        raw_token: str | None,
        all_devices: bool,
        ctx: RequestContext,
    ) -> int:
        if all_devices:
            count = await self.repo.revoke_all_for_user(user.id)
        elif raw_token:
            record = await self.repo.get_refresh_by_hash(
                security.hash_opaque_token(raw_token)
            )
            if record is None or record.user_id != user.id:
                raise AuthenticationError("Session invalide.", code="invalid_refresh_token")
            count = await self.repo.revoke_family(record.family_id)
        else:
            raise ValidationError(
                "Fournissez un refresh_token ou all_devices=true.", code="missing_token"
            )

        await self.repo.add_audit(
            action=AuditAction.USER_LOGGED_OUT,
            entity_type="user",
            entity_id=str(user.id),
            actor_type=actor_type_for(user.role),
            actor_id=user.id,
            payload={"sessions_revoked": count, "all_devices": all_devices},
            ip_address=ctx.ip,
        )
        await self.db.commit()
        return count

    # ====================================================== passwords
    async def change_password(
        self, *, user: User, current: str, new: str, ctx: RequestContext
    ) -> None:
        if not security.verify_password(current, user.password_hash):
            raise AuthenticationError(
                "Mot de passe actuel incorrect.", code="invalid_credentials"
            )
        if security.verify_password(new, user.password_hash):
            raise ValidationError(
                "Le nouveau mot de passe doit être différent de l'ancien.",
                code="password_unchanged",
            )

        user.password_hash = security.hash_password(new)
        user.must_change_password = False   # the pending flag is now satisfied
        await self.repo.revoke_all_for_user(user.id)
        await self.repo.add_audit(
            action=AuditAction.USER_PASSWORD_CHANGED,
            entity_type="user",
            entity_id=str(user.id),
            actor_type=actor_type_for(user.role),
            actor_id=user.id,
            ip_address=ctx.ip,
        )
        await self.db.commit()

    async def request_password_reset(
        self, *, email: str, ctx: RequestContext
    ) -> str | None:
        """Returns the raw token, or None when the account does not exist.

        The router always answers with the same message so the endpoint cannot
        be used to enumerate accounts.
        """
        user = await self.repo.get_by_email(email)
        if user is None or not user.is_active:
            return None

        await self.repo.invalidate_password_resets(user.id)
        raw = security.generate_numeric_code(settings.PASSWORD_RESET_CODE_DIGITS)
        await self.repo.add_password_reset(
            PasswordResetToken(
                user_id=user.id,
                token_hash=security.hash_opaque_token(raw),
                expires_at=datetime.now(UTC)
                + timedelta(minutes=settings.PASSWORD_RESET_TTL_MINUTES),
            )
        )
        await self.repo.add_audit(
            action=AuditAction.USER_PASSWORD_RESET_REQUESTED,
            entity_type="user",
            entity_id=str(user.id),
            actor_type=ActorType.SYSTEM,
            actor_id=user.id,
            ip_address=ctx.ip,
        )
        await self.db.commit()
        return raw

    async def reset_password(
        self, *, email: str, code: str, new_password: str, ctx: RequestContext
    ) -> None:
        # Mobile-friendly reset: verify the 6-digit code we e-mailed. Because the
        # code is short, the lookup is scoped to the user AND attempt-throttled
        # (a bare hash lookup would be brute-forceable, unlike the old long token).
        # Neutral errors avoid revealing whether the e-mail exists.
        user = await self.repo.get_by_email(email)
        if user is None:
            raise ValidationError("Code invalide.", code="invalid_code")

        record = await self.repo.get_active_password_reset(user.id)
        if record is None:
            raise ValidationError(
                "Code expiré ou introuvable. Demandez un nouveau code.",
                code="code_expired",
            )
        if record.attempts >= settings.PASSWORD_RESET_MAX_ATTEMPTS:
            raise ValidationError(
                "Trop de tentatives. Demandez un nouveau code.",
                code="too_many_attempts",
            )
        if not security.compare_digest(
            record.token_hash, security.hash_opaque_token(code)
        ):
            record.attempts += 1
            await self.db.commit()
            raise ValidationError("Code invalide.", code="invalid_code")

        record.used_at = datetime.now(UTC)
        user.password_hash = security.hash_password(new_password)
        user.must_change_password = False
        user.failed_login_count = 0
        user.locked_until = None
        await self.repo.revoke_all_for_user(user.id)

        await self.repo.add_audit(
            action=AuditAction.USER_PASSWORD_RESET_COMPLETED,
            entity_type="user",
            entity_id=str(user.id),
            actor_type=ActorType.SYSTEM,
            actor_id=user.id,
            ip_address=ctx.ip,
        )
        await self.db.commit()

    # ==================================================== e-mail verification
    async def _issue_email_verification(self, user: User) -> None:
        """Generate a fresh code, store its hash, and e-mail it. Best-effort:
        never raises into the caller (registration/resend must not fail on a
        mail problem). Any previous unused codes for this user are invalidated.
        """
        if user.email is None:
            return

        await self.repo.invalidate_email_verifications(user.id)

        code = security.generate_numeric_code(settings.EMAIL_VERIFICATION_CODE_DIGITS)
        await self.repo.add_email_verification(
            EmailVerificationCode(
                user_id=user.id,
                code_hash=security.hash_opaque_token(code),
                expires_at=datetime.now(UTC)
                + timedelta(minutes=settings.EMAIL_VERIFICATION_TTL_MINUTES),
            )
        )
        await self.repo.add_audit(
            action=AuditAction.EMAIL_VERIFICATION_SENT,
            entity_type="user",
            entity_id=str(user.id),
            actor_type=ActorType.SYSTEM,
            actor_id=user.id,
        )
        await self.db.commit()

        # send() uses its OWN committed transaction and never raises for a
        # delivery problem, so this can't break registration.
        from app.modules.notifications.constants import NotificationChannel
        from app.modules.notifications.dependencies import get_notification_service

        notifier = get_notification_service(self.db)
        await notifier.send(
            "auth.email_verification",
            channel=NotificationChannel.EMAIL,
            to_email=user.email,
            context={
                "full_name": user.full_name,
                "code": code,
                "ttl_minutes": settings.EMAIL_VERIFICATION_TTL_MINUTES,
            },
        )

    async def verify_email(
        self, *, email: str, code: str, ctx: RequestContext
    ) -> None:
        """Confirm the code. On success, stamps user.email_verified_at."""
        user = await self.repo.get_by_email(email)
        if user is None:
            raise ValidationError("Code invalide.", code="invalid_code")
        if user.email_verified_at is not None:
            return  # already verified — idempotent

        record = await self.repo.get_active_email_verification(user.id)
        if record is None:
            raise ValidationError(
                "Code expiré ou introuvable. Demandez un nouveau code.",
                code="code_expired",
            )
        if record.attempts >= settings.EMAIL_VERIFICATION_MAX_ATTEMPTS:
            raise ValidationError(
                "Trop de tentatives. Demandez un nouveau code.",
                code="too_many_attempts",
            )
        if not security.compare_digest(
            record.code_hash, security.hash_opaque_token(code)
        ):
            record.attempts += 1
            await self.db.commit()
            raise ValidationError("Code invalide.", code="invalid_code")

        now = datetime.now(UTC)
        record.used_at = now
        user.email_verified_at = now
        await self.repo.add_audit(
            action=AuditAction.EMAIL_VERIFIED,
            entity_type="user",
            entity_id=str(user.id),
            actor_type=ActorType.CUSTOMER,
            actor_id=user.id,
            ip_address=ctx.ip,
            user_agent=ctx.user_agent,
        )
        await self.db.commit()

    async def resend_email_verification(
        self, *, email: str, ctx: RequestContext
    ) -> None:
        """Issue a fresh code if the account exists and isn't verified yet.

        The router answers with the same neutral message whether or not the
        account exists (no enumeration).
        """
        user = await self.repo.get_by_email(email)
        if user is None or not user.is_active or user.email_verified_at is not None:
            return
        await self._issue_email_verification(user)

    # =========================================================== 2FA
    async def start_mfa_setup(self, *, user: User) -> tuple[str, str, list[str]]:
        if user.mfa_enabled:
            raise ConflictError("La double authentification est déjà active.", code="mfa_already_enabled")
        secret = security.generate_totp_secret()
        user.totp_secret = secret
        user.totp_enabled_at = None
        await self.db.commit()
        uri = security.totp_provisioning_uri(
            secret=secret, account_name=user.email or str(user.id)
        )
        return secret, uri, security.generate_recovery_codes()

    async def confirm_mfa_setup(
        self, *, user: User, code: str, ctx: RequestContext
    ) -> None:
        if not user.totp_secret:
            raise ValidationError("Aucune configuration 2FA en cours.", code="mfa_not_started")
        if not security.verify_totp(secret=user.totp_secret, code=code):
            raise AuthenticationError("Code invalide.", code="invalid_code")

        user.totp_enabled_at = datetime.now(UTC)
        await self.repo.add_audit(
            action=AuditAction.MFA_ENABLED,
            entity_type="user",
            entity_id=str(user.id),
            actor_type=actor_type_for(user.role),
            actor_id=user.id,
            ip_address=ctx.ip,
        )
        await self.db.commit()

    async def disable_mfa(
        self, *, user: User, password: str, code: str, ctx: RequestContext
    ) -> None:
        if not user.mfa_enabled:
            raise ConflictError("La double authentification n'est pas active.", code="mfa_not_enabled")
        if not security.verify_password(password, user.password_hash):
            raise AuthenticationError("Mot de passe incorrect.", code="invalid_credentials")
        if not security.verify_totp(secret=user.totp_secret or "", code=code):
            raise AuthenticationError("Code invalide.", code="invalid_code")
        if settings.ADMIN_REQUIRES_2FA and user.role is UserRole.ADMIN:
            raise PermissionDeniedError(
                "La double authentification est obligatoire pour un compte administrateur.",
                code="mfa_required_for_admin",
            )

        user.totp_secret = None
        user.totp_enabled_at = None
        await self.repo.add_audit(
            action=AuditAction.MFA_DISABLED,
            entity_type="user",
            entity_id=str(user.id),
            actor_type=actor_type_for(user.role),
            actor_id=user.id,
            ip_address=ctx.ip,
        )
        await self.db.commit()

    # ======================================================= profile
    async def update_profile(
        self,
        *,
        user: User,
        full_name: str | None,
        phone: str | None,
        city: str | None,
        email: str | None = None,
        current_password: str | None = None,
        ctx: RequestContext,
    ) -> User:
        changed: dict[str, str | None] = {}

        if email is not None and email.lower().strip() != (user.email or "").lower():
            # The e-mail is the login identifier and there is no verification
            # step in this version, so require the password as proof of intent.
            if not current_password or not security.verify_password(
                current_password, user.password_hash
            ):
                raise AuthenticationError(
                    "Mot de passe requis pour changer l'adresse e-mail.",
                    code="password_required",
                )
            if await self.repo.email_exists(email):
                raise ConflictError(
                    "Cette adresse e-mail est déjà utilisée.", code="email_taken"
                )
            previous_email = user.email
            user.email = email.lower().strip()
            changed["email"] = user.email
            await self.repo.add_audit(
                action=AuditAction.USER_PROFILE_UPDATED,
                entity_type="user",
                entity_id=str(user.id),
                actor_type=actor_type_for(user.role),
                actor_id=user.id,
                payload={"field": "email", "from": previous_email},
                ip_address=ctx.ip,
            )

        if full_name is not None and full_name != user.full_name:
            user.full_name = full_name.strip()
            changed["full_name"] = user.full_name
        if phone is not None and phone != user.phone:
            user.phone = phone
            changed["phone"] = phone
        if city is not None and city != user.city:
            user.city = city
            changed["city"] = city

        if changed:
            await self.repo.add_audit(
                action=AuditAction.USER_PROFILE_UPDATED,
                entity_type="user",
                entity_id=str(user.id),
                actor_type=actor_type_for(user.role),
                actor_id=user.id,
                payload={"fields": sorted(changed)},
                ip_address=ctx.ip,
            )
        await self.db.commit()
        await self.db.refresh(user)
        return user

    # ================================================ administration
    async def admin_create_user(
        self,
        *,
        admin: User,
        email: str,
        full_name: str,
        role: UserRole,
        phone: str | None,
        password: str | None,
        ctx: RequestContext,
    ) -> tuple[User, str | None]:
        # Sourcer role is granted only through the application flow — an admin
        # cannot create an account directly as a sourcer.
        if role is UserRole.SOURCER:
            raise ValidationError(
                "Un nouveau sourceur doit passer par la phase de candidature "
                "(demande d'adhésion puis approbation) : le rôle sourceur ne "
                "peut pas être attribué directement.",
                code="sourcer_requires_application",
            )
        if await self.repo.email_exists(email):
            raise ConflictError("Un compte existe déjà avec cette adresse.", code="email_taken")

        user = User(
            email=email.lower().strip(),
            full_name=full_name.strip(),
            phone=phone,
            role=role,
            is_active=True,
            password_hash=security.hash_password(password) if password else None,
        )
        await self.repo.add_user(user)

        reset_token: str | None = None
        if password is None:
            reset_token = security.generate_opaque_token()
            await self.repo.add_password_reset(
                PasswordResetToken(
                    user_id=user.id,
                    token_hash=security.hash_opaque_token(reset_token),
                    expires_at=datetime.now(UTC)
                    + timedelta(hours=settings.PASSWORD_RESET_HOURS),
                )
            )

        await self.repo.add_audit(
            action=AuditAction.USER_REGISTERED,
            entity_type="user",
            entity_id=str(user.id),
            actor_type=ActorType.ADMIN,
            actor_id=admin.id,
            payload={"created_by_admin": True, "role": role.value},
            ip_address=ctx.ip,
        )
        await self.db.commit()
        await self.db.refresh(user)
        return user, reset_token

    async def admin_change_role(
        self,
        *,
        admin: User,
        user_id: uuid.UUID,
        role: UserRole,
        reason: str | None,
        ctx: RequestContext,
    ) -> User:
        user = await self.repo.get_user(user_id)
        if user is None:
            raise NotFoundError("Utilisateur introuvable.")
        if user.id == admin.id and role is not UserRole.ADMIN:
            raise ValidationError(
                "Vous ne pouvez pas retirer votre propre rôle administrateur.",
                code="cannot_demote_self",
            )

        previous = user.role
        if previous is role:
            return user

        # Sourcer role is granted only by approving an application — never by
        # a manual role change here.
        if role is UserRole.SOURCER:
            raise ValidationError(
                "Un nouveau sourceur doit passer par la phase de candidature "
                "(demande d'adhésion puis approbation) : le rôle sourceur ne "
                "peut pas être attribué directement.",
                code="sourcer_requires_application",
            )

        user.role = role
        # Permissions are embedded in access tokens, so old sessions would keep
        # the old rights until they expire: revoke them now.
        await self.repo.revoke_all_for_user(user.id)

        await self.repo.add_audit(
            action=AuditAction.USER_ROLE_CHANGED,
            entity_type="user",
            entity_id=str(user.id),
            actor_type=ActorType.ADMIN,
            actor_id=admin.id,
            payload={"from": previous.value, "to": role.value, "reason": reason},
            ip_address=ctx.ip,
        )
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def admin_set_active(
        self,
        *,
        admin: User,
        user_id: uuid.UUID,
        is_active: bool,
        ctx: RequestContext,
    ) -> User:
        user = await self.repo.get_user(user_id)
        if user is None:
            raise NotFoundError("Utilisateur introuvable.")
        if user.id == admin.id and not is_active:
            raise ValidationError(
                "Vous ne pouvez pas désactiver votre propre compte.",
                code="cannot_disable_self",
            )

        user.is_active = is_active
        if not is_active:
            await self.repo.revoke_all_for_user(user.id)

        await self.repo.add_audit(
            action=AuditAction.USER_REACTIVATED if is_active else AuditAction.USER_DEACTIVATED,
            entity_type="user",
            entity_id=str(user.id),
            actor_type=ActorType.ADMIN,
            actor_id=admin.id,
            ip_address=ctx.ip,
        )
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def admin_delete_user(
        self, *, admin: User, user_id: uuid.UUID, ctx: RequestContext
    ) -> None:
        """Soft delete: orders and audit history must survive the account."""
        user = await self.repo.get_user(user_id)
        if user is None:
            raise NotFoundError("Utilisateur introuvable.")
        if user.id == admin.id:
            raise ValidationError(
                "Vous ne pouvez pas supprimer votre propre compte.",
                code="cannot_delete_self",
            )

        user.deleted_at = datetime.now(UTC)
        user.is_active = False
        # Free the address for a future account while keeping the row.
        if user.email:
            user.email = f"deleted+{user.id}@closet.invalid"
        await self.repo.revoke_all_for_user(user.id)

        await self.repo.add_audit(
            action=AuditAction.USER_DELETED,
            entity_type="user",
            entity_id=str(user.id),
            actor_type=ActorType.ADMIN,
            actor_id=admin.id,
            ip_address=ctx.ip,
        )
        await self.db.commit()

    async def grant_sourcer_role(self, *, user_id: uuid.UUID, approved_by: uuid.UUID) -> User:
        """Called by the sourcing module when a membership is approved."""
        user = await self.repo.get_user(user_id)
        if user is None:
            raise NotFoundError("Utilisateur introuvable.")
        if user.role is UserRole.ADMIN:
            return user
        if user.role is not UserRole.SOURCER:
            previous = user.role
            user.role = UserRole.SOURCER
            await self.repo.revoke_all_for_user(user.id)
            await self.repo.add_audit(
                action=AuditAction.USER_ROLE_CHANGED,
                entity_type="user",
                entity_id=str(user.id),
                actor_type=ActorType.ADMIN,
                actor_id=approved_by,
                payload={"from": previous.value, "to": UserRole.SOURCER.value,
                         "reason": "sourcer_membership_approved"},
            )
            await self.db.commit()
            await self.db.refresh(user)
        return user

    # ================================================== brute force
    def _assert_not_locked(self, user: User) -> None:
        if user.locked_until and user.locked_until > datetime.now(UTC):
            remaining = int((user.locked_until - datetime.now(UTC)).total_seconds() // 60) + 1
            raise RateLimitedError(
                f"Compte temporairement bloqué. Réessayez dans {remaining} minute(s).",
                code="account_locked",
            )

    async def _register_failed_attempt(
        self,
        user: User,
        ctx: RequestContext,
        *,
        action: str = AuditAction.USER_LOGIN_FAILED,
    ) -> None:
        user.failed_login_count += 1
        locked = False
        if user.failed_login_count >= settings.MAX_FAILED_LOGINS:
            user.locked_until = datetime.now(UTC) + timedelta(
                minutes=settings.LOCKOUT_MINUTES
            )
            user.failed_login_count = 0
            locked = True

        await self.repo.add_audit(
            action=AuditAction.USER_LOCKED if locked else action,
            entity_type="user",
            entity_id=str(user.id),
            actor_type=ActorType.SYSTEM,
            actor_id=user.id,
            ip_address=ctx.ip,
            user_agent=ctx.user_agent,
        )
        await self.db.commit()

    async def _audit_failed_login(
        self, user_id: uuid.UUID | None, email: str, ctx: RequestContext
    ) -> None:
        await self.repo.add_audit(
            action=AuditAction.USER_LOGIN_FAILED,
            entity_type="user",
            entity_id=str(user_id) if user_id else None,
            actor_type=ActorType.SYSTEM,
            payload={"email_attempted": email[:120]},
            ip_address=ctx.ip,
            user_agent=ctx.user_agent,
        )
        await self.db.commit()