import logging
import re
from urllib.parse import unquote

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.security.ip_blocklist import is_ip_blocked


logger = logging.getLogger("security")


SQL_INJECTION_PATTERNS = [
    re.compile(r"(?i)(union\s+select)"),
    re.compile(r"(?i)(select\s+.+\s+from)"),
    re.compile(r"(?i)(insert\s+into)"),
    re.compile(r"(?i)(drop\s+table)"),
    re.compile(r"(?i)(delete\s+from)"),
    re.compile(r"(?i)(update\s+.+\s+set)"),
    re.compile(r"(?i)(or\s+1\s*=\s*1)"),
    re.compile(r"(?i)(and\s+1\s*=\s*1)"),
    re.compile(r"(?i)(--\s*$)"),
    re.compile(r"(?i)(;\s*(drop|delete|insert|update)\b)"),
]


XSS_PATTERNS = [
    re.compile(r"(?i)<\s*script\b"),
    re.compile(r"(?i)javascript\s*:"),
    re.compile(r"(?i)<\s*iframe\b"),
    re.compile(r"(?i)<\s*object\b"),
    re.compile(r"(?i)<\s*embed\b"),
    re.compile(r"(?i)onerror\s*="),
    re.compile(r"(?i)onload\s*="),
    re.compile(r"(?i)onclick\s*="),
]


PATH_TRAVERSAL_PATTERNS = [
    re.compile(r"\.\./"),
    re.compile(r"\.\.\\"),
    re.compile(r"(?i)%2e%2e%2f"),
    re.compile(r"(?i)%2e%2e/"),
    re.compile(r"(?i)\.\.%2f"),
    re.compile(r"(?i)%2e%2e%5c"),
]


def detect_attack(value: str) -> str | None:
    decoded = unquote(value)

    for pattern in SQL_INJECTION_PATTERNS:
        if pattern.search(decoded):
            return "sql_injection"

    for pattern in XSS_PATTERNS:
        if pattern.search(decoded):
            return "xss"

    for pattern in PATH_TRAVERSAL_PATTERNS:
        if pattern.search(decoded):
            return "path_traversal"

    return None


class WAFMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next,
    ):
        request_id = getattr(
            request.state,
            "request_id",
            request.headers.get(
                "X-Correlation-ID",
                "",
            ),
        )

        client_ip = (
            request.client.host
            if request.client
            else "unknown"
        )

        # --------------------------------------------------
        # Redis IP blocklist
        # --------------------------------------------------

        if (
            client_ip != "unknown"
            and is_ip_blocked(client_ip)
        ):
            logger.warning(
                "Security event: blocked IP "
                "ip=%s method=%s path=%s request_id=%s",
                client_ip,
                request.method,
                request.url.path,
                request_id,
            )

            response = JSONResponse(
                status_code=403,
                content={
                    "detail": "IP address blocked",
                    "request_id": request_id,
                },
            )

            if request_id:
                response.headers[
                    "X-Correlation-ID"
                ] = request_id

            return response

        # --------------------------------------------------
        # WAF attack detection
        # --------------------------------------------------

        attack = detect_attack(request.url.path)

        if not attack:
            attack = detect_attack(
                str(request.url.query)
            )

        if not attack and request.method in {
            "POST",
            "PUT",
            "PATCH",
        }:
            body = await request.body()

            if body:
                body_text = body.decode(
                    "utf-8",
                    errors="ignore",
                )

                attack = detect_attack(body_text)

        # --------------------------------------------------
        # Block malicious request
        # --------------------------------------------------

        if attack:
            logger.warning(
                "Security event: blocked request "
                "attack=%s method=%s path=%s "
                "client=%s request_id=%s",
                attack,
                request.method,
                request.url.path,
                client_ip,
                request_id,
            )

            response = JSONResponse(
                status_code=403,
                content={
                    "detail": "Request blocked by security policy",
                    "request_id": request_id,
                },
            )

            if request_id:
                response.headers[
                    "X-Correlation-ID"
                ] = request_id

            return response

        return await call_next(request)