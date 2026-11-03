import math
from navigation.command import NavigationCommand
from missions.mission_common import MissionResult, MissionLogger
from config import MAX_SURGE


class DebrisMission:
    """
    Task 2 — Debris Clearance.
    - Transit channel (red/green gate pairs)
    - Enter debris field, avoid black obstacles
    - Red indicator  -> hazard: report position, avoid
    - Green indicator -> survivor: report, circle 360°, continue
    - Return through channel
    """

    def __init__(self):
        self.logger = MissionLogger()
        self.state = "ENTER_CHANNEL"

        self.reported = set()
        self.active_survivor = None
        self.survivor_start_heading = None
        self.survivor_accumulated = 0.0
        self.last_heading = None

    def start(self):
        self.state = "ENTER_CHANNEL"
        self.reported.clear()
        self.active_survivor = None
        self.survivor_start_heading = None
        self.survivor_accumulated = 0.0
        self.last_heading = None
        self.logger.record("mission_2_started")

    # ------------------------------------------------------------------
    def _record_detections(self, detections):
        """Log each new detection exactly once.  Returns first green found."""
        first_green = None

        for det in detections:
            color = det.get("color")
            pos = det.get("position")
            if color not in ("red", "green", "black"):
                continue

            key = (color, tuple(pos) if pos else det.get("center"))
            if key in self.reported:
                continue

            event = {
                "red":   "red_hazard_detected",
                "green": "green_survivor_detected",
                "black": "black_obstacle_detected",
            }[color]

            self.logger.record(event, position=pos,
                               center=det.get("center"),
                               area=det.get("area"))
            self.reported.add(key)

            if color == "green" and first_green is None:
                first_green = det

        return first_green

    # ------------------------------------------------------------------
    def _track_circle(self, current_heading):
        """Accumulate heading change while circling a survivor."""
        if self.last_heading is None:
            self.last_heading = current_heading
            return

        delta = (current_heading - self.last_heading + 180) % 360 - 180
        self.survivor_accumulated += abs(delta)
        self.last_heading = current_heading

    # ------------------------------------------------------------------
    def update(self, inputs):
        detections = inputs.get("detections", [])
        heading = inputs.get("heading", 0.0)

        first_green = self._record_detections(detections)

        # ---------- ENTER_CHANNEL ----------
        if self.state == "ENTER_CHANNEL":
            if inputs.get("channel_entered", False):
                self.state = "TRANSIT_CHANNEL"
                self.logger.record("channel_entered")
            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE),
                message="Entering debris channel",
            )

        # ---------- TRANSIT_CHANNEL ----------
        if self.state == "TRANSIT_CHANNEL":
            if inputs.get("debris_field_entered", False):
                self.state = "SCANNING_DEBRIS"
                self.logger.record("debris_field_entered")
            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE),
                message="Transiting channel",
            )

        # ---------- SCANNING_DEBRIS ----------
        if self.state == "SCANNING_DEBRIS":
            if first_green is not None:
                self.active_survivor = first_green
                self.survivor_start_heading = heading
                self.last_heading = heading
                self.survivor_accumulated = 0.0
                self.state = "CIRCLING_SURVIVOR"
                self.logger.record(
                    "survivor_circle_started",
                    position=first_green.get("position"),
                )
                return MissionResult(
                    command=NavigationCommand(),
                    message="Green survivor found — commencing circle",
                )

            if inputs.get("debris_field_exit_complete", False):
                self.state = "RETURNING"
                self.logger.record("returning_through_channel")

            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE * 0.8),
                message="Scanning debris field",
            )

        # ---------- CIRCLING_SURVIVOR ----------
        if self.state == "CIRCLING_SURVIVOR":
            self._track_circle(heading)

            if self.survivor_accumulated >= 355.0:  # full 360° minus tolerance
                self.logger.record(
                    "survivor_circle_completed",
                    position=self.active_survivor.get("position"),
                )
                self.active_survivor = None
                self.state = "SCANNING_DEBRIS"
                return MissionResult(
                    message="Survivor circle completed",
                )

            # 360° circle: alternate surge + constant yaw.
            # Direction sign is up to your geometry; default starboard.
            return MissionResult(
                command=NavigationCommand(
                    surge=MAX_SURGE * 0.4,
                    yaw=0.18,
                ),
                message=f"Circling survivor "
                        f"({self.survivor_accumulated:.0f}°)",
            )

        # ---------- RETURNING ----------
        if self.state == "RETURNING":
            if inputs.get("channel_exit_complete", False):
                self.state = "COMPLETED"
                self.logger.record("mission_2_completed")
                return MissionResult(
                    status="completed",
                    message="Debris clearance completed",
                )
            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE),
                message="Returning through channel",
            )

        return MissionResult(status="completed", message="Mission 2 complete")

    def stop(self):
        self.logger.record("mission_2_stopped")