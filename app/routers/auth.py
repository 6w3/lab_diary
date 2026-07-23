from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import get_settings
from app.deps import DbDep, LocaleDep, OptionalUserDep, redirect, template_context
from app.models import User
from app.services.brevo import send_password_reset_email, send_verification_email
from app.services.security import (
    consume_email_token,
    create_email_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])
templates = Jinja2Templates(directory="app/templates")


def _oauth_flags():
    s = get_settings()
    return {
        "google_enabled": bool(s.google_client_id and s.google_client_secret),
        "apple_enabled": bool(s.apple_client_id),
    }


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, locale: LocaleDep, error: str | None = None):
    return templates.TemplateResponse(
        request,
        "auth/login.html",
        template_context(request, locale, error=error, **_oauth_flags()),
    )


@router.post("/login")
def login(
    request: Request,
    db: DbDep,
    locale: LocaleDep,
    email: str = Form(...),
    password: str = Form(...),
):
    user = db.query(User).filter(User.email == email.lower().strip()).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
        request,
        "auth/login.html",
            template_context(request, locale, error="Invalid credentials", **_oauth_flags()),
            status_code=400,
        )
    if not user.email_verified:
        request.session["user_id"] = user.id
        return redirect("/auth/verify-pending")
    request.session["user_id"] = user.id
    return redirect("/draws")


@router.get("/register", response_class=HTMLResponse)
def register_form(request: Request, locale: LocaleDep, error: str | None = None):
    return templates.TemplateResponse(
        request,
        "auth/register.html",
        template_context(request, locale, error=error, **_oauth_flags()),
    )


@router.post("/register")
def register(
    request: Request,
    db: DbDep,
    locale: LocaleDep,
    email: str = Form(...),
    password: str = Form(...),
):
    email_norm = email.lower().strip()
    if db.query(User).filter(User.email == email_norm).first():
        return templates.TemplateResponse(
        request,
        "auth/register.html",
            template_context(request, locale, error="Email already registered", **_oauth_flags()),
            status_code=400,
        )
    if len(password) < 8:
        return templates.TemplateResponse(
        request,
        "auth/register.html",
            template_context(request, locale, error="Password too short", **_oauth_flags()),
            status_code=400,
        )
    user = User(
        email=email_norm,
        password_hash=hash_password(password),
        email_verified=False,
        locale=locale,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_email_token(db, user, "verify")
    verify_url = f"{get_settings().app_base_url}/auth/verify?token={token.token}"
    send_verification_email(user.email, verify_url, locale=locale)
    request.session["user_id"] = user.id
    return redirect("/auth/verify-pending")


@router.get("/verify")
def verify_email(db: DbDep, token: str):
    user = consume_email_token(db, token, "verify")
    if not user:
        return redirect("/auth/login")
    user.email_verified = True
    db.commit()
    return redirect("/auth/login?verified=1")


@router.get("/verify-pending", response_class=HTMLResponse)
def verify_pending(request: Request, locale: LocaleDep, user: OptionalUserDep):
    if not user:
        return redirect("/auth/login")
    if user.email_verified:
        return redirect("/draws")
    return templates.TemplateResponse(
        request,
        "auth/verify_pending.html",
        template_context(request, locale),
    )


@router.post("/resend-verify")
def resend_verify(request: Request, db: DbDep, locale: LocaleDep, user: OptionalUserDep):
    if not user:
        return redirect("/auth/login")
    token = create_email_token(db, user, "verify")
    verify_url = f"{get_settings().app_base_url}/auth/verify?token={token.token}"
    send_verification_email(user.email, verify_url, locale=locale)
    return redirect("/auth/verify-pending")


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return redirect("/")


@router.get("/forgot", response_class=HTMLResponse)
def forgot_form(request: Request, locale: LocaleDep):
    return templates.TemplateResponse(
        request,
        "auth/forgot.html", template_context(request, locale))


@router.post("/forgot")
def forgot(db: DbDep, locale: LocaleDep, email: str = Form(...)):
    user = db.query(User).filter(User.email == email.lower().strip()).first()
    if user:
        token = create_email_token(db, user, "reset", hours=2)
        reset_url = f"{get_settings().app_base_url}/auth/reset?token={token.token}"
        send_password_reset_email(user.email, reset_url, locale=locale)
    return redirect("/auth/login")


@router.get("/reset", response_class=HTMLResponse)
def reset_form(request: Request, locale: LocaleDep, token: str):
    return templates.TemplateResponse(
        request,
        "auth/reset.html",
        template_context(request, locale, token=token),
    )


@router.post("/reset")
def reset(db: DbDep, token: str = Form(...), password: str = Form(...)):
    user = consume_email_token(db, token, "reset")
    if not user or len(password) < 8:
        return redirect("/auth/forgot")
    user.password_hash = hash_password(password)
    user.email_verified = True
    db.commit()
    return redirect("/auth/login")
