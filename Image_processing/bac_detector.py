import cv2
import numpy as np

class BacteriaDetector:
    def __init__(self):
        self.hue_ranges = [(0, 30), (30, 90), (90, 150), (150, 179)]  # Default hue categories
        self.size_ranges = [(100, 500), (500, 1500), (1500, 99999)]   # Size categories

    def set_params(self, hue_ranges, size_ranges, split_threshold=40):
        self.hue_ranges = hue_ranges
        self.size_ranges = size_ranges
        self.split_threshold = split_threshold

    def detect(self, image, mask):
        if image is None or mask is None:
            return image

        # Optional: apply slight blur to reduce noise
        blurred = cv2.GaussianBlur(image, (5, 5), 0)
        hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)

        output = image.copy()
        object_id = 1
        category_counts = [0 for _ in self.hue_ranges]

        # Display color per hue range
        colors = {
            0: (255, 0, 0),     # Red
            1: (0, 255, 0),     # Green
            2: (0, 0, 255),     # Blue
            3: (255, 255, 0),   # Yellow
        }

        for hue_idx, (h_min, h_max) in enumerate(self.hue_ranges):
            # 1. Define HSV range
            lower = np.array([h_min, 50, 50])
            upper = np.array([h_max, 255, 255])
            hsv_mask = cv2.inRange(hsv, lower, upper)

            # 2. Morphological cleanup
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            hsv_mask = cv2.morphologyEx(hsv_mask, cv2.MORPH_CLOSE, kernel)
            hsv_mask = cv2.morphologyEx(hsv_mask, cv2.MORPH_OPEN, kernel)

            # 3. Limit to inside Petri dish
            final_mask = cv2.bitwise_and(hsv_mask, hsv_mask, mask=mask)

            # === Split merged blobs using Distance Transform + Watershed ===

            # Step 1: Distance transform to find peaks (foreground centers)
            dist_transform = cv2.distanceTransform(final_mask, cv2.DIST_L2, 5)

            # 🔧 Controlled by UI slider
            threshold_value = (self.split_threshold / 100.0) * dist_transform.max()
            _, sure_fg = cv2.threshold(dist_transform, threshold_value, 255, 0)
            sure_fg = np.uint8(sure_fg)

            sure_fg = np.uint8(sure_fg)

            # Step 2: Identify unknown regions (edges between touching blobs)
            unknown = cv2.subtract(final_mask, sure_fg)

            # Step 3: Connected components on foreground
            _, markers = cv2.connectedComponents(sure_fg)
            markers = markers + 1  # reserve 0 for unknown
            markers[unknown == 255] = 0

            # Step 4: Convert to color image for watershed
            watershed_input = cv2.cvtColor(image, cv2.COLOR_BGR2RGB).copy()
            cv2.watershed(watershed_input, markers)

            # Step 5: Create mask for new contours
            watershed_mask = np.zeros_like(final_mask)
            watershed_mask[markers > 1] = 255

            # Step 6: Find contours from watershed result
            contours, _ = cv2.findContours(watershed_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for contour in contours:
                area = cv2.contourArea(contour)
                matched = False

                # Match area to size category
                for size_idx, (min_size, max_size) in enumerate(self.size_ranges):
                    if min_size <= area <= max_size:
                        matched = True
                        break

                if not matched:
                    continue

                # Draw result
                color = colors.get(hue_idx % len(colors), (255, 255, 255))
                cv2.drawContours(output, [contour], -1, color, 2)
                x, y, w, h = cv2.boundingRect(contour)
                label = f"ID:{object_id}"
                cv2.putText(output, label, (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
                object_id += 1
                category_counts[hue_idx] += 1

        # Draw category counts as a legend
        y_start = 20
        for idx, count in enumerate(category_counts):
            text = f"Cat {idx+1} ({self.hue_ranges[idx][0]}–{self.hue_ranges[idx][1]}): {count}"
            color = colors.get(idx % len(colors), (255, 255, 255))
            cv2.rectangle(output, (10, y_start - 12), (30, y_start + 4), color, -1)
            cv2.putText(output, text, (35, y_start), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            y_start += 20

        petri_mask_3ch = cv2.merge([mask, mask, mask])
        output = cv2.bitwise_and(output, petri_mask_3ch)

        return output
