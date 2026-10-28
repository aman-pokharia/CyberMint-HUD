import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from cybermint_hud.monitoring import Metric, SystemMonitor


class MonitoringTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.proc = self.root / "proc"
        self.sys = self.root / "sys"
        self.proc.mkdir()
        self.sys.mkdir()
        self.monitor = SystemMonitor(self.proc, self.sys, self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_cpu_uses_two_samples(self):
        stat = self.proc / "stat"
        stat.write_text("cpu 100 0 100 800 0 0 0 0\n", encoding="ascii")
        self.assertIsNone(self.monitor.cpu().value)
        stat.write_text("cpu 200 0 200 900 0 0 0 0\n", encoding="ascii")
        self.assertEqual(self.monitor.cpu().value, 66.66666666666667)

    def test_memory_uses_available_counter(self):
        (self.proc / "meminfo").write_text("MemTotal: 1048576 kB\nMemAvailable: 262144 kB\n", encoding="ascii")
        metric = self.monitor.memory()
        self.assertEqual(metric.value, 75.0)
        self.assertIn("0.8 / 1.0 GiB", metric.detail)

    def test_missing_sources_are_unavailable_and_battery_is_optional(self):
        # Empty mock filesystem
        mem = self.monitor.memory()
        self.assertIsNone(mem.value)
        self.assertIn("unavailable", mem.detail)

        # Battery returns None when no battery device is detected
        self.assertIsNone(self.monitor.battery())

    def test_never_fabricates_telemetry_on_failure(self):
        # Even with garbage in procfs, value must be None, never a fake number
        (self.proc / "stat").write_text("invalid cpu content\n", encoding="ascii")
        cpu = self.monitor.cpu()
        self.assertIsNone(cpu.value)

        (self.proc / "meminfo").write_text("Garbage: 1234\n", encoding="ascii")
        mem = self.monitor.memory()
        self.assertIsNone(mem.value)

    def test_battery_capacity_and_status_reported(self):
        battery = self.sys / "class" / "power_supply" / "BAT0"
        battery.mkdir(parents=True)
        (battery / "type").write_text("Battery\n", encoding="ascii")
        (battery / "capacity").write_text("85\n", encoding="ascii")
        (battery / "status").write_text("Charging\n", encoding="ascii")

        metric = self.monitor.battery()
        self.assertIsNotNone(metric)
        self.assertEqual(metric.value, 85.0)
        self.assertEqual(metric.detail, "Charging")

    def test_disk_percentage_uses_available_blocks(self):
        stats = SimpleNamespace(f_blocks=100, f_frsize=1024, f_bavail=25)
        with mock.patch("cybermint_hud.monitoring.os.statvfs", return_value=stats, create=True):
            metric = self.monitor.disk()
        self.assertEqual(metric.value, 75.0)
        self.assertEqual(metric.detail, "75.0 KiB / 100.0 KiB")

    def test_snapshot_returns_all_components(self):
        snap = self.monitor.snapshot()
        self.assertIsInstance(snap.cpu, Metric)
        self.assertIsInstance(snap.memory, Metric)
        self.assertIsInstance(snap.disk, Metric)
        self.assertTrue(snap.battery is None or isinstance(snap.battery, Metric))


if __name__ == "__main__":
    unittest.main()
