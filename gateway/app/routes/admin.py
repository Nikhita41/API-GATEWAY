from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.api_key_service import create_api_key

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
)


@router.post("/api-keys")
def create_new_api_key(
    owner_id: int,
    tier: str = "free",
    scopes: str = "",
    db: Session = Depends(get_db),
):
    raw_key, api_key = create_api_key(
        db=db,
        owner_id=owner_id,
        tier=tier,
        scopes=scopes,
    )

    return {
        "api_key": raw_key,
        "tier": api_key.tier,
        "scopes": api_key.scopes,
    }