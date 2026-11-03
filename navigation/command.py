from dataclasses import dataclass


@dataclass
class NavigationCommand:
    surge: float = 0.0
    yaw: float = 0.0

    def clamp(self, limit: float = 1.0):
        self.surge = max(-limit, min(limit, self.surge))
        self.yaw = max(-limit, min(limit, self.yaw))

    def stop(self):
        self.surge = 0.0
        self.yaw = 0.0