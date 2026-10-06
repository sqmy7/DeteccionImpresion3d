from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from cryptography.fernet import Fernet

from app.core.config import settings

_fernet = Fernet(settings.field_encryption_key.encode())


def encrypt_secret(value: str) -> str:
    return _fernet.encrypt(value.encode()).decode()


def decrypt_secret(token: str) -> str:
    return _fernet.decrypt(token.encode()).decode()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed_password.encode())


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.jwt_expire_minutes))
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
