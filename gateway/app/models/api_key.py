from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.sql import func

from app.db.database import Base


class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True)

    key = Column(String(255), unique=True, nullable=False)

    owner_id = Column(Integer, ForeignKey("users.id"))

    tier = Column(String(50), default="free")

    scopes = Column(String(255))

    is_active = Column(Boolean, default=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )