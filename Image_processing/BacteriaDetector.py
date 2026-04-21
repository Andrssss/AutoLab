import cv2
import numpy as np


class BacteriaDetector:
    """
    HSV threshold -> contour detection -> area filter.
    Produces:
      - overlay image (contours + labels)
      - centers: list[(x, y)] in *image coordinates*
      - stats per object (area, center, contour)
    """
    def __init__(self):
        self.size_min = 100
        self.size_max = 99999

        # HSV filtering parameters
        self.saturation_min = 50
        self.value_min = 50

    def set_params(self, saturation_min=50, value_min=50):
        self.saturation_min = int(saturation_min)
        self.value_min = int(value_min)

    def _centroid(self, contour):
        m = cv2.moments(contour)
        if m["m00"] == 0:
            return None
        cx = int(m["m10"] / m["m00"])
        cy = int(m["m01"] / m["m00"])
        return (cx, cy)

    # ===================== Main Detection =====================

    def detect(self, image_bgr, full_mask, roi_rect=None):
        if image_bgr is None:
            return None, [], []

        H, W = image_bgr.shape[:2]
        if roi_rect is None:
            x, y, w, h = 0, 0, W, H
        else:
            x, y, w, h = roi_rect

        roi_img = image_bgr[y:y+h, x:x+w]
        if roi_img.size == 0:
            return image_bgr.copy(), [], []

        roi_mask = None
        if full_mask is not None:
            if roi_rect is None:
                roi_mask = full_mask
            else:
                roi_mask = full_mask[y:y+h, x:x+w]

        hsv = cv2.cvtColor(roi_img, cv2.COLOR_BGR2HSV)

        overlay = image_bgr.copy()
        object_id = 1
        centers = []
        objects = []

        lower = np.array([0, self.saturation_min, self.value_min], dtype=np.uint8)
        upper = np.array([179, 255, 255], dtype=np.uint8)
        mask = cv2.inRange(hsv, lower, upper)

        if roi_mask is not None:
            mask = cv2.bitwise_and(mask, roi_mask)

        if np.count_nonzero(mask) == 0:
            return overlay, centers, objects

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if not (self.size_min <= area <= self.size_max):
                continue

            cnt_full = cnt + np.array([[x, y]])
            cv2.drawContours(overlay, [cnt_full], -1, (0, 255, 0), 2)

            cxcy = self._centroid(cnt)
            if cxcy is not None:
                cx, cy = cxcy
                cx_full, cy_full = x + cx, y + cy
                centers.append((cx_full, cy_full))
                cv2.circle(overlay, (cx_full, cy_full), 4, (0, 255, 0), 2)
                cv2.putText(overlay, f"ID:{object_id}", (cx_full + 5, cy_full - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)

            objects.append({
                "id": object_id,
                "area": float(area),
                "center": (cx_full, cy_full) if cxcy else None,
                "contour": cnt_full.squeeze(1).tolist()
            })
            object_id += 1

        # total count label
        cv2.putText(overlay, f"Total: {len(objects)}", (10, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        return overlay, centers, objects
