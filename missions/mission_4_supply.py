from navigation.command import NavigationCommand
from missions.mission_common import MissionResult, MissionLogger
from config import MAX_SURGE


class SupplyMission:
    """
    Task 4 — Supply Drop.
    - Yellow vessels: stream water at black triangle (>=3 s)
    - Black vessels:  fire racquetball at black plus
    Reports position and color for each delivery.
    """

    MAX_BALLS = 3
    WATER_DURATION_S = 3.0

    def __init__(self):
        self.logger = MissionLogger()
        self.state = "SEARCHING"
        self.current_target = None
        self.balls_used = 0
        self.delivered_targets = set()

    def start(self):
        self.state = "SEARCHING"
        self.current_target = None
        self.balls_used = 0
        self.delivered_targets.clear()
        self.logger.record("mission_4_started")

    def update(self, inputs):
        # ---------- SEARCHING ----------
        if self.state == "SEARCHING":
            if self.balls_used >= self.MAX_BALLS and not inputs.get(
                "yellow_target"
            ):
                # No more balls, but may still deliver water.
                pass

            target = inputs.get("target")
            if target is None:
                return MissionResult(
                    command=NavigationCommand(surge=MAX_SURGE * 0.6),
                    message="Searching for supply targets",
                )

            ttype = target.get("target_type")
            if ttype not in ("water", "racquetball"):
                return MissionResult(message="Unknown target type")

            key = (ttype, tuple(target.get("position") or []))
            if key in self.delivered_targets:
                return MissionResult(
                    command=NavigationCommand(surge=MAX_SURGE * 0.6),
                    message="Target already served",
                )

            # Respect ball budget
            if ttype == "racquetball" and self.balls_used >= self.MAX_BALLS:
                return MissionResult(
                    command=NavigationCommand(surge=MAX_SURGE * 0.6),
                    message="Out of racquetballs; continuing scan",
                )

            self.current_target = target
            self.state = "ALIGNING"
            self.logger.record(
                "supply_target_acquired",
                target_type=ttype,
                position=target.get("position"),
                color=target.get("vessel_color"),
            )
            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE * 0.5),
                message=f"Approaching {ttype} target",
            )

        # ---------- ALIGNING ----------
        if self.state == "ALIGNING":
            if inputs.get("aligned_for_delivery", False):
                self.state = "DELIVERING"
            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE * 0.4),
                message="Aligning with target",
            )

        # ---------- DELIVERING ----------
        if self.state == "DELIVERING":
            ttype = self.current_target["target_type"]

            action = None
            if ttype == "water":
                action = {
                    "type": "water_delivery",
                    "duration_seconds": self.WATER_DURATION_S,
                    "target": "black_triangle",
                }
            else:
                action = {
                    "type": "racquetball_delivery",
                    "target": "black_plus",
                }

            if inputs.get("delivery_complete", False):
                if ttype == "racquetball":
                    self.balls_used += 1

                pos = self.current_target.get("position")
                key = (ttype, tuple(pos) if pos else ())
                self.delivered_targets.add(key)

                self.logger.record(
                    "supply_delivery_completed",
                    target_type=ttype,
                    position=pos,
                    vessel_color=self.current_target.get("vessel_color"),
                    balls_used=self.balls_used,
                )

                self.current_target = None
                self.state = "SEARCHING"
                return MissionResult(message="Delivery completed")

            return MissionResult(
                command=NavigationCommand(),
                action=action,
                message=f"Delivering {ttype}",
            )

        return MissionResult(status="completed", message="Mission 4 complete")

    def stop(self):
        self.logger.record("mission_4_stopped")