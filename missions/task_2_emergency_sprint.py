import time

from navigation.command import NavigationCommand
from missions.mission_common import MissionResult, MissionLogger
from config import (
    MAX_SURGE,
    SPRINT_ACOUSTIC_FREQS_HZ,
    SPRINT_PINGER_TOLERANCE,
    DEFAULT_TIER,
)


class EmergencySprintTask:
    """
    Task 2 — Emergency Response Sprint (2027).
    Core:       Start at GREEN → loop target buoy → exit field.
    Advanced:   Exit near buoy with active acoustic pinger.
    Disruptive: START and END only findable via pinger.
    """

    CIRCLE_THRESHOLD_DEG = 355.0
    CIRCLE_TIMEOUT_S     = 8.0
    EXIT_TIMEOUT_S       = 12.0

    def __init__(self, tier: str = DEFAULT_TIER):
        self.logger = MissionLogger()
        self.tier = tier
        self.state = "FINDING_START"
        self.start_time = None
        self.circle_accum = 0.0
        self.last_heading = None
        self.circle_start = None
        self.exit_start = None
        self.start_buoy = None
        self.target_buoy = None
        self.end_buoy = None

    def start(self):
        self.state = "FINDING_START"
        self.start_time = time.time()
        self.circle_accum = 0.0
        self.last_heading = None
        self.circle_start = None
        self.exit_start = None
        self.start_buoy = None
        self.target_buoy = None
        self.end_buoy = None
        self.logger.record("task_2_started", tier=self.tier)

    def _accumulate(self, heading):
        if self.last_heading is None:
            self.last_heading = heading
            return
        delta = (heading - self.last_heading + 180) % 360 - 180
        self.circle_accum += abs(delta)
        self.last_heading = heading

    def _match_pinger(self, freq):
        if freq is None:
            return None
        for nominal in SPRINT_ACOUSTIC_FREQS_HZ:
            lo = nominal * (1 - SPRINT_PINGER_TOLERANCE)
            hi = nominal * (1 + SPRINT_PINGER_TOLERANCE)
            if lo <= freq <= hi:
                return nominal
        return None

    def update(self, inputs):
        now = inputs.get("time", time.time())
        heading = inputs.get("heading", 0.0)
        pinger = inputs.get("pinger_frequency_hz")  # from audio pipeline

        # ---------- DISRUPTIVE: find START via pinger only ----------
        if self.tier == "disruptive" and self.state == "FINDING_START":
            matched = self._match_pinger(pinger)
            if matched is None:
                return MissionResult(
                    command=NavigationCommand(surge=MAX_SURGE * 0.6),
                    message="Listening for START pinger",
                )
            self.start_buoy = {"nominal_hz": matched, "detected_hz": pinger}
            self.logger.record("start_pinger_acquired", nominal_hz=matched)
            self.state = "SEEKING_TARGET"
            return MissionResult(message="START pinger acquired")

        # ---------- CORE / ADVANCED: find GREEN START ----------
        if self.state == "FINDING_START":
            if inputs.get("start_green_detected", False):
                self.start_buoy = {"visual": "green"}
                self.state = "SEEKING_TARGET"
                self.logger.record("start_green_acquired")
                return MissionResult(message="Green START acquired")
            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE * 0.8),
                message="Searching for GREEN start",
            )

        # ---------- SEEK TARGET ----------
        if self.state == "SEEKING_TARGET":
            target = inputs.get("target_buoy")  # {position, color}
            if target:
                self.target_buoy = target
                self.circle_accum = 0.0
                self.last_heading = heading
                self.circle_start = now
                self.state = "CIRCLING_TARGET"
                self.logger.record("target_acquired",
                                   color=target.get("color"))
                return MissionResult(message="Target acquired")
            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE * 0.8),
                message="Seeking target buoy",
            )

        # ---------- CIRCLE TARGET ----------
        if self.state == "CIRCLING_TARGET":
            self._accumulate(heading)
            elapsed = now - (self.circle_start or now)
            if (self.circle_accum >= self.CIRCLE_THRESHOLD_DEG
                    or elapsed > self.CIRCLE_TIMEOUT_S):
                self.logger.record("target_circled",
                                   accum_deg=self.circle_accum)
                self.state = "EXITING"
                self.exit_start = now
                return MissionResult(message="Target circled; exiting")
            yaw = 0.18 if self.target_buoy.get("color") == "green" else -0.18
            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE * 0.4, yaw=yaw),
                message=f"Circling target ({self.circle_accum:.0f}°)",
                tier=self.tier,
            )

        # ---------- EXIT ----------
        if self.state == "EXITING":
            if self.exit_start is None:
                self.exit_start = now
            elapsed = now - self.exit_start

            # Disruptive: must locate END via pinger
            if self.tier == "disruptive":
                matched = self._match_pinger(pinger)
                if matched and inputs.get("end_pinger_acquired", False):
                    self.end_buoy = {"nominal_hz": matched}
                    self.logger.record("end_pinger_acquired",
                                       nominal_hz=matched)
                    self.state = "COMPLETED"
                    elapsed_total = now - self.start_time
                    self.logger.record("task_2_completed",
                                       tier=self.tier,
                                       elapsed_s=elapsed_total)
                    return MissionResult(
                        status="completed",
                        message=f"Sprint complete in {elapsed_total:.1f}s",
                        tier=self.tier, task_badge="assessment_discovery",
                        events=[{"event": "sprint_completed",
                                 "tier": self.tier,
                                 "time_s": elapsed_total}],
                    )
                if elapsed > self.EXIT_TIMEOUT_S:
                    self.state = "COMPLETED"
                    return MissionResult(
                        status="completed",
                        message="Sprint timeout (END pinger not found)",
                        tier=self.tier,
                    )
                return MissionResult(
                    command=NavigationCommand(surge=MAX_SURGE * 0.6),
                    message="Listening for END pinger",
                )

            # Core / Advanced: exit field, Advanced requires pinger at exit
            if self.tier == "advanced":
                matched = self._match_pinger(pinger)
                if matched:
                    self.end_buoy = {"nominal_hz": matched}
                    self.state = "COMPLETED"
                    elapsed_total = now - self.start_time
                    return MissionResult(
                        status="completed",
                        message=f"Sprint complete near pinger "
                                f"({matched} Hz) in {elapsed_total:.1f}s",
                        tier=self.tier, task_badge="assessment_discovery",
                    )

            if (inputs.get("exit_complete", False)
                    or elapsed > self.EXIT_TIMEOUT_S):
                self.state = "COMPLETED"
                elapsed_total = now - self.start_time
                return MissionResult(
                    status="completed",
                    message=f"Sprint complete in {elapsed_total:.1f}s",
                    tier=self.tier, task_badge="assessment_discovery",
                )
            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE),
                message="Exiting sprint field",
                tier=self.tier,
            )

        return MissionResult(status="completed", message="Task 2 complete")

    def stop(self):
        self.logger.record("task_2_stopped", tier=self.tier)