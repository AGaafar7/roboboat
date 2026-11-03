# ==============================
# ROBOBOAT CONFIGURATION
# ==============================

# ESP32 communication
SERIAL_PORT = "/dev/ttyUSB0"
SERIAL_BAUDRATE = 115200

# Cameras
CAMERA_FRONT_INDEX = 0
CAMERA_SECONDARY_INDEX = 1

CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
CAMERA_FPS = 30

# ESC configuration
NUMBER_OF_THRUSTERS = 4

# Conservative initial limits
MAX_SURGE = 0.20
MAX_YAW = 0.20

# Communication timeout
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

# Navigation
WAYPOINT_ARRIVAL_RADIUS = 3.0

# Obstacle detection
OBSTACLE_MIN_AREA = 1500