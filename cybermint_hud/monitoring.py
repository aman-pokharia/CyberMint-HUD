from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Metric:
    value: float | None
    detail: str


@dataclass(frozen=True)
class SystemSnapshot:
    cpu: Metric
    memory: Metric
    disk: Metric
    battery: Metric | None


class SystemMonitor:
    """Reads system performance counters; failures are isolated per metric."""

    def __init__(
        self,
        proc_root: Path = Path("/proc"),
        sys_root: Path = Path("/sys"),
        root_path: Path = Path("/"),
        enable_psutil_fallback: bool | None = None,
    ) -> None:
        self.proc_root = proc_root
        self.sys_root = sys_root
        self.root_path = root_path

        # If custom proc_root or sys_root was injected (e.g. in unit tests),
        # do not fall back to host psutil unless explicitly requested.
        if enable_psutil_fallback is None:
            self.enable_psutil_fallback = (proc_root == Path("/proc") and sys_root == Path("/sys"))
        else:
            self.enable_psutil_fallback = enable_psutil_fallback

        self._last_cpu: tuple[int, int] | None = None

    def snapshot(self) -> SystemSnapshot:
        return SystemSnapshot(
            cpu=self.cpu(),
            memory=self.memory(),
            disk=self.disk(),
            battery=self.battery(),
        )

    def cpu(self) -> Metric:
        stat_file = self.proc_root / "stat"

        # 1. Try Linux procfs stat
        if stat_file.is_file():
            try:
                lines = stat_file.read_text(encoding="ascii").splitlines()
                if not lines:
                    return Metric(None, "Empty /proc/stat")
                fields = lines[0].split()
                if fields[0] != "cpu" or len(fields) < 5:
                    return Metric(None, "Invalid aggregate CPU counter in /proc/stat")

                values = [int(f) for f in fields[1:]]
                idle = values[3] + (values[4] if len(values) > 4 else 0)
                total = sum(values)
                previous = self._last_cpu
                self._last_cpu = (total, idle)
                if previous is None or total <= previous[0]:
                    return Metric(None, "Waiting for initial CPU sample")

                delta_total = total - previous[0]
                delta_idle = idle - previous[1]
                if delta_total <= 0:
                    return Metric(0.0, "Idle")

                pct = max(0.0, min(100.0, 100.0 * (delta_total - delta_idle) / delta_total))
                return Metric(pct, f"{pct:.1f}% load")
            except (OSError, UnicodeError, ValueError, IndexError) as exc:
                return Metric(None, f"procfs cpu error: {exc}")

        # 2. Cross-platform fallback via psutil if procfs is absent
        if self.enable_psutil_fallback:
            try:
                import psutil

                pct = psutil.cpu_percent(interval=0.0)
                return Metric(pct, f"{pct:.1f}% load")
            except ImportError:
                pass
            except Exception as exc:
                return Metric(None, f"psutil cpu error: {exc}")

        return Metric(None, "CPU counters unavailable (no /proc/stat)")

    def memory(self) -> Metric:
        meminfo_file = self.proc_root / "meminfo"

        # 1. Try Linux procfs meminfo
        if meminfo_file.is_file():
            try:
                values: dict[str, int] = {}
                for line in meminfo_file.read_text(encoding="ascii").splitlines():
                    key, _, rest = line.partition(":")
                    parts = rest.split()
                    if parts and key in {"MemTotal", "MemAvailable"}:
                        values[key] = int(parts[0])

                if "MemTotal" in values and "MemAvailable" in values:
                    total = values["MemTotal"]
                    available = values["MemAvailable"]
                    if total > 0 and 0 <= available <= total:
                        used = total - available
                        pct = 100.0 * used / total
                        return Metric(pct, f"{used / 1024 / 1024:.1f} / {total / 1024 / 1024:.1f} GiB")
                return Metric(None, "MemTotal or MemAvailable missing in /proc/meminfo")
            except (OSError, UnicodeError, ValueError) as exc:
                return Metric(None, f"procfs meminfo error: {exc}")

        # 2. Cross-platform fallback via psutil
        if self.enable_psutil_fallback:
            try:
                import psutil

                vmem = psutil.virtual_memory()
                used_gib = (vmem.total - vmem.available) / (1024**3)
                total_gib = vmem.total / (1024**3)
                return Metric(vmem.percent, f"{used_gib:.1f} / {total_gib:.1f} GiB")
            except ImportError:
                pass
            except Exception as exc:
                return Metric(None, f"psutil memory error: {exc}")

        return Metric(None, "Memory counters unavailable (no /proc/meminfo)")

    def disk(self) -> Metric:
        # 1. Try statvfs (Unix / Linux)
        statvfs = getattr(os, "statvfs", None)
        if statvfs is not None:
            try:
                stats = statvfs(self.root_path)
                total = stats.f_blocks * stats.f_frsize
                available = stats.f_bavail * stats.f_frsize
                if total > 0:
                    used = max(0, total - available)
                    pct = 100.0 * used / total
                    return Metric(pct, f"{_format_bytes(used)} / {_format_bytes(total)}")
            except (OSError, ValueError):
                pass

        # 2. Fallback via shutil.disk_usage
        try:
            path_str = str(self.root_path)
            usage = shutil.disk_usage(path_str)
            if usage.total > 0:
                pct = 100.0 * usage.used / usage.total
                return Metric(pct, f"{_format_bytes(usage.used)} / {_format_bytes(usage.total)}")
        except (OSError, ValueError) as exc:
            return Metric(None, f"Disk usage error: {exc}")

        return Metric(None, "Disk capacity statistics unavailable")

    def battery(self) -> Metric | None:
        power_root = self.sys_root / "class" / "power_supply"

        # 1. Try Linux sysfs power_supply
        if power_root.is_dir():
            try:
                batteries = []
                for p in power_root.iterdir():
                    type_file = p / "type"
                    if type_file.is_file() and type_file.read_text(encoding="ascii").strip() == "Battery":
                        batteries.append(p)

                if batteries:
                    readings: list[int] = []
                    statuses: list[str] = []
                    for b in batteries:
                        cap_file = b / "capacity"
                        if cap_file.is_file():
                            capacity = int(cap_file.read_text(encoding="ascii").strip())
                            if 0 <= capacity <= 100:
                                readings.append(capacity)
                        status_file = b / "status"
                        if status_file.is_file():
                            statuses.append(status_file.read_text(encoding="ascii").strip())

                    if readings:
                        avg_cap = sum(readings) / len(readings)
                        status_label = statuses[0] if statuses else "Discharging"
                        return Metric(avg_cap, status_label)
                    return Metric(None, "Battery found but capacity is unreadable")
                return None
            except (OSError, UnicodeError, ValueError) as exc:
                return Metric(None, f"sysfs battery error: {exc}")

        # 2. Cross-platform fallback via psutil
        if self.enable_psutil_fallback:
            try:
                import psutil

                b_info = psutil.sensors_battery()
                if b_info is None:
                    return None
                status = "Charging (AC)" if b_info.power_plugged else "Discharging"
                return Metric(float(b_info.percent), status)
            except (ImportError, AttributeError):
                return None
            except Exception as exc:
                return Metric(None, f"Battery reading error: {exc}")

        return None


def _format_bytes(count: int) -> str:
    value = float(count)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TiB"
