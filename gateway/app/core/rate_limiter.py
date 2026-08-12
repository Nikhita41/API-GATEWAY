import time

from fastapi import HTTPException, status

from app.core.redis import redis_client


FREE_LIMIT = 10
PRO_LIMIT = 30

WINDOW_SECONDS = 60


def check_rate_limit(
    identifier: str,
    tier: str = "free",
):
    if tier.lower() == "pro":
        limit = PRO_LIMIT
    else:
        limit = FREE_LIMIT

    key = f"rate_limit:{identifier}"

    now = int(time.time())
    window = now // WINDOW_SECONDS
    redis_key = f"{key}:{window}"

    current_count = redis_client.incr(redis_key)

    if current_count == 1:
        redis_client.expire(redis_key, WINDOW_SECONDS)

    remaining = max(limit - current_count, 0)

    if current_count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "Retry-After": str(
                    WINDOW_SECONDS - (now % WINDOW_SECONDS)
                ),
            },
        )

    return {
        "limit": limit,
        "remaining": remaining,
        "reset": WINDOW_SECONDS - (now % WINDOW_SECONDS),
    }