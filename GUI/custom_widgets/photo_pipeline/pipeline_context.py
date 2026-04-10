# GUI/custom_widgets/photo_pipeline/pipeline_context.py
from File_managers import config_manager
from Image_processing.BacteriaDetector import BacteriaDetector
from typing import Any, Dict, List, Optional, Tuple
import os
import cv2
import numpy as np
import logging
import yaml


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
        self._detector_params_path = os.path.join(config_manager.CONFIG_DIR, "detector_params.yaml")
        self._detector_params_mtime: Optional[float] = None

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

        self._refresh_detector_params(force=True)

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


    def _refresh_detector_params(self, force: bool = False) -> None:
        """Keep detector params in sync with config_profiles/detector_params.yaml."""
        path = self._detector_params_path
        if not os.path.exists(path):
            return

        try:
            mtime = os.path.getmtime(path)
        except Exception:
            mtime = None

        if not force and mtime is not None and self._detector_params_mtime is not None and mtime == self._detector_params_mtime:
            return

        try:
            with open(path, "r") as f:
                state = yaml.safe_load(f) or {}

            self.detector.set_params(
                split_threshold=float(state.get("split_threshold", 40)),
                saturation_min=int(state.get("saturation_min", 50)),
                value_min=int(state.get("value_min", 50)),
                morph_close_radius=int(state.get("morph_close_radius", 2)),
                morph_open_radius=int(state.get("morph_open_radius", 1)),
                use_texture=bool(state.get("use_texture", False)),
                use_edge_split=bool(state.get("use_edge_split", False)),
            )

            self._detector_params_mtime = mtime
        except Exception as e:
            logging.getLogger(__name__).warning(f"[WARN] Failed to load detector params from {path}: {e}")

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

        petri_params = {
            "circle_blur": int(blur),
            "circle_sensitivity": int(sens),
        }
        overlay_style = {
            "overlay_color_bgr": tuple(getattr(w, "overlay_color", (255, 0, 0))),
            "overlay_thickness": int(getattr(w, "overlay_thickness", 2)),
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
        pp = self.get_petri_params({"circle_blur": 7, "circle_sensitivity": 30})
        if hasattr(w, "circle_blur_slider"): w.circle_blur_slider.setValue(int(pp["circle_blur"]))
        if hasattr(w, "circle_slider"):      w.circle_slider.setValue(int(pp["circle_sensitivity"]))

        style = self.get_overlay_style({
            "overlay_color_bgr": getattr(w, "overlay_color", (255, 0, 0)),
            "overlay_thickness": getattr(w, "overlay_thickness", 2),
        })
        if hasattr(w, "overlay_color"):      w.overlay_color = tuple(style["overlay_color_bgr"])
        if hasattr(w, "overlay_thickness"):  w.overlay_thickness = int(style["overlay_thickness"])

        if self.image is not None: w.original_image = self.image
        if self.mask is not None:  w.petri_mask = self.mask
        if refresh and hasattr(w, "update_petri_params"):
            w.update_petri_params(force_detect=False)



