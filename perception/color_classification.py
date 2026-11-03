import cv2
import numpy as np

from config import HSV_RANGES


class ColorClassifier:

    @staticmethod
    def classify(frame, bbox):

        x, y, w, h = bbox

        roi = frame[y:y+h, x:x+w]

        if roi.size == 0:
            return None

        hsv = cv2.cvtColor(
            roi,
            cv2.COLOR_BGR2HSV
        )

        scores = {}

        for color, ranges in HSV_RANGES.items():

            mask = np.zeros(
                hsv.shape[:2],
                dtype=np.uint8
            )

            for lower, upper in ranges:

                mask |= cv2.inRange(
                    hsv,
                    np.array(lower),
                    np.array(upper)
                )

            scores[color] = np.count_nonzero(mask)

        best_color = max(
            scores,
            key=scores.get
        )

        if scores[best_color] == 0:
            return None

        return best_color