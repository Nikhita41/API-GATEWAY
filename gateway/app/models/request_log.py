from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.sql import func

from app.db.database import Base


class RequestLog(Base):
    __tablename__ = "request_logs"

    id = Column(Integer, primary_key=True)

    method = Column(String(10))

    path = Column(String(255))

    status_code = Column(Integer)

    latency = Column(Float)

    client_ip = Column(String(100))

    request_id = Column(String(100))

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )