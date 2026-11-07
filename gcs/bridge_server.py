"""
GCS Bridge: WebSocket server that mediates between the browser UI
and the RoboBoat control loop (main.py).

Auto-start behaviour:
  - Importing this module does NOT start the server.
  - Calling .start() starts it (idempotent).
  - `python -m gcs.bridge_server` starts it standalone and keeps the
    process alive until Ctrl-C. Useful for bench-testing the UI
    without the full control loop.
"""

import asyncio
import json
import os
import threading
import time
from dataclasses import dataclass, field
from queue import Queue, Empty
from typing import Optional

try:
    import websockets
except ImportError:
    raise RuntimeError("pip install websockets")


DEFAULT_PORT = int(os.environ.get("ROBOBOAT_GCS_PORT", "8765"))


@dataclass
class GCSCommand:
    """A command issued from the GCS UI."""
    kind: str
    payload: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class GCSBridge:
    """
    Thread-safe bridge. The control loop calls:
      - publish_telemetry(dict)
      - poll_command() -> Optional[GCSCommand]
      - push_event(dict)
    """

    # Allowed command kinds. Anything else is rejected with an error
    # frame so the UI logs it.
    ALLOWED = {
        "arm", "disarm", "estop", "clear_faults",
        "start_badge", "stop_badge",
        # legacy aliases kept so an old UI still works
        "start_mission", "stop_mission",
    }

    def __init__(self, host="0.0.0.0", port=DEFAULT_PORT):
        self.host = host
        self.port = port

        self._clients = set()
        self._telemetry_lock = threading.Lock()
        self._latest_telemetry: dict = {}

        self._incoming: "Queue[GCSCommand]" = Queue()
        self._stop_event = threading.Event()

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._server = None
        self._started = False
        self._start_lock = threading.Lock()

    # ---------- Control-loop-facing API ----------

    def publish_telemetry(self, telemetry: dict):
        with self._telemetry_lock:
            self._latest_telemetry = dict(telemetry)
            payload = json.dumps({"type": "telemetry", **telemetry})

        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            asyncio.run_coroutine_threadsafe(self._broadcast(payload), loop)
        except RuntimeError:
            # Loop shutting down between the check and the call.
            pass

    def poll_command(self) -> Optional[GCSCommand]:
        try:
            return self._incoming.get_nowait()
        except Empty:
            return None

    def push_event(self, event: dict):
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        payload = json.dumps({"type": "event", **event})
        try:
            asyncio.run_coroutine_threadsafe(self._broadcast(payload), loop)
        except RuntimeError:
            pass

    # ---------- Lifecycle ----------

    def start(self):
        """Idempotent. Safe to call from main.py and from tests."""
        with self._start_lock:
            if self._started:
                return
            self._started = True
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run, name="GCSBridge", daemon=True
            )
            self._thread.start()

    def stop(self):
        with self._start_lock:
            if not self._started:
                return
            self._started = False

        self._stop_event.set()
        loop = self._loop
        if loop is not None and not loop.is_closed():
            try:
                asyncio.run_coroutine_threadsafe(self._shutdown(), loop)
            except RuntimeError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None

    # ---------- Async internals ----------

    async def _handler(self, websocket):
        self._clients.add(websocket)
        peer = getattr(websocket, "remote_address", ("?", 0))
        print(f"[GCS] client connected {peer[0]}:{peer[1]} "
              f"({len(self._clients)} total)")
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
        except Exception as e:
            print(f"[GCS] handler error: {e}")
        finally:
            self._clients.discard(websocket)
            print(f"[GCS] client disconnected ({len(self._clients)} left)")

    async def _handle_message(self, websocket, msg):
        kind = msg.get("command")
        if kind not in self.ALLOWED:
            await websocket.send(json.dumps({
                "type": "error",
                "message": f"unknown_command: {kind}",
            }))
            return

        # Normalise legacy aliases
        if kind == "start_mission":
            kind = "start_badge"
        elif kind == "stop_mission":
            kind = "stop_badge"

        self._incoming.put(GCSCommand(
            kind=kind,
            payload=msg.get("payload", {}),
        ))
        await websocket.send(json.dumps({
            "type": "ack",
            "command": kind,
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
            try:
                await self._server.wait_closed()
            except Exception:
                pass
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
        except OSError as e:
            # Port in use, permission denied, etc.
            print(f"[GCS] FATAL: cannot bind {self.host}:{self.port}: {e}")
            print("[GCS] Is another instance running? "
                  "Try: pkill -f bridge_server")
        except Exception as e:
            print(f"[GCS] bridge crashed: {e}")
        finally:
            try:
                self._loop.close()
            except Exception:
                pass
            self._loop = None

    async def _serve(self):
        self._server = await websockets.serve(
            self._handler, self.host, self.port
        )
        print(f"[GCS] WebSocket bridge listening on "
              f"ws://{self.host}:{self.port}")
        while not self._stop_event.is_set():
            await asyncio.sleep(0.25)


# --------------------------------------------------
# Standalone entry point
# --------------------------------------------------
if __name__ == "__main__":
    import sys
    bridge = GCSBridge(port=DEFAULT_PORT)
    bridge.start()
    print(f"[GCS] standalone mode. Ctrl-C to quit. "
          f"Open the UI at http://<pi-ip>:{DEFAULT_PORT}/ "
          f"(or a local index.html pointing at ws://<pi-ip>:{DEFAULT_PORT})")
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[GCS] stopping...")
        bridge.stop()
        print("[GCS] stopped.")
        sys.exit(0)