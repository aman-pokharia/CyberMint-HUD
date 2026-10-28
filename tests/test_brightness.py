import subprocess
import unittest
from unittest.mock import Mock

from cybermint_hud.brightness import (
    BrightnessControl,
    BrightnessCtl,
    BrightnessReading,
    CinnamonDbusBrightness,
    INTERFACE,
    OBJECT_PATH,
    SERVICE,
    _validate_interface,
    parse_brightnessctl,
)


INTERFACE_XML = """<node>
<interface name="org.cinnamon.SettingsDaemon.Power.Screen">
  <method name="GetPercentage"><arg type="u" name="percentage" direction="out"/></method>
  <method name="SetPercentage">
    <arg type="u" name="percentage" direction="in"/>
    <arg type="u" name="new_percentage" direction="out"/>
  </method>
</interface></node>"""


class FakeVariant:
    def __init__(self, value):
        self.value = value

    def unpack(self):
        return self.value


class FakeProxy:
    def __init__(self):
        self.calls = []

    def call_sync(self, method, parameters, flags, timeout, cancellable):
        self.calls.append((method, parameters.value))
        if method == "GetPercentage":
            return FakeVariant((42,))
        return FakeVariant((parameters.value[0],))


class FakeConnection:
    def __init__(self, proxy):
        self.proxy = proxy
        self.calls = []

    def call_sync(self, *args):
        self.calls.append(args)
        return FakeVariant((INTERFACE_XML,))


class BrightnessTests(unittest.TestCase):
    def test_brightnessctl_sample_parser_and_invalid_data(self):
        self.assertEqual(parse_brightnessctl("backlight,intel_backlight,5000,65%,7500"), 65)
        with self.assertRaisesRegex(ValueError, "no brightness percentage"):
            parse_brightnessctl("backlight,intel_backlight,5000,7500")

    def test_dbus_introspection_uses_expected_cinnamon_endpoint_and_signatures(self):
        proxy = FakeProxy()
        connection = FakeConnection(proxy)

        class FakeGio:
            class BusType:
                SESSION = 1

            class DBusCallFlags:
                NONE = 0

            class DBusProxyFlags:
                DO_NOT_AUTO_START = 1

            @staticmethod
            def bus_get_sync(bus_type, cancellable):
                return connection

            class DBusProxy:
                @staticmethod
                def new_sync(*args):
                    return proxy

        class FakeGLib:
            class VariantType:
                @staticmethod
                def new(signature):
                    return signature

            @staticmethod
            def Variant(signature, values):
                return FakeVariant(values)

        adapter = CinnamonDbusBrightness.connect(gio=FakeGio, glib=FakeGLib)
        self.assertEqual(adapter.read().value, 42)
        self.assertEqual(adapter.set_value(130).value, 100)
        self.assertEqual(proxy.calls, [("GetPercentage", ()), ("SetPercentage", (100,))])
        introspection_call = connection.calls[0]
        self.assertEqual(introspection_call[:4], (SERVICE, OBJECT_PATH, "org.freedesktop.DBus.Introspectable", "Introspect"))
        self.assertEqual(introspection_call[4].value, ())
        self.assertEqual(INTERFACE, "org.cinnamon.SettingsDaemon.Power.Screen")

    def test_dbus_signature_mismatch_is_rejected_before_use(self):
        with self.assertRaisesRegex(ValueError, "unsupported signature"):
            _validate_interface(INTERFACE_XML.replace('direction="out"/></method>', 'direction="in"/></method>', 1))

    def test_brightnessctl_is_primary_and_dbus_is_best_effort_fallback(self):
        events = []

        class Primary:
            def read(self):
                events.append("brightnessctl")
                return BrightnessReading(61, "brightnessctl")

        def dbus():
            events.append("cinnamon-dbus")
            return None

        controller = BrightnessControl(dbus_factory=dbus, brightnessctl_factory=Primary)
        result = controller.read()
        self.assertEqual(result.value, 61)
        self.assertEqual(events, ["brightnessctl"])

    def test_dbus_is_tried_when_brightnessctl_is_unavailable(self):
        events = []

        class Fallback:
            def read(self):
                events.append("cinnamon-dbus")
                return BrightnessReading(42, "Cinnamon D-Bus")

        def no_brightnessctl():
            events.append("brightnessctl")
            raise RuntimeError("not installed")

        controller = BrightnessControl(dbus_factory=Fallback, brightnessctl_factory=no_brightnessctl)
        result = controller.read()
        self.assertEqual(result.value, 42)
        self.assertEqual(events, ["brightnessctl", "cinnamon-dbus"])

    def test_unavailable_when_both_brightness_sources_fail(self):
        controller = BrightnessControl(
            dbus_factory=lambda: (_ for _ in ()).throw(RuntimeError("no Cinnamon session")),
            brightnessctl_factory=lambda: (_ for _ in ()).throw(RuntimeError("no backlight device")),
        )
        result = controller.read()
        self.assertIsNone(result.value)
        self.assertIn("no Cinnamon session", result.error)
        self.assertIn("no backlight device", result.error)

    def test_brightnessctl_uses_injected_safe_runner_and_clamps_values(self):
        runner = Mock(side_effect=[
            subprocess.CompletedProcess([], 0, "", ""),
            subprocess.CompletedProcess([], 0, "backlight,x,80,80%,100\n", ""),
        ])
        control = BrightnessCtl(run=runner, which=lambda _name: "/usr/bin/brightnessctl")
        result = control.set_value(115)
        self.assertEqual(result.value, 80)
        self.assertEqual(runner.call_args_list[0].args[0], ["/usr/bin/brightnessctl", "set", "100%"])
        self.assertFalse(runner.call_args_list[0].kwargs["shell"])


if __name__ == "__main__":
    unittest.main()


class BrightnessBackoffTests(unittest.TestCase):
    def test_unavailable_result_is_cached_until_retry_window_passes(self):
        now = [100.0]
        calls = []

        def failing_dbus():
            calls.append("dbus")
            raise RuntimeError("no service")

        def failing_ctl():
            calls.append("ctl")
            raise RuntimeError("not installed")

        control = BrightnessControl(
            dbus_factory=failing_dbus,
            brightnessctl_factory=failing_ctl,
            clock=lambda: now[0],
            retry_seconds=30,
        )
        first = control.read()
        self.assertIsNone(first.value)
        self.assertEqual(calls, ["ctl", "dbus"])
        now[0] = 110.0
        self.assertIs(control.read(), first)           # cached, no new probing
        self.assertEqual(calls, ["ctl", "dbus"])
        now[0] = 131.0
        control.read()                                  # retry window passed
        self.assertEqual(calls, ["ctl", "dbus", "ctl", "dbus"])
