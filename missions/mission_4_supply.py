import time

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

    SEARCH_TIMEOUT_S     = 90.0    # give up if no targets ever found
    POST_DELIVER_WINDOW  = 30.0    # stop after at least one delivery
    ALIGN_TIMEOUT_S      = 6.0
    DELIVERY_TIMEOUT_S   = 5.0

    def __init__(self):
        self.logger = MissionLogger()
        self.state = "SEARCHING"
        self.current_target = None
        self.balls_used = 0
        self.delivered_targets = set()

        self.search_start_time = None
        self.align_start_time = None
        self.delivery_start_time = None

    def start(self):
        self.state = "SEARCHING"
        self.current_target = None
        self.balls_used = 0
        self.delivered_targets.clear()
        self.search_start_time = None
        self.align_start_time = None
        self.delivery_start_time = None
        self.logger.record("mission_4_started")

    def update(self, inputs):
        now = inputs.get("time", time.time())

        # ---------- SEARCHING ----------
        if self.state == "SEARCHING":
            if self.search_start_time is None:
                self.search_start_time = now
            search_elapsed = now - self.search_start_time

            # Nothing found in a long time: end cleanly.
            if (search_elapsed > self.SEARCH_TIMEOUT_S
                    and not self.delivered_targets):
                self.state = "COMPLETED"
                self.logger.record(
                    "mission_4_timeout",
                    elapsed_s=search_elapsed,
                )
                return MissionResult(
                    status="completed",
                    message="Supply mission ended (no targets found)",
                )

            # At least one delivered; give a short window for more.
            if (search_elapsed > self.POST_DELIVER_WINDOW
                    and self.delivered_targets):
                self.state = "COMPLETED"
                self.logger.record(
                    "mission_4_completed",
                    delivered=len(self.delivered_targets),
                    balls_used=self.balls_used,
                )
                return MissionResult(
                    status="completed",
                    message=f"Supply drop complete "
                            f"({len(self.delivered_targets)} delivered)",
                )

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

            if ttype == "racquetball" and self.balls_used >= self.MAX_BALLS:
                return MissionResult(
                    command=NavigationCommand(surge=MAX_SURGE * 0.6),
                    message="Out of racquetballs; continuing scan",
                )

            self.current_target = target
            self.state = "ALIGNING"
            self.align_start_time = now
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
            elapsed = now - self.align_start_time

            if (inputs.get("aligned_for_delivery", False)
                    or elapsed > self.ALIGN_TIMEOUT_S):
                self.state = "DELIVERING"
                self.delivery_start_time = now
            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE * 0.4),
                message="Aligning with target",
            )

        # ---------- DELIVERING ----------
        if self.state == "DELIVERING":
            ttype = self.current_target["target_type"]

            if self.delivery_start_time is None:
                self.delivery_start_time = now
            delivery_elapsed = now - self.delivery_start_time

            if (inputs.get("delivery_complete", False)
                    or delivery_elapsed > self.DELIVERY_TIMEOUT_S):
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
                self.delivery_start_time = None
                self.search_start_time = now
                self.state = "SEARCHING"
                return MissionResult(message="Delivery completed")

            action = (
                {"type": "water_delivery",
                 "duration_seconds": self.WATER_DURATION_S,
                 "target": "black_triangle"}
                if ttype == "water"
                else {"type": "racquetball_delivery",
                      "target": "black_plus"}
            )

            return MissionResult(
                command=NavigationCommand(),
                action=action,
                message=f"Delivering {ttype}",
            )

        return MissionResult(status="completed", message="Mission 4 complete")

    def stop(self):
        self.logger.record("mission_4_stopped")