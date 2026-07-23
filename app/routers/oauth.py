from __future__ import annotations

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import redirect
from app.models import OAuthAccount, User

router = APIRouter(prefix="/auth", tags=["oauth"])

oauth = OAuth()
_settings = get_settings()

if _settings.google_client_id and _settings.google_client_secret:
    oauth.register(
        name="google",
        client_id=_settings.google_client_id,
        client_secret=_settings.google_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

if _settings.apple_client_id:
    oauth.register(
        name="apple",
        client_id=_settings.apple_client_id,
        client_secret=_settings.apple_client_id,  # replaced dynamically if private key set
        server_metadata_url="https://appleid.apple.com/.well-known/openid-configuration",
        client_kwargs={"scope": "name email", "response_mode": "form_post"},
    )


def _upsert_oauth_user(db: Session, *, provider: str, provider_user_id: str, email: str, locale: str) -> User:
    email_norm = email.lower().strip()
    account = (
        db.query(OAuthAccount)
        .filter(OAuthAccount.provider == provider, OAuthAccount.provider_user_id == provider_user_id)
        .first()
    )
    if account:
        return account.user

    user = db.query(User).filter(User.email == email_norm).first()
    if not user:
        user = User(email=email_norm, password_hash=None, email_verified=True, locale=locale)
        db.add(user)
        db.flush()
    else:
        user.email_verified = True

    db.add(OAuthAccount(user_id=user.id, provider=provider, provider_user_id=provider_user_id))
    db.commit()
    db.refresh(user)
    return user


@router.get("/google")
async def google_login(request: Request):
    if not get_settings().google_client_id:
        return redirect("/auth/login")
    redirect_uri = f"{get_settings().app_base_url}/auth/google/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback")
async def google_callback(request: Request):
    if not get_settings().google_client_id:
        return redirect("/auth/login")
    token = await oauth.google.authorize_access_token(request)
    info = token.get("userinfo") or {}
    email = info.get("email")
    sub = info.get("sub")
    if not email or not sub:
        return redirect("/auth/login")
    db = next(get_db())
    try:
        locale = request.cookies.get("locale", "cs")
        user = _upsert_oauth_user(db, provider="google", provider_user_id=sub, email=email, locale=locale)
        request.session["user_id"] = user.id
    finally:
        db.close()
    return redirect("/draws")


@router.get("/apple")
async def apple_login(request: Request):
    if not get_settings().apple_client_id:
        return redirect("/auth/login")
    redirect_uri = f"{get_settings().app_base_url}/auth/apple/callback"
    return await oauth.apple.authorize_redirect(request, redirect_uri)


@router.post("/apple/callback")
@router.get("/apple/callback")
async def apple_callback(request: Request):
    if not get_settings().apple_client_id:
        return redirect("/auth/login")
    token = await oauth.apple.authorize_access_token(request)
    info = token.get("userinfo") or {}
    email = info.get("email")
    sub = info.get("sub")
    if not email or not sub:
        return redirect("/auth/login")
    db = next(get_db())
    try:
        locale = request.cookies.get("locale", "cs")
        user = _upsert_oauth_user(db, provider="apple", provider_user_id=sub, email=email, locale=locale)
        request.session["user_id"] = user.id
    finally:
        db.close()
    return redirect("/draws")
