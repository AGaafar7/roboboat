import math

from navigation.command import NavigationCommand
from config import MAX_SURGE, MAX_YAW


class WaypointNavigator:

    def __init__(self):
        self.kp_heading = 0.8
        self.arrival_radius = 3.0  # meters

    @staticmethod
    def calculate_distance(lat1, lon1, lat2, lon2):

        radius = 6371000

        lat1 = math.radians(lat1)
        lat2 = math.radians(lat2)

        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)

        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1)
            * math.cos(lat2)
            * math.sin(dlon / 2) ** 2
        )

        return radius * 2 * math.atan2(
            math.sqrt(a),
            math.sqrt(1 - a)
        )

    @staticmethod
    def calculate_bearing(lat1, lon1, lat2, lon2):

        lat1 = math.radians(lat1)
        lat2 = math.radians(lat2)
        dlon = math.radians(lon2 - lon1)

        x = math.sin(dlon) * math.cos(lat2)

        y = (
            math.cos(lat1) * math.sin(lat2)
            - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
        )

        bearing = math.degrees(math.atan2(x, y))

        return (bearing + 360) % 360

    def calculate_command(
        self,
        current_lat,
        current_lon,
        current_heading,
        target_lat,
        target_lon
    ):

        distance = self.calculate_distance(
            current_lat,
            current_lon,
            target_lat,
            target_lon
        )

        if distance <= self.arrival_radius:
            return NavigationCommand()

        target_bearing = self.calculate_bearing(
            current_lat,
            current_lon,
            target_lat,
            target_lon
        )

        heading_error = (
            target_bearing - current_heading + 180
        ) % 360 - 180

        yaw = heading_error / 90 * self.kp_heading

        return NavigationCommand(
            surge=MAX_SURGE,
            yaw=max(-MAX_YAW, min(MAX_YAW, yaw))
        )