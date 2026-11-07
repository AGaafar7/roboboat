from missions.task_1_safe_passage   import SafePassageTask
from missions.task_2_emergency_sprint import EmergencySprintTask
from missions.task_3_marina         import MarinaTask
from missions.task_4_delivery       import DeliveryRunTask
from missions.task_5_dynamic        import DynamicResponseTask

from config import DEFAULT_TIER


# Badge → required tasks (per 2027 manual p. 8)
BADGE_TASKS = {
    "assessment_discovery": [SafePassageTask, EmergencySprintTask],
    "automated_logistics":  [MarinaTask, DeliveryRunTask],
    "dynamic_tasking":      [SafePassageTask, EmergencySprintTask,
                             DynamicResponseTask],
}


class MissionManager:
    """
    RoboBoat 2027: Mission Badges → Tasks → Tiers.
    """

    def __init__(self):
        self.badge = None
        self.tier = DEFAULT_TIER
        self.task_sequence = []
        self.current_task = None
        self.completed_tasks = []

    # ---------- Badge orchestration ----------
    def start_badge(self, badge_name, tier=DEFAULT_TIER):
        if badge_name not in BADGE_TASKS:
            raise ValueError(f"Unknown badge: {badge_name}")
        if tier not in ("core", "advanced", "disruptive"):
            raise ValueError(f"Unknown tier: {tier}")

        self.badge = badge_name
        self.tier = tier
        self.completed_tasks.clear()

        classes = BADGE_TASKS[badge_name]
        # Only include tasks that meaningfully run at this tier
        self.task_sequence = [cls(tier=tier) for cls in classes]
        self.current_task = self.task_sequence.pop(0)
        self.current_task.start()

        print(f"[Badge] {badge_name} ({tier}) → {self.current_task.__class__.__name__}")

    # ---------- Update loop ----------
    def update(self, inputs):
        if self.current_task is None:
            return None

        result = self.current_task.update(inputs)

        if result.status == "completed":
            self.completed_tasks.append(self.current_task.__class__.__name__)
            self.current_task.stop()
            if self.task_sequence:
                self.current_task = self.task_sequence.pop(0)
                self.current_task.start()
                # Return a “badge_progress” result; caller can observe events
                return result
            else:
                self.current_task = None
                return result
        return result

    # ---------- Accessors used by main.py / GCS ----------
    @property
    def active_task(self):
        return self.current_task

    @property
    def active_mission(self):
        """Backwards-compatible alias for main.py."""
        return self.current_task

    def stop(self):
        if self.current_task is not None:
            self.current_task.stop()
        self.current_task = None
        self.task_sequence.clear()
        self.badge = None