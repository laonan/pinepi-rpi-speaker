#!/usr/bin/env python3
"""WebSocket subscription daemon.

Connects to the pinepi-broadcast-mid server, receives push messages,
stores them in the local message store, and speaks them via TTS when
play_now is set.

Credentials and server URL are read from /etc/pinepi-speaker/config.json.
"""

import asyncio
import json
import logging
import sys
import time

import websockets

from pinepi_speaker import config
from pinepi_speaker.messages import add_message
from pinepi_speaker.tts.registry import resolve_adapter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

HEARTBEAT_TIMEOUT = 60
RECONNECT_DELAY = 3
MAX_RECONNECT_DELAY = 60

# ---------------- WebSocket message handler ----------------

async def on_message(msg) -> dict | None:
    if isinstance(msg, bytes):
        logger.info("Received binary frame: %d bytes (ignored by speaker device)", len(msg))
        return None

    try:
        data = json.loads(msg)
    except json.JSONDecodeError:
        logger.warning("Invalid JSON received: %s", msg)
        return None

    if data.get("type") == "ping":
        return data

    event = data.get("event")
    if not event:
        logger.warning("Message missing 'event' field, ignored: %s", msg)
        return None

    title = event.get("title")
    content = event.get("content")
    if not title or not content:
        logger.warning("Message missing title/content in event, ignored: %s", msg)
        return None

    play_now = event.get("play_now", 0) == 1
    tts_type = event.get("tts_type")  # optional per-message TTS override

    add_message(title, content, play_now=play_now, tts_type=tts_type)
    return None

# ---------------- Main reconnect loop ----------------

async def listen() -> None:
    uri = config.wss_url()
    token = config.auth_token()
    device = config.device_name()

    if not token or not device:
        logger.error(
            "auth_token and device_name must be set in /etc/pinepi-speaker/config.json"
        )
        sys.exit(1)

    delay = RECONNECT_DELAY

    while True:
        try:
            async with websockets.connect(
                uri,
                ping_interval=None,
                ping_timeout=None,
                close_timeout=5,
            ) as ws:
                await ws.send(json.dumps({"token": token, "device": device}))
                logger.info("Connected to %s", uri)
                delay = RECONNECT_DELAY
                last_server_ping = time.monotonic()

                while True:
                    try:
                        raw = await asyncio.wait_for(
                            ws.recv(), timeout=HEARTBEAT_TIMEOUT
                        )
                    except asyncio.TimeoutError:
                        elapsed = time.monotonic() - last_server_ping
                        if elapsed > HEARTBEAT_TIMEOUT:
                            logger.warning(
                                "No server ping for %ds, reconnecting", int(elapsed)
                            )
                            break
                        continue

                    parsed = await on_message(raw)
                    if parsed and parsed.get("type") == "ping":
                        last_server_ping = time.monotonic()
                        try:
                            await ws.send(json.dumps({"type": "pong"}))
                        except Exception:
                            break

        except websockets.exceptions.ConnectionClosedError as e:
            logger.warning("Connection closed: %s", e)
        except Exception as e:
            logger.warning("Connection error: %s", e)

        logger.info("Reconnecting in %ds...", delay)
        await asyncio.sleep(delay)
        delay = min(delay * 2, MAX_RECONNECT_DELAY)


def main() -> None:
    resolve_adapter(None)  # warm up default adapter
    asyncio.run(listen())


if __name__ == "__main__":
    main()
