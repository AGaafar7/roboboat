from missions.mission_common import MissionResult, MissionLogger
from navigation.command import NavigationCommand


class HarborAlertMission:

    ALLOWED_FREQUENCIES = (600, 800, 1000)

    def __init__(self):

        self.logger = MissionLogger()
        self.state = "LISTENING"

        self.selected_zone = None
        self.detected_frequency = None
        self.blast_count = None

    def start(self):

        self.state = "LISTENING"

        self.selected_zone = None
        self.detected_frequency = None
        self.blast_count = None

        self.logger.record("mission_6_started")

    def update(self, inputs):

        if self.state == "LISTENING":

            alert = inputs.get("audio_alert")

            if alert is None:
                return MissionResult(
                    message="Listening for harbor alert"
                )

            count = alert.get("blast_count")
            frequency = alert.get("frequency")

            if count not in (1, 2):
                return MissionResult(
                    message="Invalid blast count"
                )

            if not isinstance(frequency, (int, float)):
                return MissionResult(
                    message="Invalid audio frequency"
                )

            valid_frequency = any(
                nominal * 0.95 <= frequency <= nominal * 1.05
                for nominal in self.ALLOWED_FREQUENCIES
            )

            if not valid_frequency:
                return MissionResult(
                    message="Alert frequency outside allowed range"
                )

            self.blast_count = count
            self.detected_frequency = frequency

            if count == 1:
                self.selected_zone = "EMERGENCY_RESPONSE_ZONE"
            else:
                self.selected_zone = "MARINA"

            self.logger.record(
                "harbor_alert_detected",
                blast_count=count,
                frequency=frequency,
                response_zone=self.selected_zone,
                detection_time=alert.get("detection_time")
            )

            self.state = "RESPONDING"

        if self.state == "RESPONDING":

            if inputs.get("response_complete", False):

                self.state = "COMPLETED"

                self.logger.record(
                    "harbor_alert_response_completed",
                    response_zone=self.selected_zone,
                    frequency=self.detected_frequency,
                    blast_count=self.blast_count
                )

                return MissionResult(
                    status="completed",
                    message=f"Reached {self.selected_zone}"
                )

            return MissionResult(
                command=NavigationCommand(),
                message=f"Responding to alert: {self.selected_zone}"
            )

        return MissionResult(
            status="completed",
            message="Harbor alert mission completed"
        )

    def stop(self):

        self.logger.record("mission_6_stopped")