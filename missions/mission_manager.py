from missions.mission_1_evacuation import EvacuationMission
from missions.mission_2_debris import DebrisMission
from missions.mission_3_sprint import SprintMission
from missions.mission_4_supply import SupplyMission
from missions.mission_5_marina import MarinaMission
from missions.mission_6_harbor_alert import HarborAlertMission


class MissionManager:

    def __init__(self):

        self.missions = {
            1: EvacuationMission(),
            2: DebrisMission(),
            3: SprintMission(),
            4: SupplyMission(),
            5: MarinaMission(),
            6: HarborAlertMission()
        }

        self.active_mission = None

    def start_mission(self, mission_number):

        if mission_number not in self.missions:
            raise ValueError("Invalid mission number")

        self.active_mission = self.missions[mission_number]
        self.active_mission.start()

        print(f"Mission {mission_number} started")

    def update(self, inputs):

        if self.active_mission is None:
            return None

        return self.active_mission.update(inputs)

    def stop(self):

        if self.active_mission is not None:
            self.active_mission.stop()

        self.active_mission = None