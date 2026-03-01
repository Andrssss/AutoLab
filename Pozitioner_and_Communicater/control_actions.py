from typing import Optional
import time


def _with_newline(cmd: str, newline: bool) -> str:
	return f"{cmd}\n" if newline else cmd


def _axis(axis: str) -> str:
	value = str(axis).upper().strip()
	if value not in ("X", "Y", "Z", "E"):
		raise ValueError(f"Unsupported axis: {axis}")
	return value


def cmd_mode_relative(newline: bool = False) -> str:
	return _with_newline("G91", newline)


def cmd_mode_absolute(newline: bool = False) -> str:
	return _with_newline("G90", newline)


def cmd_move_axis(axis: str, distance: float, feedrate: int, newline: bool = False, decimals: int = 3) -> str:
	a = _axis(axis)
	return _with_newline(f"G1 {a}{float(distance):.{decimals}f} F{int(feedrate)}", newline)


def cmd_set_position(axis: str, value: float = 0.0, newline: bool = False) -> str:
	a = _axis(axis)
	if abs(float(value) - int(float(value))) < 1e-9:
		v = str(int(float(value)))
	else:
		v = f"{float(value):.3f}"
	return _with_newline(f"G92 {a}{v}", newline)


def cmd_set_xy_zero(newline: bool = False) -> str:
	return _with_newline("G92 X0 Y0", newline)


def cmd_home(axes: Optional[str] = None, newline: bool = True) -> str:
	suffix = f" {axes.strip()}" if axes and str(axes).strip() else ""
	return _with_newline(f"G28{suffix}", newline)


def cmd_position_report(newline: bool = False) -> str:
	return _with_newline("M114", newline)


def cmd_query_settings(newline: bool = True) -> str:
	return _with_newline("M503", newline)


def cmd_soft_endstops(enabled: bool, newline: bool = False) -> str:
	return _with_newline("M211 S1" if enabled else "M211 S0", newline)


def cmd_save_settings(newline: bool = False) -> str:
	return _with_newline("M500", newline)


def cmd_set_steps_xy(x_steps: float, y_steps: float, newline: bool = False) -> str:
	return _with_newline(f"M92 X{float(x_steps):.6f} Y{float(y_steps):.6f}", newline)


def cmd_set_steps_axis(axis: str, steps: float, newline: bool = False) -> str:
	a = _axis(axis)
	return _with_newline(f"M92 {a}{float(steps):.6f}", newline)


def build_manual_direction_move(direction: str, step_mm: float = 15.0, feedrate: int = 3000) -> str:
	d = str(direction).lower().strip()
	mapping = {
		"up": ("X", +float(step_mm)),
		"down": ("X", -float(step_mm)),
		"right": ("Y", +float(step_mm)),
		"left": ("Y", -float(step_mm)),
	}
	if d not in mapping:
		return ""

	axis, delta = mapping[d]
	return f"{cmd_mode_relative(newline=False)}\n{cmd_move_axis(axis, delta, feedrate, newline=False, decimals=3)}\n"


def build_move_xy_command(x: int, y: int, feedrate: int = 3000) -> str:
	return f"G0 X{int(x)} Y{int(y)} F{int(feedrate)}\n"


def cmd_led_pwm(s_value: int, newline: bool = True) -> str:
	s = max(0, min(255, int(s_value)))
	return _with_newline(f"M106 S{s}", newline)


class ControlActions:
	def __init__(self, g_control=None, command_sender=None, log_widget=None):
		self.g_control = g_control
		self.command_sender = command_sender
		self.log_widget = log_widget
		self._last_manual_jog_log_ts = 0.0

	def set_command_sender(self, command_sender):
		self.command_sender = command_sender

	def set_g_control(self, g_control):
		self.g_control = g_control

	def set_log_widget(self, log_widget):
		self.log_widget = log_widget

	def _log(self, message: str):
		if self.log_widget:
			self.log_widget.append_log(message)

	def _is_manual_jog_command(self, command: str) -> bool:
		if not command:
			return False
		lines = [line.strip().upper() for line in str(command).splitlines() if line.strip()]
		if len(lines) != 2:
			return False
		if lines[0] != "G91":
			return False
		second = lines[1]
		if not second.startswith("G1 "):
			return False
		return " X" in f" {second}" or " Y" in f" {second}"

	def _is_motion_command(self, command: str) -> bool:
		if not command:
			return False
		lines = [line.strip().upper() for line in str(command).splitlines() if line.strip()]
		if not lines:
			return False
		if self._is_manual_jog_command(command):
			return True
		for line in lines:
			if line.startswith("G0") or line.startswith("G1"):
				return True
		return False

	def send_via_command_sender(self, command: str = "") -> bool:
		if not self.command_sender or not command:
			return False
		if hasattr(self.command_sender, "isRunning") and not self.command_sender.isRunning():
			return False
		self.command_sender.sendCommand.emit(command)
		return True

	def clear_pending_manual_jog_commands(self) -> int:
		removed = 0

		if self.command_sender:
			clear_fn = getattr(self.command_sender, "clear_pending_commands", None)
			if callable(clear_fn):
				try:
					removed += int(clear_fn(self._is_manual_jog_command))
				except Exception:
					pass

		if self.g_control:
			clear_g_fn = getattr(self.g_control, "clear_pending_manual_jog_commands", None)
			if callable(clear_g_fn):
				try:
					removed += int(clear_g_fn())
				except Exception:
					pass

		return removed

	def clear_pending_motion_commands(self) -> int:
		removed = 0

		if self.command_sender:
			clear_fn = getattr(self.command_sender, "clear_pending_commands", None)
			if callable(clear_fn):
				try:
					removed += int(clear_fn(self._is_motion_command))
				except Exception:
					pass

		if self.g_control:
			clear_g_fn = getattr(self.g_control, "clear_pending_motion_commands", None)
			if callable(clear_g_fn):
				try:
					removed += int(clear_g_fn())
				except Exception:
					pass

		return removed

	def has_pending_motion_commands(self) -> bool:
		if not self.g_control:
			return False
		check_fn = getattr(self.g_control, "has_pending_motion_commands", None)
		if not callable(check_fn):
			return False
		try:
			return bool(check_fn())
		except Exception:
			return False

	def send_via_g_control_queue(self, command: str = "") -> bool:
		if not self.g_control or not command:
			return False
		if not hasattr(self.g_control, "new_command"):
			return False
		result = self.g_control.new_command(command)
		return False if result is False else True

	def clear_all_pending_commands(self) -> int:
		removed = 0

		if self.command_sender:
			clear_fn = getattr(self.command_sender, "clear_pending_commands", None)
			if callable(clear_fn):
				try:
					removed += int(clear_fn(None))
				except Exception:
					pass

		if self.g_control:
			clear_g_fn = getattr(self.g_control, "clear_all_pending_commands", None)
			if callable(clear_g_fn):
				try:
					removed += int(clear_g_fn())
				except Exception:
					pass

		return removed

	def send_via_g_control_direct(self, command: str = "", wait_for_completion: bool = False) -> bool:
		if not self.g_control or not command:
			return False
		if not hasattr(self.g_control, "send_command"):
			return False
		try:
			self.g_control.send_command(command, wait_for_completion=wait_for_completion)
		except TypeError:
			self.g_control.send_command(command)
		return True

	def action_manual_direction_move(self, direction: str, step_mm: float = 15.0, feedrate: int = 3000) -> bool:
		command = build_manual_direction_move(direction, step_mm=step_mm, feedrate=feedrate)
		if not command:
			return False
		sent = self.send_via_g_control_queue(command) or self.send_via_command_sender(command)
		if sent:
			now = time.time()
			if now - self._last_manual_jog_log_ts >= 0.25:
				log_cmd = " | ".join([p.strip() for p in command.strip().splitlines() if p.strip()])
				self._log(f"[GCODE] {log_cmd}")
				self._last_manual_jog_log_ts = now
		return sent

	def action_move_xy(self, x: int, y: int, feedrate: int = 3000) -> bool:
		command = build_move_xy_command(x, y, feedrate=feedrate)
		sent = self.send_via_g_control_queue(command) or self.send_via_command_sender(command)
		if sent:
			self._log(f"[GCODE] {command.strip()}")
		return sent

	def action_led_pwm(self, s_value: int) -> bool:
		if self.g_control is not None and hasattr(self.g_control, "connected") and not self.g_control.connected:
			self._log("[ERROR] Machine is not connected (M106 skipped).")
			return False

		command = cmd_led_pwm(s_value)
		sent = self.send_via_command_sender(command) or self.send_via_g_control_queue(command)
		if sent:
			self._log(f"[LED] -> {command.strip()}")
		return sent

	def action_home(self, axes: Optional[str] = None) -> bool:
		command = cmd_home(axes=axes)
		sent = self.send_via_command_sender(command) or self.send_via_g_control_queue(command)
		if sent:
			self._log(f"[GCODE] {command.strip()}")
		return sent

	def action_resume_print(self) -> bool:
		command = _with_newline("M24", True)
		sent = self.send_via_command_sender(command) or self.send_via_g_control_queue(command)
		if sent:
			self._log("[CONTROL_CMD] Resume requested -> M24")
		return sent

	def action_pause_print(self) -> bool:
		command = _with_newline("M0", True)
		sent = self.send_via_command_sender(command) or self.send_via_g_control_queue(command)
		if sent:
			self._log("[CONTROL_CMD] Pause requested -> M0")
		return sent

	def action_query_settings(self) -> bool:
		command = cmd_query_settings()
		sent = self.send_via_g_control_direct(command) or self.send_via_command_sender(command)
		if sent:
			self._log("[INFO] Querying configuration (M503)")
		return sent

	def action_calibration_command(self, command: str = "") -> bool:
		if not command:
			return False
		sent = self.send_via_g_control_queue(command)
		if sent:
			self._log(f"[CAL] -> {command}")
		return sent

	def send_emergency_stop(self) -> None:
		if self.g_control and hasattr(self.g_control, "set_emergency_latched"):
			try:
				self.g_control.set_emergency_latched(True)
			except Exception:
				pass

		sent = self.send_via_g_control_direct("M112\n") or self.send_via_command_sender("M112\n") or self.send_via_g_control_queue("M112\n")
		if not sent:
			self._log("[WARN] Failed to dispatch emergency stop command (M112).")
		self._log("[EMERGENCY STOP] Immediate machine stop!")
		self._log("[EMERGENCY STOP] Press the reset button on RAMPS!")

	def action_emergency_stop(self, stop_context=None, send_reset: bool = True) -> str:
		"""Unified emergency-stop flow (optional UI state latch + machine stop + optional reset)."""
		source = "fallback"
		if stop_context is not None:
			source = "context"
			if hasattr(stop_context, "stopped"):
				stop_context.stopped = True
			if hasattr(stop_context, "paused"):
				stop_context.paused = True
			timers = getattr(stop_context, "timers", None)
			if isinstance(timers, dict):
				for timer in timers.values():
					try:
						timer.stop()
					except Exception:
						pass

		self.send_emergency_stop()
		time.sleep(0.1)
		self.clear_all_pending_commands()

		if send_reset:
			sent = self.send_via_g_control_direct("M999\n") or self.send_via_command_sender("M999\n") or self.send_via_g_control_queue("M999\n")
			if sent and self.g_control and hasattr(self.g_control, "set_emergency_latched"):
				try:
					self.g_control.set_emergency_latched(False)
				except Exception:
					pass
			if sent:
				self._log("[INFO] Reset (M999) command sent to firmware.")

		return source

	def action_recover_from_emergency(self) -> bool:
		if not self.g_control:
			return True

		threads_alive = True
		if hasattr(self.g_control, "are_command_threads_alive"):
			try:
				threads_alive = bool(self.g_control.are_command_threads_alive())
			except Exception:
				threads_alive = False

		latched = False
		if hasattr(self.g_control, "is_emergency_latched"):
			try:
				latched = bool(self.g_control.is_emergency_latched())
			except Exception:
				latched = False

		connected = bool(getattr(self.g_control, "connected", False))
		if connected and not threads_alive:
			self._log("[WARN] Command threads are not running; reconnecting with saved settings...")
			return self.action_reconnect_saved_connection()

		if not latched and connected:
			return True

		if not connected:
			self._log("[WARN] Recovery requested while disconnected; trying reconnect...")
			return self.action_reconnect_saved_connection()

		self._log("[INFO] Emergency latch is active; trying M999 recovery...")

		sent = self.send_via_g_control_direct("M999\n")
		if not sent:
			sent = self.send_via_command_sender("M999\n") or self.send_via_g_control_queue("M999\n")
		if not sent:
			self._log("[WARN] M999 recovery send failed; trying reconnect...")
			return self.action_reconnect_saved_connection()

		if hasattr(self.g_control, "set_emergency_latched"):
			try:
				self.g_control.set_emergency_latched(False)
			except Exception:
				pass

		self.clear_all_pending_commands()

		if hasattr(self.g_control, "are_command_threads_alive"):
			try:
				if not self.g_control.are_command_threads_alive():
					self._log("[WARN] Threads not alive after emergency reset; reconnecting...")
					return self.action_reconnect_saved_connection()
			except Exception:
				return self.action_reconnect_saved_connection()

		self._log("[INFO] Emergency latch cleared; commands re-enabled.")
		return True

	def action_reconnect_saved_connection(self) -> bool:
		if not self.g_control:
			return False

		if hasattr(self.g_control, "set_emergency_latched"):
			try:
				self.g_control.set_emergency_latched(False)
			except Exception:
				pass

		reconnect_fn = getattr(self.g_control, "reconnect_saved", None)
		if callable(reconnect_fn):
			try:
				ok = bool(reconnect_fn(fallback=True))
			except TypeError:
				ok = bool(reconnect_fn())
			except Exception:
				ok = False
		else:
			try:
				self.g_control.autoconnect()
				ok = bool(getattr(self.g_control, "connected", False))
			except Exception:
				ok = False

		if ok:
			self.clear_all_pending_commands()
			self._log("[INFO] Reconnected using saved settings.")
		else:
			self._log("[ERROR] Reconnect failed with saved settings.")

		return ok

	def action_emergency_stop_manual(self, manual_widget=None, send_reset: bool = True) -> None:
		"""Backward-compatible wrapper for manual-control emergency stop calls."""
		self.action_emergency_stop(stop_context=manual_widget, send_reset=send_reset)

	def trigger_emergency_stop(self, main_window=None) -> str:
		control_widget: Optional[object] = getattr(main_window, "control_widget", None)
		return self.action_emergency_stop(stop_context=control_widget, send_reset=True)
