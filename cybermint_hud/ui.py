from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gio", "2.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango

from .applications import ApplicationEntry, enumerate_applications, filter_applications, launch_application
from .brightness import BrightnessControl, BrightnessReading
from .config import effective_position
from .drawing import hex_to_rgba, render_cyber_card, render_cyber_meter
from .monitoring import Metric, SystemMonitor
from .volume import ControlReading, PactlVolume, clamp_percent

FONT = '"DejaVu Sans Mono", "JetBrains Mono", "Courier New", monospace'


def _build_css(appearance: dict[str, Any], scale: float) -> str:
    primary = appearance.get("accent_primary", "#ff2a4b")
    secondary = appearance.get("accent_secondary", "#00f0ff")
    surface = appearance.get("surface", "#0d0e15")

    clock_size = int(32 * scale)
    date_size = int(11 * scale)
    eyebrow_size = int(10 * scale)
    name_size = int(11 * scale)
    value_size = int(12 * scale)
    detail_size = int(10 * scale)
    pad = int(12 * scale)
    slider = int(12 * scale)

    return f"""
    window {{ background-color: transparent; }}
    .hud-inner-box {{ padding: {pad}px; }}
    .eyebrow {{ color: {secondary}; font-family: {FONT}; font-size: {eyebrow_size}px; font-weight: bold; letter-spacing: 2px; }}
    .clock-text {{ color: #ffffff; font-family: {FONT}; font-size: {clock_size}px; font-weight: bold; letter-spacing: 3px; }}
    .date-text {{ color: #b0b8c4; font-family: {FONT}; font-size: {date_size}px; letter-spacing: 1px; }}
    .metric-name {{ color: {secondary}; font-family: {FONT}; font-size: {name_size}px; font-weight: bold; letter-spacing: 1px; }}
    .metric-value {{ color: #ffffff; font-family: {FONT}; font-size: {value_size}px; font-weight: bold; }}
    .metric-detail {{ color: #7b8594; font-family: {FONT}; font-size: {detail_size}px; }}
    button.close-btn {{ color: {primary}; background: transparent; border: 0; box-shadow: none; padding: 0 {int(4 * scale)}px; font-size: {int(14 * scale)}px; font-weight: bold; }}
    button.close-btn:hover {{ color: #ffffff; background-color: rgba(255, 42, 75, 0.35); border-radius: 2px; }}
    button.mute-btn {{ color: {secondary}; background: transparent; background-image: none; border: 1px solid {secondary}; border-radius: 0; box-shadow: none; padding: {int(2 * scale)}px {int(10 * scale)}px; font-family: {FONT}; font-size: {detail_size}px; font-weight: bold; letter-spacing: 1px; }}
    button.mute-btn:hover {{ background-color: rgba(0, 240, 255, 0.15); }}
    button.mute-btn:checked {{ color: #ffffff; background-color: rgba(255, 42, 75, 0.45); border-color: {primary}; }}
    button.mute-btn:disabled {{ color: #4a5260; border-color: #2a3040; }}
    scale trough {{ min-height: {int(6 * scale)}px; background-color: rgba(20, 24, 34, 0.9); background-image: none; border: 1px solid rgba(0, 240, 255, 0.25); border-radius: 0; }}
    scale highlight {{ min-height: {int(6 * scale)}px; background-color: {secondary}; background-image: none; border: 0; border-radius: 0; }}
    scale slider {{ min-width: {slider}px; min-height: {slider}px; background-color: {primary}; background-image: none; border: 0; border-radius: 0; box-shadow: none; }}
    scale:disabled highlight {{ background-color: #2a3040; }}
    scale:disabled slider {{ background-color: #4a5260; }}
    entry {{ color: #ffffff; caret-color: {secondary}; font-family: {FONT}; background-color: rgba(20, 24, 34, 0.9); background-image: none; border: 1px solid rgba(0, 240, 255, 0.35); border-radius: 0; box-shadow: none; padding: {int(6 * scale)}px {int(8 * scale)}px; }}
    entry:focus {{ border-color: {secondary}; }}
    scrolledwindow, viewport, list {{ background-color: transparent; background-image: none; }}
    row {{ background-color: transparent; border-left: 2px solid transparent; }}
    row:selected {{ background-color: rgba(255, 42, 75, 0.28); border-left: 2px solid {primary}; }}
    .launcher-entry {{ color: #e8ecf2; font-family: {FONT}; font-size: {value_size}px; padding: {int(6 * scale)}px {int(8 * scale)}px; }}
    row:selected .launcher-entry {{ color: #ffffff; }}
    """


class HudApplication(Gtk.Application):
    def __init__(self, config: dict[str, Any], logger: logging.Logger, report: Any) -> None:
        super().__init__(
            application_id="org.cybermint.hud",
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )
        self.config = config
        self.logger = logger
        self.report = report
        self.monitor = SystemMonitor()
        self.volume = PactlVolume()
        self.brightness = BrightnessControl()
        self.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="cybermint")
        self.windows: list[Gtk.Window] = []
        self._last_errors: dict[str, str] = {}
        self._started = False

        appearance = self.config["appearance"]
        self.scale = float(appearance.get("scale", 1.0))
        self.opacity = float(appearance.get("opacity", 0.92))
        self.primary_rgba = hex_to_rgba(appearance.get("accent_primary", "#ff2a4b"), 1.0)
        self.secondary_rgba = hex_to_rgba(appearance.get("accent_secondary", "#00f0ff"), 1.0)
        self.surface_rgba = hex_to_rgba(appearance.get("surface", "#0d0e15"), self.opacity)
        self.metric_data: dict[str, tuple[float | None, bool]] = {
            "cpu": (None, False),
            "memory": (None, False),
            "disk": (None, False),
            "battery": (None, False),
        }

        # Launcher state
        self._launcher_window: Gtk.Window | None = None
        self._launcher_search: Gtk.SearchEntry | None = None
        self._launcher_list: Gtk.ListBox | None = None
        self._launcher_status: Gtk.Label | None = None
        self._applications: list[ApplicationEntry] = []
        self._visible_applications: list[ApplicationEntry] = []

        # Quick controls state
        self._controls_updating = False
        self._controls_inflight = False
        self._write_timeout = {"volume": 0, "brightness": 0}
        self._write_pending = {"volume": 0, "brightness": 0}

        action = Gio.SimpleAction.new("toggle-launcher", None)
        action.connect("activate", self._on_toggle_launcher_action)
        self.add_action(action)

    # ----------------------------------------------------------- lifecycle
    def do_command_line(self, command_line: Gio.ApplicationCommandLine) -> int:
        if "--toggle-launcher" in command_line.get_arguments():
            self._ensure_hud()
            self.activate_action("toggle-launcher", None)
        else:
            self.activate()
        return 0

    def do_activate(self) -> None:
        self._ensure_hud()

    def do_shutdown(self) -> None:
        self.logger.info("CyberMint HUD stopped cleanly")
        self.executor.shutdown(wait=False, cancel_futures=True)
        Gtk.Application.do_shutdown(self)

    def _ensure_hud(self) -> None:
        if self._started:
            return
        try:
            self._install_css()
            self._build_clock_window()
            self._build_system_window()
            self._build_controls_window()
            for window in self.windows:
                window.show_all()
            self._refresh()
            interval = self.config.get("behavior", {}).get("refresh_interval_seconds", 2)
            GLib.timeout_add_seconds(interval, self._refresh)
            GLib.timeout_add_seconds(2, self._poll_controls)
            self._started = True
            self.logger.info(
                "CyberMint HUD started (GTK %s, Cairo %s, Session: %s, Cinnamon: %s, Scale: %.2f)",
                self.report.gtk_version,
                self.report.cairo_version,
                self.report.session,
                self.report.cinnamon_version,
                self.scale,
            )
            for warning in self.report.warnings:
                self.logger.warning("Session compatibility note: %s", warning)
        except Exception:
            self.logger.exception("CyberMint HUD startup failed")
            self.quit()

    def _install_css(self) -> None:
        css = _build_css(self.config["appearance"], self.scale)
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode("utf-8"))
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    # ------------------------------------------------------------- windows
    def _create_window(self, title: str, child: Gtk.Widget, position: dict[str, int] | None) -> Gtk.Window:
        window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL, title=title, application=self)
        screen = Gdk.Screen.get_default()
        if screen is not None:
            rgba_visual = screen.get_rgba_visual()
            if rgba_visual is not None:
                window.set_visual(rgba_visual)
        window.set_app_paintable(True)
        window.set_decorated(False)
        window.set_resizable(False)
        window.set_keep_above(self.config.get("behavior", {}).get("always_on_top", True))
        window.set_skip_taskbar_hint(True)
        window.set_skip_pager_hint(True)
        window.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        window.connect("draw", self._on_window_draw)
        window.add(child)
        if position is not None:
            window.move(position["x"], position["y"])
        else:
            window.set_position(Gtk.WindowPosition.CENTER)
        return window

    def _create_hud_window(self, name: str, title: str, child: Gtk.Widget) -> Gtk.Window:
        window = self._create_window(title, child, effective_position(self.config, name))
        window.connect("key-press-event", self._on_key_press)
        window.connect("delete-event", self._on_delete)
        self.windows.append(window)
        return window

    def _on_window_draw(self, widget: Gtk.Widget, cr: Any) -> bool:
        alloc = widget.get_allocation()
        render_cyber_card(
            cr,
            float(alloc.width),
            float(alloc.height),
            surface_rgba=self.surface_rgba,
            primary_rgba=self.primary_rgba,
            secondary_rgba=self.secondary_rgba,
            scale=self.scale,
        )
        return False  # let child widgets paint on top

    def _create_header(self, title: str, on_close: Any = None, tooltip: str = "Exit CyberMint HUD (Esc)") -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=int(8 * self.scale))
        label = Gtk.Label(label=title)
        label.set_xalign(0.0)
        label.get_style_context().add_class("eyebrow")
        row.pack_start(label, True, True, 0)
        close_btn = Gtk.Button(label="×")
        close_btn.get_style_context().add_class("close-btn")
        close_btn.set_tooltip_text(tooltip)
        close_btn.connect("clicked", (lambda *_: on_close()) if on_close else (lambda *_: self.quit()))
        row.pack_end(close_btn, False, False, 0)
        return row

    def _outer_box(self, spacing: int) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=int(spacing * self.scale))
        box.get_style_context().add_class("hud-inner-box")
        return box

    def _label(self, text: str, css_class: str, xalign: float = 0.0) -> Gtk.Label:
        label = Gtk.Label(label=text)
        label.set_xalign(xalign)
        label.get_style_context().add_class(css_class)
        return label

    def _wrapping_detail(self, text: str) -> Gtk.Label:
        """Detail line that never widens its window: wraps to at most three lines."""
        label = self._label(text, "metric-detail")
        label.set_line_wrap(True)
        label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        label.set_max_width_chars(34)
        label.set_lines(3)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        return label

    # --------------------------------------------------------- clock panel
    def _build_clock_window(self) -> None:
        outer = self._outer_box(6)
        outer.pack_start(self._create_header("// CHRONO.SYS [LOCAL]"), False, False, 0)
        self.clock_label = self._label("--:--:--", "clock-text")
        outer.pack_start(self.clock_label, False, False, 0)
        self.date_label = self._label("Initializing...", "date-text")
        outer.pack_start(self.date_label, False, False, 0)
        self._create_hud_window("clock", "CyberMint HUD — Chrono", outer)

    # ------------------------------------------------------ telemetry panel
    def _build_system_window(self) -> None:
        outer = self._outer_box(8)
        outer.pack_start(self._create_header("// TELEMETRY.SYS [LIVE]"), False, False, 0)
        self.metric_widgets: dict[str, tuple[Gtk.Label, Gtk.Label, Gtk.DrawingArea, Gtk.Box]] = {}
        meters = (("cpu", "CPU LOAD"), ("memory", "RAM USAGE"), ("disk", "ROOT DISK"), ("battery", "BATTERY"))
        for key, title in meters:
            row_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=int(2 * self.scale))
            top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=int(8 * self.scale))
            val_lbl = self._label("—", "metric-value", 1.0)
            top_row.pack_start(self._label(title, "metric-name"), True, True, 0)
            top_row.pack_end(val_lbl, False, False, 0)
            row_box.pack_start(top_row, False, False, 0)
            meter_area = Gtk.DrawingArea()
            meter_area.set_size_request(int(220 * self.scale), int(10 * self.scale))
            meter_area.connect("draw", lambda w, cr, k=key: self._on_meter_draw(w, cr, k))
            row_box.pack_start(meter_area, False, False, 0)
            detail_lbl = self._wrapping_detail("Probing sensor telemetry...")
            row_box.pack_start(detail_lbl, False, False, 0)
            outer.pack_start(row_box, False, False, 0)
            self.metric_widgets[key] = (val_lbl, detail_lbl, meter_area, row_box)
        self._create_hud_window("system", "CyberMint HUD — Telemetry", outer)

    def _on_meter_draw(self, widget: Gtk.Widget, cr: Any, key: str) -> bool:
        alloc = widget.get_allocation()
        fraction, is_active = self.metric_data.get(key, (None, False))
        render_cyber_meter(
            cr,
            float(alloc.width),
            float(alloc.height),
            fraction=fraction,
            primary_rgba=self.primary_rgba,
            secondary_rgba=self.secondary_rgba,
            scale=self.scale,
            is_active=is_active,
        )
        return True

    # -------------------------------------------------------- controls panel
    def _build_controls_window(self) -> None:
        outer = self._outer_box(8)
        outer.set_size_request(int(250 * self.scale), -1)
        outer.pack_start(self._create_header("// CONTROLS.SYS [LOCAL]"), False, False, 0)
        self.control_rows: dict[str, tuple[Gtk.Scale, Gtk.Label, Gtk.Label]] = {}
        for key, title in (("volume", "VOLUME"), ("brightness", "BRIGHTNESS")):
            row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=int(3 * self.scale))
            top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=int(8 * self.scale))
            percent = self._label("…", "metric-value", 1.0)
            top.pack_start(self._label(title, "metric-name"), True, True, 0)
            top.pack_end(percent, False, False, 0)
            scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
            scale.set_draw_value(False)
            scale.set_hexpand(True)
            detail = self._wrapping_detail("Reading current setting…")
            row.pack_start(top, False, False, 0)
            row.pack_start(scale, False, False, 0)
            row.pack_start(detail, False, False, 0)
            outer.pack_start(row, False, False, 0)
            self.control_rows[key] = (scale, percent, detail)
        self.mute_button = Gtk.ToggleButton(label="MUTE")
        self.mute_button.get_style_context().add_class("mute-btn")
        self.mute_button.set_halign(Gtk.Align.START)
        self.mute_button.set_sensitive(False)
        outer.pack_start(self.mute_button, False, False, 0)
        self.control_rows["volume"][0].connect("value-changed", lambda s: self._on_scale_changed("volume", s))
        self.control_rows["brightness"][0].connect("value-changed", lambda s: self._on_scale_changed("brightness", s))
        self.mute_button.connect("toggled", self._on_mute_toggled)
        for scale_widget, _, _ in self.control_rows.values():
            scale_widget.set_sensitive(False)
        self._create_hud_window("controls", "CyberMint HUD — Controls", outer)

    def _poll_controls(self) -> bool:
        if self._controls_inflight or not self._started:
            return GLib.SOURCE_CONTINUE
        self._controls_inflight = True

        def read_all() -> tuple[ControlReading, BrightnessReading]:
            return self.volume.read(), self.brightness.read()

        future = self.executor.submit(read_all)
        future.add_done_callback(self._controls_loaded)
        return GLib.SOURCE_CONTINUE

    def _controls_loaded(self, future: Future) -> None:
        try:
            volume, brightness = future.result()
            GLib.idle_add(self._apply_control_readings, volume, brightness)
        except Exception as exc:
            GLib.idle_add(self._apply_control_failure, str(exc) or exc.__class__.__name__)

    def _user_is_adjusting(self, key: str) -> bool:
        return bool(self._write_timeout[key] or self._write_pending[key])

    def _apply_control_readings(self, volume: ControlReading, brightness: BrightnessReading) -> bool:
        self._controls_inflight = False
        if not self._user_is_adjusting("volume"):
            self._apply_volume(volume)
        if not self._user_is_adjusting("brightness"):
            self._set_control_row("brightness", brightness.value, brightness.error, brightness.backend)
        self._log_error("volume", volume.error)
        self._log_error("brightness", brightness.error)
        return GLib.SOURCE_REMOVE

    def _apply_control_failure(self, reason: str) -> bool:
        self._controls_inflight = False
        self._set_control_row("volume", None, reason)
        self._set_control_row("brightness", None, reason)
        self.mute_button.set_sensitive(False)
        self._log_error("controls", reason)
        return GLib.SOURCE_REMOVE

    def _apply_volume(self, reading: ControlReading) -> None:
        self._set_control_row("volume", reading.value, reading.error, "default output (pactl)")
        self.mute_button.set_sensitive(reading.muted is not None)
        if reading.muted is not None:
            self._controls_updating = True
            self.mute_button.set_active(reading.muted)
            self.mute_button.set_label("MUTED" if reading.muted else "MUTE")
            self._controls_updating = False

    def _set_control_row(self, key: str, value: int | None, error: str, backend: str = "") -> None:
        scale, percent, detail = self.control_rows[key]
        available = value is not None
        scale.set_sensitive(available)
        if available:
            self._controls_updating = True
            scale.set_value(clamp_percent(value))
            self._controls_updating = False
            percent.set_text(f"{clamp_percent(value)}%")
            detail.set_text(backend)
            detail.set_tooltip_text(backend or None)
        else:
            percent.set_text("N/A")
            message = error or "no value reported"
            detail.set_text(f"Unavailable: {message}")
            detail.set_tooltip_text(message)

    def _on_scale_changed(self, key: str, scale: Gtk.Scale) -> None:
        if self._controls_updating or not scale.get_sensitive():
            return
        if self._write_timeout[key]:
            GLib.source_remove(self._write_timeout[key])
        self._write_timeout[key] = GLib.timeout_add(140, self._flush_control_write, key)

    def _flush_control_write(self, key: str) -> bool:
        self._write_timeout[key] = 0
        value = self.control_rows[key][0].get_value()
        if key == "volume":
            operation = lambda: self.volume.set_volume(value)
        else:
            operation = lambda: self.brightness.set_value(value)
        self._write_pending[key] += 1
        future = self.executor.submit(operation)
        future.add_done_callback(lambda result: GLib.idle_add(self._control_write_finished, key, result))
        return GLib.SOURCE_REMOVE

    def _control_write_finished(self, key: str, future: Future) -> bool:
        self._write_pending[key] = max(0, self._write_pending[key] - 1)
        if self._user_is_adjusting(key):
            return GLib.SOURCE_REMOVE  # a newer slider position is already on its way
        try:
            result = future.result()
            if key == "volume":
                self._apply_volume(result)
            else:
                self._set_control_row("brightness", result.value, result.error, result.backend)
            self._log_error(key, result.error)
        except Exception as exc:
            error = str(exc) or exc.__class__.__name__
            self._set_control_row(key, None, error)
            self._log_error(key, error)
        return GLib.SOURCE_REMOVE

    def _on_mute_toggled(self, _button: Gtk.ToggleButton) -> None:
        if self._controls_updating or not self.mute_button.get_sensitive():
            return
        self.mute_button.set_sensitive(False)
        future = self.executor.submit(self.volume.toggle_mute)
        future.add_done_callback(lambda result: GLib.idle_add(self._mute_finished, result))

    def _mute_finished(self, future: Future) -> bool:
        try:
            reading = future.result()
            self._apply_volume(reading)
            self._log_error("volume", reading.error)
        except Exception as exc:
            error = str(exc) or exc.__class__.__name__
            self.mute_button.set_sensitive(False)
            self._set_control_row("volume", None, error)
            self._log_error("volume", error)
        return GLib.SOURCE_REMOVE

    # ------------------------------------------------------------ launcher
    def _build_launcher_window(self) -> None:
        if self._launcher_window is not None:
            return
        card = self._outer_box(8)
        card.set_size_request(int(400 * self.scale), -1)
        card.pack_start(
            self._create_header("// LAUNCHER.SYS [APPS]", on_close=self._hide_launcher, tooltip="Close launcher (Esc)"),
            False, False, 0,
        )
        self._launcher_search = Gtk.SearchEntry()
        self._launcher_search.set_placeholder_text("Search installed applications")
        card.pack_start(self._launcher_search, False, False, 0)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(int(240 * self.scale))
        self._launcher_list = Gtk.ListBox()
        self._launcher_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._launcher_list.connect("row-activated", self._on_launcher_row_activated)
        scroll.add(self._launcher_list)
        self._launcher_scroll = scroll
        card.pack_start(scroll, True, True, 0)
        self._launcher_status = self._wrapping_detail("Loading installed applications…")
        card.pack_start(self._launcher_status, False, False, 0)
        window = self._create_window("CyberMint HUD — Launcher", card, None)
        window.connect("key-press-event", self._on_launcher_key_press)
        window.connect("delete-event", self._on_launcher_delete)
        self._launcher_window = window
        self._launcher_search.connect("changed", self._on_launcher_search_changed)
        self._launcher_search.connect("activate", self._launch_selected)

    def _on_toggle_launcher_action(self, *_args: Any) -> None:
        self._build_launcher_window()
        window = self._launcher_window
        if window is None:
            return
        if window.get_visible():
            window.hide()
            return
        self._launcher_search.set_text("")
        window.show_all()
        window.present()
        self._launcher_search.grab_focus()
        # Show the last known list immediately, then refresh it in the background so
        # newly installed applications appear.
        if self._applications:
            self._render_applications()
        else:
            self._set_launcher_status("Loading installed applications…")
        future = self.executor.submit(enumerate_applications)
        future.add_done_callback(self._applications_loaded)

    def _applications_loaded(self, future: Future) -> None:
        try:
            GLib.idle_add(self._apply_applications, future.result(), "")
        except Exception as exc:
            GLib.idle_add(self._apply_applications, [], str(exc) or exc.__class__.__name__)

    def _apply_applications(self, applications: list[ApplicationEntry], error: str) -> bool:
        if error:
            self._set_launcher_status(f"Unavailable: {error}")
            self._log_error("launcher", error)
            return GLib.SOURCE_REMOVE
        self._log_error("launcher", "")
        self._applications = applications
        self._render_applications()
        return GLib.SOURCE_REMOVE

    def _render_applications(self) -> None:
        if self._launcher_list is None:
            return
        for child in self._launcher_list.get_children():
            self._launcher_list.remove(child)
        query = self._launcher_search.get_text() if self._launcher_search else ""
        self._visible_applications = filter_applications(self._applications, query)
        for app in self._visible_applications:
            label = self._label(app.name, "launcher-entry")
            row = Gtk.ListBoxRow()
            row.add(label)
            row._cybermint_entry = app
            self._launcher_list.add(row)
        self._launcher_list.show_all()
        if self._visible_applications:
            self._launcher_list.select_row(self._launcher_list.get_row_at_index(0))
            self._set_launcher_status(f"{len(self._visible_applications)} applications")
        else:
            self._set_launcher_status("No matching applications")

    def _on_launcher_search_changed(self, *_args: Any) -> None:
        self._render_applications()

    def _on_launcher_key_press(self, _window: Gtk.Window, event: Gdk.EventKey) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            self._hide_launcher()
            return True
        if event.keyval in (Gdk.KEY_Up, Gdk.KEY_Down):
            if self._launcher_list is not None and self._visible_applications:
                current = self._launcher_list.get_selected_row()
                index = current.get_index() if current is not None else 0
                index += -1 if event.keyval == Gdk.KEY_Up else 1
                index = max(0, min(len(self._visible_applications) - 1, index))
                row = self._launcher_list.get_row_at_index(index)
                self._launcher_list.select_row(row)
                self._scroll_row_into_view(row)
            return True
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self._launch_selected()
            return True
        return False

    def _scroll_row_into_view(self, row: Gtk.ListBoxRow) -> None:
        scroll = getattr(self, "_launcher_scroll", None)
        if scroll is None or row is None:
            return
        alloc = row.get_allocation()
        scroll.get_vadjustment().clamp_page(alloc.y, alloc.y + alloc.height)

    def _on_launcher_row_activated(self, _list: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
        entry = getattr(row, "_cybermint_entry", None)
        if entry is not None:
            self._launch_entry(entry)

    def _launch_selected(self, *_args: Any) -> None:
        if self._launcher_list is None:
            return
        row = self._launcher_list.get_selected_row()
        entry = getattr(row, "_cybermint_entry", None) if row is not None else None
        if entry is not None:
            self._launch_entry(entry)

    def _launch_entry(self, entry: ApplicationEntry) -> None:
        self._set_launcher_status(f"Starting {entry.name}…")
        future = self.executor.submit(launch_application, entry)
        future.add_done_callback(lambda result: GLib.idle_add(self._launch_finished, entry.name, result))

    def _launch_finished(self, name: str, future: Future) -> bool:
        try:
            launched, error = future.result()
        except Exception as exc:
            launched, error = False, str(exc) or exc.__class__.__name__
        if launched:
            self._log_error("launcher", "")
            self._hide_launcher()
        else:
            self._set_launcher_status(f"Could not start {name}: {error}")
            self._log_error("launcher", error)
        return GLib.SOURCE_REMOVE

    def _hide_launcher(self) -> None:
        if self._launcher_window is not None:
            self._launcher_window.hide()

    def _set_launcher_status(self, message: str) -> None:
        if self._launcher_status is not None:
            self._launcher_status.set_text(message)

    def _on_launcher_delete(self, *_args: Any) -> bool:
        self._hide_launcher()
        return True  # hide only; never destroy the launcher or quit the HUD

    # ------------------------------------------------------------ telemetry
    def _refresh(self) -> bool:
        try:
            now = GLib.DateTime.new_now_local()
            self.clock_label.set_text(now.format("%H:%M:%S"))
            self.date_label.set_text(now.format("%A // %d %b %Y").upper())

            snapshot = self.monitor.snapshot()
            self._update_metric("cpu", snapshot.cpu)
            self._update_metric("memory", snapshot.memory)
            self._update_metric("disk", snapshot.disk)

            val_lbl, detail_lbl, meter_area, _ = self.metric_widgets["battery"]
            if snapshot.battery is None:
                val_lbl.set_text("N/A")
                detail_lbl.set_text("No battery hardware detected")
                self.metric_data["battery"] = (None, False)
                meter_area.hide()
            else:
                meter_area.show()
                self._update_metric("battery", snapshot.battery)
            return True
        except Exception:
            self.logger.exception("Error during HUD refresh cycle")
            return True

    def _update_metric(self, key: str, metric: Metric) -> None:
        val_lbl, detail_lbl, meter_area, _ = self.metric_widgets[key]
        if metric.value is None:
            val_lbl.set_text("N/A")
            detail_lbl.set_text(metric.detail or "Telemetry unavailable")
            self.metric_data[key] = (None, False)
            meter_area.queue_draw()
            self._log_error(f"metric:{key}", metric.detail)
            return
        self._log_error(f"metric:{key}", "")
        val_lbl.set_text(f"{metric.value:.0f}%")
        detail_lbl.set_text(metric.detail)
        self.metric_data[key] = (metric.value / 100.0, True)
        meter_area.queue_draw()

    def _log_error(self, key: str, detail: str) -> None:
        previous = self._last_errors.get(key, "")
        if detail and detail != previous:
            self.logger.warning("%s unavailable: %s", key, detail)
        self._last_errors[key] = detail

    # --------------------------------------------------------------- events
    def _on_key_press(self, _window: Gtk.Window, event: Gdk.EventKey) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            self.quit()
            return True
        return False

    def _on_delete(self, *_args: Any) -> bool:
        self.quit()
        return False


def run(config: dict[str, Any], logger: logging.Logger, report: Any, toggle_launcher: bool = False) -> int:
    app = HudApplication(config, logger, report)
    arguments = ["cybermint-hud"]
    if toggle_launcher:
        arguments.append("--toggle-launcher")
    return app.run(arguments)
