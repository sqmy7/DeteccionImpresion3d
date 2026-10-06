from fastapi import Depends, HTTPException, Query, WebSocketException, status
from fastapi.security import OAuth2PasswordBearer
from jwt import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.models import User, UserRole
from app.db.session import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(token)
    except InvalidTokenError:
        raise credentials_error

    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_error

    user = await db.get(User, int(user_id))
    if user is None:
        raise credentials_error

    return user


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return current_user


async def get_current_user_ws(
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> User:
    invalid_token = WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")

    try:
        payload = decode_access_token(token)
    except InvalidTokenError:
        raise invalid_token

    user_id = payload.get("sub")
    if user_id is None:
        raise invalid_token

    user = await db.get(User, int(user_id))
    if user is None:
        raise invalid_token

    return user


async def get_current_user_query(
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Same JWT check as get_current_user, but reads the token from a query param -
    for endpoints an <img>/<video> tag hits directly, which can't set an Authorization
    header. Only use this for GET endpoints meant to be embedded that way (e.g. MJPEG
    streams); everything else should keep using the header-based get_current_user."""
    credentials_error = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")

    try:
        payload = decode_access_token(token)
    except InvalidTokenError:
        raise credentials_error

    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_error

    user = await db.get(User, int(user_id))
    if user is None:
        raise credentials_error

    return user
