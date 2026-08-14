import hashlib
import json

from fastapi import Request

from app.core.redis import redis_client


DEFAULT_TTL = 30
CACHE_PREFIX = "gateway:cache:"


def build_cache_key(
    request: Request,
    auth_scope: str,
) -> str:
    raw_key = "|".join(
        [
            request.method.upper(),
            request.url.path,
            str(request.url.query),
            auth_scope,
        ]
    )

    digest = hashlib.sha256(
        raw_key.encode("utf-8")
    ).hexdigest()

    return f"{CACHE_PREFIX}{digest}"


def get_cached_response(cache_key: str):
    cached = redis_client.get(cache_key)

    if cached is None:
        return None

    return json.loads(cached)


def set_cached_response(
    cache_key: str,
    status_code: int,
    headers: dict,
    body: bytes,
    ttl: int = DEFAULT_TTL,
):
    data = {
        "status_code": status_code,
        "headers": headers,
        "body": body.decode("utf-8"),
    }

    redis_client.setex(
        cache_key,
        ttl,
        json.dumps(data),
    )


def invalidate_cache(route_path: str):
    pattern = f"{CACHE_PREFIX}*"

    for key in redis_client.scan_iter(match=pattern):
        redis_client.delete(key)