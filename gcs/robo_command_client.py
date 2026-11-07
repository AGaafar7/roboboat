"""
Thin wrapper around the RoboCommand WebSocket feed.
Decodes delivery / rally / badge assignments and queues them
for the control loop.
"""

import json
import threading
from queue import Queue, Empty
from typing import Optional

try:
    import websockets
    import asyncio
except ImportError:
    raise RuntimeError("pip install websockets")

from config import ROBOCOMMAND_WS_URL, ROBOCOMMAND_ENABLED


class RoboCommandClient:
    def __init__(self, url=ROBOCOMMAND_WS_URL):
        self.url = url
        self._queue: "Queue[dict]" = Queue()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self):
        if not ROBOCOMMAND_ENABLED:
            print("[RoboCommand] disabled by config")
            return
        self._thread = threading.Thread(
            target=self._run, name="RoboCommand", daemon=True)
        self._thread.start()

    def poll(self) -> Optional[dict]:
        try:
            return self._queue.get_nowait()
        except Empty:
            return None

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    # ---------- internals ----------
    def _run(self):
        asyncio.run(self._serve())

    async def _serve(self):
        try:
            async with websockets.connect(self.url) as ws:
                print(f"[RoboCommand] connected to {self.url}")
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    self._queue.put(msg)
        except Exception as e:
            print(f"[RoboCommand] connection error: {e}")