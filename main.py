import argparse
import time
import cv2

from perception.vision_pipeline import VisionPipeline

from navigation.gate_navigation import GateNavigator
from navigation.obstacle_avoidance import ObstacleAvoidance
from navigation.safety_supervisor import SafetySupervisor
from navigation.command import NavigationCommand

from communication.esp32_serial import ESP32Communication

from missions.mission_manager import MissionManager


# --------------------------------------------------
# Configuration
# --------------------------------------------------

CAMERA_1_INDEX = 0
CAMERA_2_INDEX = 1

CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480

SERIAL_PORT = "/dev/ttyUSB0"
SERIAL_BAUDRATE = 115200

CONTROL_RATE_HZ = 10


# --------------------------------------------------
# Camera initialization
# --------------------------------------------------

def initialize_camera(index):

    camera = cv2.VideoCapture(index)

    camera.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)

    if not camera.isOpened():

        raise RuntimeError(
            f"Cannot open camera {index}"
        )

    return camera


# --------------------------------------------------
# Main application
# --------------------------------------------------

def main():

    parser = argparse.ArgumentParser(
        description="RoboBoat 2026 Control System"
    )

    parser.add_argument(
        "--mission",
        type=int,
        choices=[1, 2, 3, 4, 5, 6],
        required=True
    )

    parser.add_argument(
        "--no-display",
        action="store_true"
    )

    args = parser.parse_args()

    camera_1 = None
    camera_2 = None
    esp32 = None

    mission_manager = MissionManager()

    vision = VisionPipeline()

    gate_navigator = GateNavigator()

    obstacle_avoidance = ObstacleAvoidance()

    safety = SafetySupervisor()

    try:

        print("Initializing RoboBoat system...")

        # 1. Initialize cameras.

        camera_1 = initialize_camera(CAMERA_1_INDEX)
        camera_2 = initialize_camera(CAMERA_2_INDEX)

        print("Both cameras initialized.")

        # 2. Connect to ESP32.

        esp32 = ESP32Communication(
            port=SERIAL_PORT,
            baudrate=SERIAL_BAUDRATE
        )

        if not esp32.connect():

            raise RuntimeError(
                "ESP32 connection failed"
            )

        print("ESP32 connected. Propulsion remains disarmed.")

        # 3. Start mission.

        mission_manager.start_mission(args.mission)

        print(f"Mission {args.mission} selected.")

        print("Starting control loop...")

        period = 1.0 / CONTROL_RATE_HZ

        while True:

            loop_start = time.monotonic()

            # --------------------------------------
            # Read cameras
            # --------------------------------------

            ret_1, frame_1 = camera_1.read()
            ret_2, frame_2 = camera_2.read()

            if not ret_1 or not ret_2:

                raise RuntimeError(
                    "Camera frame acquisition failed"
                )

            # --------------------------------------
            # Process camera images
            # --------------------------------------

            detections_1 = vision.detect(frame_1)
            detections_2 = vision.detect(frame_2)

            # For now, use camera 1 for navigation.
            # Camera 2 detections are retained separately.
            detections = detections_1

            red_detected = any(
                d["color"] == "red"
                for d in detections
            )

            green_detected = any(
                d["color"] == "green"
                for d in detections
            )

            gate_detected = (
                red_detected and green_detected
            )

            # --------------------------------------
            # Prepare mission inputs
            # --------------------------------------

            inputs = {
                "detections": detections,
                "camera_2_detections": detections_2,
                "gate_detected": gate_detected,
                "position": None,

                # These must come from validated
                # navigation or hardware modules.
                "gate_entry": False,
                "gate_passed": False,
                "return_complete": False,

                "channel_entered": False,
                "channel_exit_complete": False,
                "survivor_circle_complete": False,

                "circle_complete": False,
                "gate_exit_complete": False,

                "marina_entered": False,
                "docking_complete": False,

                "delivery_complete": False,
                "response_complete": False
            }

            # --------------------------------------
            # Update selected mission
            # --------------------------------------

            result = mission_manager.update(inputs)

            command = NavigationCommand()

            if result is not None:

                command = result.command

                if result.status == "completed":

                    print(result.message)
                    break

            # --------------------------------------
            # Mission-specific navigation
            # --------------------------------------

            active = mission_manager.active_mission

            if active is not None:

                # Gate guidance for Mission 1.
                if (
                    args.mission == 1
                    and active.state == "APPROACHING_GATE"
                ):

                    command = gate_navigator.calculate_command(
                        detections,
                        frame_1.shape[1]
                    )

                # Stop when black obstacles are detected
                # during Mission 2.
                elif args.mission == 2:

                    command, obstacles = obstacle_avoidance.apply(
                        command,
                        detections
                    )

                    if obstacles:
                        print("Black obstacle detected.")

            # --------------------------------------
            # Apply safety supervision
            # --------------------------------------

            command = safety.filter_command(command)

            # --------------------------------------
            # Send commands to ESP32
            # --------------------------------------

            # Firmware remains disarmed and motor output
            # is intentionally disabled.
            esp32.send_command(
                command.surge,
                command.yaw
            )

            # --------------------------------------
            # Display camera feed
            # --------------------------------------

            if not args.no_display:

                display_frame = vision.draw(
                    frame_1,
                    detections
                )

                cv2.imshow(
                    "RoboBoat Camera 1",
                    display_frame
                )

                cv2.imshow(
                    "RoboBoat Camera 2",
                    frame_2
                )

                key = cv2.waitKey(1) & 0xFF

                if key == ord("q"):

                    print("Manual stop requested.")
                    break

            # --------------------------------------
            # Maintain control loop rate
            # --------------------------------------

            elapsed = time.monotonic() - loop_start

            remaining = period - elapsed

            if remaining > 0:
                time.sleep(remaining)

    except KeyboardInterrupt:

        print("Keyboard interrupt received.")

    except Exception as error:

        print(f"System error: {error}")

    finally:

        print("Stopping RoboBoat system...")

        if esp32 is not None:

            esp32.emergency_stop()
            time.sleep(0.1)
            esp32.disarm()
            esp32.close()

        if camera_1 is not None:
            camera_1.release()

        if camera_2 is not None:
            camera_2.release()

        cv2.destroyAllWindows()

        print("System shutdown completed.")


if __name__ == "__main__":
    main()