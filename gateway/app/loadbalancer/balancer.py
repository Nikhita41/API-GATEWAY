import socket
from collections import defaultdict
from threading import Lock
from urllib.parse import urlparse, urlunparse


class RoundRobinBalancer:
    def __init__(self):
        self._counters = defaultdict(int)
        self._lock = Lock()

    def get_upstream(self, upstream: str) -> str:
        parsed = urlparse(upstream)

        hostname = parsed.hostname
        port = parsed.port

        if not hostname or not port:
            return upstream

        addresses = socket.getaddrinfo(
            hostname,
            port,
            type=socket.SOCK_STREAM,
        )

        ips = []

        for address in addresses:
            ip = address[4][0]

            if ip not in ips:
                ips.append(ip)

        if not ips:
            return upstream

        ips.sort()

        with self._lock:
            index = self._counters[hostname] % len(ips)
            self._counters[hostname] += 1

        selected_ip = ips[index]

        return urlunparse(
            (
                parsed.scheme,
                f"{selected_ip}:{port}",
                parsed.path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            )
        )


load_balancer = RoundRobinBalancer()