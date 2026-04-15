# Image_processing/overlay_draw.py
import cv2
import numpy as np
from typing import Tuple


def draw_mask_outline(
    image_bgr: np.ndarray,
    mask: np.ndarray,
    color: Tuple[int, int, int] = (255, 0, 0),
    thickness: int = 3,
) -> np.ndarray:
    if mask is None or mask.size == 0:
        return image_bgr
    contours_before, _ = cv2.findContours(mask.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    contours_after, _ = cv2.findContours(mask.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    points_before = sum(len(c) for c in contours_before)
    points_after = sum(len(c) for c in contours_after)
    print(f"[DEBUG] Contour points before={points_before}, after={points_after}")

    if not contours_after:
        return image_bgr
    cv2.drawContours(image_bgr, contours_after, -1, color, thickness)
    return image_bgr
