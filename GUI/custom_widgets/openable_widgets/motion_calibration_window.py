# GUI/custom_widgets/openable_widgets/motion_calibration_window.py
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QDoubleSpinBox, QComboBox, QMessageBox, QGroupBox, QFrame, QSizePolicy
)
from PyQt5.QtCore import Qt


class MotionCalibrationWindow(QWidget):
    """
    Two-column, step-by-step X/Y calibration for Marlin.
    Left col:  1) Enable + soft off   2) Initial steps/mm     3) Jog test
    Right col: 4) Run test move       5) Measured -> apply    6) Save + soft on
    """
    def __init__(self, g_control, log_widget=None):
        super().__init__()
        self.setWindowTitle("Motion Calibration (X/Y) – 2-column")
        self.resize(900, 520)

        self.g = g_control
        self.log = log_widget

        # Shared controls across steps
        self.sp_steps_x = self._spin(100.0, dec=6)
        self.sp_steps_y = self._spin(100.0, dec=6)
        self.sp_jog     = self._spin(5.0,   lo=0.01, hi=1000.0, dec=3)
        self.sp_feed    = self._spin(600.0, lo=1.0,  hi=60000.0, dec=0)
        self.cmb_axis   = QComboBox(); self.cmb_axis.addItems(["X", "Y"])
        self.sp_cmd     = self._spin(100.0, lo=1.0,  hi=5000.0, dec=3)
        self.sp_meas    = self._spin(100.0, lo=0.01, hi=5000.0, dec=3)

        self._build_ui()

    # ---------------- UI ----------------
    def _build_ui(self):
        root = QVBoxLayout(self)

        # GRID with two columns of step cards
        grid_wrap = QGroupBox("Lépésről lépésre")
        grid = QGridLayout(grid_wrap)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        # ---- LEFT COLUMN ----
        grid.addWidget(self._card_step1(), 0, 0)
        grid.addWidget(self._card_step2(), 1, 0)
        grid.addWidget(self._card_step3(), 2, 0)

        # ---- RIGHT COLUMN ----
        grid.addWidget(self._card_step4(), 0, 1)
        grid.addWidget(self._card_step5(), 1, 1)
        grid.addWidget(self._card_step6(), 2, 1)

        root.addWidget(grid_wrap)

        # Advanced quick actions (one compact row)
        adv = QGroupBox("Haladó – gyors műveletek")
        row = QHBoxLayout(adv)
        row.addWidget(self._btn("G28 XY  Home", self._act_g28))
        row.addWidget(self._btn("G92 X0 Y0  XY=0", self._act_g92_xy0))
        row.addWidget(self._btn("M114  Pozíció", self._act_m114))
        row.addWidget(self._btn("M503  Aktív beállítások → Log", self._act_m503))
        row.addStretch(1)
        root.addWidget(adv)

        root.addStretch(1)

    # ---------- Step cards ----------
    def _card_step1(self):
        card = self._card(1, "Motorok ON + Soft Endstops OFF",
                          "Kapcsold be a steppereket és ideiglenesen kapcsold ki a szoftveres végállásokat.")
        lay = card.layout()
        lay.addWidget(self._row([
            self._btn("M17  Stepperek ON", self._act_m17),
            self._btn("M211 S0  Soft OFF", self._act_m211_off),
            self._btn("M400  Vár",         self._act_m400),
        ]))
        return card

    def _card_step2(self):
        card = self._card(2, "Kezdő steps/mm (M92)",
                          "Ha nem tudod, hagyd 100-on; később pontosítjuk a mérés alapján.")
        lay = card.layout()
        g = QGridLayout(); g.setContentsMargins(0,0,0,0)
        g.addWidget(QLabel("X steps/mm"), 0, 0); g.addWidget(self.sp_steps_x, 0, 1)
        g.addWidget(QLabel("Y steps/mm"), 1, 0); g.addWidget(self.sp_steps_y, 1, 1)
        lay.addLayout(g)
        lay.addWidget(self._btn("Alkalmaz (M92)", self._apply_steps))
        return card

    def _card_step3(self):
        card = self._card(3, "Irány- és lépéspróba",
                          "Relatív módban lépj pár mm-t mindkét irányba. Figyeld, jó-e az irány és nagyjából a skála.")
        lay = card.layout()
        g = QGridLayout(); g.setContentsMargins(0,0,0,0)
        g.addWidget(QLabel("Relatív lépés (mm)"), 0, 0); g.addWidget(self.sp_jog, 0, 1)
        g.addWidget(QLabel("Feed (mm/perc)"),     1, 0); g.addWidget(self.sp_feed, 1, 1)
        lay.addLayout(g)
        lay.addWidget(self._row([
            self._btn("X −", lambda: self._jog("X", -self.sp_jog.value())),
            self._btn("X +", lambda: self._jog("X", +self.sp_jog.value())),
            self._btn("Y −", lambda: self._jog("Y", -self.sp_jog.value())),
            self._btn("Y +", lambda: self._jog("Y", +self.sp_jog.value())),
            self._btn("M114  Pozíció", self._act_m114),
        ]))
        return card

    def _card_step4(self):
        card = self._card(4, "Tesztmenet (pl. 100 mm)",
                          "Válaszd a tengelyt és a parancsolt utat, majd futtasd a mérést.")
        lay = card.layout()
        g = QGridLayout(); g.setContentsMargins(0,0,0,0)
        self.cmb_axis.setMaximumWidth(90)
        g.addWidget(QLabel("Tengely"),      0, 0); g.addWidget(self.cmb_axis, 0, 1)
        g.addWidget(QLabel("Parancs (mm)"), 1, 0); g.addWidget(self.sp_cmd,   1, 1)
        lay.addLayout(g)
        lay.addWidget(self._btn("Futtatás (G91/G1)", self._run_move))
        return card

    def _card_step5(self):
        card = self._card(5, "Mért érték → új steps/mm",
                          "Kézzel mérd le a tényleges utat. Képlet: új = régi × parancs / mért.")
        lay = card.layout()
        g = QGridLayout(); g.setContentsMargins(0,0,0,0)
        g.addWidget(QLabel("Mért (mm)"), 0, 0); g.addWidget(self.sp_meas, 0, 1)
        lay.addLayout(g)
        lay.addWidget(self._btn("Számol & Alkalmaz (M92 + M500)", self._compute_apply))
        return card

    def _card_step6(self):
        card = self._card(6, "Mentés + Soft Endstops ON",
                          "Mentsd EEPROM-ba és kapcsold vissza a védelmet.")
        lay = card.layout()
        lay.addWidget(self._row([
            self._btn("M500  Mentés", self._act_m500),
            self._btn("M211 S1  Soft ON", self._act_m211_on),
            self._btn("M503  Beállítások → Log", self._act_m503),
        ]))
        return card

    # ---------- actions ----------
    def _apply_steps(self):
        self._send(f"M92 X{self.sp_steps_x.value():.6f} Y{self.sp_steps_y.value():.6f}")

    def _jog(self, axis, delta):
        F = int(self.sp_feed.value())
        self._send("G91")
        self._send(f"G1 {axis}{delta:.3f} F{F}")
        self._send("G90")

    def _run_move(self):
        axis = self.cmb_axis.currentText().upper()
        mm   = self.sp_cmd.value()
        F    = int(self.sp_feed.value())
        self._send("G90")
        self._send(f"G92 {axis}0")
        self._send("G91")
        self._send(f"G1 {axis}{mm:.3f} F{F}")
        self._send("G90")
        self._send("M114")

    def _compute_apply(self):
        axis = self.cmb_axis.currentText().upper()
        commanded = self.sp_cmd.value()
        measured  = self.sp_meas.value()
        if measured <= 0:
            QMessageBox.warning(self, "Hiba", "A mért érték legyen > 0 mm.")
            return
        old = self.sp_steps_x.value() if axis == "X" else self.sp_steps_y.value()
        new_steps = old * (commanded / measured)
        if axis == "X": self.sp_steps_x.setValue(new_steps)
        else:           self.sp_steps_y.setValue(new_steps)
        self._send(f"M92 {axis}{new_steps:.6f}")
        self._send("M500")
        self._log(f"[CAL] {axis}: régi={old:.6f}, parancs={commanded:.3f}, mért={measured:.3f} → új={new_steps:.6f}")

    # ---------- low-level ----------
    def _send(self, gcode):
        if not self.g:
            QMessageBox.warning(self, "Nincs kapcsolat", "GCodeControl példány hiányzik.")
            return
        self._log(f"[CAL] → {gcode}")
        self.g.new_command(gcode)

    def _log(self, msg):
        if self.log: self.log.append_log(msg)
        else: print(msg)

    # ---------- small helpers ----------
    def _spin(self, val, lo=0.01, hi=100000.0, dec=6):
        s = QDoubleSpinBox(); s.setRange(lo, hi); s.setDecimals(dec); s.setValue(val); s.setMaximumWidth(140); return s

    def _btn(self, text, fn):
        b = QPushButton(text); b.clicked.connect(fn); b.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed); return b

    def _row(self, widgets):
        w = QWidget(); l = QHBoxLayout(w); l.setContentsMargins(0,0,0,0)
        for x in widgets: l.addWidget(x)
        l.addStretch(1); return w

    def _card(self, num, title, desc):
        f = QFrame(); f.setFrameShape(QFrame.StyledPanel)
        v = QVBoxLayout(f); v.setContentsMargins(8,8,8,8)
        tl = QLabel(f"<b>{num}. {title}</b>")
        dl = QLabel(desc); dl.setWordWrap(True)
        v.addWidget(tl); v.addWidget(dl)
        return f

    # quick actions used by advanced row and steps
    def _act_m17(self):      self._send("M17")
    def _act_m211_off(self): self._send("M211 S0")
    def _act_m211_on(self):  self._send("M211 S1")
    def _act_m400(self):     self._send("M400")
    def _act_m500(self):     self._send("M500")
    def _act_m503(self):     self._send("M503")
    def _act_m114(self):     self._send("M114")
    def _act_g28(self):      self._send("G28 XY")
    def _act_g92_xy0(self):  self._send("G92 X0 Y0")
