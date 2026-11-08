# ==============================
# ROBOBOAT 2027 CONFIGURATION
# ==============================

# --------------------------------------------------
# ESP32 serial link
# --------------------------------------------------
# Check with:
#   ls -l /dev/ttyUSB* /dev/ttyACM*
# ESP32 (DevKit / WROOM) usually shows up as ttyUSB0.
# ESP32-S2/S3 native USB shows up as ttyACM0.
SERIAL_PORT = "/dev/ttyUSB0"
SERIAL_BAUDRATE = 115200

# How long to wait for the ESP32 "ready_disarmed" banner
# before declaring the link dead. Increase to 8.0 on a Pi 0.
SERIAL_HANDSHAKE_TIMEOUT_S = 5.0

# How many times to retry the arm command before giving up.
ARM_RETRIES = 5
ARM_RETRY_DELAY_S = 0.2

# --------------------------------------------------
# Cameras
# --------------------------------------------------
CAMERA_FRONT_INDEX = 0
CAMERA_SECONDARY_INDEX = 2
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
CAMERA_FPS = 30

# --------------------------------------------------
# ESC configuration
# --------------------------------------------------
NUMBER_OF_THRUSTERS = 4

# Conservative initial limits
MAX_SURGE = 0.20
MAX_YAW = 0.20

# Communication timeout (Pi side)
COMMAND_TIMEOUT = 0.5

# Minimum detected object area
MIN_CONTOUR_AREA = 350

# HSV color ranges
HSV_RANGES = {
    "red": [
        ((0, 100, 70), (10, 255, 255)),
        ((170, 100, 70), (180, 255, 255))
    ],
    "green": [
        ((35, 60, 50), (90, 255, 255))
    ],
    "yellow": [
        ((18, 80, 80), (38, 255, 255))
    ],
    "black": [
        ((0, 0, 0), (180, 255, 65))
    ]
}

# Propulsion safety
PROPULSION_ARMED_BY_DEFAULT = False

# --------------------------------------------------
# Navigation
# --------------------------------------------------
WAYPOINT_ARRIVAL_RADIUS = 3.0
OBSTACLE_MIN_AREA = 1500

# --------------------------------------------------
# 2027 MISSION BADGES
# --------------------------------------------------
MISSION_BADGES = {
    "assessment_discovery": "Assessment and Discovery",
    "automated_logistics": "Automated Logistics Support",
    "dynamic_tasking": "Dynamic Tasking",
}

CAPABILITY_TIERS = ("core", "advanced", "disruptive")
DEFAULT_TIER = "core"

# --------------------------------------------------
# RoboCommand (system-of-systems interface)
# --------------------------------------------------
ROBOCOMMAND_WS_URL = "ws://robo-command.local:9000"
ROBOCOMMAND_ENABLED = False  # flip to True when the server exists

# --------------------------------------------------
# Proof of Readiness
# --------------------------------------------------
PROOF_OF_READINESS = {
    "nav_gates_min_width_ft": 6,
    "nav_gates_min_distance_ft": 25,
    "no_obstacle_strikes": True,
    "kill_switch": True,
    "remote_control": True,
    "tow_harness": True,
    "propeller_shrouds": True,
}

# --------------------------------------------------
# Task-specific constants
# --------------------------------------------------
SAFE_PASSAGE_BUOY_FIELD_MAX_S = 120.0
SAFE_PASSAGE_CIRCLE_RADIUS = 1.5

SPRINT_ACOUSTIC_FREQS_HZ = (600, 800, 1000)
SPRINT_PINGER_TOLERANCE = 0.05

MARINA_SLIPS = 3
MARINA_GREEN_SLIP_IDS = (1, 2, 3)

DELIVERY_WATER_DURATION_S = 3.0
DELIVERY_MAX_RACQUETBALLS = 3
DELIVERY_COROPLAST_SHAPES = ("cruciform", "circle", "square", "triangle")

DYNAMIC_RALLY_RADIUS_M = 2.0
DYNAMIC_MULTI_USV_MIN = 2
