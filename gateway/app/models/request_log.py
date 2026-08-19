from sqlalchemy import Column, DateTime, Float, Integer, String
from sqlalchemy.sql import func

from app.db.database import Base


class RequestLog(Base):
    __tablename__ = "request_logs"

    id = Column(
        Integer,
        primary_key=True,
    )

    method = Column(
        String(10),
        nullable=False,
    )

    path = Column(
        String(255),
        nullable=False,
    )

    status_code = Column(
        Integer,
        nullable=False,
    )

    latency = Column(
        Float,
        nullable=False,
    )

    client_ip = Column(
        String(100),
    )

    request_id = Column(
        String(100),
        nullable=False,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )