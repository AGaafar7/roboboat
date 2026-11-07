import time

from navigation.command import NavigationCommand
from missions.mission_common import MissionResult, MissionLogger
from config import (
    MAX_SURGE, DEFAULT_TIER,
    DELIVERY_WATER_DURATION_S,
    DELIVERY_MAX_RACQUETBALLS,
    DELIVERY_COROPLAST_SHAPES,
)


class DeliveryRunTask:
    """
    Task 4 — Delivery Run (2027).
    Receives urgent RoboCommand assignment. Delivers water to N
    coprolast vessels identified by shape:
        cruciform / circle / square / triangle.
    Core: 1 vessel | Advanced: 2 vessels | Disruptive: 3 vessels.
    """

    SEARCH_TIMEOUT_S   = 60.0
    ALIGN_TIMEOUT_S    = 6.0
    DELIVERY_TIMEOUT_S = 8.0

    REQUIRED_DELIVERIES = {"core": 1, "advanced": 2, "disruptive": 3}

    def __init__(self, tier: str = DEFAULT_TIER):
        self.logger = MissionLogger()
        self.tier = tier
        self.state = "AWAITING_ASSIGNMENT"
        self.required = self.REQUIRED_DELIVERIES[tier]

        self.assigned_shapes = []
        self.delivered = set()
        self.current_target = None
        self.search_start = None
        self.align_start = None
        self.deliver_start = None

    def start(self):
        self.state = "AWAITING_ASSIGNMENT"
        self.assigned_shapes = []
        self.delivered.clear()
        self.current_target = None
        self.search_start = None
        self.align_start = None
        self.deliver_start = None
        self.logger.record("task_4_started", tier=self.tier)

    def assign(self, shapes):
        """Called by RoboCommand handler with the assignment."""
        valid = [s for s in shapes if s in DELIVERY_COROPLAST_SHAPES]
        self.assigned_shapes = valid[:self.required]
        self.logger.record("delivery_assigned",
                           shapes=self.assigned_shapes,
                           tier=self.tier)
        if self.assigned_shapes:
            self.state = "SEARCHING"

    def update(self, inputs):
        now = inputs.get("time", time.time())

        # ---------- AWAITING ----------
        if self.state == "AWAITING_ASSIGNMENT":
            assignment = inputs.get("robo_command_assignment")
            if assignment:
                self.assign(assignment)
                return MissionResult(
                    message=f"Delivery assigned: {self.assigned_shapes}")
            return MissionResult(
                command=NavigationCommand(),
                message="Awaiting RoboCommand delivery assignment",
                tier=self.tier, task_badge="dynamic_tasking",
            )

        # ---------- SEARCHING ----------
        if self.state == "SEARCHING":
            if self.search_start is None:
                self.search_start = now
            elapsed = now - self.search_start

            remaining = [
                s for s in self.assigned_shapes if s not in self.delivered
            ]
            if not remaining:
                self.state = "COMPLETED"
                self.logger.record("delivery_run_complete",
                                   delivered=list(self.delivered))
                return MissionResult(
                    status="completed",
                    message=f"All {len(self.delivered)} deliveries complete",
                    tier=self.tier, task_badge="dynamic_tasking",
                )

            if elapsed > self.SEARCH_TIMEOUT_S:
                self.state = "COMPLETED"
                return MissionResult(
                    status="completed",
                    message="Delivery search timed out",
                    tier=self.tier,
                )

            det = inputs.get("coprolast_detections", [])
            for d in det:
                shape = d.get("shape")
                if shape in remaining:
                    self.current_target = d
                    self.state = "ALIGNING"
                    self.align_start = now
                    self.logger.record("delivery_target_acquired",
                                       shape=shape,
                                       position=d.get("center"))
                    break

            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE * 0.6),
                message=f"Searching for {remaining}",
                tier=self.tier, task_badge="dynamic_tasking",
            )

        # ---------- ALIGNING ----------
        if self.state == "ALIGNING":
            if self.align_start is None:
                self.align_start = now
            elapsed = now - self.align_start
            if (inputs.get("aligned_for_delivery", False)
                    or elapsed > self.ALIGN_TIMEOUT_S):
                self.state = "DELIVERING"
                self.deliver_start = now
            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE * 0.4),
                message="Aligning with coprolast",
                tier=self.tier,
            )

        # ---------- DELIVERING ----------
        if self.state == "DELIVERING":
            if self.deliver_start is None:
                self.deliver_start = now
            elapsed = now - self.deliver_start
            if (inputs.get("delivery_complete", False)
                    or elapsed > self.DELIVERY_TIMEOUT_S):
                shape = self.current_target.get("shape")
                self.delivered.add(shape)
                self.logger.record("water_delivered",
                                   shape=shape,
                                   position=self.current_target.get("center"))
                self.current_target = None
                self.search_start = None
                self.state = "SEARCHING"
                return MissionResult(message=f"Delivered to {shape}")

            return MissionResult(
                command=NavigationCommand(),
                action={"type": "water_delivery",
                        "duration_seconds": DELIVERY_WATER_DURATION_S},
                message=f"Delivering water to {self.current_target['shape']}",
                tier=self.tier,
            )

        return MissionResult(status="completed", message="Task 4 complete")

    def stop(self):
        self.logger.record("task_4_stopped", tier=self.tier)