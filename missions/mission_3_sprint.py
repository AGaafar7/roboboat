import time
from navigation.command import NavigationCommand
from missions.mission_common import MissionResult, MissionLogger
from config import MAX_SURGE


class SprintMission:
    """
    Task 3 — Emergency Response Sprint.
    - Enter gate
    - Locate yellow buoy
    - Red indicator  -> circle counter-clockwise (from the right)
    - Green indicator -> circle clockwise (from the left)
    - Exit through gate, report time
    """

    CIRCLE_THRESHOLD_DEG = 355.0

    def __init__(self):
        self.logger = MissionLogger()
        self.state = "WAITING_FOR_GATE"
        self.indicator_color = None
        self.circle_direction = None
        self.start_time = None
        self.circle_accumulated = 0.0
        self.last_heading = None

    def start(self):
        self.state = "WAITING_FOR_GATE"
        self.indicator_color = None
        self.circle_direction = None
        self.start_time = None
        self.circle_accumulated = 0.0
        self.last_heading = None
        self.logger.record("mission_3_started")

    def _accumulate(self, heading):
        if self.last_heading is None:
            self.last_heading = heading
            return
        delta = (heading - self.last_heading + 180) % 360 - 180
        self.circle_accumulated += abs(delta)
        self.last_heading = heading

    def update(self, inputs):
        heading = inputs.get("heading", 0.0)

        # ---------- WAITING_FOR_GATE ----------
        if self.state == "WAITING_FOR_GATE":
            if inputs.get("gate_detected", False):
                self.state = "CROSSING_GATE"
                self.start_time = time.monotonic()
                self.logger.record("sprint_gate_acquired")
            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE),
                message="Searching for sprint gate",
            )

        # ---------- CROSSING_GATE ----------
        if self.state == "CROSSING_GATE":
            if inputs.get("gate_passed", False):
                self.state = "FINDING_TARGET"
                self.logger.record("sprint_gate_crossed")
            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE),
                message="Crossing sprint gate",
            )

        # ---------- FINDING_TARGET ----------
        if self.state == "FINDING_TARGET":
            target = inputs.get("yellow_target")
            if target:
                color = target.get("indicator_color")
                if color not in ("red", "green"):
                    return MissionResult(
                        message="Waiting for valid indicator color",
                    )
                self.indicator_color = color
                self.circle_direction = (
                    "counter_clockwise" if color == "red" else "clockwise"
                )
                self.circle_accumulated = 0.0
                self.last_heading = heading
                self.logger.record(
                    "yellow_target_detected",
                    indicator_color=color,
                    detection_time=time.time(),
                    position=target.get("position"),
                    circle_direction=self.circle_direction,
                )
                self.state = "CIRCLING_TARGET"
            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE * 0.8),
                message="Searching for yellow target",
            )

        # ---------- CIRCLING_TARGET ----------
        if self.state == "CIRCLING_TARGET":
            self._accumulate(heading)

            if self.circle_accumulated >= self.CIRCLE_THRESHOLD_DEG:
                self.logger.record(
                    "yellow_target_circle_completed",
                    direction=self.circle_direction,
                    accumulated_deg=self.circle_accumulated,
                )
                self.state = "EXITING_GATE"
                return MissionResult(
                    message="Circle complete; exiting",
                )

            yaw = 0.18 if self.circle_direction == "clockwise" else -0.18
            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE * 0.4, yaw=yaw),
                message=f"Circling {self.circle_direction} "
                        f"({self.circle_accumulated:.0f}°)",
            )

        # ---------- EXITING_GATE ----------
        if self.state == "EXITING_GATE":
            if inputs.get("gate_exit_complete", False):
                self.state = "COMPLETED"
                elapsed = (
                    time.monotonic() - self.start_time
                    if self.start_time else 0.0
                )
                self.logger.record(
                    "mission_3_completed",
                    elapsed_s=elapsed,
                    indicator_color=self.indicator_color,
                )
                return MissionResult(
                    status="completed",
                    message=f"Sprint complete in {elapsed:.1f}s",
                    events=[{
                        "event": "sprint_completed",
                        "time_s": elapsed,
                        "indicator_color": self.indicator_color,
                    }],
                )
            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE),
                message="Exiting sprint gate",
            )

        return MissionResult(status="completed", message="Mission 3 complete")

    def stop(self):
        self.logger.record("mission_3_stopped")