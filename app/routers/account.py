from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.deps import DbDep, LocaleDep, UserDep, redirect, template_context
from app.models import Attachment, BloodDraw, User
from app.services.storage import delete_file

router = APIRouter(prefix="/account", tags=["account"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
def account_page(request: Request, locale: LocaleDep, user: UserDep):
    return templates.TemplateResponse(
        request,
        "account.html", template_context(request, locale))


@router.post("/locale")
def set_user_locale(db: DbDep, user: UserDep, locale: str = Form(...)):
    if locale not in {"cs", "en"}:
        locale = "cs"
    # request.state.user is detached (middleware session closed) — mutate via DbDep
    db_user = db.get(User, user.id)
    if db_user:
        db_user.locale = locale
        db.commit()
    response = redirect("/account")
    response.set_cookie("locale", locale, max_age=60 * 60 * 24 * 365)
    return response


@router.post("/delete")
def delete_account(request: Request, db: DbDep, user: UserDep):
    user_id = user.id
    draw_ids = [d.id for d in db.query(BloodDraw).filter(BloodDraw.user_id == user_id).all()]
    if draw_ids:
        for att in db.query(Attachment).filter(Attachment.blood_draw_id.in_(draw_ids)).all():
            delete_file(att.storage_path)
    db_user = db.get(User, user_id)
    if db_user:
        db.delete(db_user)
        db.commit()
    request.session.clear()
    return redirect("/")
