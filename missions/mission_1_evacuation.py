from navigation.command import NavigationCommand
from missions.mission_common import MissionResult, MissionLogger


class EvacuationMission:

    def __init__(self):

        self.logger = MissionLogger()
        self.state = "WAITING_FOR_GATE"

    def start(self):

        self.state = "WAITING_FOR_GATE"

        self.logger.record(
            "mission_1_started"
        )

    def update(self, inputs):

        if self.state == "WAITING_FOR_GATE":

            if inputs.get("gate_detected", False):

                self.state = "APPROACHING_GATE"

                self.logger.record(
                    "gate_detected",
                    position=inputs.get("position")
                )

            return MissionResult(
                command=NavigationCommand(),
                message="Searching for evacuation gate"
            )

        if self.state == "APPROACHING_GATE":

            if inputs.get("gate_entry", False):

                self.logger.record(
                    "gate_entry",
                    position=inputs.get("position")
                )

            if inputs.get("gate_passed", False):

                self.logger.record(
                    "gate_exit",
                    position=inputs.get("position")
                )

                self.state = "RETURNING"

            return MissionResult(
                command=NavigationCommand(),
                message="Navigating through gate"
            )

        if self.state == "RETURNING":

            if inputs.get("return_complete", False):

                self.state = "COMPLETED"

                self.logger.record(
                    "mission_1_completed",
                    position=inputs.get("position")
                )

                return MissionResult(
                    status="completed",
                    message="Evacuation route and return completed"
                )

            return MissionResult(
                command=NavigationCommand(),
                message="Returning to starting area"
            )

        return MissionResult(
            status="completed",
            message="Mission 1 completed"
        )

    def stop(self):

        self.logger.record("mission_1_stopped")