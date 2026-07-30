"""First-login onboarding for admins created from the /ops panel.

An admin created in the panel is handed a password and has no 2FA. Before the
dashboard opens, they must (1) set their own password and (2) enrol 2FA. These
two browser pages let them do that without touching the API or a terminal.

Mounted at /ops/onboarding, OUTSIDE OpsAuthProvider's protection (that guard
holds pending admins out of the panel), but every route here re-checks the
session and the account, so only a logged-in, still-pending admin can use it.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.routing import Route

import segno

from app.core import security
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.modules.identity.models import User

SESSION_KEY = "ops_user_id"
MFA_OK_KEY = "ops_mfa_ok"


# --------------------------------------------------------------- helpers
async def _current_user(request: Request) -> User | None:
    raw = request.session.get(SESSION_KEY)
    if not raw:
        return None
    try:
        uid = uuid.UUID(raw)
    except ValueError:
        return None
    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.id == uid))
        ).scalar_one_or_none()
    return user


def _page(title: str, body: str, error: str = "") -> HTMLResponse:
    err_html = f'<p class="err">{error}</p>' if error else ""
    return HTMLResponse(
        f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>{title} — ClosET</title>
<style>
 body{{font-family:system-ui,sans-serif;background:#f5f4f2;margin:0;
   display:flex;min-height:100vh;align-items:center;justify-content:center}}
 .card{{background:#fff;max-width:420px;width:90%;padding:2rem;border-radius:12px;
   box-shadow:0 4px 24px rgba(0,0,0,.08)}}
 h1{{font-size:1.25rem;margin:0 0 .25rem}} p{{color:#555;line-height:1.5}}
 label{{display:block;margin:1rem 0 .25rem;font-weight:600;font-size:.9rem}}
 input{{width:100%;padding:.6rem;border:1px solid #ccc;border-radius:8px;
   box-sizing:border-box;font-size:1rem}}
 button{{margin-top:1.25rem;width:100%;padding:.7rem;border:0;border-radius:8px;
   background:#1a1a1a;color:#fff;font-size:1rem;cursor:pointer}}
 .err{{background:#fde8e8;color:#9b1c1c;padding:.6rem .8rem;border-radius:8px}}
 .step{{color:#888;font-size:.8rem;text-transform:uppercase;letter-spacing:.05em}}
 code{{background:#f0f0f0;padding:.2rem .4rem;border-radius:4px;font-size:.85rem;
   word-break:break-all}}
 .qr{{text-align:center;margin:1rem 0}}
</style></head><body><div class="card">{err_html}{body}</div></body></html>"""
    )


# ---------------------------------------------------- step 1: password
def _qr_svg(uri: str) -> str:
    """Render an otpauth URI as an inline SVG QR code (server-side, no CDN, no JS).

    Returned markup embeds directly in the page, so it works offline and is not
    subject to the panel's script CSP.
    """
    return segno.make(uri).svg_inline(scale=4, border=2)


async def onboarding_home(request: Request) -> Response:
    user = await _current_user(request)
    if user is None:
        return RedirectResponse("/ops", status_code=302)
    if user.must_change_password:
        return RedirectResponse("/ops/onboarding/password", status_code=302)
    if settings.ADMIN_REQUIRES_2FA and not user.mfa_enabled:
        return RedirectResponse("/ops/onboarding/mfa", status_code=302)
    # both done — into the panel
    return RedirectResponse("/ops", status_code=302)


async def password_form(request: Request) -> Response:
    user = await _current_user(request)
    if user is None:
        return RedirectResponse("/ops", status_code=302)
    if not user.must_change_password:
        return RedirectResponse("/ops/onboarding", status_code=302)
    return _page(
        "Changer le mot de passe",
        """<p class="step">Étape 1 sur 2</p>
        <h1>Choisissez votre mot de passe</h1>
        <p>Ce compte a été créé pour vous. Définissez votre propre mot de passe
        (au moins 8 caractères, lettres et chiffres).</p>
        <form method="post">
          <label>Mot de passe actuel (celui qu'on vous a donné)</label>
          <input type="password" name="current" required>
          <label>Nouveau mot de passe</label>
          <input type="password" name="new" required>
          <label>Confirmer le nouveau mot de passe</label>
          <input type="password" name="confirm" required>
          <button type="submit">Continuer</button>
        </form>""",
    )


def _password_ok(pw: str) -> str | None:
    if len(pw) < 8:
        return "Au moins 8 caractères."
    if len(pw.encode("utf-8")) > 72:
        return "Trop long (72 octets maximum)."
    if not (any(c.isalpha() for c in pw) and any(c.isdigit() for c in pw)):
        return "Doit contenir des lettres et des chiffres."
    return None


async def password_submit(request: Request) -> Response:
    user = await _current_user(request)
    if user is None:
        return RedirectResponse("/ops", status_code=302)
    form = await request.form()
    current = str(form.get("current", ""))
    new = str(form.get("new", ""))
    confirm = str(form.get("confirm", ""))

    def again(err: str) -> Response:
        return _page(
            "Changer le mot de passe",
            '<h1>Choisissez votre mot de passe</h1>'
            '<form method="post">'
            '<label>Mot de passe actuel</label><input type="password" name="current" required>'
            '<label>Nouveau mot de passe</label><input type="password" name="new" required>'
            '<label>Confirmer</label><input type="password" name="confirm" required>'
            '<button type="submit">Continuer</button></form>',
            error=err,
        )

    if not security.verify_password(current, user.password_hash):
        return again("Mot de passe actuel incorrect.")
    if new != confirm:
        return again("Les deux mots de passe ne correspondent pas.")
    problem = _password_ok(new)
    if problem:
        return again(problem)
    if security.verify_password(new, user.password_hash):
        return again("Le nouveau mot de passe doit être différent de l'ancien.")

    async with AsyncSessionLocal() as db:
        u = (await db.execute(select(User).where(User.id == user.id))).scalar_one()
        u.password_hash = security.hash_password(new)
        u.must_change_password = False
        await db.commit()

    return RedirectResponse("/ops/onboarding", status_code=302)


# --------------------------------------------------------- step 2: 2FA
async def mfa_form(request: Request) -> Response:
    user = await _current_user(request)
    if user is None:
        return RedirectResponse("/ops", status_code=302)
    if user.must_change_password:
        return RedirectResponse("/ops/onboarding/password", status_code=302)
    if user.mfa_enabled:
        return RedirectResponse("/ops", status_code=302)

    # generate (or reuse) a pending secret and show the provisioning URI as a QR
    async with AsyncSessionLocal() as db:
        u = (await db.execute(select(User).where(User.id == user.id))).scalar_one()
        if not u.totp_secret or u.totp_enabled_at is not None:
            u.totp_secret = security.generate_totp_secret()
            u.totp_enabled_at = None
            await db.commit()
        secret = u.totp_secret
    uri = security.totp_provisioning_uri(secret=secret, account_name=user.email)

    # Render the QR server-side as inline SVG — no CDN, no JS, works offline and
    # is not blocked by the panel's script CSP.
    qr_svg = _qr_svg(uri)
    return _page(
        "Configurer la double authentification",
        f"""<p class="step">Étape 2 sur 2</p>
        <h1>Activez la double authentification</h1>
        <p>Scannez ce code dans Google Authenticator, Authy ou 1Password,
        puis entrez le code à 6 chiffres.</p>
        <div class="qr">{qr_svg}</div>
        <p>Ou saisissez cette clé manuellement :<br><code>{secret}</code></p>
        <form method="post">
          <label>Code à 6 chiffres</label>
          <input type="text" name="code" inputmode="numeric" pattern="[0-9]{{6}}"
                 maxlength="6" required autocomplete="one-time-code">
          <button type="submit">Activer et accéder au panneau</button>
        </form>""",
    )


async def mfa_submit(request: Request) -> Response:
    user = await _current_user(request)
    if user is None:
        return RedirectResponse("/ops", status_code=302)
    form = await request.form()
    code = str(form.get("code", "")).strip()

    async with AsyncSessionLocal() as db:
        u = (await db.execute(select(User).where(User.id == user.id))).scalar_one()
        if not u.totp_secret:
            return RedirectResponse("/ops/onboarding/mfa", status_code=302)
        if not security.verify_totp(secret=u.totp_secret, code=code):
            uri = security.totp_provisioning_uri(secret=u.totp_secret, account_name=user.email)
            qr_svg = _qr_svg(uri)
            return _page(
                "Configurer la double authentification",
                f"""<h1>Activez la double authentification</h1>
                <div class="qr">{qr_svg}</div>
                <p>Clé : <code>{u.totp_secret}</code></p>
                <form method="post">
                  <label>Code à 6 chiffres</label>
                  <input type="text" name="code" inputmode="numeric"
                         pattern="[0-9]{{6}}" maxlength="6" required>
                  <button type="submit">Activer</button>
                </form>""",
                error="Code invalide. Réessayez avec le code actuel.",
            )
        from datetime import UTC, datetime

        u.totp_enabled_at = datetime.now(UTC)
        await db.commit()

    # They just proved possession of the authenticator: this login is now
    # fully 2FA-authenticated.
    request.session[MFA_OK_KEY] = True
    return RedirectResponse("/ops", status_code=302)


# ------------------------------------------------ TOTP challenge (existing 2FA)
async def verify_2fa_form(request: Request) -> Response:
    user = await _current_user(request)
    if user is None:
        return RedirectResponse("/ops", status_code=302)
    # if they somehow have no 2FA enrolled, send them to enrol instead
    if not user.mfa_enabled:
        return RedirectResponse("/ops/onboarding", status_code=302)
    # already passed this session -> into the panel
    if request.session.get(MFA_OK_KEY):
        return RedirectResponse("/ops", status_code=302)
    return _page(
        "Vérification en deux étapes",
        """<h1>Vérification en deux étapes</h1>
        <p>Entrez le code à 6 chiffres de votre application d'authentification.</p>
        <form method="post">
          <label>Code à 6 chiffres</label>
          <input type="text" name="code" inputmode="numeric" pattern="[0-9]{6}"
                 maxlength="6" required autocomplete="one-time-code" autofocus>
          <button type="submit">Vérifier</button>
        </form>""",
    )


async def verify_2fa_submit(request: Request) -> Response:
    user = await _current_user(request)
    if user is None:
        return RedirectResponse("/ops", status_code=302)
    form = await request.form()
    code = str(form.get("code", "")).strip()

    if not user.mfa_enabled or not security.verify_totp(
        secret=user.totp_secret or "", code=code
    ):
        return _page(
            "Vérification en deux étapes",
            """<h1>Vérification en deux étapes</h1>
            <p>Entrez le code à 6 chiffres de votre application.</p>
            <form method="post">
              <label>Code à 6 chiffres</label>
              <input type="text" name="code" inputmode="numeric"
                     pattern="[0-9]{6}" maxlength="6" required autofocus>
              <button type="submit">Vérifier</button>
            </form>""",
            error="Code invalide. Réessayez avec le code actuel.",
        )

    # correct code -> this session is now 2FA-authenticated
    request.session[MFA_OK_KEY] = True
    return RedirectResponse("/ops", status_code=302)


onboarding_routes = [
    Route("/onboarding", onboarding_home, methods=["GET"], name="ops-onboarding"),
    Route("/onboarding/password", password_form, methods=["GET"], name="ops-onboarding-password"),
    Route("/onboarding/password", password_submit, methods=["POST"], name="ops-onboarding-password"),
    Route("/onboarding/mfa", mfa_form, methods=["GET"], name="ops-onboarding-mfa"),
    Route("/onboarding/mfa", mfa_submit, methods=["POST"], name="ops-onboarding-mfa"),
    Route("/verify-2fa", verify_2fa_form, methods=["GET"], name="ops-verify-2fa"),
    Route("/verify-2fa", verify_2fa_submit, methods=["POST"], name="ops-verify-2fa"),
]