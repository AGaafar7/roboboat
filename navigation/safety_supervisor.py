from navigation.command import NavigationCommand


class SafetySupervisor:

    def __init__(self, max_surge=0.20, max_yaw=0.20):

        self.max_surge = max_surge
        self.max_yaw = max_yaw

        self.emergency_stop_active = False

    def emergency_stop(self):

        self.emergency_stop_active = True

    def reset(self):

        self.emergency_stop_active = False

    def filter_command(self, command):

        if self.emergency_stop_active:

            return NavigationCommand()

        command.surge = max(
            -self.max_surge,
            min(self.max_surge, command.surge)
        )

        command.yaw = max(
            -self.max_yaw,
            min(self.max_yaw, command.yaw)
        )

        return command