# Image_processing/petri_detector.py
import cv2
import numpy as np

class PetriDetector:
    def __init__(self):
        self.blur = 7
        self.sensitivity = 30

    def set_params(self, blur: int, sensitivity: int):
        if blur % 2 == 0:
            blur += 1
        self.blur = max(3, blur)
        self.sensitivity = int(np.clip(sensitivity, 1, 100))


    def detect(self, bgr_image):
        if bgr_image is None:
            return None

        # Előfeldolgozás: szürkeárnyalatosítás és zajcsökkentés
        h, w = bgr_image.shape[:2]
        gray = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2GRAY)
        gray = cv2.medianBlur(gray, 3)
        gray = cv2.GaussianBlur(gray, (self.blur, self.blur), 0)

        
        param2 = int(np.interp(self.sensitivity, [1, 100], [20, 45]))
        min_r = int(min(h, w) * 0.2)
        max_r = int(min(h, w) * 0.45)
        min_dist = int(min(h, w) * 0.25)

        # körök detektálása
        circles = cv2.HoughCircles(
            gray, 
            cv2.HOUGH_GRADIENT, 
            dp=1.3,
            minDist=min_dist,
            param1=150,
            param2=param2, 
            minRadius=min_r, 
            maxRadius=max_r
        )

        if circles is None:
            return None

        # Legnagyobb kör kiválasztása
        best = max(circles[0], key=lambda c: c[2])

        # mask rajzolása
        mask = np.zeros_like(gray, dtype=np.uint8)
        cv2.circle(mask, (int(best[0]), int(best[1])), int(best[2]), 255, -1)

        return mask
