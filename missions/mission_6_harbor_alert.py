import time

from missions.mission_common import MissionResult, MissionLogger
from navigation.command import NavigationCommand
from config import MAX_SURGE


class HarborAlertMission:
    """
    Task 6 — Harbor Alert.
    Listen for 1 or 2 blast signal (600/800/1000 Hz ±5%).
    Override current mission and respond to zone.
    """

    ALLOWED_FREQUENCIES = (600, 800, 1000)
    TOLERANCE = 0.05
    RESPOND_TIMEOUT_S = 25.0

    def __init__(self):
        self.logger = MissionLogger()
        self.state = "LISTENING"
        self.selected_zone = None
        self.detected_frequency = None
        self.blast_count = None
        self.detection_time = None
        self.respond_start_time = None

    def start(self):
        self.state = "LISTENING"
        self.selected_zone = None
        self.detected_frequency = None
        self.blast_count = None
        self.detection_time = None
        self.respond_start_time = None
        self.logger.record("mission_6_started")

    def _validate_alert(self, alert):
        count = alert.get("blast_count")
        freq = alert.get("frequency")
        if count not in (1, 2):
            return None
        if not isinstance(freq, (int, float)):
            return None
        for nominal in self.ALLOWED_FREQUENCIES:
            lo = nominal * (1 - self.TOLERANCE)
            hi = nominal * (1 + self.TOLERANCE)
            if lo <= freq <= hi:
                return nominal
        return None

    def update(self, inputs):
        now = inputs.get("time", time.time())

        # ---------- LISTENING ----------
        if self.state == "LISTENING":
            alert = inputs.get("audio_alert")
            if alert is None:
                return MissionResult(
                    command=NavigationCommand(surge=MAX_SURGE * 0.4),
                    message="Listening for harbor alert",
                )

            nominal = self._validate_alert(alert)
            if nominal is None:
                return MissionResult(
                    message="Invalid alert — ignoring",
                )

            self.blast_count = alert["blast_count"]
            self.detected_frequency = alert["frequency"]
            self.detection_time = alert.get("detection_time", now)
            self.selected_zone = (
                "EMERGENCY_RESPONSE_ZONE"
                if self.blast_count == 1
                else "MARINA"
            )
            self.respond_start_time = now
            self.logger.record(
                "harbor_alert_detected",
                blast_count=self.blast_count,
                frequency=self.detected_frequency,
                matched_nominal_hz=nominal,
                response_zone=self.selected_zone,
                detection_time=self.detection_time,
            )
            self.state = "RESPONDING"
            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE),
                message=f"Alert! Responding to {self.selected_zone}",
                events=[{
                    "event": "harbor_alert_detected",
                    "blast_count": self.blast_count,
                    "zone": self.selected_zone,
                }],
            )

        # ---------- RESPONDING ----------
        if self.state == "RESPONDING":
            if self.respond_start_time is None:
                self.respond_start_time = now
            elapsed = now - self.respond_start_time

            if (inputs.get("response_complete", False)
                    or elapsed > self.RESPOND_TIMEOUT_S):
                self.state = "COMPLETED"
                self.logger.record(
                    "harbor_alert_response_completed",
                    response_zone=self.selected_zone,
                    frequency=self.detected_frequency,
                    blast_count=self.blast_count,
                    elapsed_s=elapsed,
                    via_timeout=elapsed > self.RESPOND_TIMEOUT_S,
                )
                return MissionResult(
                    status="completed",
                    message=f"Reached {self.selected_zone}",
                )
            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE),
                message=f"Navigating to {self.selected_zone}",
            )

        return MissionResult(status="completed", message="Mission 6 complete")

    def stop(self):
        self.logger.record("mission_6_stopped")