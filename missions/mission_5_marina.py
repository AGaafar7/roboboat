from navigation.command import NavigationCommand
from missions.mission_common import MissionResult, MissionLogger
from config import MAX_SURGE


class MarinaMission:
    """
    Task 5 — Navigate the Marina.
    Select lowest-numbered slip with a green indicator, then dock.
    """

    def __init__(self):
        self.logger = MissionLogger()
        self.state = "ENTERING_MARINA"
        self.selected_slip = None

    def start(self):
        self.state = "ENTERING_MARINA"
        self.selected_slip = None
        self.logger.record("mission_5_started")

    def update(self, inputs):
        # ---------- ENTERING_MARINA ----------
        if self.state == "ENTERING_MARINA":
            if inputs.get("marina_entered", False):
                self.state = "SELECTING_SLIP"
                self.logger.record("marina_entered")
            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE * 0.6),
                message="Entering marina",
            )

        # ---------- SELECTING_SLIP ----------
        if self.state == "SELECTING_SLIP":
            slips = inputs.get("slips", [])

            available = [
                s for s in slips
                if s.get("available") is True
                and isinstance(s.get("slip_number"), int)
                and 1 <= s["slip_number"] <= 3
            ]

            if not available:
                return MissionResult(
                    command=NavigationCommand(surge=MAX_SURGE * 0.4),
                    message="Waiting for green-indicator slip",
                )

            self.selected_slip = min(
                available, key=lambda s: s["slip_number"]
            )
            self.logger.record(
                "slip_selected",
                dock_id=self.selected_slip.get("dock_id"),
                slip_number=self.selected_slip["slip_number"],
            )
            self.state = "APPROACHING_SLIP"
            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE * 0.5),
                message=f"Slip {self.selected_slip['slip_number']} selected",
            )

        # ---------- APPROACHING_SLIP ----------
        if self.state == "APPROACHING_SLIP":
            if inputs.get("at_slip_approach", False):
                self.state = "FINAL_DOCKING"
                self.logger.record("slip_approach_reached")
            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE * 0.3),
                message=f"Approaching slip {self.selected_slip['slip_number']}",
            )

        # ---------- FINAL_DOCKING ----------
        if self.state == "FINAL_DOCKING":
            if inputs.get("docking_complete", False):
                self.state = "COMPLETED"
                self.logger.record(
                    "docking_completed",
                    dock_id=self.selected_slip.get("dock_id"),
                    slip_number=self.selected_slip["slip_number"],
                )
                return MissionResult(
                    status="completed",
                    message="Successfully docked",
                )
            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE * 0.15),
                message="Final docking maneuver",
            )

        return MissionResult(status="completed", message="Mission 5 complete")

    def stop(self):
        self.logger.record("mission_5_stopped")