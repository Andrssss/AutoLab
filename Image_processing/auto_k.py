import math
import cv2
import numpy as np


def _build_sample_mask(image_shape, valid_mask=None, rois=None):
    h, w = image_shape[:2]
    sel = np.ones((h, w), dtype=np.uint8)

    if valid_mask is not None:
        vm = (valid_mask > 0).astype(np.uint8)
        if vm.shape[:2] != (h, w):
            vm = cv2.resize(vm, (w, h), interpolation=cv2.INTER_NEAREST)
        sel = cv2.bitwise_and(sel, vm)

    if rois:
        roi_mask = np.zeros((h, w), dtype=np.uint8)
        for rect in rois:
            try:
                x, y, rw, rh = rect
            except Exception:
                continue
            x0 = max(0, int(x))
            y0 = max(0, int(y))
            x1 = min(w, int(x + rw))
            y1 = min(h, int(y + rh))
            if x1 <= x0 or y1 <= y0:
                continue
            roi_mask[y0:y1, x0:x1] = 1
        sel = cv2.bitwise_and(sel, roi_mask)

    return sel > 0


def _sample_hsv_pixels(image_bgr, valid_mask=None, rois=None, saturation_min=0, value_min=0):
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    H = hsv[:, :, 0].astype(np.float32)
    S = hsv[:, :, 1].astype(np.float32)
    V = hsv[:, :, 2].astype(np.float32)

    sel = _build_sample_mask(image_bgr.shape, valid_mask=valid_mask, rois=rois)
    sel = sel & (S >= float(max(0, saturation_min))) & (V >= float(max(0, value_min)))

    h = H[sel]
    s = S[sel]
    v = V[sel]
    return h, s, v


def _kmeans_centers_hsv(h, s, v, k, max_samples=60000):
    if h.size == 0:
        return []

    n = h.shape[0]
    k_eff = min(max(1, int(k)), int(n))

    if n > max_samples:
        idx = np.random.choice(n, max_samples, replace=False)
        h = h[idx]
        s = s[idx]
        v = v[idx]

    angle = (h / 179.0) * (2.0 * np.pi)
    h_cos = np.cos(angle)
    h_sin = np.sin(angle)
    s_norm = s / 255.0
    v_norm = v / 255.0

    features = np.column_stack([
        h_cos,
        h_sin,
        0.9 * s_norm,
        0.25 * v_norm,
    ]).astype(np.float32)

    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.2)
    try:
        _, _, centers = cv2.kmeans(features, k_eff, None, criteria, 8, cv2.KMEANS_PP_CENTERS)
    except Exception:
        return []

    result = []
    for c in centers:
        cx, cy, cs, _cv = [float(x) for x in c]
        ang = math.atan2(cy, cx)
        if ang < 0:
            ang += 2.0 * math.pi
        h_center = int(round((ang / (2.0 * math.pi)) * 179.0))
        s_center = int(round(np.clip((cs / 0.9) * 255.0, 0, 255)))
        result.append((h_center, s_center))

    result.sort(key=lambda t: t[0])
    return result


def _merge_near_centers(centers, hue_tol=8, sat_tol=40):
    if not centers:
        return []

    merged = []
    for h, s in centers:
        placed = False
        for i, (mh, ms, cnt) in enumerate(merged):
            dh = abs(h - mh)
            dh = min(dh, 180 - dh)
            ds = abs(s - ms)
            if dh <= hue_tol and ds <= sat_tol:
                new_cnt = cnt + 1
                mh2 = int(round((mh * cnt + h) / new_cnt))
                ms2 = int(round((ms * cnt + s) / new_cnt))
                merged[i] = (mh2, ms2, new_cnt)
                placed = True
                break
        if not placed:
            merged.append((int(h), int(s), 1))

    out = [(h, s) for h, s, _ in merged]
    out.sort(key=lambda t: t[0])
    return out


def compute_autok_centers(
    image_bgr,
    k=8,
    valid_mask=None,
    rois=None,
    saturation_min=35,
    value_min=30,
    fallback_to_whole=True,
):
    if image_bgr is None:
        return []

    h, s, v = _sample_hsv_pixels(
        image_bgr,
        valid_mask=valid_mask,
        rois=rois,
        saturation_min=saturation_min,
        value_min=value_min,
    )

    centers = _kmeans_centers_hsv(h, s, v, k=k)

    if not centers and fallback_to_whole:
        h, s, v = _sample_hsv_pixels(
            image_bgr,
            valid_mask=valid_mask,
            rois=None,
            saturation_min=max(20, int(saturation_min) // 2),
            value_min=max(20, int(value_min) // 2),
        )
        centers = _kmeans_centers_hsv(h, s, v, k=k)

    return _merge_near_centers(centers)


def classify_contour_to_center(image_bgr, contour, centers):
    if image_bgr is None or contour is None or not centers:
        return None

    try:
        cnt = np.array(contour, dtype=np.int32)
        if cnt.ndim != 2 or len(cnt) < 3:
            return None

        h_img, w_img = image_bgr.shape[:2]
        mask = np.zeros((h_img, w_img), dtype=np.uint8)
        cv2.drawContours(mask, [cnt], -1, 255, thickness=-1)
        if cv2.countNonZero(mask) == 0:
            return None

        hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
        H = hsv[:, :, 0][mask > 0].astype(np.float32)
        S = hsv[:, :, 1][mask > 0].astype(np.float32)
        if H.size == 0:
            return None

        theta = (H / 179.0) * (2.0 * np.pi)
        sin_m = float(np.mean(np.sin(theta)))
        cos_m = float(np.mean(np.cos(theta)))
        mean_angle = math.atan2(sin_m, cos_m)
        if mean_angle < 0:
            mean_angle += 2.0 * np.pi
        mean_h = (mean_angle / (2.0 * np.pi)) * 179.0
        mean_s = float(np.mean(S))

        best_idx = None
        best_dist = None
        for ci, center in enumerate(centers):
            if isinstance(center, (list, tuple)) and len(center) >= 2:
                ch = float(center[0])
                cs = float(center[1])
            else:
                ch = float(center)
                cs = 128.0

            dh = abs(mean_h - ch)
            dh = min(dh, 179.0 - dh) / 179.0
            ds = abs(mean_s - cs) / 255.0
            dist = math.sqrt(dh * dh + ds * ds)
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best_idx = ci

        return best_idx
    except Exception:
        return None
