class ObjectDetector:

    def __init__(self, model_path=None):

        self.model = None

        if model_path:

            try:
                from ultralytics import YOLO
                self.model = YOLO(model_path)

            except ImportError:
                raise RuntimeError(
                    "Install ultralytics to use YOLO:  "
                    "pip install ultralytics"
                )

    def detect(self, frame):

        if self.model is None:
            return []

        results = self.model.predict(frame, verbose=False)

        detections = []

        for result in results:

            for box in result.boxes:

                x1, y1, x2, y2 = (
                    box.xyxy[0].cpu().numpy()
                )

                detections.append({
                    "class_id": int(box.cls[0]),
                    "confidence": float(box.conf[0]),
                    "bbox": (int(x1), int(y1), int(x2), int(y2))
                })

        return detections