import argparse
import math
import time
from collections import deque

import cv2
import numpy as np

from perception.vision_pipeline import VisionPipeline
from navigation.gate_navigation import GateNavigator
from navigation.obstacle_avoidance import ObstacleAvoidance
from navigation.safety_supervisor import SafetySupervisor
from navigation.command import NavigationCommand
from communication.esp32_serial import ESP32Communication
from missions.mission_manager import MissionManager
from gcs.bridge_server import GCSBridge

# --------------------------------------------------
# Config
# --------------------------------------------------
CAMERA_1_INDEX = 0
CAMERA_2_INDEX = 1
CAMERA_WIDTH  = 640
CAMERA_HEIGHT = 480
SERIAL_PORT   = "/dev/ttyUSB0"
SERIAL_BAUDRATE = 115200
CONTROL_RATE_HZ = 10


# --------------------------------------------------
# Helpers
# --------------------------------------------------
def initialize_camera(index):
    cam = cv2.VideoCapture(index)
    cam.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
    cam.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
    if not cam.isOpened():
        raise RuntimeError(f"Cannot open camera {index}")
    return cam


class GateTracker:
    """
    Turns per-frame red/green detections into:
      - gate_detected
      - gate_entry       (boat between buoys)
      - gate_passed      (boat has moved past the pair)
      - exit_gate_detected / exit_gate_passed
    """

    PASS_AREA_FACTOR = 2.6     # area growth ratio that means "passed"
    PASS_FRAMES = 3

    def __init__(self):
        self.prev_pair_area = None
        self.pass_streak = 0

    def _pair(self, detections):
        reds = [d for d in detections if d["color"] == "red"]
        greens = [d for d in detections if d["color"] == "green"]
        if not reds or not greens:
            return None
        r = max(reds, key=lambda d: d["area"])
        g = max(greens, key=lambda d: d["area"])
        return r, g

    def update(self, detections, frame_width):
        pair = self._pair(detections)
        if pair is None:
            self.prev_pair_area = None
            self.pass_streak = 0
            return {"gate_detected": False, "gate_entry": False,
                    "gate_passed": False}

        r, g = pair
        total = r["area"] + g["area"]

        span = abs(r["center"][0] - g["center"][0])
        gate_entry = (
            span > frame_width * 0.55
            and abs((r["center"][0] + g["center"][0]) / 2
                    - frame_width / 2) < frame_width * 0.2
        )

        gate_passed = False
        if self.prev_pair_area is not None and gate_entry:
            if total > self.prev_pair_area * self.PASS_AREA_FACTOR:
                self.pass_streak += 1
                if self.pass_streak >= self.PASS_FRAMES:
                    gate_passed = True
            else:
                self.pass_streak = 0

        self.prev_pair_area = total

        return {
            "gate_detected": True,
            "gate_entry": gate_entry,
            "gate_passed": gate_passed,
        }


class AudioAlertDetector:
    """
    Minimal fidgetting-free stub for the Harbor Alert task.
    Replace with your real .wav FFT pipeline. Emits an alert dict when
    a matching blast pattern is confirmed.
    """

    def __init__(self, nominal_hz=(600, 800, 1000), tolerance=0.05):
        self.nominal = nominal_hz
        self.tolerance = tolerance
        self.last_alert = None

    def poll(self):
        # STUB — a real implementation reads from an audio device,
        # computes FFT, counts blasts, and returns:
        #   {"blast_count": 1, "frequency": 800.0,
        #    "detection_time": time.time()}
        return self.last_alert

    def inject_test_alert(self, blast_count, frequency):
        self.last_alert = {
            "blast_count": blast_count,
            "frequency": frequency,
            "detection_time": time.time(),
        }


# --------------------------------------------------
# Main
# --------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mission", type=int, choices=[1,2,3,4,5,6],
                        default=None,
                        help="Initial mission (can be started from GCS)")
    parser.add_argument("--no-display", action="store_true")
    parser.add_argument("--gcs-port", type=int, default=8765)
    args = parser.parse_args()

    camera_1 = camera_2 = None
    esp32 = None
    bridge = GCSBridge(port=args.gcs_port)

    mission_manager = MissionManager()
    vision           = VisionPipeline()
    gate_navigator   = GateNavigator()
    obstacle_avoid   = ObstacleAvoidance()
    safety           = SafetySupervisor()
    gate_tracker     = GateTracker()
    audio            = AudioAlertDetector()

    try:
        print("Initializing RoboBoat system...")

        camera_1 = initialize_camera(CAMERA_1_INDEX)
        camera_2 = initialize_camera(CAMERA_2_INDEX)

        esp32 = ESP32Communication(SERIAL_PORT, SERIAL_BAUDRATE)
        if not esp32.connect():
            raise RuntimeError("ESP32 connection failed")

        bridge.start()

        if args.mission is not None:
            mission_manager.start_mission(args.mission)

        print("Control loop running. Awaiting GCS arm command…")

        armed = False
        estop = False
        period = 1.0 / CONTROL_RATE_HZ
        loop_times = deque(maxlen=20)

        while True:
            t0 = time.monotonic()

            # ---------- GCS commands ----------
            cmd = bridge.poll_command()
            while cmd is not None:
                if cmd.kind == "arm" and not estop:
                    armed = True
                    esp32.arm()
                    bridge.push_event({"event": "armed"})
                elif cmd.kind == "disarm":
                    armed = False
                    esp32.disarm()
                    bridge.push_event({"event": "disarmed"})
                elif cmd.kind == "estop":
                    estop = True
                    armed = False
                    esp32.emergency_stop()
                    safety.emergency_stop()
                    bridge.push_event({"event": "emergency_stop"})
                elif cmd.kind == "clear_faults":
                    estop = False
                    safety.reset()
                    esp32.send({"type": "clear_faults"})
                    bridge.push_event({"event": "faults_cleared"})
                elif cmd.kind == "start_mission":
                    n = int(cmd.payload.get("mission", 0))
                    if 1 <= n <= 6:
                        mission_manager.start_mission(n)
                        bridge.push_event({"event": "mission_started",
                                           "mission": n})
                elif cmd.kind == "stop_mission":
                    mission_manager.stop()
                    bridge.push_event({"event": "mission_stopped"})
                cmd = bridge.poll_command()

            # ---------- Perception ----------
            ok1, f1 = camera_1.read()
            ok2, f2 = camera_2.read()
            if not ok1 or not ok2:
                raise RuntimeError("Camera frame acquisition failed")

            dets1 = vision.detect(f1)
            dets2 = vision.detect(f2)

            gate_state = gate_tracker.update(dets1, f1.shape[1])

            yellow_target = None
            for d in dets1:
                if d["color"] == "yellow":
                    yellow_target = {
                        "position": d["center"],
                        "indicator_color": self._infer_indicator(dets1),
                    }
                    break

            audio_alert = audio.poll()

            mission_inputs = {
                "detections": dets1,
                "camera_2_detections": dets2,
                "heading": 0.0,          # TODO: wire from IMU/GPS
                "position": None,
                "time": time.time(),

                # Gate tracking
                "gate_detected": gate_state["gate_detected"],
                "gate_entry": gate_state["gate_entry"],
                "gate_passed": gate_state["gate_passed"],
                "exit_gate_detected": False,
                "exit_gate_passed": False,

                # Channel / debris
                "channel_entered": False,
                "debris_field_entered": False,
                "debris_field_exit_complete": False,
                "channel_exit_complete": False,

                # Circle helpers
                "circle_complete": False,
                "survivor_circle_complete": False,

                # Sprint
                "yellow_target": yellow_target,
                "gate_exit_complete": False,

                # Marina
                "marina_entered": False,
                "slips": [],
                "at_slip_approach": False,
                "docking_complete": False,

                # Supply
                "target": None,
                "aligned_for_delivery": False,
                "delivery_complete": False,

                # Harbor alert
                "audio_alert": audio_alert,
                "response_complete": False,
            }

            # ---------- Mission update ----------
            result = None
            if mission_manager.active_mission is not None:
                result = mission_manager.update(mission_inputs)
                if result and result.status == "completed":
                    bridge.push_event({
                        "event": "mission_completed",
                        "message": result.message,
                    })
                    mission_manager.stop()
                    result = None

            command = result.command if result else NavigationCommand()

            # ---------- Mission-specific navigation ----------
            active = mission_manager.active_mission
            if active is not None:
                if args.mission == 1 and active.state in (
                    "APPROACHING_GATE", "CROSSING_ENTRY"
                ):
                    command = gate_navigator.calculate_command(
                        dets1, f1.shape[1]
                    )
                elif args.mission == 2 and active.state in (
                    "TRANSIT_CHANNEL", "SCANNING_DEBRIS", "RETURNING"
                ):
                    command, obstacles = obstacle_avoid.apply(
                        command, dets1
                    )
                    if obstacles:
                        bridge.push_event({
                            "event": "obstacle_avoided",
                            "count": len(obstacles),
                        })

            # ---------- Safety + arming gate ----------
            command = safety.filter_command(command)
            if not armed or estop:
                command = NavigationCommand()

            esp32.send_command(command.surge, command.yaw)

            # ---------- Telemetry ----------
            loop_times.append(time.monotonic() - t0)
            bridge.publish_telemetry({
                "armed": armed,
                "estop": estop,
                "mission": args.mission,
                "mission_state": active.state if active else "idle",
                "surge": command.surge,
                "yaw": command.yaw,
                "gate_detected": gate_state["gate_detected"],
                "detections": len(dets1),
                "fps": round(1.0 / max(0.001, sum(loop_times) / len(loop_times)), 1),
            })

            # ---------- Display ----------
            if not args.no_display:
                cv2.imshow("Camera 1",
                           vision.draw(f1, dets1))
                cv2.imshow("Camera 2", f2)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

            elapsed = time.monotonic() - t0
            time.sleep(max(0.0, period - elapsed))

    except KeyboardInterrupt:
        print("Interrupted.")
    except Exception as e:
        print(f"System error: {e}")
    finally:
        print("Shutting down...")
        bridge.stop()
        if esp32:
            esp32.emergency_stop()
            time.sleep(0.1)
            esp32.disarm()
            esp32.close()
        if camera_1: camera_1.release()
        if camera_2: camera_2.release()
        cv2.destroyAllWindows()
        print("Done.")


if __name__ == "__main__":
    main()