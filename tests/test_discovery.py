import asyncio

import pytest

from aio_astro.adapters.alpaca.discovery import discover, parse_response


@pytest.mark.parametrize(
    "data",
    [
        b"bad",
        b"[]",
        b"{}",
        b'{"AlpacaPort":true}',
        b'{"AlpacaPort":0}',
        b'{"AlpacaPort":65536}',
        b"\xff",
    ],
)
def test_malformed_discovery_responses_are_ignored(data):
    assert parse_response(data, "127.0.0.1") is None


async def test_discovers_and_deduplicates_loopback_server():
    received = []

    class Server(asyncio.DatagramProtocol):
        def connection_made(self, transport):
            self.transport = transport

        def datagram_received(self, data, address):
            received.append(data)
            for message in (b"invalid", b'{"AlpacaPort":12345}', b'{"AlpacaPort":12345}'):
                self.transport.sendto(message, address)

    transport, _ = await asyncio.get_running_loop().create_datagram_endpoint(
        Server, local_addr=("127.0.0.1", 0)
    )
    try:
        port = transport.get_extra_info("sockname")[1]
        servers = await discover(duration=0.05, broadcast="127.0.0.1", port=port)
    finally:
        transport.close()
    assert received == [b"alpacadiscovery1"]
    assert [server.url for server in servers] == ["http://127.0.0.1:12345"]
