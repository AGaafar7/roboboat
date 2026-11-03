import json
import time
import threading

import serial


class ESP32Communication:

    def __init__(
        self,
        port="/dev/ttyUSB0",
        baudrate=115200,
        timeout=0.2
    ):

        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout

        self.serial = None
        self.lock = threading.Lock()

    def connect(self):

        try:
            self.serial = serial.Serial(
                self.port,
                self.baudrate,
                timeout=self.timeout,
                write_timeout=self.timeout
            )

            time.sleep(2)

            print(f"Connected to ESP32 on {self.port}")
            return True

        except serial.SerialException as error:

            print(f"ESP32 connection failed: {error}")
            return False

    def send(self, data):

        if self.serial is None or not self.serial.is_open:
            return False

        try:
            message = json.dumps(data) + "\n"

            with self.lock:
                self.serial.write(message.encode("utf-8"))

            return True

        except (serial.SerialException, OSError) as error:

            print(f"ESP32 send error: {error}")
            return False

    def send_command(self, surge, yaw):

        return self.send({
            "type": "command",
            "surge": float(surge),
            "yaw": float(yaw),
            "timestamp": time.monotonic()
        })

    def arm(self):
        return self.send({"type": "arm"})

    def disarm(self):
        return self.send({"type": "disarm"})

    def emergency_stop(self):
        return self.send({"type": "emergency_stop"})

    def read_telemetry(self):

        if self.serial is None or not self.serial.is_open:
            return None

        try:

            with self.lock:
                line = self.serial.readline().decode(
                    "utf-8", errors="ignore"
                ).strip()

            if not line:
                return None

            return json.loads(line)

        except (serial.SerialException, ValueError, OSError) as error:

            print(f"ESP32 telemetry error: {error}")
            return None

    def close(self):

        if self.serial and self.serial.is_open:

            self.disarm()
            time.sleep(0.1)
            self.serial.close()