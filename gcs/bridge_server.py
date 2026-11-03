"""
GCS Bridge: WebSocket server that mediates between the browser UI
and the RoboBoat control loop (main.py).

Run alongside main.py. Control loop publishes telemetry and polls
pending commands through a shared thread-safe queue.
"""

import asyncio
import json
import threading
import time
from dataclasses import dataclass, field
from queue import Queue, Empty
from typing import Optional

try:
    import websockets
except ImportError:
    raise RuntimeError("pip install websockets")


@dataclass
class GCSCommand:
    """A command issued from the GCS UI."""
    kind: str                     # "arm" | "disarm" | "estop" | "start_mission" | "stop_mission" | "clear_faults"
    payload: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class GCSBridge:
    """
    Thread-safe bridge. The control loop calls:
      - publish_telemetry(dict)  -> pushes to any connected UI
      - poll_command() -> Optional[GCSCommand]
    """

    def __init__(self, host="0.0.0.0", port=8765):
        self.host = host
        self.port = port

        self._clients = set()
        self._telemetry_lock = threading.Lock()
        self._latest_telemetry: dict = {}

        self._incoming: "Queue[GCSCommand]" = Queue()

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._server = None
        self._stop_event = threading.Event()

    # ---------- Control-loop-facing API ----------

    def publish_telemetry(self, telemetry: dict):
        with self._telemetry_lock:
            self._latest_telemetry = telemetry
            payload = json.dumps({"type": "telemetry", **telemetry})

        if self._loop is None:
            return

        asyncio.run_coroutine_threadsafe(
            self._broadcast(payload),
            self._loop,
        )

    def poll_command(self) -> Optional[GCSCommand]:
        try:
            return self._incoming.get_nowait()
        except Empty:
            return None

    def push_event(self, event: dict):
        """Push a one-off event (mission completed, alert, etc.)."""
        if self._loop is None:
            return
        payload = json.dumps({"type": "event", **event})
        asyncio.run_coroutine_threadsafe(self._broadcast(payload), self._loop)

    # ---------- Lifecycle ----------

    def start(self):
        self._thread = threading.Thread(
            target=self._run, name="GCSBridge", daemon=True
        )
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._loop is not None:
            asyncio.run_coroutine_threadsafe(
                self._shutdown(), self._loop
            )
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    # ---------- Async internals ----------

    async def _handler(self, websocket):
        self._clients.add(websocket)
        try:
            with self._telemetry_lock:
                if self._latest_telemetry:
                    await websocket.send(json.dumps({
                        "type": "telemetry",
                        **self._latest_telemetry,
                    }))

            async for raw in websocket:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": "invalid_json",
                    }))
                    continue

                await self._handle_message(websocket, msg)

        except websockets.ConnectionClosed:
            pass
        finally:
            self._clients.discard(websocket)

    async def _handle_message(self, websocket, msg):
        kind = msg.get("command")

        if kind in ("arm", "disarm", "estop",
                    "start_mission", "stop_mission",
                    "clear_faults"):
            self._incoming.put(GCSCommand(
                kind=kind,
                payload=msg.get("payload", {}),
            ))
            await websocket.send(json.dumps({
                "type": "ack",
                "command": kind,
            }))
        else:
            await websocket.send(json.dumps({
                "type": "error",
                "message": f"unknown_command: {kind}",
            }))

    async def _broadcast(self, payload: str):
        if not self._clients:
            return
        await asyncio.gather(
            *[self._safe_send(c, payload) for c in list(self._clients)],
            return_exceptions=True,
        )

    @staticmethod
    async def _safe_send(websocket, payload):
        try:
            await websocket.send(payload)
        except Exception:
            pass

    async def _shutdown(self):
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        for ws in list(self._clients):
            try:
                await ws.close()
            except Exception:
                pass

    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
        finally:
            self._loop.close()

    async def _serve(self):
        self._server = await websockets.serve(
            self._handler, self.host, self.port
        )
        print(f"[GCS] WebSocket bridge listening on "
              f"ws://{self.host}:{self.port}")
        while not self._stop_event.is_set():
            await asyncio.sleep(0.25)