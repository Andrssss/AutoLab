# Image_processing/petri_detector.py
import cv2
import numpy as np

class PetriDetector:
    """
    Detects a round Petri dish and returns a binary mask.
    """
    def __init__(self):
        self.blur = 7
        self.sensitivity = 30
        self._last_metrics = {}

    def set_params(self, blur: int, sensitivity: int):
        if blur % 2 == 0:
            blur += 1
        self.blur = max(3, blur)
        self.sensitivity = int(np.clip(sensitivity, 1, 100))

    def get_last_metrics(self):
        return dict(self._last_metrics)

    def detect(self, bgr_image):
        if bgr_image is None:
            return None

        img = bgr_image
        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.medianBlur(gray, 3)
        gray = cv2.GaussianBlur(gray, (self.blur, self.blur), 0)

        s = np.interp(self.sensitivity, [1, 100], [50, 150]).astype(np.float32)
        canny_low = int(s)
        canny_high = int(s * 2)
        edges = cv2.Canny(gray, canny_low, canny_high)

        mask, score, metrics = self._detect_round(gray, edges, (h, w))

        if mask is None:
            self._last_metrics = {"result": "none"}
            return None

        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

        metrics = dict(metrics)
        metrics.update({"score": float(score)})
        self._last_metrics = metrics
        return mask

    # ---------------------- internals ----------------------

    def _detect_round(self, gray, edges, hw):
        h, w = hw
        dp = 1.2
        min_dist = int(min(h, w) * 0.25)
        param2 = int(np.interp(self.sensitivity, [1, 100], [15, 40]))
        min_r = int(min(h, w) * 0.25)
        max_r = int(min(h, w) * 0.90 // 2)

        mask = np.zeros_like(gray, dtype=np.uint8)
        best_circle = None
        max_radius = -1
        circles = cv2.HoughCircles(
            gray, cv2.HOUGH_GRADIENT, dp=dp, minDist=min_dist,
            param1=150, param2=param2, minRadius=min_r, maxRadius=max_r
        )

        if circles is not None and len(circles) > 0:
            circles = np.uint16(np.around(circles[0, :]))
            for c in circles:
                x, y, r = int(c[0]), int(c[1]), int(c[2])
                if r > max_radius:
                    max_radius = r
                    best_circle = (x, y, r)

        if best_circle is not None:
            x, y, r = best_circle
            cv2.circle(mask, (x, y), r, 255, -1)
            best_score = float(np.pi * (r ** 2))
            return mask, best_score, {"detector": "round_hough", "radius": r}

        # Fallback: contour-based
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None, -1.0, {"detector": "round_contour", "reason": "no_contours"}

        def circularity(cnt):
            area_ = cv2.contourArea(cnt)
            peri = cv2.arcLength(cnt, True)
            if peri == 0:
                return 0
            return 4 * np.pi * area_ / (peri * peri)

        min_area = 0.15 * h * w
        best_cnt, best_score = None, -1.0

        for c in contours:
            area = cv2.contourArea(c)
            if area < min_area:
                continue
            circ = circularity(c)
            score = float(area * circ)
            if score > best_score:
                best_score = score
                best_cnt = c

        if best_cnt is None:
            return None, -1.0, {"detector": "round_contour", "reason": "no_candidate"}

        circ_val = 4 * np.pi * cv2.contourArea(best_cnt) / (cv2.arcLength(best_cnt, True) ** 2 + 1e-6)
        if circ_val < 0.70:
            return None, -1.0, {"detector": "round_contour", "reason": "low_circularity", "circularity": float(circ_val)}

        mask = np.zeros_like(gray, dtype=np.uint8)
        cv2.drawContours(mask, [best_cnt], -1, 255, -1)
        return mask, best_score, {"detector": "round_contour", "circularity": float(circ_val)}
