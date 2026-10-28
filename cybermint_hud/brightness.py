"""Cinnamon screen brightness with a brightnessctl fallback."""

from __future__ import annotations

import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from .volume import clamp_percent


SERVICE = "org.cinnamon.SettingsDaemon.Power"
OBJECT_PATH = "/org/cinnamon/SettingsDaemon/Power"
INTERFACE = "org.cinnamon.SettingsDaemon.Power.Screen"
# UNVERIFIED on real Mint: the endpoint names and signatures above are isolated here and
# are checked against the live D-Bus introspection data at connect time, but they were
# written without access to a Cinnamon session. If the real interface differs, the check
# fails cleanly and the control is reported as unavailable.


@dataclass(frozen=True)
class BrightnessReading:
    value: int | None
    backend: str
    error: str = ""


def parse_brightnessctl(text: str) -> int:
    # UNVERIFIED on real Mint: -m output is isolated here and covered by fixture tests.
    # brightnessctl -m output includes device, current, percentage, and maximum.
    match = re.search(r"(?:^|,)\s*([0-9]{1,3})%\s*(?:,|$)", text.strip())
    if not match:
        raise ValueError("brightnessctl returned no brightness percentage")
    return clamp_percent(int(match.group(1)))


class CinnamonDbusBrightness:
    """Calls the live Cinnamon endpoint only after validating its introspection XML."""

    def __init__(self, proxy: Any, variant_factory: Callable[[str, tuple], Any]) -> None:
        self.proxy = proxy
        self._variant = variant_factory

    @classmethod
    def connect(cls, gio: Any | None = None, glib: Any | None = None, timeout_ms: int = 1500) -> "CinnamonDbusBrightness":
        if gio is None or glib is None:
            import gi

            gi.require_version("Gio", "2.0")
            gi.require_version("GLib", "2.0")
            from gi.repository import Gio, GLib

            gio, glib = Gio, GLib

        connection = gio.bus_get_sync(gio.BusType.SESSION, None)
        xml_variant = connection.call_sync(
            SERVICE,
            OBJECT_PATH,
            "org.freedesktop.DBus.Introspectable",
            "Introspect",
            glib.Variant("()", ()),
            glib.VariantType.new("(s)"),
            gio.DBusCallFlags.NONE,
            timeout_ms,
            None,
        )
        xml_text = xml_variant.unpack()[0]
        _validate_interface(xml_text)
        proxy = gio.DBusProxy.new_sync(
            connection,
            gio.DBusProxyFlags.DO_NOT_AUTO_START,
            None,
            SERVICE,
            OBJECT_PATH,
            INTERFACE,
            None,
        )
        return cls(proxy, glib.Variant)

    def read(self) -> BrightnessReading:
        try:
            result = self.proxy.call_sync("GetPercentage", self._variant("()", ()), 0, 1500, None)
            return BrightnessReading(clamp_percent(result.unpack()[0]), "Cinnamon D-Bus")
        except Exception as exc:
            raise RuntimeError(f"Cinnamon brightness read failed: {_reason(exc)}") from exc

    def set_value(self, value: float | int) -> BrightnessReading:
        try:
            result = self.proxy.call_sync("SetPercentage", self._variant("(u)", (clamp_percent(value),)), 0, 1500, None)
            return BrightnessReading(clamp_percent(result.unpack()[0]), "Cinnamon D-Bus")
        except Exception as exc:
            raise RuntimeError(f"Cinnamon brightness change failed: {_reason(exc)}") from exc


class BrightnessCtl:
    def __init__(
        self,
        run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
        which: Callable[[str], str | None] = shutil.which,
        timeout: float = 2.0,
    ) -> None:
        self._run = run
        self._which = which
        self.timeout = timeout

    def read(self) -> BrightnessReading:
        executable = self._which("brightnessctl")
        if not executable:
            raise RuntimeError("brightnessctl is not installed or not on PATH")
        result = self._execute([executable, "-m"])
        if result.returncode != 0:
            raise RuntimeError(_command_error("brightnessctl query", result))
        try:
            return BrightnessReading(parse_brightnessctl(result.stdout), "brightnessctl")
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc

    def set_value(self, value: float | int) -> BrightnessReading:
        executable = self._which("brightnessctl")
        if not executable:
            raise RuntimeError("brightnessctl is not installed or not on PATH")
        result = self._execute([executable, "set", f"{clamp_percent(value)}%"])
        if result.returncode != 0:
            raise RuntimeError(_command_error("brightnessctl change", result))
        return self.read()

    def _execute(self, args: list[str]) -> subprocess.CompletedProcess:
        try:
            return self._run(args, capture_output=True, text=True, timeout=self.timeout, check=False, shell=False)
        except FileNotFoundError as exc:
            raise RuntimeError("brightnessctl is not installed or not on PATH") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("brightnessctl timed out") from exc
        except OSError as exc:
            raise RuntimeError(str(exc)) from exc


class BrightnessControl:
    """Use brightnessctl first; try the unverified Cinnamon D-Bus route second."""

    def __init__(
        self,
        dbus_factory: Callable[[], Any] = CinnamonDbusBrightness.connect,
        brightnessctl_factory: Callable[[], Any] | None = None,
        clock: Callable[[], float] = time.monotonic,
        retry_seconds: float = 30.0,
    ) -> None:
        self._dbus_factory = dbus_factory
        self._brightnessctl_factory = brightnessctl_factory or BrightnessCtl
        self._backend: Any | None = None
        self._dbus_error = ""
        self._clock = clock
        self._retry_seconds = retry_seconds
        self._unavailable_until = 0.0
        self._unavailable: BrightnessReading | None = None

    def read(self) -> BrightnessReading:
        if self._backend is not None:
            try:
                return self._backend.read()
            except Exception as exc:
                self._dbus_error = _reason(exc)
                self._backend = None
        # When no backend works (for example on a desktop PC without a backlight), do not
        # re-probe every poll: reuse the last "unavailable" answer for a while.
        if self._unavailable is not None and self._clock() < self._unavailable_until:
            return self._unavailable
        return self._read_with_fallback()

    def set_value(self, value: float | int) -> BrightnessReading:
        if self._backend is None:
            initial = self.read()
            if initial.value is None:
                return initial
        try:
            return self._backend.set_value(clamp_percent(value))
        except Exception as exc:
            self._dbus_error = _reason(exc)
            self._backend = None
            return self._read_with_fallback(set_value=clamp_percent(value))

    def _read_with_fallback(self, set_value: int | None = None) -> BrightnessReading:
        errors = []
        try:
            backend = self._brightnessctl_factory()
            result = backend.set_value(set_value) if set_value is not None else backend.read()
            if result.value is None:
                raise RuntimeError(result.error or "brightnessctl returned no brightness value")
            self._backend = backend
            self._unavailable = None
            return result
        except Exception as exc:
            errors.append(f"brightnessctl: {_reason(exc)}")

        try:
            # Best-effort only: this endpoint cannot be verified without real Mint.
            backend = self._dbus_factory()
            result = backend.set_value(set_value) if set_value is not None else backend.read()
            if result.value is None:
                raise RuntimeError(result.error or "Cinnamon returned no brightness value")
            self._backend = backend
            self._unavailable = None
            return result
        except Exception as exc:
            self._backend = None
            errors.append(f"Cinnamon D-Bus: {_reason(exc)}")
            self._unavailable = BrightnessReading(None, "unavailable", "; ".join(errors))
            self._unavailable_until = self._clock() + self._retry_seconds
            return self._unavailable


def _validate_interface(xml_text: str) -> None:
    try:
        root = ET.fromstring(xml_text)
        interface = next((item for item in root.findall("interface") if item.get("name") == INTERFACE), None)
        if interface is None:
            raise ValueError(f"D-Bus interface {INTERFACE} is missing")
        methods = {item.get("name"): item for item in interface.findall("method")}
        get_method = methods.get("GetPercentage")
        set_method = methods.get("SetPercentage")
        if get_method is None or set_method is None:
            raise ValueError("Cinnamon brightness methods are missing")
        get_out = [(arg.get("type"), arg.get("direction", "in")) for arg in get_method.findall("arg")]
        set_args = [(arg.get("type"), arg.get("direction", "in")) for arg in set_method.findall("arg")]
        if get_out != [("u", "out")] or set_args != [("u", "in"), ("u", "out")]:
            raise ValueError("Cinnamon brightness methods have an unsupported signature")
    except ET.ParseError as exc:
        raise ValueError(f"invalid Cinnamon D-Bus introspection data: {exc}") from exc


def _reason(exc: Exception) -> str:
    return str(exc).strip() or exc.__class__.__name__


def _command_error(operation: str, result: subprocess.CompletedProcess) -> str:
    detail = (result.stderr or result.stdout or "no details").strip()
    return f"{operation} unavailable: {detail}"
