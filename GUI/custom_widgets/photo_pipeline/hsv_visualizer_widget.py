import cv2
import numpy as np
from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QSizePolicy
from PyQt5.QtCore import Qt, QTimer, QSize
from PyQt5.QtGui import QImage, QPixmap, QFont
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401


class _ConeCanvas(FigureCanvas):
    """FigureCanvas whose size hint stays put.

    The stock canvas reports its *current* size as its hint, so inside a
    QScrollArea it feeds its own growth back into the layout and summons a
    scrollbar. Pin the hint to the minimum and it just fills what it is given.
    """

    HINT = QSize(180, 190)

    def sizeHint(self):
        return self.HINT

    def minimumSizeHint(self):
        return self.HINT


class HSVVisualizerWidget(QWidget):
    """Embeddable HSV filter visualiser (no controls of its own).

    - Left:  matplotlib 3-D cone (H=angle, S=radius, V=height), mouse-rotatable.
    - Right: S-V cross-section (H=0/red).

    The host feeds it values with set_params(); the darkened regions are the
    colours BacteriaDetector would reject at those thresholds.
    The 2-D panel redraws instantly, the 3-D cone after a short debounce.

    Mesh sizes are deliberately small: matplotlib z-sorts and draws every quad
    in Python, so the cone's redraw cost is roughly linear in H_N*(V_N+S_N),
    and it blocks the GUI thread while it runs.
    """

    H_N = 40    # hue steps (kept low: this is the main cost driver)
    V_N = 20    # value steps along the cone height
    S_N = 12    # saturation steps for the top disc

    SV_SIZE = 260   # render size of the S-V cross-section, in px

    def __init__(self, parent=None, saturation_min=50, value_min=50):
        super().__init__(parent)
        self._s_min = int(saturation_min)
        self._v_min = int(value_min)

        self._cone_dirty = False

        # Debounce: the cone re-renders 400 ms after the last change
        self._cone_timer = QTimer(self)
        self._cone_timer.setSingleShot(True)
        self._cone_timer.setInterval(400)
        self._cone_timer.timeout.connect(self._draw_cone)

        self._precompute()
        self._build_ui()
        self._draw_cone()
        self._update_sv()
        self._update_info()

    # ------------------------------------------------------- static data --

    def _precompute(self):
        """Build everything that does not depend on the thresholds, once.

        Only the darkening mask and the two rings move when S_min/V_min change,
        so the geometry and the base colours are computed here instead of on
        every redraw.
        """
        H = np.linspace(0, 2 * np.pi, self.H_N)

        # outer cone surface (S = 1)
        V = np.linspace(0, 1, self.V_N)
        self._hh, self._vv = np.meshgrid(H, V)
        self._cone_x = self._vv * np.cos(self._hh)
        self._cone_y = self._vv * np.sin(self._hh)
        self._cone_z = self._vv
        self._cone_rgb = self._hsv_to_rgb(self._hh / (2 * np.pi) * 179,
                                          np.full_like(self._hh, 255),
                                          self._vv * 255)

        # top disc (V = 1, S 0->1)
        S_d = np.linspace(0, 1, self.S_N)
        self._hh_d, self._ss_d = np.meshgrid(H, S_d)
        self._disc_x = self._ss_d * np.cos(self._hh_d)
        self._disc_y = self._ss_d * np.sin(self._hh_d)
        self._disc_z = np.ones_like(self._ss_d)
        self._disc_rgb = self._hsv_to_rgb(self._hh_d / (2 * np.pi) * 179,
                                          self._ss_d * 255,
                                          np.full_like(self._ss_d, 255))

        # inner S_min cone (a translucent guide; kept coarse on purpose)
        self._hh_i, self._vv_i = np.meshgrid(np.linspace(0, 2 * np.pi, 32),
                                             np.linspace(0, 1, 12))

        self._ring_t = np.linspace(0, 2 * np.pi, 120)

        # S-V cross-section: the colour field never changes, only the mask
        W = Hh = self.SV_SIZE
        self._sv_ss, self._sv_vv = np.meshgrid(
            np.linspace(0, 255, W, dtype=np.float32),
            np.linspace(255, 0, Hh, dtype=np.float32))
        hsv = np.stack([np.zeros((Hh, W), np.uint8),
                        self._sv_ss.astype(np.uint8),
                        self._sv_vv.astype(np.uint8)], axis=2)
        self._sv_base = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

    # ---------------------------------------------------------------- UI --

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        # cone and cross-section sit side by side so the panel stays short
        views = QHBoxLayout()
        views.setContentsMargins(0, 0, 0, 0)
        views.setSpacing(6)

        self._fig = Figure(figsize=(3.0, 3.0), facecolor="#1a1a1a")
        self._canvas = _ConeCanvas(self._fig)
        self._canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._canvas.setMinimumSize(_ConeCanvas.HINT)
        self._ax = self._fig.add_subplot(111, projection="3d")
        views.addWidget(self._canvas, 3)

        self._sv_label = QLabel()
        self._sv_label.setAlignment(Qt.AlignCenter)
        self._sv_label.setMinimumSize(120, 190)
        self._sv_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._sv_label.setStyleSheet("background-color: #1a1a1a;")   # match the cone canvas
        views.addWidget(self._sv_label, 2)

        root.addLayout(views, 1)

        self._info = QLabel()
        self._info.setAlignment(Qt.AlignCenter)
        self._info.setWordWrap(True)
        f = QFont(); f.setPointSize(8)
        self._info.setFont(f)
        root.addWidget(self._info, 0)

    # ------------------------------------------------------------ public --

    def set_params(self, saturation_min: int, value_min: int):
        """Point the visualiser at new thresholds (no-op if unchanged)."""
        s, v = int(saturation_min), int(value_min)
        if (s, v) == (self._s_min, self._v_min):
            return
        self._s_min, self._v_min = s, v
        self._update_sv()
        self._update_info()
        self._cone_timer.start()    # restart the countdown

    def get_params(self) -> tuple:
        return self._s_min, self._v_min

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rescale_sv()

    def showEvent(self, event):
        super().showEvent(event)
        if getattr(self, "_cone_dirty", False):
            self._cone_timer.start()    # redraw what we skipped while hidden

    # ------------------------------------------------------------ 3-D cone --

    def _draw_cone(self):
        if not self.isVisible():
            self._cone_dirty = True     # catch up when the panel comes back
            return
        self._cone_dirty = False

        ax = self._ax
        ax.cla()
        ax.set_facecolor("#1a1a1a")
        self._fig.patch.set_facecolor("#1a1a1a")

        s_f = self._s_min / 255.0
        v_f = self._v_min / 255.0

        # -- outer cone surface  (S = 1) --
        rgb_surf = self._cone_rgb.copy()
        rgb_surf[self._vv < v_f] *= 0.18

        ax.plot_surface(self._cone_x, self._cone_y, self._cone_z,
                        facecolors=rgb_surf,
                        rstride=1, cstride=1, linewidth=0,
                        antialiased=False, shade=False)

        # -- top disc  (V = 1, S 0->1) --
        rgb_disc = self._disc_rgb.copy()
        rgb_disc[self._ss_d < s_f] *= 0.15

        ax.plot_surface(self._disc_x, self._disc_y, self._disc_z,
                        facecolors=rgb_disc,
                        rstride=1, cstride=1, linewidth=0,
                        antialiased=False, shade=False)

        t = self._ring_t

        # -- V_min ring --
        if 0 < v_f < 1:
            ax.plot(v_f * np.cos(t), v_f * np.sin(t),
                    np.full_like(t, v_f),
                    color="white", linewidth=2.0, zorder=6)
            ax.text(-0.30, -0.75, v_f,
                    f"V_min {self._v_min}",
                    color="white", fontsize=7.5, zorder=10)

        # -- S_min inner cone + top circle --
        if 0 < s_f < 1:
            ax.plot_surface(self._vv_i * s_f * np.cos(self._hh_i),
                            self._vv_i * s_f * np.sin(self._hh_i),
                            self._vv_i,
                            color=(0.85, 0.85, 0.85), alpha=0.10,
                            rstride=2, cstride=2, linewidth=0, shade=False)

            ax.plot(s_f * np.cos(t), s_f * np.sin(t), np.ones_like(t),
                    color="white", linewidth=2.0, zorder=6)
            ax.text(0.10, -0.95, 1.02,
                    f"S_min {self._s_min}",
                    color="white", fontsize=7.5, zorder=10)

        # -- axis labels --
        ax.text(0, 0, 1.30, "V", color="white", fontsize=10,
                fontweight="bold", ha="center", va="bottom")
        ax.text(1.30, 0, 0.45, "S", color="white", fontsize=10,
                fontweight="bold", ha="left", va="center")
        ax.text(-0.95, 0.95, 1.05, "H", color="white", fontsize=10,
                fontweight="bold", ha="center")

        for deg, name in [(0, "R"), (60, "Y"), (120, "G"),
                          (180, "C"), (240, "B"), (300, "M")]:
            a = np.radians(deg)
            ax.text(1.13 * np.cos(a), 1.13 * np.sin(a), 1.00,
                    name, color="white", fontsize=7, ha="center", va="bottom")

        ax.set_xlim(-1.05, 1.05)
        ax.set_ylim(-1.05, 1.05)
        ax.set_zlim(0.0, 1.10)
        ax.set_box_aspect((1, 1, 0.95))     # fill the (narrow) panel
        ax.set_axis_off()
        ax.view_init(elev=22, azim=-55)

        self._fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
        self._canvas.draw_idle()

    # --------------------------------------------------- S-V cross-section --

    def _update_sv(self):
        W = H = self.SV_SIZE
        ss, vv = self._sv_ss, self._sv_vv
        bgr = self._sv_base.copy()      # colour field is static; only mask below moves

        rejected = (ss < self._s_min) | (vv < self._v_min)
        bgr[rejected] = (bgr[rejected].astype(np.float32) * 0.15).astype(np.uint8)

        sx = int(self._s_min / 255 * (W - 1))
        vy = int((255 - self._v_min) / 255 * (H - 1))
        cv2.line(bgr, (sx, 0), (sx, H - 1), (255, 255, 255), 2)
        cv2.line(bgr, (0, vy), (W - 1, vy), (255, 255, 255), 2)

        cv2.putText(bgr, "S ->", (W // 2 - 18, H - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (180, 180, 180), 1)
        cv2.putText(bgr, "V", (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)
        cv2.putText(bgr, f"S_min={self._s_min}", (min(sx + 3, W - 72), 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)
        cv2.putText(bgr, f"V_min={self._v_min}", (4, max(vy - 5, 14)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)
        if sx < W - 40 and vy > 24:
            cv2.putText(bgr, "elfogadott", (sx + 5, vy - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.32, (80, 255, 80), 1)
        cv2.rectangle(bgr, (0, 0), (W - 1, H - 1), (80, 80, 80), 1)

        rgb = np.ascontiguousarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        qi = QImage(rgb.data, W, H, W * 3, QImage.Format_RGB888)
        self._sv_pixmap = QPixmap.fromImage(qi.copy())
        self._rescale_sv()

    def _rescale_sv(self):
        pm = getattr(self, "_sv_pixmap", None)
        if pm is None:
            return
        # never scale past the rendered size: an oversized pixmap would grow the
        # label's size hint and push a scrollbar onto the panel (see _ConeCanvas)
        side = max(60, min(self._sv_label.width(), self._sv_label.height(), self.SV_SIZE))
        self._sv_label.setPixmap(pm.scaled(side, side,
                                           Qt.KeepAspectRatio,
                                           Qt.SmoothTransformation))

    # ------------------------------------------------------------ helpers --

    def _update_info(self):
        pct = (1 - self._s_min / 255) * (1 - self._v_min / 255) * 100
        self._info.setText(
            f"Elfogadott: H 0-179 | S {self._s_min}-255 | V {self._v_min}-255 "
            f"| terulet: ~{pct:.1f}%"
        )

    @staticmethod
    def _hsv_to_rgb(h_0_179, s_0_255, v_0_255) -> np.ndarray:
        hsv = np.stack([h_0_179.astype(np.uint8),
                        np.clip(s_0_255, 0, 255).astype(np.uint8),
                        np.clip(v_0_255, 0, 255).astype(np.uint8)], axis=2)
        bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        return bgr[:, :, ::-1].astype(np.float32) / 255.0
