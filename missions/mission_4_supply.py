from navigation.command import NavigationCommand
from missions.mission_common import MissionResult, MissionLogger


class SupplyMission:

    def __init__(self):

        self.logger = MissionLogger()
        self.state = "SEARCHING"

        self.current_target = None

    def start(self):

        self.state = "SEARCHING"
        self.current_target = None

        self.logger.record("mission_4_started")

    def update(self, inputs):

        if self.state == "SEARCHING":

            target = inputs.get("target")

            if target is None:
                return MissionResult(
                    message="Searching for supply targets"
                )

            target_type = target.get("target_type")

            if target_type not in ("water", "racquetball"):
                return MissionResult(
                    message="Unrecognized supply target"
                )

            self.current_target = target

            self.logger.record(
                "supply_target_detected",
                target_type=target_type,
                position=target.get("position")
            )

            self.state = "DELIVERING"

            return MissionResult(
                message=f"Target identified: {target_type}"
            )

        if self.state == "DELIVERING":

            if self.current_target["target_type"] == "water":

                action = {
                    "type": "water_delivery",
                    "duration_seconds": 3
                }

            else:

                action = {
                    "type": "racquetball_delivery"
                }

            if inputs.get("delivery_complete", False):

                self.logger.record(
                    "supply_delivery_completed",
                    target_type=self.current_target["target_type"],
                    position=self.current_target.get("position")
                )

                self.current_target = None
                self.state = "SEARCHING"

                return MissionResult(
                    message="Delivery completed"
                )

            return MissionResult(
                command=NavigationCommand(),
                action=action,
                message="Waiting for delivery mechanism confirmation"
            )

        return MissionResult()

    def stop(self):

        self.logger.record("mission_4_stopped")