import time

from missions.mission_1_evacuation  import EvacuationMission
from missions.mission_2_debris      import DebrisMission
from missions.mission_3_sprint      import SprintMission
from missions.mission_4_supply      import SupplyMission
from missions.mission_5_marina      import MarinaMission
from missions.mission_6_harbor_alert import HarborAlertMission


# ---------------------------------------------------------------
# Timeout overrides.  Applied to the *instance* inside run()
# right before m.start(), so they always win regardless of where
# they'd otherwise be defined.
# ---------------------------------------------------------------
TIMEOUT_OVERRIDES = {
    EvacuationMission: {
        "SEARCH_EXIT_TIMEOUT_S": 2.0,
        "CROSS_EXIT_TIMEOUT_S":  1.0,
        "RETURN_TIMEOUT_S":      2.0,
    },
    DebrisMission: {
        "TRANSIT_TIMEOUT_S": 2.0,
        "SCAN_TIMEOUT_S":    3.0,
        "RETURN_TIMEOUT_S":  2.0,
        "CIRCLE_TIMEOUT_S":  2.0,
    },
    SprintMission: {
        "CIRCLE_TIMEOUT_S": 3.0,
        "EXIT_TIMEOUT_S":   3.0,
    },
    SupplyMission: {
        "SEARCH_TIMEOUT_S":    5.0,
        "POST_DELIVER_WINDOW": 3.0,
        "ALIGN_TIMEOUT_S":     2.0,
        "DELIVERY_TIMEOUT_S":  2.0,
    },
    MarinaMission: {
        "ENTER_TIMEOUT_S":    2.0,
        "SELECT_TIMEOUT_S":   3.0,
        "APPROACH_TIMEOUT_S": 2.0,
        "DOCK_TIMEOUT_S":     2.0,
    },
    HarborAlertMission: {
        "RESPOND_TIMEOUT_S": 3.0,
    },
}


def apply_overrides(m):
    for k, v in TIMEOUT_OVERRIDES.get(type(m), {}).items():
        setattr(m, k, v)


def run(m, name, extra_inputs=None, max_steps=2000):
    apply_overrides(m)
    m.start()
    t = time.time()
    for i in range(max_steps):
        inputs = {
            "time": t,
            "heading": 0.0,
            "position": None,
            "detections": [],
            "audio_alert": None,
        }
        if extra_inputs:
            inputs.update(extra_inputs(i, t, m) or {})
        r = m.update(inputs)
        if r.status == "completed":
            print(f"{name:10s} COMPLETED in {i:4d} steps  ({r.message})")
            m.stop()
            return True
        t += 0.1

    print(f"{name:10s} DID NOT COMPLETE  (state={m.state})")
    for k in TIMEOUT_OVERRIDES.get(type(m), {}):
        print(f"     {k} = {getattr(m, k)}")
    m.stop()
    return False


# ---------------------------------------------------------------
# Per-mission input simulations
# ---------------------------------------------------------------
def m1_inputs(i, t, m):
    if m.state == "WAITING_FOR_GATE" and i > 2:
        return {"gate_detected": True}
    if m.state == "APPROACHING_GATE":
        return {"gate_entry": True}
    if m.state == "CROSSING_ENTRY":
        return {"gate_passed": True}
    if m.state == "SEARCHING_EXIT_GATE":
        return {"exit_gate_detected": True}
    if m.state == "CROSSING_EXIT":
        return {"exit_gate_passed": True}
    return {}

def m2_inputs(i, t, m):
    if m.state == "ENTER_CHANNEL" and i > 2:
        return {"channel_entered": True}
    return {}

def m3_inputs(i, t, m):
    if m.state == "WAITING_FOR_GATE" and i > 2:
        return {"gate_detected": True}
    if m.state == "CROSSING_GATE":
        return {"gate_passed": True}
    if m.state == "FINDING_TARGET":
        return {"yellow_target": {"position": (320, 240),
                                  "indicator_color": "red"}}
    return {}

def m6_inputs(i, t, m):
    if m.state == "LISTENING" and i == 5:
        return {"audio_alert": {"blast_count": 1,
                                "frequency": 800.0,
                                "detection_time": t}}
    return {}


if __name__ == "__main__":
    results = [
        run(EvacuationMission(),    "Mission 1", m1_inputs),
        run(DebrisMission(),        "Mission 2", m2_inputs),
        run(SprintMission(),        "Mission 3", m3_inputs),
        run(SupplyMission(),        "Mission 4", None),
        run(MarinaMission(),        "Mission 5", None),
        run(HarborAlertMission(),   "Mission 6", m6_inputs),
    ]

    print()
    if all(results):
        print(f"ALL {len(results)} MISSIONS COMPLETED ✅")
        raise SystemExit(0)
    failed = [i + 1 for i, ok in enumerate(results) if not ok]
    print(f"FAILED MISSIONS: {failed} ❌")
    raise SystemExit(1)