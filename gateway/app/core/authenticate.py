import hashlib

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.api_key import APIKey
from app.core.security import get_current_user


def authenticate(
    db: Session,
    authorization: str | None = None,
    api_key: str | None = None,
):
    # JWT authentication
    if authorization:
        if not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authorization header",
            )

        token = authorization.split(" ", 1)[1]

        # Reuse our existing JWT + blacklist validation
        # by passing the token through the same logic.
        from app.auth.jwt_handler import decode_token
        from app.core.redis import redis_client
        from jose import JWTError

        try:
            payload = decode_token(token)
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )

        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid access token",
            )

        jti = payload.get("jti")

        if not jti or redis_client.exists(f"blacklist:{jti}"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
            )

        return payload

    # API key authentication
    if api_key:
        hashed_key = hashlib.sha256(
            api_key.encode("utf-8")
        ).hexdigest()

        stored_key = (
            db.query(APIKey)
            .filter(
                APIKey.key == hashed_key,
                APIKey.is_active == True,
            )
            .first()
        )

        if not stored_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
            )

        return stored_key

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
    )