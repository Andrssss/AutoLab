# GUI/custom_widgets/photo_pipeline/pipeline_context.py
from File_managers import config_manager
from Image_processing.BacteriaDetector import BacteriaDetector
from typing import Any, Dict, List, Optional, Tuple
import os
import cv2
import numpy as np


class PipelineContext:
    def __init__(self):
        # ---- runtime data ----
        self.image: Optional[np.ndarray] = None            # BGR
        self.mask: Optional[np.ndarray] = None             # uint8 0/255
        self.filtered_image: Optional[np.ndarray] = None   # preview/overlay
        self.settings: Dict[str, Any] = {}                 # step params etc.
        self.analysis: Dict[str, Any] = {}                 # misc cache

        self.detector = BacteriaDetector()
        self.image_path: Optional[str] = None
        self.output_dir: Optional[str] = None

        # user selections
        self.rois_areas: List[Tuple[int, int, int, int]] = []  # (x,y,w,h)
        self.roi_points: List[Tuple[int, int]] = []
        self.merged_points: List[Tuple[int, int]] = []

        # UI preferences
        # Pipeline steps should open full-screen by default. Can be toggled by user.
        try:
            cfg = config_manager.load_settings()
            self.pipeline_fullscreen: bool = bool(cfg.get("pipeline_fullscreen", True))
        except Exception:
            self.pipeline_fullscreen: bool = True

        # calibration
        self.pixel_per_cm: Optional[float] = self._load_pixel_per_cm()

    # ===================== public API (called by widgets) =====================

    def update_capture(
        self,
        *,
        image: Optional[np.ndarray],
        mask: Optional[np.ndarray],
        processed: Optional[np.ndarray],
        petri_params: Optional[Dict[str, Any]] = None,
        overlay_style: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Store capture results + params."""
        self.image = image
        self.mask = mask
        self.filtered_image = processed

        if petri_params:
            pp = dict(self.settings.get("petri_params", {}))
            pp.update(petri_params)
            self.settings["petri_params"] = pp

        if overlay_style:
            osd = dict(self.settings.get("overlay_style", {}))
            osd.update(overlay_style)
            self.settings["overlay_style"] = osd

        self.analysis["preview_image"] = processed
        self.analysis["petri_only"] = True

    def get_petri_params(self, defaults: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        base = {} if defaults is None else defaults.copy()
        base.update(self.settings.get("petri_params", {}))
        return base

    def get_overlay_style(self, defaults: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        base = {} if defaults is None else defaults.copy()
        base.update(self.settings.get("overlay_style", {}))
        return base

    def set_image(self, image: np.ndarray, path: Optional[str] = None) -> None:
        """Set current image and decide default debug output dir."""
        self.image = image
        self.image_path = path
        if path:
            base = os.path.splitext(os.path.basename(path))[0]
            root = os.path.dirname(path)
            self.output_dir = os.path.join(root, f"{base}_debug")
        else:
            self.output_dir = os.path.join(os.getcwd(), "debug")

    def analyze_roi(self, image: np.ndarray, rect: Tuple[int, int, int, int]) -> Dict[str, Any]:
        x, y, w, h = rect
        overlay, centers, objects, counts = self.detector.detect(
            image_bgr=image,
            full_mask=self.mask,
            roi_rect=rect,
            save_debug=True,
            save_dir=self.output_dir,
            prefix=f"roi_{x}_{y}_{w}x{h}_"
        )
        self.analysis.setdefault("overlays", []).append(overlay)
        return {"rect": rect, "centers": centers, "stats": objects, "counts": counts}

    def analyze_whole(self, image: np.ndarray, mask: Optional[np.ndarray]) -> Dict[str, Any]:
        overlay, centers, objects, counts = self.detector.detect(
            image_bgr=image,
            full_mask=mask,
            roi_rect=None,
            save_debug=False,
            save_dir=self.output_dir,
            prefix="whole_"
        )
        self.analysis["whole_overlay"] = overlay
        return {"centers": centers, "stats": objects, "counts": counts}

    def on_analysis_done(self, results: Any) -> None:
        auto_pts: List[Tuple[int, int]] = []
        if isinstance(results, dict) and "centers" in results:
            auto_pts.extend(results["centers"])
        elif isinstance(results, list):
            for r in results:
                if isinstance(r, dict) and "centers" in r:
                    auto_pts.extend(r["centers"])
        self.merged_points = list(self.roi_points) + auto_pts

    # ===================== internals =====================

    def _load_pixel_per_cm(self) -> Optional[float]:
        """Best-effort lookup of pixel_per_cm from camera or global settings."""
        try:
            try:
                cs = config_manager.load_camera_settings()
            except Exception:
                cs = {}
            cam_index = cs.get("camera_index", None)
            if cam_index is None:
                gs = config_manager.load_settings()
                cam_index = gs.get("camera_index", 0)
            cam_settings = cs.get("camera_settings", {}).get(str(cam_index), {})
            ppcm = cam_settings.get("pixel_per_cm")
            if ppcm is not None:
                self.settings = cs
                return ppcm

            gs = config_manager.load_settings()
            self.settings = gs
            cam_settings = gs.get("camera_settings", {}).get(str(cam_index), {})
            return cam_settings.get("pixel_per_cm", None)
        except Exception as e:
            print(f"[HIBA] Nem sikerült betölteni a pixel_per_cm értéket: {e}")
            return None

    def capture_from_widget(self, w, log=None) -> None:
        # grabs images + sliders + radios + overlay attrs from the widget
        image = getattr(w, "original_image", None)
        mask = getattr(w, "petri_mask", None)
        processed = getattr(w, "processed_image", None)
        img_path = getattr(w, "image_path", None)

        if image is not None:
            self.set_image(image, img_path)

        blur = getattr(getattr(w, "circle_blur_slider", None), "value", lambda: 7)()
        sens = getattr(getattr(w, "circle_slider", None), "value", lambda: 30)()
        mode = "round"
        if getattr(getattr(w, "radio_auto", None), "isChecked", lambda: False)():
            mode = "auto"
        elif getattr(getattr(w, "radio_rectangle", None), "isChecked", lambda: False)():
            mode = "rectangle"

        petri_params = {
            "circle_blur": int(blur),
            "circle_sensitivity": int(sens),
            "shape_mode": mode,
        }
        overlay_style = {
            "overlay_color_bgr": tuple(getattr(w, "overlay_color", (0, 255, 0))),
            "overlay_thickness": int(getattr(w, "overlay_thickness", 2)),
            "overlay_fill_alpha": float(getattr(w, "overlay_fill_alpha", 0.0)),
        }

        self.update_capture(
            image=image,
            mask=mask,
            processed=processed,
            petri_params=petri_params,
            overlay_style=overlay_style,
        )
        if log:
            log.append_log(f"[DEBUG] Saved to context: {petri_params} | {overlay_style}")

    def apply_to_widget(self, w, *, refresh: bool = True) -> None:
        # pushes saved params back into the widget and refreshes its preview
        pp = self.get_petri_params({"circle_blur": 7, "circle_sensitivity": 30, "shape_mode": "round"})
        if hasattr(w, "circle_blur_slider"): w.circle_blur_slider.setValue(int(pp["circle_blur"]))
        if hasattr(w, "circle_slider"):      w.circle_slider.setValue(int(pp["circle_sensitivity"]))
        mode = pp["shape_mode"]
        if hasattr(w, "radio_auto"):       w.radio_auto.setChecked(mode == "auto")
        if hasattr(w, "radio_rectangle"):  w.radio_rectangle.setChecked(mode == "rectangle")
        if hasattr(w, "radio_round"):      w.radio_round.setChecked(mode == "round")
        if hasattr(w, "petri_detector"):   w.petri_detector.set_mode(mode)

        style = self.get_overlay_style({
            "overlay_color_bgr": getattr(w, "overlay_color", (255, 255, 0)),
            "overlay_thickness": getattr(w, "overlay_thickness", 2),
            "overlay_fill_alpha": getattr(w, "overlay_fill_alpha", 0.0),
        })
        if hasattr(w, "overlay_color"):      w.overlay_color = tuple(style["overlay_color_bgr"])
        if hasattr(w, "overlay_thickness"):  w.overlay_thickness = int(style["overlay_thickness"])
        if hasattr(w, "overlay_fill_alpha"): w.overlay_fill_alpha = float(style["overlay_fill_alpha"])

        if self.image is not None: w.original_image = self.image
        if self.mask is not None:  w.petri_mask = self.mask
        if refresh and hasattr(w, "update_petri_params"):
            w.update_petri_params(force_detect=False)


