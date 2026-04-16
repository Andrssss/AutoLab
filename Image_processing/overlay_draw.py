# Image_processing/overlay_draw.py
import cv2
import numpy as np
from typing import List, Optional, Tuple


def draw_mask_outline(image, mask, color=(255, 0, 0), thickness=3):
    if mask is None or mask.size == 0:
        return image
    cnts, _ = cv2.findContours(mask.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if cnts:
        cv2.drawContours(image, cnts, -1, color, thickness)
    return image


def draw_rois(image, rois, selected_idx=-1, color=(0, 180, 255), thickness=2):
    for i, (x, y, w, h) in enumerate(rois):
        if i == selected_idx:
            cv2.rectangle(image, (x - 1, y - 1), (x + w + 1, y + h + 1), (255, 255, 255), 3)
        cv2.rectangle(image, (x, y), (x + w, y + h), color, thickness)
        cv2.putText(image, f"A{i}", (x + 3, y + 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)


def draw_drag_rect(image, rect, color=(255, 80, 0), thickness=2):
    if rect is None:
        return
    x, y, w, h = rect
    cv2.rectangle(image, (x, y), (x + w, y + h), color, thickness)


def draw_contours(image, contour_polygons, color=(0, 255, 0), thickness=2):
    for poly in contour_polygons:
        cnt = np.array(poly, dtype=np.int32)
        if cnt.ndim == 2 and len(cnt) >= 3:
            cv2.polylines(image, [cnt], isClosed=True, color=color, thickness=thickness)


def draw_points(image, points, selected_idx=-1,
                color=(0, 0, 255), selected_radius=12, halo=4, marker_size=12):
    for j, (px, py) in enumerate(points):
        px, py = int(px), int(py)
        if j == selected_idx:
            cv2.circle(image, (px, py), selected_radius + halo, (255, 255, 255), -1)
            cv2.circle(image, (px, py), selected_radius, color, -1)
        else:
            cv2.drawMarker(image, (px, py), color,
                           markerType=cv2.MARKER_TILTED_CROSS,
                           markerSize=marker_size, thickness=2)
        cv2.putText(image, f"P{j}", (px + 6, py - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)


def draw_points_simple(image, points, color=(0, 200, 0), radius=5, thickness=-1):
    for (px, py) in points:
        cv2.circle(image, (int(px), int(py)), radius, color, thickness)


def draw_picking_progress(image, points, current_idx=None):
    if not points:
        return
    pts = [(int(x), int(y)) for (x, y) in points]

    for i in range(1, len(pts)):
        if current_idx is not None and i <= current_idx:
            cv2.line(image, pts[i - 1], pts[i], (40, 170, 40), 2, cv2.LINE_AA)
        else:
            cv2.line(image, pts[i - 1], pts[i], (120, 120, 120), 1, cv2.LINE_AA)

    for i, (x, y) in enumerate(pts):
        if current_idx is not None and i < current_idx:
            cv2.circle(image, (x, y), 7, (40, 170, 40), -1, cv2.LINE_AA)
            cv2.circle(image, (x, y), 10, (0, 70, 0), 2, cv2.LINE_AA)
        elif current_idx is not None and i == current_idx:
            cv2.circle(image, (x, y), 10, (0, 0, 255), -1, cv2.LINE_AA)
            cv2.circle(image, (x, y), 15, (255, 255, 255), 2, cv2.LINE_AA)
        else:
            cv2.circle(image, (x, y), 6, (0, 180, 255), -1, cv2.LINE_AA)
            cv2.circle(image, (x, y), 9, (0, 90, 130), 1, cv2.LINE_AA)
