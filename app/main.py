from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.db import SessionLocal
from app.deps import LocaleDep, OptionalUserDep, redirect, template_context
from app.models import User
from app.routers import account, auth, draws, imports, oauth, trends
from app.services.markers import seed_markers
from app.services.storage import ensure_upload_dir

settings = get_settings()
templates = Jinja2Templates(directory="app/templates")

app = FastAPI(title="Lab Diary")

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.include_router(auth.router)
app.include_router(oauth.router)
app.include_router(imports.router)
app.include_router(draws.router)
app.include_router(trends.router)
app.include_router(account.router)


@app.middleware("http")
async def load_user(request: Request, call_next):
    # Runs inside SessionMiddleware (added last = outermost).
    request.state.user = None
    user_id = request.session.get("user_id")
    if user_id:
        db = SessionLocal()
        try:
            request.state.user = db.get(User, user_id)
        finally:
            db.close()
    return await call_next(request)


# Must be added AFTER @app.middleware so SessionMiddleware is outermost.
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie=settings.session_cookie_name,
    max_age=settings.session_max_age,
    same_site="lax",
    https_only=settings.app_base_url.startswith("https"),
)

@app.exception_handler(StarletteHTTPException)
async def redirect_http_exception(request: Request, exc: StarletteHTTPException):
    if exc.status_code in {303, 302} and exc.headers and "Location" in exc.headers:
        return RedirectResponse(url=exc.headers["Location"], status_code=303)
    return await http_exception_handler(request, exc)


@app.on_event("startup")
def on_startup() -> None:
    ensure_upload_dir()
    db = SessionLocal()
    try:
        seed_markers(db)
    finally:
        db.close()
    from app.services.import_worker import start_import_worker

    start_import_worker()


@app.on_event("shutdown")
def on_shutdown() -> None:
    from app.services.import_worker import stop_import_worker

    stop_import_worker()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home(request: Request, locale: LocaleDep, user: OptionalUserDep):
    if user is not None:
        if not user.email_verified:
            return RedirectResponse(url="/auth/verify-pending", status_code=303)
        return RedirectResponse(url="/draws", status_code=303)
    return templates.TemplateResponse(
        request,
        "home.html",
        template_context(request, locale),
    )


@app.post("/locale")
def set_locale_cookie(request: Request, locale: str = Form("cs")):
    from urllib.parse import urlparse

    if locale not in {"cs", "en"}:
        locale = "cs"
    user = getattr(request.state, "user", None)
    if user is not None:
        db = SessionLocal()
        try:
            db_user = db.get(User, user.id)
            if db_user:
                db_user.locale = locale
                db.commit()
        finally:
            db.close()
    next_path = "/"
    referer = request.headers.get("referer") or ""
    if referer:
        parsed = urlparse(referer)
        req_host = urlparse(str(request.base_url)).netloc
        if not parsed.netloc or parsed.netloc == req_host:
            next_path = parsed.path or "/"
            if parsed.query:
                next_path = f"{next_path}?{parsed.query}"
    response = redirect(next_path)
    response.set_cookie("locale", locale, max_age=60 * 60 * 24 * 365)
    return response
