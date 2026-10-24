"""Bounded IPv4 discovery; device probing is a separate management API operation."""

import asyncio
import json
import socket
from dataclasses import dataclass


@dataclass(frozen=True, order=True, slots=True)
class AlpacaServer:
    host: str
    port: int

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


def parse_response(data: bytes, host: str) -> AlpacaServer | None:
    try:
        payload = json.loads(data)
        port = payload.get("AlpacaPort") if isinstance(payload, dict) else None
        if type(port) is int and 1 <= port <= 65535:
            return AlpacaServer(host, port)
    except (ValueError, UnicodeDecodeError):
        pass
    return None


async def discover(
    *, duration: float = 2.0, broadcast: str = "255.255.255.255", port: int = 32227
) -> list[AlpacaServer]:
    if duration <= 0:
        raise ValueError("Discovery timeout must be positive")
    loop = asyncio.get_running_loop()
    found: set[AlpacaServer] = set()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setblocking(False)
        sock.bind(("0.0.0.0", 0))
        await loop.sock_sendto(sock, b"alpacadiscovery1", (broadcast, port))
        try:
            async with asyncio.timeout(duration):
                while True:
                    data, address = await loop.sock_recvfrom(sock, 4096)
                    server = parse_response(data, address[0])
                    if server:
                        found.add(server)
        except TimeoutError:
            return sorted(found)
