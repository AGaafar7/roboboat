from navigation.command import NavigationCommand


class ObstacleAvoidance:

    def __init__(self, minimum_area=1500):
        self.minimum_area = minimum_area

    def check_obstacles(self, detections):

        obstacles = [
            d for d in detections
            if d["color"] == "black"
            and d["area"] >= self.minimum_area
        ]

        return obstacles

    def apply(self, command, detections):

        obstacles = self.check_obstacles(detections)

        if obstacles:
            command.stop()

        return command, obstacles