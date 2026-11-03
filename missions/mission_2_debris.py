from navigation.command import NavigationCommand
from missions.mission_common import MissionResult, MissionLogger


class DebrisMission:

    def __init__(self):

        self.logger = MissionLogger()
        self.state = "ENTER_CHANNEL"

        self.reported = set()

    def start(self):

        self.state = "ENTER_CHANNEL"
        self.reported.clear()

        self.logger.record("mission_2_started")

    def update(self, inputs):

        detections = inputs.get("detections", [])

        for index, detection in enumerate(detections):

            color = detection.get("color")
            position = detection.get("position")

            key = (
                color,
                tuple(position) if position else None
            )

            if key in self.reported:
                continue

            if color == "red":

                self.logger.record(
                    "red_hazard_detected",
                    position=position
                )

                self.reported.add(key)

            elif color == "green":

                self.logger.record(
                    "green_survivor_indicator_detected",
                    position=position
                )

                self.reported.add(key)

                self.state = "SURVIVOR_CIRCLE"

                return MissionResult(
                    command=NavigationCommand(),
                    message="Green indicator detected; preparing survivor circle"
                )

            elif color == "black":

                self.logger.record(
                    "black_obstacle_detected",
                    position=position
                )

                self.reported.add(key)

        if self.state == "ENTER_CHANNEL":

            if inputs.get("channel_entered", False):
                self.state = "CLEAR_DEBRIS"

            return MissionResult(
                message="Entering debris channel"
            )

        if self.state == "SURVIVOR_CIRCLE":

            if inputs.get("survivor_circle_complete", False):

                self.logger.record(
                    "survivor_circle_completed",
                    position=inputs.get("position")
                )

                self.state = "CLEAR_DEBRIS"

                return MissionResult(
                    message="Survivor circle completed"
                )

            return MissionResult(
                command=NavigationCommand(),
                message="Completing survivor circle"
            )

        if self.state == "CLEAR_DEBRIS":

            if inputs.get("channel_exit_complete", False):

                self.state = "COMPLETED"

                self.logger.record(
                    "mission_2_completed"
                )

                return MissionResult(
                    status="completed",
                    message="Debris clearance completed"
                )

            return MissionResult(
                message="Navigating debris field"
            )

        return MissionResult(
            status="completed",
            message="Mission 2 completed"
        )

    def stop(self):

        self.logger.record("mission_2_stopped")