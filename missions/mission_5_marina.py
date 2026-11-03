import time

from navigation.command import NavigationCommand
from missions.mission_common import MissionResult, MissionLogger
from config import MAX_SURGE


class MarinaMission:
    """
    Task 5 — Navigate the Marina.
    Select lowest-numbered slip with a green indicator, then dock.
    """

    ENTER_TIMEOUT_S   = 10.0
    SELECT_TIMEOUT_S  = 15.0
    APPROACH_TIMEOUT_S = 12.0
    DOCK_TIMEOUT_S    = 10.0

    def __init__(self):
        self.logger = MissionLogger()
        self.state = "ENTERING_MARINA"
        self.selected_slip = None

        self.enter_start_time = None
        self.select_start_time = None
        self.approach_start_time = None
        self.dock_start_time = None

    def start(self):
        self.state = "ENTERING_MARINA"
        self.selected_slip = None
        self.enter_start_time = None
        self.select_start_time = None
        self.approach_start_time = None
        self.dock_start_time = None
        self.logger.record("mission_5_started")

    def update(self, inputs):
        now = inputs.get("time", time.time())

        # ---------- ENTERING_MARINA ----------
        if self.state == "ENTERING_MARINA":
            if self.enter_start_time is None:
                self.enter_start_time = now
            elapsed = now - self.enter_start_time

            if (inputs.get("marina_entered", False)
                    or elapsed > self.ENTER_TIMEOUT_S):
                self.state = "SELECTING_SLIP"
                self.select_start_time = now
                self.logger.record(
                    "marina_entered",
                    via_timeout=elapsed > self.ENTER_TIMEOUT_S,
                )
            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE * 0.6),
                message="Entering marina",
            )

        # ---------- SELECTING_SLIP ----------
        if self.state == "SELECTING_SLIP":
            if self.select_start_time is None:
                self.select_start_time = now
            elapsed = now - self.select_start_time

            slips = inputs.get("slips", [])
            available = [
                s for s in slips
                if s.get("available") is True
                and isinstance(s.get("slip_number"), int)
                and 1 <= s["slip_number"] <= 3
            ]

            if not available:
                if elapsed > self.SELECT_TIMEOUT_S:
                    self.state = "COMPLETED"
                    self.logger.record(
                        "mission_5_no_slips",
                        elapsed_s=elapsed,
                    )
                    return MissionResult(
                        status="completed",
                        message="Marina mission ended (no slips detected)",
                    )
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
            self.approach_start_time = now
            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE * 0.5),
                message=f"Slip {self.selected_slip['slip_number']} selected",
            )

        # ---------- APPROACHING_SLIP ----------
        if self.state == "APPROACHING_SLIP":
            if self.approach_start_time is None:
                self.approach_start_time = now
            elapsed = now - self.approach_start_time

            if (inputs.get("at_slip_approach", False)
                    or elapsed > self.APPROACH_TIMEOUT_S):
                self.state = "FINAL_DOCKING"
                self.dock_start_time = now
                self.logger.record(
                    "slip_approach_reached",
                    via_timeout=elapsed > self.APPROACH_TIMEOUT_S,
                )
            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE * 0.3),
                message=f"Approaching slip {self.selected_slip['slip_number']}",
            )

        # ---------- FINAL_DOCKING ----------
        if self.state == "FINAL_DOCKING":
            if self.dock_start_time is None:
                self.dock_start_time = now
            elapsed = now - self.dock_start_time

            if (inputs.get("docking_complete", False)
                    or elapsed > self.DOCK_TIMEOUT_S):
                self.state = "COMPLETED"
                self.logger.record(
                    "docking_completed",
                    dock_id=self.selected_slip.get("dock_id"),
                    slip_number=self.selected_slip["slip_number"],
                    via_timeout=elapsed > self.DOCK_TIMEOUT_S,
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