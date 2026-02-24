# Image_processing/overlay_draw.py
import cv2
import numpy as np
from typing import Tuple, List


def _ensure_u8_mask(mask: np.ndarray) -> np.ndarray:
    """Return a single-channel uint8 mask (0/255)."""
    if mask is None:
        return None
    m = mask
    if m.ndim == 3:
        # if someone passed a 3-ch image, take a single channel
        m = cv2.cvtColor(m, cv2.COLOR_BGR2GRAY)
    if m.dtype != np.uint8:
        m = (m > 0).astype(np.uint8) * 255
    return m


def external_contours(mask: np.ndarray) -> List[np.ndarray]:
    """Find outer contours of a binary mask."""
    m = _ensure_u8_mask(mask)
    if m is None or m.size == 0:
        return []
    contours, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return contours


def draw_mask_outline(
    image_bgr: np.ndarray,
    mask: np.ndarray,
    color: Tuple[int, int, int] = (255, 255, 0),  # BGR (cyan)
    thickness: int = 2,
) -> np.ndarray:
    """
    Draws the outline of the mask onto the image (in-place) and returns it.
    """
    cnts = external_contours(mask)
    if not cnts:
        return image_bgr
    cv2.drawContours(image_bgr, cnts, -1, color, thickness)
    return image_bgr


def blend_mask_fill(
    image_bgr: np.ndarray,
    mask: np.ndarray,
    color: Tuple[int, int, int] = (255, 255, 0),  # BGR (cyan)
    alpha: float = 0.3,
    outline_color: Tuple[int, int, int] | None = None,
    outline_thickness: int = 2,
) -> np.ndarray:
    """
    Returns a new image with a semi-transparent filled mask blended on top.
    Optionally draws an outline on the blended result.
    """
    m = _ensure_u8_mask(mask)
    if m is None:
        return image_bgr

    overlay = image_bgr.copy()
    cnts = external_contours(m)
    if cnts:
        # Fill the region on the overlay, then blend with the original
        cv2.drawContours(overlay, cnts, -1, color, thickness=cv2.FILLED)
        blended = cv2.addWeighted(overlay, alpha, image_bgr, 1.0 - alpha, 0)
        # Optional outline
        if outline_thickness and outline_thickness > 0:
            if outline_color is None:
                outline_color = color
            cv2.drawContours(blended, cnts, -1, outline_color, outline_thickness)
        return blended

    return image_bgr
