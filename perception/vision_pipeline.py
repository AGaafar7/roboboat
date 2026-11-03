import cv2
import numpy as np


class VisionPipeline:

    def __init__(self, min_area=350):

        self.min_area = min_area

        self.color_ranges = {
            "red": [
                (
                    np.array([0, 100, 70]),
                    np.array([10, 255, 255])
                ),
                (
                    np.array([170, 100, 70]),
                    np.array([180, 255, 255])
                )
            ],

            "green": [
                (
                    np.array([35, 60, 50]),
                    np.array([90, 255, 255])
                )
            ],

            "yellow": [
                (
                    np.array([18, 80, 80]),
                    np.array([38, 255, 255])
                )
            ],

            "black": [
                (
                    np.array([0, 0, 0]),
                    np.array([180, 255, 65])
                )
            ]
        }

    def detect(self, frame):

        if frame is None:
            return []

        hsv = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2HSV
        )

        detections = []

        for color, ranges in self.color_ranges.items():

            mask = np.zeros(
                hsv.shape[:2],
                dtype=np.uint8
            )

            for lower, upper in ranges:

                mask |= cv2.inRange(
                    hsv,
                    lower,
                    upper
                )

            kernel = np.ones((5, 5), np.uint8)

            mask = cv2.morphologyEx(
                mask,
                cv2.MORPH_OPEN,
                kernel
            )

            mask = cv2.morphologyEx(
                mask,
                cv2.MORPH_CLOSE,
                kernel
            )

            contours, _ = cv2.findContours(
                mask,
                cv2.RETR_EXTERNAL,
                cv2.CHAIN_APPROX_SIMPLE
            )

            for contour in contours:

                area = cv2.contourArea(contour)

                if area < self.min_area:
                    continue

                x, y, w, h = cv2.boundingRect(contour)

                detections.append({
                    "color": color,
                    "bbox": (x, y, w, h),
                    "center": (
                        x + w // 2,
                        y + h // 2
                    ),
                    "area": float(area)
                })

        return detections

    def draw(self, frame, detections):

        output = frame.copy()

        colors = {
            "red": (0, 0, 255),
            "green": (0, 255, 0),
            "yellow": (0, 255, 255),
            "black": (255, 255, 255)
        }

        for detection in detections:

            x, y, w, h = detection["bbox"]

            color = colors.get(
                detection["color"],
                (255, 255, 255)
            )

            cv2.rectangle(
                output,
                (x, y),
                (x + w, y + h),
                color,
                2
            )

            cv2.putText(
                output,
                detection["color"],
                (x, y - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                color,
                2
            )

        return output