from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.models import EmailToken, User

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    return pwd_context.verify(password, password_hash)


def create_email_token(db: Session, user: User, purpose: str, hours: int = 48) -> EmailToken:
    token = secrets.token_urlsafe(32)
    row = EmailToken(
        user_id=user.id,
        token=token,
        purpose=purpose,
        expires_at=datetime.now(UTC) + timedelta(hours=hours),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def consume_email_token(db: Session, token: str, purpose: str) -> User | None:
    row = db.query(EmailToken).filter(EmailToken.token == token, EmailToken.purpose == purpose).first()
    if not row or row.used_at is not None:
        return None
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if expires < datetime.now(UTC):
        return None
    row.used_at = datetime.now(UTC)
    user = row.user
    db.commit()
    return user
