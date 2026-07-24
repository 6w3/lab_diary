from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.db import get_db
from app.i18n import t
from app.models import User


def get_locale(request: Request) -> str:
    user: User | None = getattr(request.state, "user", None)
    if user and user.locale in {"cs", "en"}:
        return user.locale
    cookie = request.cookies.get("locale")
    if cookie in {"cs", "en"}:
        return cookie
    return "cs"


def get_current_user(request: Request) -> User | None:
    return getattr(request.state, "user", None)


def require_user(request: Request) -> User:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/auth/login"})
    return user


def require_verified_user(request: Request) -> User:
    user = require_user(request)
    if not user.email_verified:
        raise HTTPException(status_code=303, headers={"Location": "/auth/verify-pending"})
    return user


DbDep = Annotated[Session, Depends(get_db)]
LocaleDep = Annotated[str, Depends(get_locale)]
UserDep = Annotated[User, Depends(require_verified_user)]
OptionalUserDep = Annotated[User | None, Depends(get_current_user)]


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url=url, status_code=303)


def template_context(request: Request, locale: str, **extra):
    user = get_current_user(request)
    flash = None
    if hasattr(request, "session"):
        flash = request.session.pop("flash", None)
    return {
        "request": request,
        "locale": locale,
        "user": user,
        "t": lambda key, **kw: t(locale, key, **kw),
        "disclaimer": t(locale, "disclaimer"),
        "flash": flash,
        **extra,
    }
