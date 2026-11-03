import time

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

    TRANSIT_TIMEOUT_S    = 8.0
    SCAN_TIMEOUT_S       = 20.0
    RETURN_TIMEOUT_S     = 15.0
    CIRCLE_TIMEOUT_S     = 10.0
    CIRCLE_THRESHOLD_DEG = 355.0

    def __init__(self):
        self.logger = MissionLogger()
        self.state = "ENTER_CHANNEL"

        self.reported = set()
        self.active_survivor = None
        self.survivor_start_heading = None
        self.survivor_accumulated = 0.0
        self.last_heading = None

        self.channel_enter_time = None
        self.scan_start_time = None
        self.return_start_time = None
        self.circle_start_time = None

    def start(self):
        self.state = "ENTER_CHANNEL"
        self.reported.clear()
        self.active_survivor = None
        self.survivor_start_heading = None
        self.survivor_accumulated = 0.0
        self.last_heading = None
        self.channel_enter_time = None
        self.scan_start_time = None
        self.return_start_time = None
        self.circle_start_time = None
        self.logger.record("mission_2_started")

    # ------------------------------------------------------------------
    def _record_detections(self, detections):
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
        now = inputs.get("time", time.time())

        first_green = self._record_detections(detections)

        # ---------- ENTER_CHANNEL ----------
        if self.state == "ENTER_CHANNEL":
            if self.channel_enter_time is None:
                self.channel_enter_time = now

            if inputs.get("channel_entered", False):
                self.state = "TRANSIT_CHANNEL"
                self.logger.record("channel_entered")

            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE),
                message="Entering debris channel",
            )

        # ---------- TRANSIT_CHANNEL ----------
        if self.state == "TRANSIT_CHANNEL":
            if self.channel_enter_time is None:
                # Defensive: state entered without prior timer.
                self.channel_enter_time = now

            elapsed = now - self.channel_enter_time

            if (inputs.get("debris_field_entered", False)
                    or elapsed > self.TRANSIT_TIMEOUT_S):
                self.state = "SCANNING_DEBRIS"
                self.scan_start_time = now
                self.logger.record(
                    "debris_field_entered",
                    via_timeout=elapsed > self.TRANSIT_TIMEOUT_S,
                )

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
                self.circle_start_time = now
                self.state = "CIRCLING_SURVIVOR"
                self.logger.record(
                    "survivor_circle_started",
                    position=first_green.get("position"),
                )
                return MissionResult(
                    command=NavigationCommand(),
                    message="Green survivor found — commencing circle",
                )

            if self.scan_start_time is None:
                # Defensive: state entered without prior timer.
                self.scan_start_time = now

            elapsed = now - self.scan_start_time

            if (inputs.get("debris_field_exit_complete", False)
                    or elapsed > self.SCAN_TIMEOUT_S):
                self.state = "RETURNING"
                self.return_start_time = now
                self.logger.record(
                    "returning_through_channel",
                    via_timeout=elapsed > self.SCAN_TIMEOUT_S,
                )
                return MissionResult(
                    command=NavigationCommand(surge=MAX_SURGE),
                    message="Returning through channel",
                )

            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE * 0.8),
                message="Scanning debris field",
            )

        # ---------- CIRCLING_SURVIVOR ----------
        if self.state == "CIRCLING_SURVIVOR":
            self._track_circle(heading)

            if self.circle_start_time is None:
                self.circle_start_time = now

            circle_elapsed = now - self.circle_start_time

            if (self.survivor_accumulated >= self.CIRCLE_THRESHOLD_DEG
                    or circle_elapsed > self.CIRCLE_TIMEOUT_S):
                pos = (self.active_survivor or {}).get("position")
                self.logger.record(
                    "survivor_circle_completed",
                    position=pos,
                    accumulated_deg=self.survivor_accumulated,
                    elapsed_s=circle_elapsed,
                )
                self.active_survivor = None
                self.circle_start_time = None
                self.survivor_accumulated = 0.0
                self.last_heading = None

                # Return to scanning so a second green indicator can
                # be handled, or the SCAN timeout can end the mission.
                self.state = "SCANNING_DEBRIS"
                # Restart scan timer so we don't instantly time out
                # based on the pre-circle scan window.
                self.scan_start_time = now
                return MissionResult(
                    message="Survivor circle completed",
                )

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
            if self.return_start_time is None:
                # Defensive: guarantees the timeout can always fire,
                # even if RETURNING is entered without an explicit timer.
                self.return_start_time = now

            elapsed = now - self.return_start_time

            if (inputs.get("channel_exit_complete", False)
                    or elapsed > self.RETURN_TIMEOUT_S):
                self.state = "COMPLETED"
                self.logger.record(
                    "mission_2_completed",
                    elapsed_s=elapsed,
                )
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