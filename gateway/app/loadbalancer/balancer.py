import socket
from collections import defaultdict
from threading import Lock
from urllib.parse import urlparse, urlunparse


class RoundRobinBalancer:
    def __init__(self):
        self._counters = defaultdict(int)
        self._lock = Lock()
        self._healthy = {}

    def discover_upstreams(self, upstream: str) -> list[str]:
        parsed = urlparse(upstream)

        hostname = parsed.hostname
        port = parsed.port

        if not hostname or not port:
            return [upstream]

        try:
            addresses = socket.getaddrinfo(
                hostname,
                port,
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

    def update_health(
        self,
        upstream: str,
        health: dict[str, bool],
    ):
        self._healthy[upstream] = health

    def get_healthy_upstreams(
        self,
        upstream: str,
    ) -> list[str]:
        ips = self.discover_upstreams(upstream)

        if not ips:
            return []

        health = self._healthy.get(upstream)

        # If health has not been checked yet,
        # keep the existing Day 4 behaviour.
        if health is None:
            return ips

        return [
            ip
            for ip in ips
            if health.get(ip, False)
        ]

    def get_upstream(self, upstream: str) -> str:
        parsed = urlparse(upstream)

        hostname = parsed.hostname
        port = parsed.port

        if not hostname or not port:
            return upstream

        ips = self.get_healthy_upstreams(upstream)

        if not ips:
            return upstream

        with self._lock:
            index = (
                self._counters[hostname]
                % len(ips)
            )
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