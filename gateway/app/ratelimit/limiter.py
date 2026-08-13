from pathlib import Path
import time

from app.core.redis import redis_client


FREE_LIMIT = 10
PRO_LIMIT = 100

WINDOW_SECONDS = 60

LUA_SCRIPT = Path(__file__).with_name("token_bucket.lua").read_text(
    encoding="utf-8"
)

token_bucket = redis_client.register_script(LUA_SCRIPT)


def check_rate_limit(
    client_id: str,
    tier: str = "free",
):
    if tier.lower() == "pro":
        limit = PRO_LIMIT
    else:
        limit = FREE_LIMIT

    refill_rate = limit / WINDOW_SECONDS

    now = time.time()

    redis_key = f"rate_limit:{tier.lower()}:{client_id}"

    result = token_bucket(
        keys=[redis_key],
        args=[
            limit,
            refill_rate,
            now,
        ],
    )

    allowed = int(result[0])
    remaining = int(result[1])

    reset = WINDOW_SECONDS

    if not allowed:
        return {
            "allowed": False,
            "limit": limit,
            "remaining": remaining,
            "retry_after": reset,
        }

    return {
        "allowed": True,
        "limit": limit,
        "remaining": remaining,
        "retry_after": reset,
    }