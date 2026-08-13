from pathlib import Path
from uuid import uuid4

import httpx
import yaml
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.authenticate import authenticate
from app.db.database import get_db
from app.ratelimit.limiter import check_rate_limit


ROUTES_FILE = Path("/app/routes.yaml")
if not ROUTES_FILE.exists():
    ROUTES_FILE = Path(__file__).resolve().parents[2] / "routes.yaml"

with ROUTES_FILE.open("r", encoding="utf-8") as file:
    config = yaml.safe_load(file)

routes = config["routes"]

router = APIRouter()


def find_route(path: str):
    for route in routes:
        if path.startswith(route["path"]):
            return route

    return None


def get_authenticated_identity(
    request: Request,
    db: Session,
):
    authorization = request.headers.get("authorization")
    api_key = request.headers.get("x-api-key")

    user = authenticate(
        db=db,
        authorization=authorization,
        api_key=api_key,
    )

    if api_key:
        return f"apikey:{user.id}", user.tier

    return f"user:{user.get('sub')}", "free"


async def proxy_request(
    request: Request,
    db: Session,
):
    route = find_route(request.url.path)

    if route is None:
        return Response(
            content="Route not found",
            status_code=404,
        )

    # -----------------------------
    # Authentication
    # -----------------------------

    identifier, tier = get_authenticated_identity(
        request,
        db,
    )

    # -----------------------------
    # Redis Lua rate limiting
    # -----------------------------

    rate_limit = check_rate_limit(
        client_id=identifier,
        tier=tier,
    )

    if not rate_limit["allowed"]:
        correlation_id = request.headers.get(
            "X-Correlation-ID",
            str(uuid4()),
        )

        return Response(
            content='{"detail":"Rate limit exceeded"}',
            status_code=429,
            media_type="application/json",
            headers={
                "X-RateLimit-Limit": str(
                    rate_limit["limit"]
                ),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(
                    rate_limit["retry_after"]
                ),
                "Retry-After": str(
                    rate_limit["retry_after"]
                ),
                "X-Correlation-ID": correlation_id,
            },
        )

    # -----------------------------
    # Correlation ID
    # -----------------------------

    correlation_id = request.headers.get(
        "X-Correlation-ID",
        str(uuid4()),
    )

    # -----------------------------
    # Build upstream URL
    # -----------------------------

    upstream_url = (
        route["upstream"] + request.url.path
    )

    if request.url.query:
        upstream_url += f"?{request.url.query}"

    # -----------------------------
    # Forward request headers
    # -----------------------------

    headers = dict(request.headers)

    headers.pop("host", None)

    headers["X-Correlation-ID"] = correlation_id

    # -----------------------------
    # Forward request
    # -----------------------------

    async with httpx.AsyncClient() as client:
        upstream_response = await client.request(
            method=request.method,
            url=upstream_url,
            headers=headers,
            content=await request.body(),
        )

    # -----------------------------
    # Build response headers
    # -----------------------------

    response_headers = dict(
        upstream_response.headers
    )

    response_headers["X-Correlation-ID"] = (
        correlation_id
    )

    response_headers["X-RateLimit-Limit"] = str(
        rate_limit["limit"]
    )

    response_headers["X-RateLimit-Remaining"] = str(
        rate_limit["remaining"]
    )

    response_headers["X-RateLimit-Reset"] = str(
        rate_limit["retry_after"]
    )

    # -----------------------------
    # Return upstream response
    # -----------------------------

    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=response_headers,
        media_type=upstream_response.headers.get(
            "content-type"
        ),
    )


@router.api_route(
    "/users/{path:path}",
    methods=[
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "OPTIONS",
    ],
)
@router.api_route(
    "/users",
    methods=[
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "OPTIONS",
    ],
)
async def users_proxy(
    request: Request,
    db: Session = Depends(get_db),
):
    return await proxy_request(
        request,
        db,
    )


@router.api_route(
    "/orders/{path:path}",
    methods=[
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "OPTIONS",
    ],
)
@router.api_route(
    "/orders",
    methods=[
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "OPTIONS",
    ],
)
async def orders_proxy(
    request: Request,
    db: Session = Depends(get_db),
):
    return await proxy_request(
        request,
        db,
    )