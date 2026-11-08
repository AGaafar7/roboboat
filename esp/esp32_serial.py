import json
import time
import threading

import serial


class ESP32Communication:

    def __init__(self, port="/dev/ttyUSB0", baudrate=115200, timeout=0.2):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout

        self.serial = None
        self.lock = threading.Lock()
        self.last_status = None

    # --------------------------------------------------
    # Connection + handshake
    # --------------------------------------------------
    def connect(self, handshake_timeout=5.0):
        """
        Open the port and wait for the ESP32's
        {"type":"status","status":"ready_disarmed"} banner.
        Returns True only if the handshake succeeds.
        """
        try:
            self.serial = serial.Serial(
                self.port,
                self.baudrate,
                timeout=self.timeout,
                write_timeout=self.timeout,
            )
        except serial.SerialException as error:
            print(f"[ESP32] open failed on {self.port}: {error}")
            self.serial = None
            return False

        deadline = time.monotonic() + handshake_timeout
        while time.monotonic() < deadline:
            line = self._readline()
            if line is None:
                time.sleep(0.05)
                continue
            if line.get("type") == "status" and line.get("status") == "ready_disarmed":
                self.last_status = "ready_disarmed"
                print(f"[ESP32] handshake OK on {self.port}")
                return True

        print(f"[ESP32] no ready banner within {handshake_timeout:.1f}s")
        try:
            self.serial.close()
        except Exception:
            pass
        self.serial = None
        return False

    # --------------------------------------------------
    # Low-level I/O
    # --------------------------------------------------
    def _readline(self):
        if self.serial is None or not self.serial.is_open:
            return None
        try:
            with self.lock:
                raw = self.serial.readline()
            if not raw:
                return None
            text = raw.decode("utf-8", errors="ignore").strip()
            if not text:
                return None
            return json.loads(text)
        except (serial.SerialException, OSError, ValueError) as error:
            print(f"[ESP32] read error: {error}")
            return None

    def send(self, data):
        if self.serial is None or not self.serial.is_open:
            print("[ESP32] send skipped: port closed")
            return False
        try:
            message = json.dumps(data) + "\n"
            with self.lock:
                self.serial.write(message.encode("utf-8"))
                self.serial.flush()
            return True
        except (serial.SerialException, OSError) as error:
            print(f"[ESP32] send error: {error}")
            return False

    # --------------------------------------------------
    # Public command API
    # --------------------------------------------------
    def send_command(self, surge, yaw):
        return self.send({
            "type": "command",
            "surge": float(surge),
            "yaw": float(yaw),
            "timestamp": time.monotonic(),
        })

    def arm(self):
        return self.send({"type": "arm"})

    def disarm(self):
        return self.send({"type": "disarm"})

    def emergency_stop(self):
        return self.send({"type": "emergency_stop"})

    def clear_faults(self):
        return self.send({"type": "clear_faults"})

    # --------------------------------------------------
    # Telemetry
    # --------------------------------------------------
    def read_telemetry(self):
        parsed = self._readline()
        if parsed is None:
            return None
        if parsed.get("type") == "status":
            self.last_status = parsed.get("status")
        return parsed

    # --------------------------------------------------
    # Shutdown
    # --------------------------------------------------
    def close(self):
        if self.serial and self.serial.is_open:
            try:
                self.disarm()
                time.sleep(0.1)
            except Exception:
                pass
            try:
                self.serial.close()
            except Exception:
                pass
        self.serial = None
