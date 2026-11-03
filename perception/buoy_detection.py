import cv2
import numpy as np

from config import HSV_RANGES, MIN_CONTOUR_AREA


class BuoyDetector:

    def detect(self, frame):

        hsv = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2HSV
        )

        detections = []

        for color, ranges in HSV_RANGES.items():

            mask = np.zeros(
                hsv.shape[:2],
                dtype=np.uint8
            )

            for lower, upper in ranges:

                lower = np.array(lower)
                upper = np.array(upper)

                current_mask = cv2.inRange(
                    hsv,
                    lower,
                    upper
                )

                mask = cv2.bitwise_or(mask, current_mask)

            kernel = np.ones((5, 5), np.uint8)

            mask = cv2.morphologyEx(
                mask, cv2.MORPH_OPEN, kernel
            )

            mask = cv2.morphologyEx(
                mask, cv2.MORPH_CLOSE, kernel
            )

            contours, _ = cv2.findContours(
                mask,
                cv2.RETR_EXTERNAL,
                cv2.CHAIN_APPROX_SIMPLE
            )

            for contour in contours:

                area = cv2.contourArea(contour)

                if area < MIN_CONTOUR_AREA:
                    continue

                x, y, w, h = cv2.boundingRect(contour)

                detections.append({
                    "color": color,
                    "bbox": (x, y, w, h),
                    "center": (x + w // 2, y + h // 2),
                    "area": area
                })

        return detections

    def draw(self, frame, detections):

        colors = {
            "red": (0, 0, 255),
            "green": (0, 255, 0),
            "yellow": (0, 255, 255),
            "black": (255, 255, 255)
        }

        for detection in detections:

            x, y, w, h = detection["bbox"]

            color = colors[detection["color"]]

            cv2.rectangle(
                frame, (x, y), (x + w, y + h), color, 2
            )

            cv2.putText(
                frame,
                detection["color"],
                (x, y - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6, color, 2
            )

        return frame