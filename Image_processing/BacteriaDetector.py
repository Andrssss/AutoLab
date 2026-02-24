import cv2
import numpy as np
import os
import SimpleITK as sitk


class BacteriaDetector:
    """
    HSV bandpass per hue-range -> morph clean -> distance transform -> watershed split.
    Filters by contour area ranges. Produces:
      - overlay image (contours + labels + legend)
      - centers: list[(x, y)] in *image coordinates*
      - stats per object (area, bbox, hue_idx)
    """
    def __init__(self):
        # default bins (like your original)
        self.hue_ranges = [(0, 30), (30, 90), (90, 150), (150, 179)]
        self.size_ranges = [(100, 500), (500, 1500), (1500, 99999)]
        self.split_threshold = 40.0   # percent of dist.max used for seeds
        
        # HSV filtering parameters
        self.saturation_min = 50   # Minimum saturation value
        self.value_min = 50        # Minimum value (brightness)
        
        # Morphological operation parameters
        self.morph_close_radius = 2
        self.morph_open_radius = 1

        # advanced options
        # If `hue_centers` is provided (list of hue or (h,s) tuples) the detector
        # will compute soft HS-based masks allowing overlaps between colors.
        self.hue_centers = None
        self.use_hs_soft_assignment = True
        # standard deviation for the gaussian soft assignment in normalized units
        self.soft_assign_sigma = 0.08
        self.soft_assign_prob_thresh = 0.45

        # texture & edge options
        self.use_texture = False
        self.use_edge_split = False
        self.color_calibration = False

        # file outputs live next to this source by default
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.pictures_dir = os.path.join(self.script_dir, "pictures")
        os.makedirs(self.pictures_dir, exist_ok=True) # Creates the folder

    def set_params(self, hue_ranges=None, hue_centers=None, size_ranges=None, split_threshold=40,
                   saturation_min=50, value_min=50, morph_close_radius=2, morph_open_radius=1,
                   use_hs_soft_assignment=True, soft_assign_sigma=0.08, soft_assign_prob_thresh=0.45,
                   use_texture=False, use_edge_split=False, color_calibration=False):
        if hue_ranges is not None:
            self.hue_ranges = hue_ranges
        if hue_centers is not None:
            self.hue_centers = hue_centers
        self.use_hs_soft_assignment = bool(use_hs_soft_assignment)
        self.soft_assign_sigma = float(soft_assign_sigma)
        self.soft_assign_prob_thresh = float(soft_assign_prob_thresh)
        self.use_texture = bool(use_texture)
        self.use_edge_split = bool(use_edge_split)
        self.color_calibration = bool(color_calibration)
        if size_ranges is not None:
            self.size_ranges = size_ranges
        # Keep this as a percentage [0..100]; your original had /20 then /100 again,
        # which made it ~2000x smaller than intended.
        self.split_threshold = float(split_threshold)
        self.saturation_min = int(saturation_min)
        self.value_min = int(value_min)
        self.morph_close_radius = int(morph_close_radius)
        self.morph_open_radius = int(morph_open_radius)

    def _legend_color(self, idx):
        # Dynamic palette with more colors
        palette = [
            (255, 0, 0),        # BGR Red
            (0, 255, 0),        # Green
            (0, 0, 255),        # Blue
            (255, 255, 0),      # Cyan/Yellow
            (255, 0, 255),      # Magenta
            (0, 255, 255),      # Yellow (BGR)
            (255, 128, 0),      # Orange
            (128, 0, 255),      # Purple
            (0, 128, 255),      # Orange-ish
            (255, 255, 128),    # Light blue
        ]
        return palette[idx % len(palette)]

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

    # ===================== New Helpers: Soft HS masks, texture, CSV export =====================
    def _compute_soft_hs_masks(self, hsv_img, centers, sigma=None, prob_thresh=None):
        """
        Compute soft HS-based masks for given centers.
        - hsv_img: HxWx3 uint8 image
        - centers: list of either hue ints or (h,s) tuples (0..179, 0..255)
        Returns list of binary masks (uint8 0/255) allowing overlaps.
        """
        if sigma is None:
            sigma = self.soft_assign_sigma
        if prob_thresh is None:
            prob_thresh = self.soft_assign_prob_thresh

        H = hsv_img[:, :, 0].astype(np.float32)
        S = hsv_img[:, :, 1].astype(np.float32)

        h_norm = H / 179.0
        s_norm = S / 255.0

        masks = []
        for c in centers:
            if isinstance(c, (list, tuple)) and len(c) >= 2:
                ch, cs = float(c[0]), float(c[1])
                chn = ch / 179.0
                csn = cs / 255.0
            else:
                ch = float(c)
                chn = ch / 179.0
                # if center has only hue, approximate ideal saturation at 0.6
                csn = 0.6

            # circular hue distance
            dh = np.abs(h_norm - chn)
            dh = np.minimum(dh, 1.0 - dh)

            # Euclidean distance in (h,s) normalized space
            dist = np.sqrt(dh * dh + (s_norm - csn) ** 2)

            # gaussian probability
            prob = np.exp(-0.5 * (dist / sigma) ** 2)
            mask = (prob >= prob_thresh).astype(np.uint8) * 255
            masks.append(mask)

        return masks

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
        fields = ["id", "hue_idx", "area", "bbox_x", "bbox_y", "bbox_w", "bbox_h", "center_x", "center_y", "texture_var", "texture_grad_mean"]
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(fields)
            for obj in objects:
                bbox = obj.get("bbox", (0, 0, 0, 0))
                cx, cy = obj.get("center", (None, None))
                tex = obj.get("texture", {})
                writer.writerow([
                    obj.get("id"),
                    obj.get("hue_idx"),
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
            # whole dish bbox if mask present, else full image
            if full_mask is not None:
                x, y, w, h = cv2.boundingRect(full_mask)
            else:
                x, y, w, h = 0, 0, W, H
        else:
            x, y, w, h = roi_rect

        # crop working region
        roi_img = image_bgr[y:y+h, x:x+w]
        if roi_img.size == 0:
            return image_bgr.copy(), [], [], []

        roi_mask = None
        if full_mask is not None:
            roi_mask = full_mask[y:y+h, x:x+w]

        # slight blur using cv2 (more reliable) -> HSV using cv2
        blurred = cv2.GaussianBlur(roi_img, (5, 5), 0)
        hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
        gray = cv2.cvtColor(blurred, cv2.COLOR_BGR2GRAY)

        overlay = image_bgr.copy()
        object_id = 1
        category_counts = [0 for _ in self.hue_ranges]
        centers = []
        objects = []

        # choose where to save
        out_dir = save_dir or self.pictures_dir
        if save_debug:
            os.makedirs(out_dir, exist_ok=True)

        # debug: HSV preview
        if save_debug:
            cv2.imwrite(os.path.join(out_dir, f"{prefix}hsv_vis.png"), hsv)

        # Decide masks to process: either explicit hue_ranges or soft HS masks from hue_centers
        masks_to_process = []
        mask_labels = []
        if self.hue_centers is not None and self.use_hs_soft_assignment:
            soft_masks = self._compute_soft_hs_masks(hsv, self.hue_centers,
                                                     sigma=self.soft_assign_sigma,
                                                     prob_thresh=self.soft_assign_prob_thresh)
            for i, m in enumerate(soft_masks):
                masks_to_process.append(m)
                mask_labels.append((i, self.hue_centers[i] if i < len(self.hue_centers) else None))
        else:
            for i, (h_min, h_max) in enumerate(self.hue_ranges):
                lower = np.array([h_min, self.saturation_min, self.value_min], dtype=np.uint8)
                upper = np.array([h_max, 255, 255], dtype=np.uint8)
                hsv_mask = cv2.inRange(hsv, lower, upper)
                masks_to_process.append(hsv_mask)
                mask_labels.append((i, (h_min, h_max)))

        for hue_idx, label_info in enumerate(mask_labels):
            final_mask = masks_to_process[hue_idx]

            # adaptive morph radius estimate based on mask area
            est_area = max(1, np.count_nonzero(final_mask) // 10)
            adaptive_radius = self._adaptive_kernel_radius([est_area])

            # morph clean using SimpleITK (use adaptive radius for closing)
            final_mask = self._sitk_morphology(final_mask, operation='close', radius=adaptive_radius)
            final_mask = self._sitk_morphology(final_mask, operation='open', radius=self.morph_open_radius)

            # limit to dish/ROI
            if roi_mask is not None:
                final_mask = np.bitwise_and(final_mask, roi_mask)

            if save_debug:
                cv2.imwrite(os.path.join(out_dir, f"{prefix}output_hsv_hole_deleted_cat{hue_idx + 1}.png"), final_mask)

            if np.count_nonzero(final_mask) == 0:
                continue

            # --- split merged blobs via distance transform peaks + watershed ---
            dist = self._sitk_distance_transform(final_mask)
            # threshold for "sure" foreground seeds
            if np.max(dist) > 0:
                thresh_val = (self.split_threshold / 100.0) * float(np.max(dist))
            else:
                thresh_val = 0.5
            sure_fg = np.where(dist > thresh_val, 255, 0).astype(np.uint8)

            # If sure_fg is empty, use the final_mask directly
            if np.count_nonzero(sure_fg) == 0:
                sure_fg = final_mask.copy()

            unknown = final_mask.astype(int) - sure_fg.astype(int)
            unknown = np.clip(unknown, 0, 255).astype(np.uint8)

            # connected components using cv2
            num_labels, labels = cv2.connectedComponents(sure_fg)
            markers = (labels + 1).astype(np.int32)
            markers[unknown == 0] = 0

            # Make sure markers are valid for watershed
            if np.max(markers) < 2:
                # If watershed can't work, just use the binary mask
                ws_mask = sure_fg.copy()
            else:
                # Watershed using OpenCV (SimpleITK doesn't have direct watershed equivalent)
                ws_in = roi_img.copy()
                cv2.watershed(ws_in, markers)
                ws_mask = np.zeros_like(final_mask)
                ws_mask[markers > 1] = 255

            contours, _ = cv2.findContours(ws_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for cnt in contours:
                area = cv2.contourArea(cnt)

                # size-range matching
                matched = False
                for size_idx, (amin, amax) in enumerate(self.size_ranges):
                    if amin <= area <= amax:
                        matched = True
                        break
                if not matched:
                    continue

                color = self._legend_color(hue_idx)
                # draw on full overlay (shift contour back to full image coords)
                cnt_full = cnt + np.array([[x, y]])
                cv2.drawContours(overlay, [cnt_full], -1, color, 2)

                # label & center
                cxcy = self._centroid(cnt)
                if cxcy is not None:
                    cx, cy = cxcy
                    cx_full, cy_full = x + cx, y + cy
                    centers.append((cx_full, cy_full))
                    cv2.circle(overlay, (cx_full, cy_full), 4, color, 2)

                bx, by, bw, bh = cv2.boundingRect(cnt)
                bx_full, by_full = x + bx, y + by
                label = f"ID:{object_id}"
                cv2.putText(overlay, label, (bx_full, by_full - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

                obj = {
                    "id": object_id,
                    "hue_idx": hue_idx,
                    "area": float(area),
                    "bbox": (bx_full, by_full, bw, bh),
                    "center": (cx_full, cy_full) if cxcy else None,
                    "contour": cnt_full.squeeze(1).tolist()
                }

                # texture features (optional)
                if self.use_texture:
                    tex = self._extract_texture_features(gray, cnt)
                    obj["texture"] = tex
                else:
                    obj["texture"] = {}

                objects.append(obj)

                object_id += 1
                # ensure category_counts length matches
                if hue_idx >= len(category_counts):
                    # extend category_counts if necessary
                    category_counts.extend([0] * (hue_idx - len(category_counts) + 1))
                category_counts[hue_idx] += 1

        # legend
        y0 = 20
        for idx, count in enumerate(category_counts):
            color = self._legend_color(idx)
            cv2.rectangle(overlay, (10, y0 - 12), (30, y0 + 4), color, -1)
            cv2.putText(overlay,
                        f"Cat {idx+1} ({self.hue_ranges[idx][0]}–{self.hue_ranges[idx][1]}): {count}",
                        (35, y0), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            y0 += 20

        if save_debug:
            cv2.imwrite(os.path.join(out_dir, f"{prefix}overlay.png"), overlay)

        return overlay, centers, objects, category_counts
