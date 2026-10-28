import os
import unittest
from unittest import mock

from cybermint_hud.compat import compatibility_report


class CompatTests(unittest.TestCase):
    def test_report_structure_and_headless_detection(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            report = compatibility_report()
            self.assertIn("Headless", report.session)
            self.assertTrue(len(report.lines) >= 4)

    def test_x11_session_detection(self):
        with mock.patch.dict(os.environ, {"DISPLAY": ":0"}, clear=True):
            report = compatibility_report()
            self.assertEqual(report.session, "X11")
            self.assertFalse(any("Wayland" in w for w in report.warnings))

    def test_wayland_session_warning(self):
        with mock.patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0"}, clear=True):
            report = compatibility_report()
            self.assertEqual(report.session, "Wayland")
            self.assertTrue(any("Wayland compositor controls window placement" in w for w in report.warnings))

    def test_cinnamon_version_warning(self):
        with mock.patch.dict(os.environ, {"CINNAMON_VERSION": "5.4.12"}, clear=True):
            report = compatibility_report()
            self.assertEqual(report.cinnamon_version, "5.4.12")
            self.assertTrue(any("below the documented target of 6.2" in w for w in report.warnings))


if __name__ == "__main__":
    unittest.main()
