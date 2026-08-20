from app.core.redis import redis_client


BLOCKED_IP_PREFIX = "security:blocked_ip:"


def block_ip(ip: str, ttl: int | None = None) -> None:
    key = f"{BLOCKED_IP_PREFIX}{ip}"

    if ttl:
        redis_client.setex(key, ttl, "1")
    else:
        redis_client.set(key, "1")


def unblock_ip(ip: str) -> None:
    redis_client.delete(
        f"{BLOCKED_IP_PREFIX}{ip}"
    )


def is_ip_blocked(ip: str) -> bool:
    return bool(
        redis_client.exists(
            f"{BLOCKED_IP_PREFIX}{ip}"
        )
    )