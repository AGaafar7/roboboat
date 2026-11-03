import time

from navigation.command import NavigationCommand
from missions.mission_common import MissionResult, MissionLogger


class SprintMission:

    def __init__(self):

        self.logger = MissionLogger()
        self.state = "WAITING_FOR_GATE"

        self.indicator_color = None
        self.circle_direction = None

    def start(self):

        self.state = "WAITING_FOR_GATE"

        self.indicator_color = None
        self.circle_direction = None

        self.logger.record("mission_3_started")

    def update(self, inputs):

        if self.state == "WAITING_FOR_GATE":

            if inputs.get("gate_detected", False):
                self.state = "CROSSING_GATE"

            return MissionResult(
                message="Searching for sprint gate"
            )

        if self.state == "CROSSING_GATE":

            if inputs.get("gate_passed", False):
                self.state = "FINDING_TARGET"

                self.logger.record(
                    "sprint_gate_crossed"
                )

            return MissionResult(
                message="Crossing sprint gate"
            )

        if self.state == "FINDING_TARGET":

            target = inputs.get("yellow_target")

            if target:

                color = target.get("indicator_color")

                if color not in ("red", "green"):
                    return MissionResult(
                        message="Waiting for valid target indicator"
                    )

                self.indicator_color = color

                if color == "red":
                    self.circle_direction = "counter_clockwise"
                else:
                    self.circle_direction = "clockwise"

                self.logger.record(
                    "yellow_target_detected",
                    indicator_color=color,
                    detection_time=time.time(),
                    position=target.get("position"),
                    circle_direction=self.circle_direction
                )

                self.state = "CIRCLING_TARGET"

            return MissionResult(
                message="Searching for yellow target"
            )

        if self.state == "CIRCLING_TARGET":

            if inputs.get("circle_complete", False):

                self.logger.record(
                    "yellow_target_circle_completed",
                    direction=self.circle_direction
                )

                self.state = "EXITING_GATE"

            return MissionResult(
                command=NavigationCommand(),
                message=f"Circling target {self.circle_direction}"
            )

        if self.state == "EXITING_GATE":

            if inputs.get("gate_exit_complete", False):

                self.state = "COMPLETED"

                self.logger.record(
                    "mission_3_completed"
                )

                return MissionResult(
                    status="completed",
                    message="Emergency response sprint completed"
                )

            return MissionResult(
                message="Exiting sprint gate"
            )

        return MissionResult(
            status="completed",
            message="Mission 3 completed"
        )

    def stop(self):

        self.logger.record("mission_3_stopped")