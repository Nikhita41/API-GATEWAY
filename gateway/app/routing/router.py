import asyncio
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx
import yaml
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.cache.cache import (
    build_cache_key,
    get_cached_response,
    invalidate_cache,
    set_cached_response,
)
from app.circuitbreaker.breaker import CircuitBreaker, CircuitState
from app.core.authenticate import authenticate
from app.db.database import get_db
from app.health.checker import check_service
from app.loadbalancer.balancer import load_balancer
from app.ratelimit.limiter import check_rate_limit


ROUTES_FILE = Path("/app/routes.yaml")

if not ROUTES_FILE.exists():
    ROUTES_FILE = Path(__file__).resolve().parents[2] / "routes.yaml"


with ROUTES_FILE.open("r", encoding="utf-8") as file:
    config = yaml.safe_load(file)


routes = config["routes"]

router = APIRouter()


# ============================================================
# Health monitoring
# ============================================================

_health_status: dict[str, dict[str, bool]] = {}
_health_task: asyncio.Task | None = None


@router.get("/health/status")
async def health_status():
    return {
        "status": "healthy",
        "upstreams": _health_status,
    }


async def refresh_health():
    global _health_status

    for route in routes:
        upstream = route["upstream"]

        health = await check_service(upstream)

        _health_status[upstream] = health

        load_balancer.update_health(
            upstream,
            health,
        )


async def health_monitor():
    while True:
        try:
            await refresh_health()
        except Exception:
            pass

        await asyncio.sleep(5)


async def start_health_monitor():
    global _health_task

    await refresh_health()

    _health_task = asyncio.create_task(
        health_monitor()
    )


# ============================================================
# Routing helpers
# ============================================================

def find_route(path: str):
    for route in routes:
        if path.startswith(route["path"]):
            return route

    return None


def get_circuit_breaker(route: dict) -> CircuitBreaker:
    upstream = route["upstream"]

    parsed = urlparse(upstream)

    service_name = parsed.hostname or upstream

    return CircuitBreaker(
        service=service_name,
    )


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


# ============================================================
# Proxy
# ============================================================

async def proxy_request(
    request: Request,
    db: Session,
):
    # --------------------------------------------------------
    # Find route
    # --------------------------------------------------------

    route = find_route(request.url.path)

    if route is None:
        return Response(
            content="Route not found",
            status_code=404,
        )

    # --------------------------------------------------------
    # Circuit breaker
    # --------------------------------------------------------

    circuit_breaker = get_circuit_breaker(route)

    if not circuit_breaker.allow_request():
        correlation_id = request.headers.get(
            "X-Correlation-ID",
            str(uuid4()),
        )

        return Response(
            content='{"detail":"Upstream service temporarily unavailable"}',
            status_code=503,
            media_type="application/json",
            headers={
                "X-Correlation-ID": correlation_id,
                "X-Circuit-State": CircuitState.OPEN.value,
            },
        )

    # --------------------------------------------------------
    # Authentication
    # --------------------------------------------------------

    identifier, tier = get_authenticated_identity(
        request,
        db,
    )

    # --------------------------------------------------------
    # Rate limiting
    # --------------------------------------------------------

    rate_limit = check_rate_limit(
        client_id=identifier,
        tier=tier,
    )

    correlation_id = request.headers.get(
        "X-Correlation-ID",
        str(uuid4()),
    )

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

    # --------------------------------------------------------
    # Cache lookup
    # --------------------------------------------------------

    cache_key = build_cache_key(
        request,
        identifier,
    )

    if request.method.upper() == "GET":
        cached_response = get_cached_response(
            cache_key
        )

        if cached_response is not None:
            cached_headers = dict(
                cached_response.get("headers", {})
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
                content=cached_response["body"],
                status_code=cached_response["status_code"],
                headers=cached_headers,
                media_type=cached_headers.get(
                    "content-type"
                ),
            )

    # --------------------------------------------------------
    # Build upstream URL
    # --------------------------------------------------------

    upstream_url = load_balancer.get_upstream(
        route["upstream"]
    )

    upstream_url += request.url.path

    if request.url.query:
        upstream_url += f"?{request.url.query}"

    # --------------------------------------------------------
    # Forward request headers
    # --------------------------------------------------------

    headers = dict(request.headers)

    headers.pop("host", None)

    headers["X-Correlation-ID"] = correlation_id

    # --------------------------------------------------------
    # Forward request
    # --------------------------------------------------------

    try:
        async with httpx.AsyncClient() as client:
            upstream_response = await client.request(
                method=request.method,
                url=upstream_url,
                headers=headers,
                content=await request.body(),
            )

    except (
        httpx.ConnectError,
        httpx.ConnectTimeout,
        httpx.ReadTimeout,
        httpx.RemoteProtocolError,
    ):
        circuit_breaker.record_failure()

        return Response(
            content='{"detail":"Upstream service unavailable"}',
            status_code=503,
            media_type="application/json",
            headers={
                "X-Correlation-ID": correlation_id,
                "X-Circuit-State": (
                    circuit_breaker.get_state().value
                ),
            },
        )

    # --------------------------------------------------------
    # Circuit breaker result
    # --------------------------------------------------------

    if upstream_response.status_code >= 500:
        circuit_breaker.record_failure()
    else:
        circuit_breaker.record_success()

    # --------------------------------------------------------
    # Response headers
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Cache successful GET responses
    # --------------------------------------------------------

    if (
        request.method.upper() == "GET"
        and upstream_response.status_code == 200
    ):
        cache_headers = dict(
            upstream_response.headers
        )

        set_cached_response(
            cache_key=cache_key,
            status_code=upstream_response.status_code,
            headers=cache_headers,
            body=upstream_response.content,
        )

        response_headers["X-Cache"] = "MISS"

    # --------------------------------------------------------
    # Invalidate cache for mutations
    # --------------------------------------------------------

    if request.method.upper() in {
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
    }:
        invalidate_cache(
            request.url.path
        )

    # --------------------------------------------------------
    # Return upstream response
    # --------------------------------------------------------

    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=response_headers,
        media_type=upstream_response.headers.get(
            "content-type"
        ),
    )


# ============================================================
# User routes
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
# Order routes
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