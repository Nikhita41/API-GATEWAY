import asyncio
import socket
from urllib.parse import urlparse

import httpx


HEALTH_CHECK_TIMEOUT = 2.0


def resolve_upstreams(upstream: str) -> list[str]:
    parsed = urlparse(upstream)

    if not parsed.hostname or not parsed.port:
        return [upstream]

    try:
        addresses = socket.getaddrinfo(
            parsed.hostname,
            parsed.port,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror:
        return []

    ips = []

    for address in addresses:
        ip = address[4][0]

        if ip not in ips:
            ips.append(ip)

    return sorted(ips)


async def check_upstream(
    upstream: str,
    ip: str,
) -> bool:
    parsed = urlparse(upstream)

    health_url = (
        f"{parsed.scheme}://{ip}:{parsed.port}/health"
    )

    try:
        async with httpx.AsyncClient(
            timeout=HEALTH_CHECK_TIMEOUT
        ) as client:
            response = await client.get(health_url)

        return response.status_code == 200

    except (
        httpx.HTTPError,
        OSError,
    ):
        return False


async def check_service(
    upstream: str,
) -> dict[str, bool]:
    ips = resolve_upstreams(upstream)

    if not ips:
        return {}

    results = await asyncio.gather(
        *[
            check_upstream(upstream, ip)
            for ip in ips
        ]
    )

    return dict(zip(ips, results))
