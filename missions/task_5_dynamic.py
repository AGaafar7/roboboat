import math
import time

from navigation.command import NavigationCommand
from missions.mission_common import MissionResult, MissionLogger
from config import (
    MAX_SURGE, DEFAULT_TIER,
    DYNAMIC_RALLY_RADIUS_M,
    DYNAMIC_MULTI_USV_MIN,
)


class DynamicResponseTask:
    """
    Task 5 — Dynamic Response (2027).
    Core:       Abandon current tasking → rally at requested GPS point.
    Advanced:   2 USVs respond to a Mission Badge requested at run start.
    Disruptive: 2 USVs respond to a badge requested after tasking begins.
    """

    RALLY_TIMEOUT_S  = 25.0
    BADGE_TIMEOUT_S  = 30.0

    def __init__(self, tier: str = DEFAULT_TIER, usv_id: str = "alpha"):
        self.logger = MissionLogger()
        self.tier = tier
        self.usv_id = usv_id
        self.state = "STANDBY"
        self.requested_badge = None
        self.rally_point = None
        self.partner_ready = False
        self.start = None
        self.rally_start = None
        self.badge_start = None

    def start(self):
        self.state = "STANDBY"
        self.requested_badge = None
        self.rally_point = None
        self.partner_ready = False
        self.start = time.time()
        self.rally_start = None
        self.badge_start = None
        self.logger.record("task_5_started",
                           tier=self.tier, usv_id=self.usv_id)

    def _dist(self, pos, target):
        if pos is None or target is None:
            return None
        return math.hypot(pos[0] - target[0], pos[1] - target[1])

    def update(self, inputs):
        now = inputs.get("time", time.time())

        # ---------- STANDBY: wait for RoboCommand ----------
        if self.state == "STANDBY":
            # Core: GPS rally request
            rally = inputs.get("robo_command_rally_point")
            if rally:
                self.rally_point = rally
                self.rally_start = now
                self.state = "RALLYING"
                self.logger.record("rally_requested",
                                   point=rally, tier=self.tier)
                return MissionResult(message="Rallying to GPS point")

            # Advanced/Disruptive: badge requested
            badge = inputs.get("robo_command_badge")
            if badge:
                self.requested_badge = badge
                self.badge_start = now
                if self.tier in ("advanced", "disruptive"):
                    if not self.partner_ready:
                        self.state = "WAITING_PARTNER"
                        return MissionResult(
                            message=f"Badge {badge} received; awaiting partner")
                    self.state = "RESPONDING"
                else:
                    self.state = "RESPONDING"
                self.logger.record("badge_requested",
                                   badge=badge, tier=self.tier)
                return MissionResult(message=f"Responding to {badge}")

            return MissionResult(
                command=NavigationCommand(),
                message="Standing by for RoboCommand",
                tier=self.tier, task_badge="dynamic_tasking",
            )

        # ---------- WAITING_PARTNER ----------
        if self.state == "WAITING_PARTNER":
            if inputs.get("partner_ready", False):
                self.partner_ready = True
                self.state = "RESPONDING"
                return MissionResult(message="Partner joined; responding")
            return MissionResult(
                command=NavigationCommand(),
                message="Awaiting partner USV",
                tier=self.tier,
            )

        # ---------- RALLYING (Core) ----------
        if self.state == "RALLYING":
            if self.rally_start is None:
                self.rally_start = now
            elapsed = now - self.rally_start
            pos = inputs.get("position")
            d = self._dist(pos, self.rally_point)
            if (d is not None and d <= DYNAMIC_RALLY_RADIUS_M) \
                    or inputs.get("rally_complete", False) \
                    or elapsed > self.RALLY_TIMEOUT_S:
                self.state = "COMPLETED"
                self.logger.record("rally_complete",
                                   distance_m=d,
                                   via_timeout=elapsed > self.RALLY_TIMEOUT_S)
                return MissionResult(
                    status="completed",
                    message="Rally complete",
                    tier=self.tier, task_badge="dynamic_tasking",
                )
            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE),
                message="Rallying to requested GPS point",
                tier=self.tier,
            )

        # ---------- RESPONDING (Advanced/Disruptive) ----------
        if self.state == "RESPONDING":
            if self.badge_start is None:
                self.badge_start = now
            elapsed = now - self.badge_start
            if (inputs.get("badge_complete", False)
                    or elapsed > self.BADGE_TIMEOUT_S):
                self.state = "COMPLETED"
                self.logger.record("badge_response_complete",
                                   badge=self.requested_badge,
                                   elapsed_s=elapsed)
                return MissionResult(
                    status="completed",
                    message=f"{self.requested_badge} response complete",
                    tier=self.tier, task_badge="dynamic_tasking",
                    events=[{"event": "dynamic_badge_complete",
                             "badge": self.requested_badge,
                             "usv": self.usv_id}],
                )
            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE),
                message=f"Executing badge: {self.requested_badge}",
                tier=self.tier,
            )

        return MissionResult(status="completed", message="Task 5 complete")

    def stop(self):
        self.logger.record("task_5_stopped", tier=self.tier)
        