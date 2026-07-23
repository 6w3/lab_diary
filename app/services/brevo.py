from __future__ import annotations

import logging

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


def send_email(*, to_email: str, subject: str, html_content: str, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    # Local/dev: always log instead of calling Brevo (even if key is set).
    if settings.dev_log_email:
        logger.warning("DEV email to=%s subject=%s\n%s", to_email, subject, html_content)
        return
    if not settings.brevo_api_key:
        raise RuntimeError("BREVO_API_KEY is not configured")

    payload = {
        "sender": {"name": settings.brevo_sender_name, "email": settings.brevo_sender_email},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_content,
    }
    response = httpx.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={
            "api-key": settings.brevo_api_key,
            "accept": "application/json",
            "content-type": "application/json",
        },
        json=payload,
        timeout=30.0,
    )
    if response.is_error:
        detail = response.text[:500]
        logger.error("Brevo send failed status=%s body=%s", response.status_code, detail)
        raise RuntimeError(f"Brevo email failed ({response.status_code}): {detail}") from None


def send_verification_email(to_email: str, verify_url: str, locale: str = "cs") -> None:
    if locale == "en":
        subject = "Verify your Lab Diary account"
        html = f"<p>Please verify your email:</p><p><a href=\"{verify_url}\">{verify_url}</a></p>"
    else:
        subject = "Potvrzení e-mailu — Lab deník"
        html = f"<p>Potvrď prosím svůj e-mail:</p><p><a href=\"{verify_url}\">{verify_url}</a></p>"
    send_email(to_email=to_email, subject=subject, html_content=html)


def send_password_reset_email(to_email: str, reset_url: str, locale: str = "cs") -> None:
    if locale == "en":
        subject = "Reset your Lab Diary password"
        html = f"<p>Reset password:</p><p><a href=\"{reset_url}\">{reset_url}</a></p>"
    else:
        subject = "Obnovení hesla — Lab deník"
        html = f"<p>Obnovení hesla:</p><p><a href=\"{reset_url}\">{reset_url}</a></p>"
    send_email(to_email=to_email, subject=subject, html_content=html)
