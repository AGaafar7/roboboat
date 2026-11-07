import time

from navigation.command import NavigationCommand
from missions.mission_common import MissionResult, MissionLogger
from config import (
    MAX_SURGE, MAX_YAW,
    SAFE_PASSAGE_BUOY_FIELD_MAX_S,
    DEFAULT_TIER,
)


class SafePassageTask:
    """
    Task 1 — Safe Passage (RoboBoat 2027).
    Core:       Circle ENTRY CW → transit (RED stbd / GREEN port) → circle EXIT CCW.
    Advanced:   EXIT buoy changes while transiting.
    Disruptive: EXIT + up to 2 buoys change color.
    """

    CIRCLE_THRESHOLD_DEG = 355.0
    CIRCLE_TIMEOUT_S     = 8.0
    TRANSIT_TIMEOUT_S    = SAFE_PASSAGE_BUOY_FIELD_MAX_S

    def __init__(self, tier: str = DEFAULT_TIER):
        self.logger = MissionLogger()
        self.tier = tier
        self.state = "SEARCHING_ENTRY"
        self.entry_center = None
        self.exit_center = None
        self.exit_center_original = None
        self.start_time = None

        self.circle_accum = 0.0
        self.last_heading = None
        self.circle_start = None
        self.transit_start = None

        # Disruptive: track buoys that changed color
        self.color_changes = {}

    def start(self):
        self.state = "SEARCHING_ENTRY"
        self.entry_center = None
        self.exit_center = None
        self.exit_center_original = None
        self.start_time = time.time()
        self.circle_accum = 0.0
        self.last_heading = None
        self.circle_start = None
        self.transit_start = None
        self.color_changes.clear()
        self.logger.record("task_1_started", tier=self.tier)

    def _accumulate(self, heading):
        if self.last_heading is None:
            self.last_heading = heading
            return
        delta = (heading - self.last_heading + 180) % 360 - 180
        self.circle_accum += abs(delta)
        self.last_heading = heading

    def _circle_target(self, now):
        if self.circle_start is None:
            self.circle_start = now
        return now - self.circle_start

    def update(self, inputs):
        heading = inputs.get("heading", 0.0)
        now = inputs.get("time", time.time())
        detections = inputs.get("detections", [])

        # ---------- 1. SEARCH ENTRY ----------
        if self.state == "SEARCHING_ENTRY":
            entry = next((d for d in detections if d["color"] == "entry"), None)
            if entry is None:
                # In vision pipeline we may emit "entry" via yellow+shape
                entry = inputs.get("entry_buoy")
            if entry:
                self.entry_center = entry["center"]
                self.state = "CIRCLING_ENTRY"
                self.circle_accum = 0.0
                self.last_heading = heading
                self.circle_start = now
                self.logger.record("entry_buoy_acquired",
                                   center=self.entry_center)
            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE * 0.8),
                message="Searching for ENTRY buoy",
                tier=self.tier, task_badge="assessment_discovery",
            )

        # ---------- 2. CIRCLE ENTRY CW ----------
        if self.state == "CIRCLING_ENTRY":
            self._accumulate(heading)
            elapsed = self._circle_target(now)
            if (self.circle_accum >= self.CIRCLE_THRESHOLD_DEG
                    or elapsed > self.CIRCLE_TIMEOUT_S):
                self.logger.record("entry_circle_done",
                                   accum_deg=self.circle_accum)
                self.state = "TRANSITING"
                self.transit_start = now
                self.last_heading = None
                return MissionResult(message="Entry circled; transiting")
            # Clockwise = positive yaw
            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE * 0.4, yaw=MAX_YAW * 0.8),
                message=f"Circling ENTRY CW ({self.circle_accum:.0f}°)",
                tier=self.tier,
            )

        # ---------- 3. TRANSIT BUOY FIELD ----------
        if self.state == "TRANSITING":
            if self.transit_start is None:
                self.transit_start = now
            if now - self.transit_start > self.TRANSIT_TIMEOUT_S:
                self.logger.record("transit_timeout")
                self.state = "SEARCHING_EXIT"
                return MissionResult(message="Transit timeout; seeking exit")

            # Detect mid-transit color changes (Advanced / Disruptive)
            if self.tier in ("advanced", "disruptive"):
                self._track_color_changes(detections, now)

            # Lateral steering: red starboard, green port
            reds = [d for d in detections if d["color"] == "red"]
            greens = [d for d in detections if d["color"] == "green"]
            yaw = 0.0
            if reds and greens:
                r = max(reds, key=lambda d: d["area"])
                g = max(greens, key=lambda d: d["area"])
                mid = (r["center"][0] + g["center"][0]) / 2
                img_c = inputs.get("frame_width", 640) / 2
                err = mid - img_c
                yaw = max(-MAX_YAW, min(MAX_YAW, (err / img_c) * 0.8))

            if inputs.get("exit_buoy_ahead", False):
                self.state = "CIRCLING_EXIT"
                self.circle_accum = 0.0
                self.last_heading = heading
                self.circle_start = now

            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE, yaw=yaw),
                message="Transiting buoy field",
                tier=self.tier, task_badge="assessment_discovery",
            )

        # ---------- 4. CIRCLE EXIT CCW ----------
        if self.state == "CIRCLING_EXIT":
            self._accumulate(heading)
            elapsed = self._circle_target(now)
            if (self.circle_accum >= self.CIRCLE_THRESHOLD_DEG
                    or elapsed > self.CIRCLE_TIMEOUT_S):
                self.logger.record("exit_circle_done",
                                   accum_deg=self.circle_accum,
                                   color_changes=self.color_changes)
                self.state = "COMPLETED"
                return MissionResult(
                    status="completed",
                    message=f"Safe Passage ({self.tier}) complete",
                    tier=self.tier, task_badge="assessment_discovery",
                    events=[{"event": "safe_passage_completed",
                             "tier": self.tier,
                             "color_changes": self.color_changes}],
                )
            # Counter-clockwise = negative yaw
            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE * 0.4, yaw=-MAX_YAW * 0.8),
                message=f"Circling EXIT CCW ({self.circle_accum:.0f}°)",
                tier=self.tier,
            )

        if self.state == "SEARCHING_EXIT":
            if inputs.get("exit_buoy_ahead", False):
                self.state = "CIRCLING_EXIT"
                self.circle_accum = 0.0
                self.last_heading = heading
                self.circle_start = now
                return MissionResult(message="Exit acquired late")
            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE * 0.7),
                message="Searching for EXIT buoy",
            )

        return MissionResult(status="completed", message="Task 1 complete")

    def _track_color_changes(self, detections, now):
        """Detect mid-transit color changes for Advanced/Disruptive."""
        for d in detections:
            key = tuple(d.get("center", ()))
            prev = self.color_changes.get(key)
            if prev and prev["color"] != d["color"]:
                self.logger.record("buoy_color_changed",
                                   center=key,
                                   old=prev["color"],
                                   new=d["color"])
            self.color_changes[key] = {"color": d["color"], "t": now}

    def stop(self):
        self.logger.record("task_1_stopped", tier=self.tier)