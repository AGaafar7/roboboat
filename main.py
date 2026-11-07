import argparse
import signal
import subprocess
import sys
import time
from collections import deque

import cv2

from perception.vision_pipeline import VisionPipeline
from navigation.gate_navigation import GateNavigator
from navigation.obstacle_avoidance import ObstacleAvoidance
from navigation.safety_supervisor import SafetySupervisor
from navigation.command import NavigationCommand
from communication.esp32_serial import ESP32Communication
from missions.mission_manager import MissionManager, BADGE_TASKS
from gcs.bridge_server import GCSBridge

from config import (
    CAMERA_FRONT_INDEX, CAMERA_SECONDARY_INDEX,
    CAMERA_WIDTH, CAMERA_HEIGHT,
    SERIAL_PORT, SERIAL_BAUDRATE,
    SERIAL_HANDSHAKE_TIMEOUT_S,
    ARM_RETRIES, ARM_RETRY_DELAY_S,
    DEFAULT_TIER, CAPABILITY_TIERS,
    PROOF_OF_READINESS,
)

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


def verify_proof_of_readiness():
    missing = [k for k, v in PROOF_OF_READINESS.items() if not v]
    if missing:
        print(f"[Readiness] MISSING: {missing}")
        return False
    print("[Readiness] Kill switch, RC, tow harness, shrouds OK")
    return True


def kill_stale_bridge():
    """Kill any leftover bridge_server from a crashed prior run."""
    if sys.platform != "linux":
        return
    try:
        subprocess.run(
            ["pkill", "-f", "gcs.bridge_server"],
            check=False, timeout=1.0,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


# --------------------------------------------------
# ESP32 monitor
# --------------------------------------------------
class Esp32Monitor:
    """
    Single owner of esp32.read_telemetry(). Every frame goes through
    here so no code path can silently swallow a status message.
    Local `armed` / `estop` are DERIVED from the ESP32's own status,
    eliminating drift between the two sides.
    """

    # Statuses that force the boat into a known state
    _ARMED_STATUSES = {"armed"}
    _DISARMED_STATUSES = {"disarmed", "command_timeout",
                          "emergency_stop", "ready_disarmed"}

    def __init__(self, esp32, bridge):
        self.esp32 = esp32
        self.bridge = bridge
        self.armed = False
        self.estop = False
        self.last_status = None
        self.last_reason = None
        self._frames_seen = 0

    def drain(self, max_frames=8):
        """Read at most max_frames telemetry frames; apply state mirrors."""
        for _ in range(max_frames):
            tel = self.esp32.read_telemetry()
            if tel is None:
                break
            self._apply(tel)

    def _apply(self, tel):
        self._frames_seen += 1
        status = tel.get("status")
        reason = tel.get("reason")
        if status is None:
            # Not a status frame (e.g. an ACK without status)
            return

        self.last_status = status
        self.last_reason = reason

        # Push every status frame to the UI exactly once
        self.bridge.push_event({
            "event": "esp32_status",
            "status": status,
            "reason": reason,
        })

        # Derive local state from the ESP32's own state
        if status in self._ARMED_STATUSES:
            self.armed = True
        elif status in self._DISARMED_STATUSES:
            self.armed = False
        if status == "emergency_stop":
            self.estop = True
        elif status in ("disarmed", "faults_cleared", "armed",
                        "command_timeout"):
            self.estop = False

    def await_status(self, wanted, timeout_s=0.5):
        """
        Block until a frame with status == wanted arrives, or timeout.
        Returns True if the wanted status was seen.
        """
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            tel = self.esp32.read_telemetry()
            if tel is not None:
                self._apply(tel)
                if self.last_status == wanted:
                    return True
            time.sleep(0.02)
        return False

    def request_arm(self, retries, delay,
                    cancel_event=lambda: False):
        """
        Retry the arm write and confirm the ESP32 reports 'armed'.
        Returns True only on confirmed arm.
        """
        for attempt in range(1, retries + 1):
            if cancel_event():
                self.bridge.push_event({"event": "arm_aborted",
                                        "reason": "cancel_event"})
                return False

            if not self.esp32.arm():
                self.bridge.push_event({
                    "event": "esp32_write_failed",
                    "command": "arm", "attempt": attempt,
                })
                time.sleep(delay)
                continue

            if self.await_status("armed", timeout_s=0.5):
                return True
            if self.last_status == "arm_rejected":
                return False

            print(f"[Arm] attempt {attempt}: wrote OK, no ack "
                  f"(last_status={self.last_status})")
            time.sleep(delay)
        return False

    def request_disarm(self, timeout_s=0.5):
        if not self.esp32.disarm():
            self.bridge.push_event({"event": "esp32_write_failed",
                                    "command": "disarm"})
            return False
        return self.await_status("disarmed", timeout_s=timeout_s)

    def request_clear_faults(self, timeout_s=0.5):
        if not self.esp32.clear_faults():
            self.bridge.push_event({"event": "esp32_write_failed",
                                    "command": "clear_faults"})
            return False
        return self.await_status("faults_cleared", timeout_s=timeout_s)


# --------------------------------------------------
# Main
# --------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--badge", choices=list(BADGE_TASKS.keys()), default=None,
        help="Mission Badge to run at startup (also GCS-selectable)")
    parser.add_argument(
        "--tier", choices=CAPABILITY_TIERS, default=DEFAULT_TIER)
    parser.add_argument("--no-display", action="store_true")
    parser.add_argument("--gcs-port", type=int, default=8765)
    parser.add_argument(
        "--esp32-port", type=str, default=None,
        help="Override SERIAL_PORT from config.py")
    parser.add_argument("--skip-readiness", action="store_true")
    parser.add_argument(
        "--fps-log", action="store_true",
        help="Print a control-loop health line every 5 seconds")
    args = parser.parse_args()

    esp32_port = args.esp32_port or SERIAL_PORT

    if not args.skip_readiness and not verify_proof_of_readiness():
        print("[Readiness] Aborting. Pass --skip-readiness for bench testing.")
        return

    kill_stale_bridge()

    camera_1 = camera_2 = None
    esp32 = None
    monitor = None

    # Start the bridge FIRST so any startup failure is visible in the UI
    bridge = GCSBridge(port=args.gcs_port)
    bridge.start()
    time.sleep(0.2)

    mission_manager = MissionManager()
    vision          = VisionPipeline()
    gate_navigator  = GateNavigator()
    obstacle_avoid  = ObstacleAvoidance()
    safety          = SafetySupervisor()

    active_badge = args.badge
    active_tier  = args.tier

    shutdown_requested = False

    def _stop_handler(signum, frame):
        nonlocal shutdown_requested
        shutdown_requested = True

    signal.signal(signal.SIGINT,  _stop_handler)
    signal.signal(signal.SIGTERM, _stop_handler)

    try:
        print("Initializing RoboBoat 2027 system...")

        # --- Cameras ---
        try:
            camera_1 = initialize_camera(CAMERA_FRONT_INDEX)
            bridge.push_event({"event": "camera_ready",
                               "camera": "front",
                               "index": CAMERA_FRONT_INDEX})
        except RuntimeError as e:
            print(f"[Cam] {e}")
            bridge.push_event({"event": "camera_failed",
                               "camera": "front", "message": str(e)})

        try:
            camera_2 = initialize_camera(CAMERA_SECONDARY_INDEX)
            bridge.push_event({"event": "camera_ready",
                               "camera": "secondary",
                               "index": CAMERA_SECONDARY_INDEX})
        except RuntimeError as e:
            print(f"[Cam] {e}")
            bridge.push_event({"event": "camera_failed",
                               "camera": "secondary", "message": str(e)})

        # --- ESP32 ---
        esp32 = ESP32Communication(esp32_port, SERIAL_BAUDRATE)
        if not esp32.connect(handshake_timeout=SERIAL_HANDSHAKE_TIMEOUT_S):
            msg = (
                f"ESP32 handshake failed on {esp32_port}. "
                f"Check `ls -l /dev/ttyUSB* /dev/ttyACM*` "
                f"and your dialout group."
            )
            bridge.push_event({"event": "esp32_connect_failed",
                               "port": esp32_port,
                               "message": msg})
            raise RuntimeError(msg)
        bridge.push_event({"event": "esp32_connected",
                           "port": esp32_port})

        monitor = Esp32Monitor(esp32, bridge)
        monitor.drain()  # absorb the ready_disarmed banner

        # --- Optional boot-time badge ---
        if active_badge:
            try:
                mission_manager.start_badge(active_badge, active_tier)
                bridge.push_event({"event": "badge_started",
                                   "badge": active_badge,
                                   "tier": active_tier,
                                   "source": "boot"})
            except Exception as e:
                print(f"[Badge] boot start failed: {e}")
                bridge.push_event({"event": "badge_error",
                                   "reason": str(e),
                                   "source": "boot"})
                active_badge = None

        print("Control loop running. Awaiting GCS arm command...")
        bridge.push_event({"event": "control_loop_ready"})

        period = 1.0 / CONTROL_RATE_HZ
        loop_times = deque(maxlen=20)
        consecutive_camera_failures = 0
        last_fps_print = time.monotonic()

        while not shutdown_requested:
            t0 = time.monotonic()

            # ==========================================
            # 1. GCS COMMANDS
            # ==========================================
            cmd = bridge.poll_command()
            while cmd is not None:
                try:
                    if cmd.kind == "arm":
                        if monitor.estop:
                            # Clear latched E-stop before arming
                            monitor.request_clear_faults()
                        ok = monitor.request_arm(
                            ARM_RETRIES, ARM_RETRY_DELAY_S,
                            cancel_event=lambda: monitor.estop,
                        )
                        bridge.push_event({
                            "event": "armed" if ok else "arm_failed",
                            "reason": None if ok else (
                                monitor.last_reason or "no_ack"),
                        })

                    elif cmd.kind == "disarm":
                        monitor.request_disarm()
                        bridge.push_event({"event": "disarmed"})

                    elif cmd.kind == "estop":
                        esp32.emergency_stop()
                        safety.emergency_stop()
                        bridge.push_event({"event": "emergency_stop"})

                    elif cmd.kind == "clear_faults":
                        safety.reset()
                        monitor.request_clear_faults()
                        bridge.push_event({"event": "faults_cleared"})

                    elif cmd.kind == "start_badge":
                        b = cmd.payload.get("badge")
                        t = cmd.payload.get("tier", DEFAULT_TIER)
                        if b in BADGE_TASKS and t in CAPABILITY_TIERS:
                            mission_manager.start_badge(b, t)
                            active_badge, active_tier = b, t
                            bridge.push_event({"event": "badge_started",
                                               "badge": b, "tier": t,
                                               "source": "gcs"})
                        else:
                            bridge.push_event({
                                "event": "badge_error",
                                "reason": f"unknown badge/tier {b}/{t}",
                            })

                    elif cmd.kind == "stop_badge":
                        mission_manager.stop()
                        active_badge = None
                        bridge.push_event({"event": "badge_stopped"})

                    else:
                        bridge.push_event({"event": "unknown_command",
                                           "command": cmd.kind})

                except Exception as e:
                    print(f"[Cmd] {cmd.kind} failed: {e}")
                    bridge.push_event({"event": "command_error",
                                       "command": cmd.kind,
                                       "message": str(e)})

                cmd = bridge.poll_command()

            # ==========================================
            # 2. ESP32 TELEMETRY  (single owner)
            # ==========================================
            monitor.drain()

            # ==========================================
            # 3. PERCEPTION
            # ==========================================
            dets1, dets2 = [], []
            frame_width = CAMERA_WIDTH
            f1 = f2 = None
            ok1 = ok2 = False

            if camera_1 is not None:
                ok1, f1 = camera_1.read()
                if ok1:
                    frame_width = f1.shape[1]
                    dets1 = vision.detect(f1)
                else:
                    consecutive_camera_failures += 1

            if camera_2 is not None:
                ok2, f2 = camera_2.read()
                if ok2:
                    dets2 = vision.detect(f2)
                else:
                    consecutive_camera_failures += 1

            if ok1 or ok2:
                consecutive_camera_failures = 0
            elif consecutive_camera_failures > 50:
                bridge.push_event({"event": "camera_lost"})
                consecutive_camera_failures = 0

            # ==========================================
            # 4. MISSION UPDATE
            # ==========================================
            active = mission_manager.active_task
            mission_inputs = {
                "detections": dets1,
                "camera_2_detections": dets2,
                "heading": 0.0,
                "position": None,
                "frame_width": frame_width,
                "time": time.time(),
                "entry_buoy": None,
                "exit_buoy_ahead": False,
                "start_green_detected": False,
                "target_buoy": None,
                "pinger_frequency_hz": None,
                "end_pinger_acquired": False,
                "marina_entered": False,
                "slips": [],
                "at_slip_approach": False,
                "docking_complete": False,
                "fire_extinguished": False,
                "flash_sequence": None,
                "delivery_complete": False,
                "aligned_for_delivery": False,
                "coprolast_detections": [],
                "robo_command_assignment": None,
                "robo_command_rally_point": None,
                "robo_command_badge": None,
                "partner_ready": False,
                "rally_complete": False,
                "badge_complete": False,
            }

            result = None
            if active is not None:
                try:
                    result = mission_manager.update(mission_inputs)
                except Exception as e:
                    print(f"[Mission] update failed: {e}")
                    bridge.push_event({"event": "mission_error",
                                       "message": str(e)})
                    mission_manager.stop()
                    active_badge = None
                    result = None

                if result and result.status == "completed":
                    bridge.push_event({
                        "event": "task_completed",
                        "badge": mission_manager.badge,
                        "message": result.message,
                    })
                    if mission_manager.active_task is None:
                        bridge.push_event({"event": "badge_completed",
                                           "badge": mission_manager.badge})
                        active_badge = None

            command = result.command if result else NavigationCommand()

            # ==========================================
            # 5. OBSTACLE AVOIDANCE
            # ==========================================
            if active is not None and active.__class__.__name__ in (
                "SafePassageTask", "EmergencySprintTask"
            ):
                try:
                    command, obstacles = obstacle_avoid.apply(command, dets1)
                    if obstacles:
                        bridge.push_event({"event": "obstacle_avoided",
                                           "count": len(obstacles)})
                except Exception as e:
                    print(f"[Avoid] {e}")

            # ==========================================
            # 6. SAFETY + ARM GATE + SEND
            # ==========================================
            command = safety.filter_command(command)
            if not monitor.armed or monitor.estop:
                command = NavigationCommand()

            if not esp32.send_command(command.surge, command.yaw):
                bridge.push_event({"event": "esp32_write_failed",
                                   "command": "command"})

            # ==========================================
            # 7. TELEMETRY TO GCS
            # ==========================================
            loop_times.append(time.monotonic() - t0)
            fps = round(1.0 / max(0.001,
                       sum(loop_times) / len(loop_times)), 1)
            bridge.publish_telemetry({
                "armed": monitor.armed,
                "estop": monitor.estop,
                "badge": mission_manager.badge,
                "tier": mission_manager.tier,
                "task": (mission_manager.active_task.__class__.__name__
                         if mission_manager.active_task else "idle"),
                "surge": command.surge,
                "yaw": command.yaw,
                "detections": len(dets1),
                "fps": fps,
                "esp32_last_status": monitor.last_status,
            })

            if args.fps_log and time.monotonic() - last_fps_print > 5.0:
                last_fps_print = time.monotonic()
                task_name = (mission_manager.active_task.__class__.__name__
                             if mission_manager.active_task else "idle")
                print(f"[Loop] fps={fps} armed={monitor.armed} "
                      f"estop={monitor.estop} task={task_name} "
                      f"esp32={monitor.last_status}")

            # ==========================================
            # 8. DISPLAY
            # ==========================================
            if not args.no_display and ok1:
                try:
                    cv2.imshow("Camera 1", vision.draw(f1, dets1))
                    if ok2:
                        cv2.imshow("Camera 2", f2)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        shutdown_requested = True
                except cv2.error as e:
                    print(f"[Display] {e}")
                    args.no_display = True

            elapsed = time.monotonic() - t0
            time.sleep(max(0.0, period - elapsed))

    except KeyboardInterrupt:
        print("Interrupted.")
    except Exception as e:
        print(f"System error: {e}")
        if bridge is not None:
            bridge.push_event({"event": "system_error",
                               "message": str(e)})
    finally:
        print("Shutting down...")
        if esp32:
            # Shutdown sequence: E-stop first so the boat stops even if
            # disarm hangs, then disarm, then close.
            print("[Shutdown] ESP32 emergency stop...")
            try:
                esp32.emergency_stop()
            except Exception as e:
                print(f"[Shutdown] e-stop error: {e}")
            time.sleep(0.15)
            print("[Shutdown] ESP32 disarm...")
            try:
                esp32.disarm()
            except Exception as e:
                print(f"[Shutdown] disarm error: {e}")
            time.sleep(0.15)
            try:
                esp32.close()
            except Exception as e:
                print(f"[Shutdown] close error: {e}")
        if camera_1:
            try: camera_1.release()
            except Exception as e: print(f"[Cam] release: {e}")
        if camera_2:
            try: camera_2.release()
            except Exception as e: print(f"[Cam] release: {e}")
        if not args.no_display:
            try:
                cv2.destroyAllWindows()
            except Exception:
                pass
        try:
            bridge.stop()
        except Exception as e:
            print(f"[GCS] stop error: {e}")
        print("Done.")


if __name__ == "__main__":
    main()