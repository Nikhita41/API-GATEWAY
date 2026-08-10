from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.services.auth_service import login_user
from app.auth.password import hash_password
from app.db.database import get_db
from app.models.user import User
from fastapi import Request
from app.core.authenticate import authenticate
from app.auth.jwt_handler import create_access_token, decode_token
from app.schemas.auth import RefreshTokenRequest
from app.schemas.user import UserCreate, UserResponse
from app.core.security import get_current_user
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.auth.jwt_handler import decode_token
from fastapi import Header
from app.core.redis import redis_client
bearer_scheme = HTTPBearer()
router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/signup",
    response_model=UserResponse,
    status_code=201,
)
def signup(
    user: UserCreate,
    db: Session = Depends(get_db),
):
    existing_user = (
        db.query(User)
        .filter(User.email == user.email)
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Email already registered",
        )

    existing_username = (
        db.query(User)
        .filter(User.username == user.username)
        .first()
    )

    if existing_username:
        raise HTTPException(
            status_code=400,
            detail="Username already taken",
        )

    new_user = User(
        username=user.username,
        email=user.email,
        hashed_password=hash_password(user.password),
    )
    

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user
@router.post("/login")
def login(
    email: str,
    password: str,
    db: Session = Depends(get_db),
):
    result = login_user(
        db=db,
        email=email,
        password=password,
    )

    if not result:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password",
        )

    return result
@router.get("/me")
def get_me(
    current_user: dict = Depends(get_current_user),
):
    return {
        "message": "You are authenticated",
        "user": current_user,
    }
@router.post("/refresh")
def refresh_token(
    data: RefreshTokenRequest,
):
    try:
        payload = decode_token(data.refresh_token)
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired refresh token",
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=401,
            detail="Invalid refresh token",
        )

    user_id = payload.get("sub")

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid refresh token",
        )

    access_token = create_access_token(
        {
            "sub": str(user_id),
        }
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }
@router.post("/logout")
def logout(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    token = credentials.credentials

    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
        )

    jti = payload.get("jti")
    exp = payload.get("exp")

    if not jti or not exp:
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
        )

    import time

    remaining_ttl = int(exp - time.time())

    if remaining_ttl <= 0:
        raise HTTPException(
            status_code=401,
            detail="Token already expired",
        )

    redis_client.setex(
        f"blacklist:{jti}",
        remaining_ttl,
        "1",
    )

    return {
        "message": "Successfully logged out",
    }
@router.get("/test-auth")
def test_auth(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    user = authenticate(
        db=db,
        authorization=authorization,
        api_key=x_api_key,
    )

    return {
        "message": "Authentication successful",
        "authenticated_as": user,
    }