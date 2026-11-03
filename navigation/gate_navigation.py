from navigation.command import NavigationCommand
from config import MAX_SURGE, MAX_YAW


class GateNavigator:

    def __init__(self):
        self.center_tolerance = 35
        self.kp_yaw = 0.8

    def calculate_command(self, detections, frame_width):

        red = [
            d for d in detections
            if d["color"] == "red"
        ]

        green = [
            d for d in detections
            if d["color"] == "green"
        ]

        if not red or not green:
            return NavigationCommand()

        # Use the largest detected buoy of each color.
        red_buoy = max(red, key=lambda d: d["area"])
        green_buoy = max(green, key=lambda d: d["area"])

        red_x = red_buoy["center"][0]
        green_x = green_buoy["center"][0]

        gate_center = (red_x + green_x) / 2
        image_center = frame_width / 2

        error = gate_center - image_center

        yaw = (error / image_center) * self.kp_yaw

        command = NavigationCommand(
            surge=MAX_SURGE,
            yaw=max(-MAX_YAW, min(MAX_YAW, yaw))
        )

        if abs(error) < self.center_tolerance:
            command.yaw = 0.0

        return command