import cv2

from config import (
    CAMERA_WIDTH,
    CAMERA_HEIGHT,
    CAMERA_FPS
)


class CameraManager:

    def __init__(self, front_index=0, secondary_index=1):

        self.front = self.open_camera(front_index)
        self.secondary = self.open_camera(secondary_index)

    def open_camera(self, index):

        camera = cv2.VideoCapture(index)

        camera.set(
            cv2.CAP_PROP_FRAME_WIDTH,
            CAMERA_WIDTH
        )

        camera.set(
            cv2.CAP_PROP_FRAME_HEIGHT,
            CAMERA_HEIGHT
        )

        camera.set(
            cv2.CAP_PROP_FPS,
            CAMERA_FPS
        )

        if not camera.isOpened():
            camera.release()
            raise RuntimeError(
                f"Cannot open camera {index}"
            )

        return camera

    def read(self):

        ret1, frame1 = self.front.read()
        ret2, frame2 = self.secondary.read()

        if not ret1:
            frame1 = None

        if not ret2:
            frame2 = None

        return frame1, frame2

    def release(self):

        self.front.release()
        self.secondary.release()