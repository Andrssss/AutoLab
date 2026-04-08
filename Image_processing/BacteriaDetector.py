import cv2
import numpy as np
import os


class BacteriaDetector:
    """
    HSV threshold -> morph clean -> distance transform -> watershed split.
    Filters by contour area ranges. Produces:
      - overlay image (contours + labels)
      - centers: list[(x, y)] in *image coordinates*
      - stats per object (area, bbox)
    """
    def __init__(self):
        self.size_ranges = [(100, 500), (500, 1500), (1500, 99999)]
        self.split_threshold = 40.0   # percent of dist.max used for seeds

        # HSV filtering parameters
        self.saturation_min = 50   # Minimum saturation value
        self.value_min = 50        # Minimum value (brightness)

        # Morphological operation parameters
        self.morph_close_radius = 2
        self.morph_open_radius = 1

        # texture & edge options
        self.use_texture = False
        self.use_edge_split = False

        # file outputs live next to this source by default
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.pictures_dir = os.path.join(self.script_dir, "pictures")
        os.makedirs(self.pictures_dir, exist_ok=True)

    def set_params(self, size_ranges=None, split_threshold=40,
                   saturation_min=50, value_min=50, morph_close_radius=2, morph_open_radius=1,
                   use_texture=False, use_edge_split=False, **_kwargs):
        if size_ranges is not None:
            self.size_ranges = size_ranges
        self.split_threshold = float(split_threshold)
        self.saturation_min = int(saturation_min)
        self.value_min = int(value_min)
        self.morph_close_radius = int(morph_close_radius)
        self.morph_open_radius = int(morph_open_radius)
        self.use_texture = bool(use_texture)
        self.use_edge_split = bool(use_edge_split)

    def _centroid(self, contour):
        m = cv2.moments(contour)
        if m["m00"] == 0:
            return None
        cx = int(m["m10"] / m["m00"])
        cy = int(m["m01"] / m["m00"])
        return (cx, cy)

    # ===================== SimpleITK/cv2 Wrappers =====================
    # Practical approach: use cv2 for core image processing (blur, morphology, distance, connected components)
    # as they're proven reliable. SimpleITK is imported for future enhancements.

    def _sitk_morphology(self, mask_array, operation='close', radius=2):
        """Apply morphological operations using cv2 (more reliable)."""
        # Use cv2 for morphology - it's well-tested and reliable
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2*radius+1, 2*radius+1))
        
        if operation == 'close':
            return cv2.morphologyEx(mask_array, cv2.MORPH_CLOSE, kernel)
        elif operation == 'open':
            return cv2.morphologyEx(mask_array, cv2.MORPH_OPEN, kernel)
        else:
            return mask_array

    def _sitk_distance_transform(self, mask_array):
        """Apply distance transform using cv2 (proven to work reliably)."""
        return cv2.distanceTransform(mask_array, cv2.DIST_L2, 5).astype(np.float32)

    def _sitk_connected_components(self, mask_array):
        """Apply connected components using cv2 (proven to work reliably)."""
        num_labels, labels = cv2.connectedComponents(mask_array)
        return labels.astype(np.uint32)

    def _extract_texture_features(self, gray_img, contour):
        """
        Compute simple texture features for a contour region: local variance and mean gradient magnitude.
        Returns dict with `var` and `grad_mean`.
        """
        x, y, w, h = cv2.boundingRect(contour)
        patch = gray_img[y:y+h, x:x+w]
        if patch.size == 0:
            return {"var": 0.0, "grad_mean": 0.0}

        # local intensity variance
        var = float(np.var(patch.astype(np.float32)))

        # gradient magnitude mean
        gx = cv2.Sobel(patch, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(patch, cv2.CV_32F, 0, 1, ksize=3)
        mag = np.sqrt(gx * gx + gy * gy)
        grad_mean = float(np.mean(mag))

        return {"var": var, "grad_mean": grad_mean}

    def _adaptive_kernel_radius(self, areas):
        """Return an adaptive morphology radius based on median object area (sqrt(area) heuristic)."""
        if len(areas) == 0:
            return max(1, self.morph_close_radius)
        med = np.median(np.array(areas))
        # heuristic: radius ~ sqrt(area)/40 (empirical), clamp to 1..20
        radius = int(max(1, min(20, round(np.sqrt(med) / 40))))
        return radius

    def export_csv(self, objects, path):
        """Export detected objects list to CSV. `objects` is list of dicts as returned by detect()."""
        import csv
        fields = ["id", "area", "bbox_x", "bbox_y", "bbox_w", "bbox_h", "center_x", "center_y", "texture_var", "texture_grad_mean"]
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(fields)
            for obj in objects:
                bbox = obj.get("bbox", (0, 0, 0, 0))
                cx, cy = obj.get("center", (None, None))
                tex = obj.get("texture", {})
                writer.writerow([
                    obj.get("id"),
                    obj.get("area"),
                    bbox[0], bbox[1], bbox[2], bbox[3],
                    cx if cx is not None else "", cy if cy is not None else "",
                    tex.get("var", ""), tex.get("grad_mean", "")
                ])

    # ===================== Main Detection =====================

    def detect(self, image_bgr, full_mask, roi_rect=None, save_debug=False, save_dir=None, prefix=""):
        if image_bgr is None:
            return None, [], [], []

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
            return image_bgr.copy(), [], [], []

        roi_mask = None
        if full_mask is not None:
            roi_mask = full_mask[y:y+h, x:x+w]

        blurred = cv2.GaussianBlur(roi_img, (5, 5), 0)
        hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
        gray = cv2.cvtColor(blurred, cv2.COLOR_BGR2GRAY)

        overlay = image_bgr.copy()
        object_id = 1
        centers = []
        objects = []

        out_dir = save_dir or self.pictures_dir
        if save_debug:
            os.makedirs(out_dir, exist_ok=True)
            cv2.imwrite(os.path.join(out_dir, f"{prefix}hsv_vis.png"), hsv)

        # single combined mask: saturation >= min AND value >= min (no hue filtering)
        lower = np.array([0, self.saturation_min, self.value_min], dtype=np.uint8)
        upper = np.array([179, 255, 255], dtype=np.uint8)
        final_mask = cv2.inRange(hsv, lower, upper)

        # adaptive morph radius estimate based on mask area
        est_area = max(1, np.count_nonzero(final_mask) // 10)
        adaptive_radius = self._adaptive_kernel_radius([est_area])

        final_mask = self._sitk_morphology(final_mask, operation='close', radius=adaptive_radius)
        final_mask = self._sitk_morphology(final_mask, operation='open', radius=self.morph_open_radius)

        if roi_mask is not None:
            final_mask = np.bitwise_and(final_mask, roi_mask)

        if self.use_edge_split:
            edges = cv2.Canny(gray, 40, 120)
            edge_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            edges = cv2.dilate(edges, edge_kernel, iterations=1)
            final_mask = cv2.bitwise_and(final_mask, cv2.bitwise_not(edges))

        if save_debug:
            cv2.imwrite(os.path.join(out_dir, f"{prefix}output_mask.png"), final_mask)

        if np.count_nonzero(final_mask) == 0:
            return overlay, centers, objects, []

        # split merged blobs via distance transform peaks + watershed
        dist = self._sitk_distance_transform(final_mask)
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

            matched = False
            for amin, amax in self.size_ranges:
                if amin <= area <= amax:
                    matched = True
                    break
            if not matched:
                continue

            tex = {}
            if self.use_texture:
                tex = self._extract_texture_features(gray, cnt)
                if tex.get("var", 0.0) < 10.0 and tex.get("grad_mean", 0.0) < 6.0:
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
            if self.use_texture:
                obj["texture"] = tex
            else:
                obj["texture"] = {}

            objects.append(obj)
            object_id += 1

        # total count label
        cv2.putText(overlay, f"Total: {len(objects)}", (10, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        if save_debug:
            cv2.imwrite(os.path.join(out_dir, f"{prefix}overlay.png"), overlay)

        return overlay, centers, objects, []
