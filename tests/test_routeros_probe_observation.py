"""One-way leakage must not be confused with a complete blocked probe."""

import asyncio

import pytest

from tests.routeros.ipv6_probe import forwarded_probe6
from tests.routeros.packets import (
    CLIENT_MAC,
    ROUTER_LAN_MAC,
    ROUTER_SERVER_MAC,
    SERVER_MAC,
    forwarded_probe,
)


class EmulatedRoute:
    """Pure queue-based wire relay; never a router correctness substitute."""

    def __init__(self, *, return_allowed):
        self.lan = Endpoint()
        self.server = Endpoint()
        self.lan.other, self.server.other = self.server, self.lan
        self.lan.rewrite = SERVER_MAC + ROUTER_SERVER_MAC
        self.server.rewrite = CLIENT_MAC + ROUTER_LAN_MAC
        self.server.allowed = return_allowed


class Endpoint:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.allowed = True
        self.active = 0

    async def send(self, frame):
        if self.allowed:
            await self.other.queue.put(self.rewrite + frame[12:])

    async def receive(self):
        self.active += 1
        try:
            return await self.queue.get()
        finally:
            self.active -= 1


@pytest.mark.asyncio
@pytest.mark.parametrize("version", [4, 6])
@pytest.mark.parametrize("return_allowed", [True, False])
async def test_each_direction_is_reported_and_pending_receivers_are_cancelled(
    version, return_allowed
):
    route = EmulatedRoute(return_allowed=return_allowed)
    observed = {"stale": True, "returned": True}
    if version == 4:
        result = await forwarded_probe(
            route.lan, route.server, "198.51.100.10", observations=observed
        )
    else:
        result = await forwarded_probe6(route.lan, route.server, observations=observed)
    assert result is return_allowed
    assert observed == {"forwarded": True, "returned": return_allowed}
    assert route.lan.active == route.server.active == 0
