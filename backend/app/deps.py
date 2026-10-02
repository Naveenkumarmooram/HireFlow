import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User
from app.security import ALGORITHM

bearer = HTTPBearer(auto_error=False)


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[ALGORITHM],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["sub", "org", "ver", "iat", "exp", "iss", "aud", "jti"]},
        )
        user_id = payload.get("sub")
        organization_id = payload.get("org")
    except jwt.PyJWTError as exc:
        raise unauthorized from exc
    user = db.get(User, user_id) if user_id else None
    if (
        user is None
        or not user.active
        or user.organization_id != organization_id
        or payload["ver"] != user.token_version
    ):
        raise unauthorized
    return user


def recruiter_user(user: User = Depends(current_user)) -> User:
    if user.role not in {"admin", "recruiter"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Recruiter access required"
        )
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organisation admin access required",
        )
    return user


def coordinator_user(user: User = Depends(current_user)) -> User:
    if user.role not in {"admin", "recruiter", "hiring_manager"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Recruitment coordinator access required",
        )
    return user
