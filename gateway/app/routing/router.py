from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4
import yaml
import httpx
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.cache.cache import (
    build_cache_key,
    get_cached_response,
    invalidate_cache,
    set_cached_response,
)
from app.core.authenticate import authenticate
from app.db.database import get_db
from app.loadbalancer.balancer import load_balancer
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

    # API key authentication
    if api_key:
        if isinstance(user, dict):
            user_id = user.get("id")
            tier = user.get("tier", "free")
        else:
            user_id = getattr(user, "id", None)
            tier = getattr(user, "tier", "free")

        return f"apikey:{user_id}", tier

    # JWT authentication
    if isinstance(user, dict):
        sub = user.get("sub")
    else:
        sub = getattr(user, "sub", None)

    return f"user:{sub}", "free"


async def proxy_request(
    request: Request,
    db: Session,
):
    # -----------------------------
    # Find route
    # -----------------------------

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
    # Rate limiting
    # -----------------------------

    rate_limit = check_rate_limit(
        client_id=identifier,
        tier=tier,
    )

    # -----------------------------
    # Correlation ID
    # -----------------------------

    correlation_id = request.headers.get(
        "X-Correlation-ID",
        str(uuid4()),
    )

    # -----------------------------
    # Rate limit rejection
    # -----------------------------

    if not rate_limit["allowed"]:
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
    # Cache key
    # -----------------------------

    cache_key = build_cache_key(
        request=request,
        auth_scope=identifier,
    )

    # -----------------------------
    # Cache lookup
    # -----------------------------

    if request.method.upper() == "GET":
        cached = get_cached_response(cache_key)

        if cached is not None:
            cached_headers = dict(
                cached.get("headers", {})
            )

            cached_headers["X-Cache"] = "HIT"
            cached_headers["X-Correlation-ID"] = (
                correlation_id
            )

            cached_headers["X-RateLimit-Limit"] = str(
                rate_limit["limit"]
            )

            cached_headers["X-RateLimit-Remaining"] = str(
                rate_limit["remaining"]
            )

            cached_headers["X-RateLimit-Reset"] = str(
                rate_limit["retry_after"]
            )

            return Response(
                content=cached["body"],
                status_code=cached["status_code"],
                headers=cached_headers,
                media_type=cached_headers.get(
                    "content-type"
                ),
            )

    # -----------------------------
    # Select backend replica
    # -----------------------------

    selected_upstream = load_balancer.get_upstream(
        route["upstream"]
    )

    # -----------------------------
    # Build upstream URL
    # -----------------------------

    upstream_url = (
        selected_upstream + request.url.path
    )

    if request.url.query:
        upstream_url += f"?{request.url.query}"

    # -----------------------------
    # Preserve original upstream Host
    # -----------------------------

    original_host = urlparse(
        route["upstream"]
    ).netloc

    # -----------------------------
    # Forward headers
    # -----------------------------

    headers = dict(request.headers)

    headers.pop("host", None)

    headers["Host"] = original_host
    headers["X-Correlation-ID"] = correlation_id

    # -----------------------------
    # Forward request
    # -----------------------------

    request_kwargs = {
        "method": request.method,
        "url": upstream_url,
        "headers": headers,
    }

    if request.method.upper() not in ("GET", "HEAD", "OPTIONS"):
        request_kwargs["content"] = await request.body()

    async with httpx.AsyncClient() as client:
        upstream_response = await client.request(**request_kwargs)

    # -----------------------------
    # Response headers
    # -----------------------------

    excluded_headers = {
        "content-encoding",
        "content-length",
        "transfer-encoding",
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "upgrade",
    }

    response_headers = {
        k: v
        for k, v in upstream_response.headers.items()
        if k.lower() not in excluded_headers
    }

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
    # Cache successful GET
    # -----------------------------

    if (
        request.method.upper() == "GET"
        and upstream_response.status_code == 200
    ):
        set_cached_response(
            cache_key=cache_key,
            status_code=upstream_response.status_code,
            headers=dict(upstream_response.headers),
            body=upstream_response.content,
        )

        response_headers["X-Cache"] = "MISS"

    elif request.method.upper() == "GET":
        response_headers["X-Cache"] = "BYPASS"

    else:
        response_headers["X-Cache"] = "BYPASS"

    # -----------------------------
    # Invalidate cache after mutation
    # -----------------------------

    if request.method.upper() in {
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
    }:
        invalidate_cache(request.url.path)

    # -----------------------------
    # Return response
    # -----------------------------

    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=response_headers,
        media_type=upstream_response.headers.get(
            "content-type"
        ),
    )


# ============================================================
# USERS
# ============================================================

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


# ============================================================
# ORDERS
# ============================================================

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