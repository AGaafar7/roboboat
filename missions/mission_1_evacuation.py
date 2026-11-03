import math
from navigation.command import NavigationCommand
from missions.mission_common import MissionResult, MissionLogger
from config import MAX_SURGE, MAX_YAW


class EvacuationMission:
    """
    Task 1 — Evacuation Route & Return.
    Navigate autonomously through two pairs of red/green gates
    (entry + exit), then return to start.
    """

    ENTRY_PASSED_DISTANCE = 2.0
    EXIT_PASSED_DISTANCE = 2.0

    SEARCH_EXIT_TIMEOUT_S = 25.0
    CROSS_EXIT_TIMEOUT_S  = 12.0
    RETURN_TIMEOUT_S      = 15.0

    def __init__(self):
        self.logger = MissionLogger()
        self.state = "WAITING_FOR_GATE"

        self.entry_gate_position = None
        self.exit_gate_position  = None
        self.start_position      = None
        self.gate_pass_time      = None
        self.return_start_time   = None

        self.search_exit_start = None
        self.cross_exit_start  = None

    def start(self):
        self.state = "WAITING_FOR_GATE"
        self.entry_gate_position = None
        self.exit_gate_position  = None
        self.gate_pass_time      = None
        self.return_start_time   = None
        self.search_exit_start   = None
        self.cross_exit_start    = None
        self.logger.record("mission_1_started")

    def update(self, inputs):
        now = inputs.get("time", 0.0)

        # ---------- WAITING_FOR_GATE ----------
        if self.state == "WAITING_FOR_GATE":
            if inputs.get("gate_detected", False):
                self.state = "APPROACHING_GATE"
                self.logger.record(
                    "gate_detected",
                    position=inputs.get("position"),
                )
                return MissionResult(
                    command=NavigationCommand(surge=MAX_SURGE),
                    message="Gate detected; approaching",
                )
            return MissionResult(message="Searching for entry gate")

        # ---------- APPROACHING_GATE ----------
        if self.state == "APPROACHING_GATE":
            # The GateNavigator in main.py provides steering here.
            # Advance once the boat is actually between the buoys.
            if inputs.get("gate_entry", False):
                self.entry_gate_position = inputs.get("position")
                self.logger.record(
                    "entry_gate_reached",
                    position=self.entry_gate_position,
                )
                self.state = "CROSSING_ENTRY"
                return MissionResult(
                    command=NavigationCommand(surge=MAX_SURGE),
                    message="Entering entry gate",
                )

            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE),
                message="Approaching entry gate",
            )

        # ---------- CROSSING_ENTRY ----------
        if self.state == "CROSSING_ENTRY":
            if inputs.get("gate_passed", False):
                self.gate_pass_time = now
                self.logger.record(
                    "entry_gate_passed",
                    position=inputs.get("position"),
                    time=self.gate_pass_time,
                )
                self.state = "SEARCHING_EXIT_GATE"
                self.search_exit_start = now

            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE),
                message="Crossing entry gate",
            )

        # ---------- SEARCHING_EXIT_GATE ----------
        if self.state == "SEARCHING_EXIT_GATE":
            if inputs.get("exit_gate_detected", False):
                self.state = "CROSSING_EXIT"
                self.cross_exit_start = now
                return MissionResult(
                    command=NavigationCommand(surge=MAX_SURGE),
                    message="Exit gate acquired",
                )

            if (self.search_exit_start is not None
                    and now - self.search_exit_start
                        > self.SEARCH_EXIT_TIMEOUT_S):
                # Give up on exit pair — go straight to return so we
                # still complete the task, just without the bonus.
                self.logger.record(
                    "exit_gate_search_timeout",
                    elapsed_s=now - self.search_exit_start,
                )
                self.state = "RETURNING"
                self.return_start_time = now
                return MissionResult(
                    command=NavigationCommand(surge=MAX_SURGE * 0.7),
                    message="Exit gate not found; returning",
                )

            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE),
                message="Searching for exit gate pair",
            )

        # ---------- CROSSING_EXIT ----------
        if self.state == "CROSSING_EXIT":
            if inputs.get("exit_gate_passed", False):
                self.exit_gate_position = inputs.get("position")
                self.logger.record(
                    "exit_gate_passed",
                    position=self.exit_gate_position,
                )
                self.state = "RETURNING"
                self.return_start_time = now
                return MissionResult(
                    command=NavigationCommand(surge=MAX_SURGE * 0.7),
                    message="Returning to start",
                )

            if (self.cross_exit_start is not None
                    and now - self.cross_exit_start
                        > self.CROSS_EXIT_TIMEOUT_S):
                self.logger.record(
                    "exit_gate_cross_timeout",
                    elapsed_s=now - self.cross_exit_start,
                )
                self.state = "RETURNING"
                self.return_start_time = now
                return MissionResult(
                    command=NavigationCommand(surge=MAX_SURGE * 0.7),
                    message="Exit cross timed out; returning",
                )

            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE),
                message="Crossing exit gate",
            )

        # ---------- RETURNING ----------
        if self.state == "RETURNING":
            if self.return_start_time is None:
                self.return_start_time = now

            elapsed = now - self.return_start_time

            if (inputs.get("return_complete", False)
                    or elapsed > self.RETURN_TIMEOUT_S):
                self.state = "COMPLETED"
                self.logger.record(
                    "mission_1_completed",
                    position=inputs.get("position"),
                    elapsed_s=elapsed,
                )
                return MissionResult(
                    status="completed",
                    message="Evacuation route and return completed",
                )

            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE * 0.7),
                message="Returning to start",
            )

        return MissionResult(status="completed", message="Mission 1 complete")

    def stop(self):
        self.logger.record("mission_1_stopped")