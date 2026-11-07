import time

from navigation.command import NavigationCommand
from missions.mission_common import MissionResult, MissionLogger
from config import (
    MAX_SURGE, DEFAULT_TIER,
    MARINA_GREEN_SLIP_IDS,
    DELIVERY_WATER_DURATION_S,
)


class MarinaTask:
    """
    Task 3 — Navigate the Marina (2027).
    Core:       Dock in slip with GREEN indicator.
    Advanced:   + extinguish RED fire light after docking.
    Disruptive: + two-color flash → water (RED) or racquetball (BLUE)
                delivered to correct distractor boat.
    """

    ENTER_TIMEOUT_S     = 10.0
    SELECT_TIMEOUT_S    = 15.0
    APPROACH_TIMEOUT_S  = 12.0
    DOCK_TIMEOUT_S      = 10.0
    FIRE_TIMEOUT_S      = 8.0
    FLASH_TIMEOUT_S     = 10.0
    DELIVER_TIMEOUT_S   = 12.0

    def __init__(self, tier: str = DEFAULT_TIER):
        self.logger = MissionLogger()
        self.tier = tier
        self.state = "ENTERING_MARINA"
        self.selected_slip = None
        self.flash_sequence = None
        self.delivery_payload = None
        self.delivery_target_id = None

        self.enter_start = None
        self.select_start = None
        self.approach_start = None
        self.dock_start = None
        self.fire_start = None
        self.flash_start = None
        self.deliver_start = None

    def start(self):
        self.state = "ENTERING_MARINA"
        self.selected_slip = None
        self.flash_sequence = None
        self.delivery_payload = None
        self.delivery_target_id = None
        self.enter_start = self.select_start = None
        self.approach_start = self.dock_start = None
        self.fire_start = self.flash_start = None
        self.deliver_start = None
        self.logger.record("task_3_started", tier=self.tier)

    def update(self, inputs):
        now = inputs.get("time", time.time())

        # ---------- ENTERING ----------
        if self.state == "ENTERING_MARINA":
            if self.enter_start is None:
                self.enter_start = now
            elapsed = now - self.enter_start
            if (inputs.get("marina_entered", False)
                    or elapsed > self.ENTER_TIMEOUT_S):
                self.state = "SELECTING_SLIP"
                self.select_start = now
                self.logger.record("marina_entered",
                                   via_timeout=elapsed > self.ENTER_TIMEOUT_S)
            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE * 0.6),
                message="Entering marina",
                tier=self.tier, task_badge="automated_logistics",
            )

        # ---------- SELECTING SLIP ----------
        if self.state == "SELECTING_SLIP":
            if self.select_start is None:
                self.select_start = now
            elapsed = now - self.select_start
            slips = inputs.get("slips", [])
            available = [
                s for s in slips
                if s.get("available") is True
                and s.get("color") == "green"
                and s.get("slip_number") in MARINA_GREEN_SLIP_IDS
            ]
            if not available:
                if elapsed > self.SELECT_TIMEOUT_S:
                    self.state = "COMPLETED"
                    self.logger.record("no_green_slip",
                                       elapsed_s=elapsed)
                    return MissionResult(
                        status="completed",
                        message="Marina task ended (no green slip)",
                        tier=self.tier,
                    )
                return MissionResult(
                    command=NavigationCommand(surge=MAX_SURGE * 0.4),
                    message="Waiting for GREEN slip",
                    tier=self.tier,
                )
            self.selected_slip = min(
                available, key=lambda s: s["slip_number"])
            self.logger.record("slip_selected",
                               slip_number=self.selected_slip["slip_number"])
            self.state = "APPROACHING_SLIP"
            self.approach_start = now
            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE * 0.5),
                message=f"Slip {self.selected_slip['slip_number']} chosen",
                tier=self.tier,
            )

        # ---------- APPROACHING ----------
        if self.state == "APPROACHING_SLIP":
            if self.approach_start is None:
                self.approach_start = now
            elapsed = now - self.approach_start
            if (inputs.get("at_slip_approach", False)
                    or elapsed > self.APPROACH_TIMEOUT_S):
                self.state = "DOCKING"
                self.dock_start = now
                self.logger.record("approach_done",
                                   via_timeout=elapsed > self.APPROACH_TIMEOUT_S)
            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE * 0.3),
                message="Approaching slip",
                tier=self.tier,
            )

        # ---------- DOCKING ----------
        if self.state == "DOCKING":
            if self.dock_start is None:
                self.dock_start = now
            elapsed = now - self.dock_start
            if (inputs.get("docking_complete", False)
                    or elapsed > self.DOCK_TIMEOUT_S):
                self.logger.record("docked",
                                   slip_number=self.selected_slip["slip_number"])
                if self.tier == "core":
                    self.state = "COMPLETED"
                    return MissionResult(
                        status="completed",
                        message="Marina Core complete",
                        tier=self.tier,
                        task_badge="automated_logistics",
                    )
                # Advanced/Disruptive: extinguish RED fire light
                self.state = "FIRE_FIGHTING"
                self.fire_start = now
            return MissionResult(
                command=NavigationCommand(surge=MAX_SURGE * 0.15),
                message="Final docking",
                tier=self.tier,
            )

        # ---------- FIRE FIGHTING (Advanced+) ----------
        if self.state == "FIRE_FIGHTING":
            if self.fire_start is None:
                self.fire_start = now
            elapsed = now - self.fire_start
            if (inputs.get("fire_extinguished", False)
                    or elapsed > self.FIRE_TIMEOUT_S):
                self.logger.record("fire_extinguished",
                                   via_timeout=elapsed > self.FIRE_TIMEOUT_S)
                if self.tier == "advanced":
                    self.state = "COMPLETED"
                    return MissionResult(
                        status="completed",
                        message="Marina Advanced complete",
                        tier=self.tier,
                        task_badge="automated_logistics",
                    )
                # Disruptive: observe two-color flash
                self.state = "READING_FLASH"
                self.flash_start = now
            return MissionResult(
                command=NavigationCommand(),
                action={"type": "extinguish"},
                message="Extinguishing RED fire light",
                tier=self.tier,
            )

        # ---------- READING FLASH (Disruptive) ----------
        if self.state == "READING_FLASH":
            if self.flash_start is None:
                self.flash_start = now
            elapsed = now - self.flash_start
            seq = inputs.get("flash_sequence")  # ["red"|"blue", "red"|"blue"]
            if seq and len(seq) == 2:
                self.flash_sequence = seq
                self.delivery_payload = "water" if seq[0] == "red" else "racquetball"
                self.delivery_target_id = seq[1]
                self.logger.record("flash_decoded",
                                   sequence=seq,
                                   payload=self.delivery_payload,
                                   target_id=self.delivery_target_id)
                self.state = "DELIVERING"
                self.deliver_start = now
                return MissionResult(message="Flash decoded")
            if elapsed > self.FLASH_TIMEOUT_S:
                self.state = "COMPLETED"
                return MissionResult(
                    status="completed",
                    message="Marina Disruptive ended (no flash seen)",
                    tier=self.tier,
                )
            return MissionResult(message="Watching for flash sequence")

        # ---------- DELIVERING (Disruptive) ----------
        if self.state == "DELIVERING":
            if self.deliver_start is None:
                self.deliver_start = now
            elapsed = now - self.deliver_start
            if (inputs.get("delivery_complete", False)
                    or elapsed > self.DELIVER_TIMEOUT_S):
                self.state = "COMPLETED"
                self.logger.record(
                    "marina_delivery_complete",
                    payload=self.delivery_payload,
                    target_id=self.delivery_target_id,
                    via_timeout=elapsed > self.DELIVER_TIMEOUT_S,
                )
                return MissionResult(
                    status="completed",
                    message="Marina Disruptive complete",
                    tier=self.tier, task_badge="automated_logistics",
                    events=[{"event": "marina_delivery",
                             "payload": self.delivery_payload,
                             "target": self.delivery_target_id}],
                )
            action = (
                {"type": "water_delivery",
                 "duration_seconds": DELIVERY_WATER_DURATION_S}
                if self.delivery_payload == "water"
                else {"type": "racquetball_delivery"}
            )
            return MissionResult(
                command=NavigationCommand(),
                action=action,
                message=f"Delivering {self.delivery_payload}",
                tier=self.tier,
            )

        return MissionResult(status="completed", message="Task 3 complete")

    def stop(self):
        self.logger.record("task_3_stopped", tier=self.tier)