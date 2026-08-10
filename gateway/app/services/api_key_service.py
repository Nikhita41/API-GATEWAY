import hashlib
import secrets

from sqlalchemy.orm import Session

from app.models.api_key import APIKey


def generate_api_key() -> str:
    return secrets.token_urlsafe(32)


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(
        api_key.encode("utf-8")
    ).hexdigest()


def create_api_key(
    db: Session,
    owner_id: int,
    tier: str = "free",
    scopes: str = "",
):
    raw_key = generate_api_key()
    hashed_key = hash_api_key(raw_key)

    api_key = APIKey(
        key=hashed_key,
        owner_id=owner_id,
        tier=tier,
        scopes=scopes,
    )

    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    return raw_key, api_key