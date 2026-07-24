"""Identity HTTP layer.

Two routers are exported:
  * `router`       -> mounted at /auth and /me  (public + authenticated)
  * `admin_router` -> mounted at /admin/users   (administrator only)
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.config import settings
from app.modules.identity.constants import Permission, UserRole, permissions_for
from app.modules.identity.dependencies import (
    Ctx,
    CurrentUser,
    Service,
    require_permission,
)
from app.modules.identity.schemas import (
    AdminChangeRoleRequest,
    AdminCreateUserRequest,
    AdminUpdateUserRequest,
    AuditEntry,
    AuditPage,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    MeResponse,
    MessageResponse,
    MFAChallengeRequest,
    MFADisableRequest,
    MFARequired,
    MFASetupResponse,
    MFAVerifySetupRequest,
    PageMeta,
    RefreshRequest,
    RegisterDeviceRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenPair,
    UpdateProfileRequest,
    UserPage,
    UserPublic,
)
from app.modules.identity.service import IssuedTokens, MFAChallenge

router = APIRouter()
admin_router = APIRouter()


def _token_pair(tokens: IssuedTokens) -> TokenPair:
    return TokenPair(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
        user=UserPublic.from_user(tokens.user),
    )


# ============================================================ auth
@router.post(
    "/auth/register",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Créer un compte cliente",
)
async def register(payload: RegisterRequest, service: Service, ctx: Ctx) -> UserPublic:
    user = await service.register(
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        phone=payload.phone,
        city=payload.city,
        ctx=ctx,
    )
    return UserPublic.from_user(user)


@router.post(
    "/auth/login",
    response_model=TokenPair | MFARequired,
    summary="Se connecter (e-mail + mot de passe)",
)
async def login(payload: LoginRequest, service: Service, ctx: Ctx):
    result = await service.login(
        email=payload.email, password=payload.password, ctx=ctx
    )
    if isinstance(result, MFAChallenge):
        return MFARequired(
            challenge_token=result.challenge_token, expires_in=result.expires_in
        )
    return _token_pair(result)


@router.post(
    "/auth/login/mfa",
    response_model=TokenPair,
    summary="Valider le code de double authentification",
)
async def login_mfa(payload: MFAChallengeRequest, service: Service, ctx: Ctx) -> TokenPair:
    tokens = await service.complete_mfa(
        challenge_token=payload.challenge_token, code=payload.code, ctx=ctx
    )
    return _token_pair(tokens)


@router.post("/auth/refresh", response_model=TokenPair, summary="Renouveler la session")
async def refresh(payload: RefreshRequest, service: Service, ctx: Ctx) -> TokenPair:
    tokens = await service.refresh(raw_token=payload.refresh_token, ctx=ctx)
    return _token_pair(tokens)


@router.post("/auth/logout", response_model=MessageResponse, summary="Se déconnecter")
async def logout(
    payload: LogoutRequest, user: CurrentUser, service: Service, ctx: Ctx
) -> MessageResponse:
    count = await service.logout(
        user=user,
        raw_token=payload.refresh_token,
        all_devices=payload.all_devices,
        ctx=ctx,
    )
    return MessageResponse(message=f"{count} session(s) fermée(s).")


@router.post(
    "/auth/forgot-password",
    response_model=MessageResponse,
    summary="Demander une réinitialisation du mot de passe",
)
async def forgot_password(
    payload: ForgotPasswordRequest, service: Service, ctx: Ctx
) -> MessageResponse:
    token = await service.request_password_reset(email=payload.email, ctx=ctx)
    # TODO(notifications): send `token` by e-mail / WhatsApp when not None.
    if settings.DEBUG and token:
        print(f"[dev] password reset token for {payload.email}: {token}")
    # Same answer whether or not the account exists (no enumeration).
    return MessageResponse(
        message="Si un compte existe pour cette adresse, un lien vient d'être envoyé."
    )


@router.post(
    "/auth/reset-password",
    response_model=MessageResponse,
    summary="Définir un nouveau mot de passe",
)
async def reset_password(
    payload: ResetPasswordRequest, service: Service, ctx: Ctx
) -> MessageResponse:
    await service.reset_password(
        raw_token=payload.token, new_password=payload.new_password, ctx=ctx
    )
    return MessageResponse(message="Mot de passe réinitialisé. Vous pouvez vous connecter.")


# ========================================================= account
@router.get("/me", response_model=MeResponse, summary="Mon espace")
async def me(user: CurrentUser) -> MeResponse:
    base = UserPublic.from_user(user)
    return MeResponse(
        **base.model_dump(),
        permissions=sorted(p.value for p in permissions_for(user.role)),
    )


@router.patch("/me", response_model=UserPublic, summary="Mettre à jour mon profil")
async def update_me(
    payload: UpdateProfileRequest, user: CurrentUser, service: Service, ctx: Ctx
) -> UserPublic:
    updated = await service.update_profile(
        user=user,
        full_name=payload.full_name,
        phone=payload.phone,
        city=payload.city,
        ctx=ctx,
    )
    return UserPublic.from_user(updated)


@router.post(
    "/me/password",
    response_model=MessageResponse,
    summary="Changer mon mot de passe",
)
async def change_password(
    payload: ChangePasswordRequest, user: CurrentUser, service: Service, ctx: Ctx
) -> MessageResponse:
    await service.change_password(
        user=user,
        current=payload.current_password,
        new=payload.new_password,
        ctx=ctx,
    )
    return MessageResponse(
        message="Mot de passe modifié. Toutes vos sessions ont été fermées."
    )


@router.post(
    "/me/devices",
    response_model=MessageResponse,
    summary="Enregistrer un appareil pour les notifications push",
)
async def register_device(
    payload: RegisterDeviceRequest, user: CurrentUser, service: Service
) -> MessageResponse:
    await service.repo.upsert_device_token(
        user_id=user.id,
        token=payload.token,
        platform=payload.platform,
        marketing_opt_in=payload.marketing_opt_in,
    )
    await service.db.commit()
    return MessageResponse(message="Appareil enregistré.")


@router.delete(
    "/me/devices/{token}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Retirer un appareil",
)
async def delete_device(token: str, user: CurrentUser, service: Service) -> Response:
    await service.repo.delete_device_token(user_id=user.id, token=token)
    await service.db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ============================================================= 2FA
@router.post(
    "/me/mfa/setup",
    response_model=MFASetupResponse,
    summary="Démarrer la configuration de la double authentification",
)
async def mfa_setup(user: CurrentUser, service: Service) -> MFASetupResponse:
    secret, uri, recovery = await service.start_mfa_setup(user=user)
    return MFASetupResponse(secret=secret, otpauth_uri=uri, recovery_codes=recovery)


@router.post(
    "/me/mfa/verify",
    response_model=MessageResponse,
    summary="Confirmer la double authentification",
)
async def mfa_verify(
    payload: MFAVerifySetupRequest, user: CurrentUser, service: Service, ctx: Ctx
) -> MessageResponse:
    await service.confirm_mfa_setup(user=user, code=payload.code, ctx=ctx)
    return MessageResponse(message="Double authentification activée.")


@router.post(
    "/me/mfa/disable",
    response_model=MessageResponse,
    summary="Désactiver la double authentification",
)
async def mfa_disable(
    payload: MFADisableRequest, user: CurrentUser, service: Service, ctx: Ctx
) -> MessageResponse:
    await service.disable_mfa(
        user=user, password=payload.password, code=payload.code, ctx=ctx
    )
    return MessageResponse(message="Double authentification désactivée.")


# ================================================== administration
@admin_router.get(
    "",
    response_model=UserPage,
    dependencies=[Depends(require_permission(Permission.USER_READ_ALL))],
    summary="Lister les utilisateurs",
)
async def list_users(
    service: Service,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    role: UserRole | None = None,
    is_active: bool | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> UserPage:
    rows, total = await service.repo.list_users(
        page=page, page_size=page_size, role=role, is_active=is_active, search=search
    )
    return UserPage(
        items=[UserPublic.from_user(u) for u in rows],
        meta=PageMeta(
            page=page,
            page_size=page_size,
            total=total,
            pages=(total + page_size - 1) // page_size,
        ),
    )


@admin_router.post(
    "",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Créer un utilisateur (back office)",
)
async def admin_create_user(
    payload: AdminCreateUserRequest,
    admin: Annotated[object, Depends(require_permission(Permission.USER_MANAGE))],
    service: Service,
    ctx: Ctx,
) -> UserPublic:
    user, reset_token = await service.admin_create_user(
        admin=admin,  # type: ignore[arg-type]
        email=payload.email,
        full_name=payload.full_name,
        role=payload.role,
        phone=payload.phone,
        password=payload.password,
        ctx=ctx,
    )
    if settings.DEBUG and reset_token:
        print(f"[dev] invitation token for {user.email}: {reset_token}")
    return UserPublic.from_user(user)


@admin_router.get(
    "/{user_id}",
    response_model=UserPublic,
    dependencies=[Depends(require_permission(Permission.USER_READ_ALL))],
    summary="Consulter un utilisateur",
)
async def get_user(user_id: uuid.UUID, service: Service) -> UserPublic:
    from app.core.exceptions import NotFoundError

    user = await service.repo.get_user(user_id)
    if user is None:
        raise NotFoundError("Utilisateur introuvable.")
    return UserPublic.from_user(user)


@admin_router.patch(
    "/{user_id}",
    response_model=UserPublic,
    summary="Modifier un utilisateur",
)
async def admin_update_user(
    user_id: uuid.UUID,
    payload: AdminUpdateUserRequest,
    admin: Annotated[object, Depends(require_permission(Permission.USER_MANAGE))],
    service: Service,
    ctx: Ctx,
) -> UserPublic:
    from app.core.exceptions import NotFoundError

    if payload.is_active is not None:
        user = await service.admin_set_active(
            admin=admin,  # type: ignore[arg-type]
            user_id=user_id,
            is_active=payload.is_active,
            ctx=ctx,
        )
    else:
        user = await service.repo.get_user(user_id)
        if user is None:
            raise NotFoundError("Utilisateur introuvable.")

    if any(v is not None for v in (payload.full_name, payload.phone, payload.city)):
        user = await service.update_profile(
            user=user,
            full_name=payload.full_name,
            phone=payload.phone,
            city=payload.city,
            ctx=ctx,
        )
    return UserPublic.from_user(user)


@admin_router.put(
    "/{user_id}/role",
    response_model=UserPublic,
    summary="Changer le rôle d'un utilisateur",
)
async def admin_change_role(
    user_id: uuid.UUID,
    payload: AdminChangeRoleRequest,
    admin: Annotated[object, Depends(require_permission(Permission.USER_MANAGE))],
    service: Service,
    ctx: Ctx,
) -> UserPublic:
    user = await service.admin_change_role(
        admin=admin,  # type: ignore[arg-type]
        user_id=user_id,
        role=payload.role,
        reason=payload.reason,
        ctx=ctx,
    )
    return UserPublic.from_user(user)


@admin_router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Supprimer (soft delete) un utilisateur",
)
async def admin_delete_user(
    user_id: uuid.UUID,
    admin: Annotated[object, Depends(require_permission(Permission.USER_MANAGE))],
    service: Service,
    ctx: Ctx,
) -> Response:
    await service.admin_delete_user(
        admin=admin, user_id=user_id, ctx=ctx  # type: ignore[arg-type]
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@admin_router.get(
    "/{user_id}/audit",
    response_model=AuditPage,
    dependencies=[Depends(require_permission(Permission.AUDIT_READ))],
    summary="Journal d'audit d'un utilisateur",
)
async def user_audit(
    user_id: uuid.UUID,
    service: Service,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> AuditPage:
    rows, total = await service.repo.list_audit(
        page=page, page_size=page_size, actor_id=user_id
    )
    return AuditPage(
        items=[AuditEntry.model_validate(r) for r in rows],
        meta=PageMeta(
            page=page,
            page_size=page_size,
            total=total,
            pages=(total + page_size - 1) // page_size,
        ),
    )