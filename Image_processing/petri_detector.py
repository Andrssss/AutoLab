# Image_processing/petri_detector.py
import cv2
import numpy as np

class PetriDetector:
    """
    Detects a round or rectangular Petri dish and returns a binary mask.
    Modes: 'round', 'rectangle', or 'auto'
    - Auto tries both and picks the higher-confidence result (rectangle preferred on ties).
    """
    def __init__(self, mode: str = "round"):
        self.mode = mode  # 'round' | 'rectangle' | 'auto'
        self.blur = 7
        self.sensitivity = 30
        self._last_metrics = {}  # debug/telemetry

    def set_params(self, blur: int, sensitivity: int):
        if blur % 2 == 0:
            blur += 1
        self.blur = max(3, blur)
        self.sensitivity = int(np.clip(sensitivity, 1, 100))

    def set_mode(self, mode: str):
        mode = (mode or "").lower()
        if mode not in ("round", "rectangle", "auto"):
            mode = "round"
        self.mode = mode

    # Optional: fetch latest metrics (for logging/QA)
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

        # Map sensitivity 1..100 to Canny thresholds
        s = np.interp(self.sensitivity, [1, 100], [50, 150]).astype(np.float32)
        canny_low = int(s)
        canny_high = int(s * 2)
        edges = cv2.Canny(gray, canny_low, canny_high)

        # Dispatch by mode
        if self.mode == "round":
            mask, score, metrics = self._detect_round(gray, edges, (h, w))
        elif self.mode == "rectangle":
            mask, score, metrics = self._detect_rectangle(gray, edges, (h, w))
        else:  # auto (prefer rectangle on ties)
            r_mask, r_score, r_metrics = self._detect_round(gray, edges, (h, w))
            q_mask, q_score, q_metrics = self._detect_rectangle(gray, edges, (h, w))

            if r_mask is None and q_mask is None:
                mask, score, metrics = None, -1.0, {"mode": "auto", "picked": "none"}
            elif q_mask is not None and (r_mask is None or q_score >= r_score):
                mask, score, metrics = q_mask, q_score, {"mode": "auto", "picked": "rectangle", **q_metrics}
            else:
                mask, score, metrics = r_mask, r_score, {"mode": "auto", "picked": "round", **r_metrics}

        if mask is None:
            self._last_metrics = {"result": "none", "mode": self.mode}
            return None

        # Clean mask a bit
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

        # Keep telemetry
        metrics = dict(metrics)
        metrics.update({"score": float(score), "mode": self.mode})
        self._last_metrics = metrics
        return mask

    # ---------------------- internals ----------------------

    def _detect_round(self, gray, edges, hw):
        h, w = hw
        dp = 1.2
        min_dist = int(min(h, w) * 0.25)
        # For Hough, lower param2 -> more sensitive; map inversely to our "sensitivity"
        param2 = int(np.interp(self.sensitivity, [1, 100], [15, 40]))
        min_r = int(min(h, w) * 0.25)
        max_r = int(min(h, w) * 0.90 // 2)

        mask = np.zeros_like(gray, dtype=np.uint8)
        best_score = -1.0
        best_circle = None

        circles = cv2.HoughCircles(
            gray, cv2.HOUGH_GRADIENT, dp=dp, minDist=min_dist,
            param1=150, param2=param2, minRadius=min_r, maxRadius=max_r
        )

        if circles is not None and len(circles) > 0:
            circles = np.uint16(np.around(circles[0, :]))
            # Score each circle: prefer centered & large
            cx, cy = w / 2, h / 2
            for c in circles:
                x, y, r = int(c[0]), int(c[1]), int(c[2])
                area = np.pi * (r ** 2)
                center_off = (x - cx) ** 2 + (y - cy) ** 2
                center_penalty = 1.0 / (1.0 + center_off / (0.1 * (max(h, w) ** 2)))
                score = float(area * center_penalty)
                if score > best_score:
                    best_score = score
                    best_circle = (x, y, r)

        if best_circle is not None:
            x, y, r = best_circle
            cv2.circle(mask, (x, y), r, 255, -1)
            return mask, best_score, {"detector": "round_hough"}

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
        if circ_val < 0.70:  # a bit more permissive to help Auto
            return None, -1.0, {"detector": "round_contour", "reason": "low_circularity", "circularity": float(circ_val)}

        mask = np.zeros_like(gray, dtype=np.uint8)
        cv2.drawContours(mask, [best_cnt], -1, 255, -1)
        return mask, best_score, {"detector": "round_contour", "circularity": float(circ_val)}

    def _detect_rectangle(self, gray, edges, hw):
        h, w = hw

        # Close small gaps and slightly thicken edges to aid contouring
        kernel = np.ones((5, 5), np.uint8)
        edges_proc = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)
        edges_proc = cv2.dilate(edges_proc, kernel, iterations=1)

        contours, _ = cv2.findContours(edges_proc, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None, -1.0, {"detector": "rectangle", "reason": "no_contours"}

        # Must covers 50% of the area, to detect
        min_area = 0.40 * h * w

        # Keep best SOFT and best STRICT separately
        best_soft = {"cnt": None, "score": -1.0, "metrics": {}}
        best_strict = {"cnt": None, "score": -1.0, "metrics": {}}

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < min_area:
                continue

            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)

            # ---------- SOFT (first) ----------
            rect = cv2.minAreaRect(cnt)
            (rw, rh) = rect[1]
            if rw > 0 and rh > 0:
                rect_area = rw * rh
                rectangularity = float(area / (rect_area + 1e-6))
                hull = cv2.convexHull(cnt)
                hull_area = cv2.contourArea(hull) + 1e-6
                solidity = float(area / hull_area)
                ideal_peri = 2.0 * (rw + rh) + 1e-6
                peri_ratio = float(peri / ideal_peri)

                if rectangularity >= 0.60 and solidity >= 0.85 and peri_ratio <= 1.60:
                    soft_score = float(area * rectangularity / (1.0 + max(0.0, peri_ratio - 1.0)))
                    if soft_score > best_soft["score"]:
                        best_soft = {
                            "cnt": cnt,
                            "score": soft_score,
                            "metrics": {
                                "mode": "soft",
                                "rectangularity": float(rectangularity),
                                "solidity": float(solidity),
                                "peri_ratio": float(peri_ratio),
                            },
                        }

            # ---------- STRICT (second) ----------
            if len(approx) == 4 and cv2.isContourConvex(approx):
                pts = approx.reshape(-1, 2)
                pts = self._order_quad(pts)
                angles_ok, mean_angle_dev = self._angles_near_right_stats(pts, tol_deg=15)

                rect_q = cv2.minAreaRect(approx)
                (rqw, rqh) = rect_q[1]
                if rqw > 0 and rqh > 0 and angles_ok:
                    rect_area_q = rqw * rqh
                    rectangularity_q = float(area / (rect_area_q + 1e-6))
                    strict_score = float(area * rectangularity_q / (1.0 + mean_angle_dev / 10.0))
                    if strict_score > best_strict["score"]:
                        best_strict = {
                            "cnt": approx,  # note: approx (quad) rather than full cnt
                            "score": strict_score,
                            "metrics": {
                                "mode": "strict",
                                "rectangularity": float(rectangularity_q),
                                "mean_angle_dev": float(mean_angle_dev),
                            },
                        }

        # ---------- Global selection: SOFT wins if any exists ----------
        picked = best_soft if best_soft["cnt"] is not None else best_strict
        if picked["cnt"] is None:
            return None, -1.0, {"detector": "rectangle", "reason": "no_candidate"}

        mask = np.zeros_like(gray, dtype=np.uint8)
        cv2.drawContours(mask, [picked["cnt"]], -1, 255, -1)

        metrics = dict(picked["metrics"])
        metrics.update({"detector": "rectangle", "picked_mode": picked["metrics"].get("mode", "unknown")})
        return mask, float(picked["score"]), metrics

    @staticmethod
    def _order_quad(pts):
        # roughly TL, TR, BR, BL
        s = pts.sum(axis=1)
        diff = np.diff(pts, axis=1).reshape(-1)
        tl = pts[np.argmin(s)]
        br = pts[np.argmax(s)]
        tr = pts[np.argmin(diff)]
        bl = pts[np.argmax(diff)]
        return np.array([tl, tr, br, bl], dtype=np.int32)

    @staticmethod
    def _angles_near_right_stats(quad, tol_deg=15):
        """
        Returns (ok: bool, mean_abs_deviation_from_90).
        ok if all four angles within ±tol_deg of 90.
        """
        def angle(a, b, c):
            ba = a - b
            bc = c - b
            cosang = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-6)
            cosang = np.clip(cosang, -1.0, 1.0)
            return np.degrees(np.arccos(cosang))

        devs = []
        for i in range(4):
            a = quad[(i - 1) % 4]
            b = quad[i]
            c = quad[(i + 1) % 4]
            ang = angle(a, b, c)
            devs.append(abs(ang - 90.0))

        mean_dev = float(np.mean(devs))
        ok = all(d <= tol_deg for d in devs)
        return ok, mean_dev
