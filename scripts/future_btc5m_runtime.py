"""Loopback clock push for the Chrome extension; no signals or trading controls."""

import asyncio
import json
import re
import time

from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed


async def start_runtime_server(address=("127.0.0.1", 8767)):
    if address[0] != "127.0.0.1":
        raise ValueError("RUNTIME_REQUIRES_LOOPBACK")

    def access(connection, request):
        host = f"127.0.0.1:{connection.local_address[1]}"
        if request.path != "/runtime" or request.headers.get_all("Host") != [host]:
            return connection.respond(403, "Runtime access refused\n")

    async def clocks(socket):
        try:
            while True:
                await socket.send(json.dumps({"type": "FUTURE_BTC5M_TICK", "serverTime": time.time()}))
                await asyncio.sleep(0.5)
        except ConnectionClosed:
            pass

    async def connected(socket):
        sender = asyncio.create_task(clocks(socket))
        try:
            # This channel is receive-only for the extension. It cannot change any state.
            async for _ in socket:
                await socket.close(code=1008, reason="Read-only clock channel")
                break
        finally:
            sender.cancel()
            await asyncio.gather(sender, return_exceptions=True)

    return await serve(connected, *address, origins=[re.compile(r"chrome-extension://[a-p]{32}")],
                       process_request=access, compression=None, max_size=1024, max_queue=1, close_timeout=2)
