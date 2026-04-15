import cv2
import numpy as np


class BacteriaDetector:
    """
    HSV threshold -> morph clean -> distance transform -> watershed split.
    Filters by contour area ranges. Produces:
      - overlay image (contours + labels)
      - centers: list[(x, y)] in *image coordinates*
      - stats per object (area, bbox)
    """
    def __init__(self):
        self.size_min = 100
        self.size_max = 99999
        self.split_threshold = 40.0   # percent of dist.max used for seeds

        # HSV filtering parameters
        self.saturation_min = 50   # Minimum saturation value
        self.value_min = 50        # Minimum value (brightness)

    def set_params(self, split_threshold=40,
                   saturation_min=50, value_min=50,
                   **_kwargs):
        self.split_threshold = float(split_threshold)
        self.saturation_min = int(saturation_min)
        self.value_min = int(value_min)

    def _centroid(self, contour):
        m = cv2.moments(contour)
        if m["m00"] == 0:
            return None
        cx = int(m["m10"] / m["m00"])
        cy = int(m["m01"] / m["m00"])
        return (cx, cy)

    def export_csv(self, objects, path):
        """Export detected objects list to CSV. `objects` is list of dicts as returned by detect()."""
        import csv
        fields = ["id", "area", "bbox_x", "bbox_y", "bbox_w", "bbox_h", "center_x", "center_y"]
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(fields)
            for obj in objects:
                bbox = obj.get("bbox", (0, 0, 0, 0))
                cx, cy = obj.get("center", (None, None))
                writer.writerow([
                    obj.get("id"),
                    obj.get("area"),
                    bbox[0], bbox[1], bbox[2], bbox[3],
                    cx if cx is not None else "", cy if cy is not None else "",
                ])

    # ===================== Main Detection =====================

    def detect(self, image_bgr, full_mask, roi_rect=None):
        if image_bgr is None:
            return None, [], []

        H, W = image_bgr.shape[:2]
        if roi_rect is None:
            if full_mask is not None:
                x, y, w, h = cv2.boundingRect(full_mask)
            else:
                x, y, w, h = 0, 0, W, H
        else:
            x, y, w, h = roi_rect

        roi_img = image_bgr[y:y+h, x:x+w]
        if roi_img.size == 0:
            return image_bgr.copy(), [], []

        roi_mask = None
        if full_mask is not None:
            roi_mask = full_mask[y:y+h, x:x+w]

        hsv = cv2.cvtColor(roi_img, cv2.COLOR_BGR2HSV)

        overlay = image_bgr.copy()
        object_id = 1
        centers = []
        objects = []

        # single combined mask: saturation >= min AND value >= min
        lower = np.array([0, self.saturation_min, self.value_min], dtype=np.uint8)
        upper = np.array([179, 255, 255], dtype=np.uint8)
        final_mask = cv2.inRange(hsv, lower, upper)

        close_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        open_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        final_mask = cv2.morphologyEx(final_mask, cv2.MORPH_CLOSE, close_kernel)
        final_mask = cv2.morphologyEx(final_mask, cv2.MORPH_OPEN, open_kernel)

        if roi_mask is not None:
            final_mask = np.bitwise_and(final_mask, roi_mask)

        if np.count_nonzero(final_mask) == 0:
            return overlay, centers, objects

        # split merged blobs via distance transform peaks + watershed
        dist = cv2.distanceTransform(final_mask, cv2.DIST_L2, 5).astype(np.float32)
        if np.max(dist) > 0:
            thresh_val = (self.split_threshold / 100.0) * float(np.max(dist))
        else:
            thresh_val = 0.5
        sure_fg = np.where(dist > thresh_val, 255, 0).astype(np.uint8)

        if np.count_nonzero(sure_fg) == 0:
            sure_fg = final_mask.copy()

        unknown = final_mask.astype(int) - sure_fg.astype(int)
        unknown = np.clip(unknown, 0, 255).astype(np.uint8)

        num_labels, labels = cv2.connectedComponents(sure_fg)
        markers = (labels + 1).astype(np.int32)
        markers[unknown == 0] = 0

        if np.max(markers) < 2:
            ws_mask = sure_fg.copy()
        else:
            ws_in = roi_img.copy()
            cv2.watershed(ws_in, markers)
            ws_mask = np.zeros_like(final_mask)
            ws_mask[markers > 1] = 255

        contour_color = (0, 255, 0)  # green for all colonies
        contours, _ = cv2.findContours(ws_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            area = cv2.contourArea(cnt)

            if not (self.size_min <= area <= self.size_max):
                continue

            cnt_full = cnt + np.array([[x, y]])
            cv2.drawContours(overlay, [cnt_full], -1, contour_color, 2)

            cxcy = self._centroid(cnt)
            if cxcy is not None:
                cx, cy = cxcy
                cx_full, cy_full = x + cx, y + cy
                centers.append((cx_full, cy_full))
                cv2.circle(overlay, (cx_full, cy_full), 4, contour_color, 2)

            bx, by, bw, bh = cv2.boundingRect(cnt)
            bx_full, by_full = x + bx, y + by
            label = f"ID:{object_id}"
            cv2.putText(overlay, label, (bx_full, by_full - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, contour_color, 1)

            obj = {
                "id": object_id,
                "area": float(area),
                "bbox": (bx_full, by_full, bw, bh),
                "center": (cx_full, cy_full) if cxcy else None,
                "contour": cnt_full.squeeze(1).tolist()
            }

            objects.append(obj)
            object_id += 1

        # total count label
        cv2.putText(overlay, f"Total: {len(objects)}", (10, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        return overlay, centers, objects
