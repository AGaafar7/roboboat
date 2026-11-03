from navigation.command import NavigationCommand
from missions.mission_common import MissionResult, MissionLogger


class MarinaMission:

    def __init__(self):

        self.logger = MissionLogger()
        self.state = "ENTERING_MARINA"

        self.selected_slip = None

    def start(self):

        self.state = "ENTERING_MARINA"
        self.selected_slip = None

        self.logger.record("mission_5_started")

    def update(self, inputs):

        if self.state == "ENTERING_MARINA":

            if inputs.get("marina_entered", False):

                self.state = "SELECTING_SLIP"

                self.logger.record(
                    "marina_entered"
                )

            return MissionResult(
                message="Entering marina"
            )

        if self.state == "SELECTING_SLIP":

            slips = inputs.get("slips", [])

            available_slips = [
                slip for slip in slips
                if slip.get("available") is True
                and isinstance(slip.get("slip_number"), int)
            ]

            if not available_slips:

                return MissionResult(
                    message="No available green-indicator slips detected"
                )

            self.selected_slip = min(
                available_slips,
                key=lambda slip: slip["slip_number"]
            )

            self.logger.record(
                "slip_selected",
                dock_id=self.selected_slip.get("dock_id"),
                slip_number=self.selected_slip["slip_number"]
            )

            self.state = "DOCKING"

            return MissionResult(
                message=(
                    f"Selected slip "
                    f"{self.selected_slip['slip_number']}"
                )
            )

        if self.state == "DOCKING":

            if inputs.get("docking_complete", False):

                self.state = "COMPLETED"

                self.logger.record(
                    "docking_completed",
                    dock_id=self.selected_slip.get("dock_id"),
                    slip_number=self.selected_slip["slip_number"]
                )

                return MissionResult(
                    status="completed",
                    message="Successfully docked"
                )

            return MissionResult(
                command=NavigationCommand(),
                message="Waiting for docking controller"
            )

        return MissionResult(
            status="completed",
            message="Mission 5 completed"
        )

    def stop(self):

        self.logger.record("mission_5_stopped")