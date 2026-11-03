import json
import time
from dataclasses import dataclass, field
from typing import Optional

from navigation.command import NavigationCommand


@dataclass
class MissionResult:
    command: NavigationCommand = field(
        default_factory=NavigationCommand
    )

    status: str = "running"
    message: str = ""
    events: list = field(default_factory=list)

    # Optional hardware action, such as a water or ball delivery.
    action: Optional[dict] = None


class MissionLogger:

    def __init__(self, filename="mission_report.jsonl"):
        self.filename = filename

    def record(self, event_type: str, **details):

        event = {
            "event": event_type,
            "timestamp": time.time(),
            **details
        }

        with open(self.filename, "a") as file:
            file.write(json.dumps(event) + "\n")

        return event