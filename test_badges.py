import time

from missions.task_1_safe_passage   import SafePassageTask
from missions.task_2_emergency_sprint import EmergencySprintTask
from missions.task_3_marina         import MarinaTask
from missions.task_4_delivery       import DeliveryRunTask
from missions.task_5_dynamic        import DynamicResponseTask
from missions.mission_manager       import MissionManager

TIMEOUT_OVERRIDES = {
    SafePassageTask: {
        "CIRCLE_TIMEOUT_S": 2.0,
        "TRANSIT_TIMEOUT_S": 3.0,
    },
    EmergencySprintTask: {
        "CIRCLE_TIMEOUT_S": 2.0,
        "EXIT_TIMEOUT_S":   3.0,
    },
    MarinaTask: {
        "ENTER_TIMEOUT_S": 1.0, "SELECT_TIMEOUT_S": 2.0,
        "APPROACH_TIMEOUT_S": 1.0, "DOCK_TIMEOUT_S": 1.0,
        "FIRE_TIMEOUT_S": 1.0, "FLASH_TIMEOUT_S": 2.0,
        "DELIVER_TIMEOUT_S": 2.0,
    },
    DeliveryRunTask: {
        "SEARCH_TIMEOUT_S": 3.0, "ALIGN_TIMEOUT_S": 1.0,
        "DELIVERY_TIMEOUT_S": 1.0,
    },
    DynamicResponseTask: {
        "RALLY_TIMEOUT_S": 2.0, "BADGE_TIMEOUT_S": 3.0,
    },
}


def apply_overrides(m):
    for k, v in TIMEOUT_OVERRIDES.get(type(m), {}).items():
        setattr(m, k, v)


def run_task(task_cls, name, tier, inputs_fn, max_steps=500):
    m = task_cls(tier=tier)
    apply_overrides(m)
    m.start()
    t = time.time()
    for i in range(max_steps):
        inputs = {"time": t, "heading": 0.0, "position": (0.0, 0.0),
                  "detections": [], "frame_width": 640}
        extra = inputs_fn(i, t, m)
        if extra:
            inputs.update(extra)
        r = m.update(inputs)
        if r.status == "completed":
            print(f"{name:30s} [{tier:10s}] DONE in {i:4d} steps ({r.message})")
            m.stop()
            return True
        t += 0.1
    print(f"{name:30s} [{tier:10s}] STUCK state={m.state}")
    m.stop()
    return False


# ---------- per-task simulators ----------
def sim_task1(i, t, m):
    if m.state == "SEARCHING_ENTRY" and i > 1:
        return {"entry_buoy": {"center": (100, 100)}}
    if m.state == "TRANSITING":
        return {"exit_buoy_ahead": i > 50}
    return {}

def sim_task2(i, t, m):
    if m.state == "FINDING_START" and i > 1:
        if m.tier == "disruptive":
            return {"pinger_frequency_hz": 800.0}
        return {"start_green_detected": True}
    if m.state == "SEEKING_TARGET" and i > 2:
        return {"target_buoy": {"color": "red", "position": (50, 50)}}
    if m.state == "EXITING" and m.tier in ("advanced", "disruptive"):
        return {"pinger_frequency_hz": 800.0, "end_pinger_acquired": True}
    if m.state == "EXITING":
        return {"exit_complete": i > 100}
    return {}

def sim_task3(i, t, m):
    if m.state == "ENTERING_MARINA" and i > 1:
        return {"marina_entered": True}
    if m.state == "SELECTING_SLIP":
        return {"slips": [{"slip_number": 2, "color": "green",
                           "available": True}]}
    if m.state == "APPROACHING_SLIP" and i > 5:
        return {"at_slip_approach": True}
    if m.state == "DOCKING" and i > 8:
        return {"docking_complete": True}
    if m.state == "FIRE_FIGHTING" and i > 12:
        return {"fire_extinguished": True}
    if m.state == "READING_FLASH" and i > 14:
        return {"flash_sequence": ["red", "blue"]}
    if m.state == "DELIVERING" and i > 18:
        return {"delivery_complete": True}
    return {}

def sim_task4(i, t, m):
    if m.state == "AWAITING_ASSIGNMENT" and i == 2:
        return {"robo_command_assignment": ["triangle"]}
    if m.state == "SEARCHING":
        return {"coprolast_detections": [{"shape": "triangle",
                                          "center": (100, 100)}]}
    if m.state == "ALIGNING" and i > 4:
        return {"aligned_for_delivery": True}
    if m.state == "DELIVERING" and i > 6:
        return {"delivery_complete": True}
    return {}

def sim_task5(i, t, m):
    if m.state == "STANDBY" and i == 2:
        if m.tier == "core":
            return {"robo_command_rally_point": (0.5, 0.5)}
        return {"robo_command_badge": "assessment_discovery",
                "partner_ready": True}
    if m.state == "RALLYING" and i > 6:
        return {"rally_complete": True}
    if m.state == "RESPONDING" and i > 10:
        return {"badge_complete": True}
    return {}


# ---------- badge orchestrator test ----------
def run_badge(badge_name, tier, max_steps=400):
    mgr = MissionManager()
    mgr.start_badge(badge_name, tier)
    # Override all live task instance timeouts
    for t in ([mgr.current_task] + mgr.task_sequence):
        apply_overrides(t)
    t = time.time()
    sim_map = {
        "SafePassageTask": sim_task1,
        "EmergencySprintTask": sim_task2,
        "MarinaTask": sim_task3,
        "DeliveryRunTask": sim_task4,
        "DynamicResponseTask": sim_task5,
    }
    for i in range(max_steps):
        if mgr.active_task is None:
            print(f"BADGE {badge_name:25s} [{tier:10s}] DONE")
            return True
        inputs = {"time": t, "heading": 0.0, "position": (0.0, 0.0),
                  "detections": [], "frame_width": 640}
        fn = sim_map[mgr.active_task.__class__.__name__]
        inputs.update(fn(i, t, mgr.active_task))
        mgr.update(inputs)
        t += 0.1
    print(f"BADGE {badge_name} [{tier}] STUCK at {mgr.active_task.__class__.__name__}")
    return False


if __name__ == "__main__":
    results = []
    # Task-level smoke tests across tiers
    for tier in ("core", "advanced", "disruptive"):
        results.append(run_task(SafePassageTask,   "Task1 SafePassage", tier, sim_task1))
        results.append(run_task(EmergencySprintTask,"Task2 Sprint",     tier, sim_task2))
        results.append(run_task(MarinaTask,        "Task3 Marina",     tier, sim_task3))
        results.append(run_task(DeliveryRunTask,   "Task4 Delivery",   tier, sim_task4))
        results.append(run_task(DynamicResponseTask,"Task5 Dynamic",   tier, sim_task5))

    # Badge orchestration
    for badge in ("assessment_discovery", "automated_logistics", "dynamic_tasking"):
        results.append(run_badge(badge, "core"))

    print()
    if all(results):
        print(f"ALL {len(results)} TESTS PASSED ✅")
        raise SystemExit(0)
    failed = [i for i, ok in enumerate(results) if not ok]
    print(f"FAILED: {failed} ❌")
    raise SystemExit(1)