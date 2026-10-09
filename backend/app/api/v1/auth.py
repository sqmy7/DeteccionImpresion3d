from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, oauth2_scheme
from app.core.config import settings
from app.core.security import create_access_token, decode_access_token, verify_password
from app.db.models import User
from app.db.session import get_db
from app.schemas.auth import Token
from app.schemas.user import UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> Token:
    result = await db.execute(select(User).where(User.username == form_data.username))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(subject=str(user.id))
    return Token(access_token=access_token)


@router.post("/refresh", response_model=Token)
async def refresh(token: str = Depends(oauth2_scheme), current_user: User = Depends(get_current_user)) -> Token:
    """A new token for a session that is still valid, so the web can keep it alive while it is open (a print lasts
    hours and the token one hour). The session still ends jwt_max_session_hours after the login that began it. A token
    from before this existed has no auth_time: its session counts from now."""
    payload = decode_access_token(token)  # get_current_user already accepted it
    now = datetime.now(timezone.utc)
    started = datetime.fromtimestamp(payload.get("auth_time", now.timestamp()), tz=timezone.utc)
    if now - started > timedelta(hours=settings.jwt_max_session_hours):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session too old; log in again",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(access_token=create_access_token(subject=str(current_user.id), auth_time=started))


@router.get("/me", response_model=UserRead)
async def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    return current_user
