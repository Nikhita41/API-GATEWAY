import time
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.db.database import SessionLocal
from app.models.request_log import RequestLog


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next,
    ):
        start_time = time.perf_counter()

        request_id = request.headers.get(
            "X-Correlation-ID",
            str(uuid4()),
        )

        request.state.request_id = request_id

        try:
            response = await call_next(request)

        except Exception:
            latency = time.perf_counter() - start_time

            self._save_log(
                request=request,
                status_code=500,
                latency=latency,
                request_id=request_id,
            )

            raise

        latency = time.perf_counter() - start_time

        response.headers["X-Correlation-ID"] = request_id

        self._save_log(
            request=request,
            status_code=response.status_code,
            latency=latency,
            request_id=request_id,
        )

        return response

    @staticmethod
    def _save_log(
        request: Request,
        status_code: int,
        latency: float,
        request_id: str,
    ):
        db = SessionLocal()

        try:
            log = RequestLog(
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                latency=latency,
                client_ip=(
                    request.client.host
                    if request.client
                    else None
                ),
                request_id=request_id,
            )

            db.add(log)
            db.commit()

        except Exception:
            db.rollback()

        finally:
            db.close()