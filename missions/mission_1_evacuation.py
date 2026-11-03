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

    ENTRY_PASSED_DISTANCE = 2.0      # meters past gate to count as passed
    EXIT_PASSED_DISTANCE = 2.0

    def __init__(self):
        self.logger = MissionLogger()
        self.state = "WAITING_FOR_GATE"

        self.entry_gate_position = None
        self.exit_gate_position = None
        self.start_position = None
        self.gate_pass_time = None

    def start(self):
        self.state = "WAITING_FOR_GATE"
        self.entry_gate_position = None
        self.exit_gate_position = None
        self.gate_pass_time = None
        self.logger.record("mission_1_started")

    def update(self, inputs):
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
            # The GateNavigator in main.py produces the steering command.
            # Here we just advance the state when the vision/nav layer
            # reports the boat is between the buoys.
            if inputs.get("gate_entry", False) and self.entry_gate_position is None:
                self.entry_gate_position = inputs.get("position")
                self.logger.record(
                    "entry_gate_reached",
                    position=self.entry_gate_position,
                )
                self.state = "CROSSING_ENTRY"

            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE),
                message="Approaching entry gate",
            )

        # ---------- CROSSING_ENTRY ----------
        if self.state == "CROSSING_ENTRY":
            if inputs.get("gate_passed", False):
                self.gate_pass_time = inputs.get("time")
                self.logger.record(
                    "entry_gate_passed",
                    position=inputs.get("position"),
                    time=self.gate_pass_time,
                )
                self.state = "SEARCHING_EXIT_GATE"

            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE),
                message="Crossing entry gate",
            )

        # ---------- SEARCHING_EXIT_GATE ----------
        if self.state == "SEARCHING_EXIT_GATE":
            if inputs.get("exit_gate_detected", False):
                self.state = "CROSSING_EXIT"
                return MissionResult(
                    command=NavigationCommand(surge=MAX_SURGE),
                    message="Exit gate acquired",
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

            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE),
                message="Crossing exit gate",
            )

        # ---------- RETURNING ----------
        if self.state == "RETURNING":
            if inputs.get("return_complete", False):
                self.state = "COMPLETED"
                self.logger.record(
                    "mission_1_completed",
                    position=inputs.get("position"),
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