from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class CompatibilityReport:
    gtk_available: bool
    cairo_available: bool
    gtk_version: str
    cairo_version: str
    cinnamon_version: str
    session: str
    gtk_error: str = ""
    warnings: tuple[str, ...] = ()

    @property
    def lines(self) -> tuple[str, ...]:
        result = [
            f"GTK 3 Runtime: {self.gtk_version} ({'available' if self.gtk_available else 'unavailable'})",
            f"Cairo 2D Engine: {self.cairo_version} ({'available' if self.cairo_available else 'unavailable'})",
            f"Cinnamon Desktop: {self.cinnamon_version}",
            f"Display Session: {self.session}",
        ]
        if self.gtk_error:
            result.append(f"GTK Runtime Error: {self.gtk_error}")
        for warning in self.warnings:
            result.append(f"Note: {warning}")
        return tuple(result)


def compatibility_report() -> CompatibilityReport:
    gtk_available = False
    gtk_version = "unavailable"
    cairo_available = False
    cairo_version = "unavailable"
    error = ""

    # Check GTK 3
    try:
        import gi

        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk

        gtk_version = f"{Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()}"
        gtk_available = True
    except (ImportError, ValueError, AttributeError) as exc:
        error = str(exc)

    # Check Cairo
    try:
        import cairo

        cairo_version = getattr(cairo, "cairo_version_string", lambda: "present")()
        cairo_available = True
    except (ImportError, AttributeError):
        # In PyGObject, Cairo context may still be passed to widget draw signals via gi
        pass

    session = _detect_session()
    cinnamon = _detect_cinnamon()
    warnings: list[str] = []

    if session == "Wayland":
        warnings.append("Wayland compositor controls window placement; initial X/Y coordinates may be ignored.")
    if cinnamon.startswith("unknown"):
        warnings.append("Cinnamon version was not detected; this prototype targets Cinnamon 6.2 or newer.")
    elif _version_tuple(cinnamon) < (6, 2):
        warnings.append(f"Detected Cinnamon {cinnamon} is below the documented target of 6.2.")

    if gtk_available and _version_tuple(gtk_version) < (3, 24):
        warnings.append(f"Detected GTK {gtk_version} is below the target of 3.24.")

    warnings.append("Desktop stacking, RGBA transparency, and click-through require verification on a live Linux Mint installation.")

    return CompatibilityReport(
        gtk_available=gtk_available,
        cairo_available=cairo_available,
        gtk_version=gtk_version,
        cairo_version=cairo_version,
        cinnamon_version=cinnamon,
        session=session,
        gtk_error=error,
        warnings=tuple(warnings),
    )


def _detect_session() -> str:
    if os.environ.get("WAYLAND_DISPLAY"):
        return "Wayland"
    if os.environ.get("DISPLAY"):
        return "X11"
    return "Headless / Non-graphical (no DISPLAY or WAYLAND_DISPLAY)"


def _detect_cinnamon() -> str:
    env_ver = os.environ.get("CINNAMON_VERSION")
    if env_ver:
        return env_ver

    # Attempt to probe cinnamon --version if the binary exists
    cinnamon_bin = shutil.which("cinnamon")
    if cinnamon_bin:
        try:
            output = subprocess.check_output([cinnamon_bin, "--version"], text=True, timeout=2).strip()
            # Typically outputs "Cinnamon 6.2.9"
            parts = output.split()
            if len(parts) >= 2:
                return parts[1]
            return output
        except Exception:
            pass

    return "unknown (not reported by environment or executable)"


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = []
    for item in value.split("."):
        digits = "".join(char for char in item if char.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)
