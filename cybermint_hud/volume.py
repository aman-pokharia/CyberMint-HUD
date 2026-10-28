"""PulseAudio-compatible volume controls through pactl."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable, Sequence


@dataclass(frozen=True)
class ControlReading:
    value: int | None
    muted: bool | None = None
    error: str = ""


def clamp_percent(value: float | int) -> int:
    return max(0, min(100, int(round(float(value)))))


def parse_volume(text: str) -> int:
    # UNVERIFIED on real Mint: tests cover representative pactl output; a live PipeWire
    # PulseAudio-compatibility response still needs to be checked on the target machine.
    values = [int(value) for value in re.findall(r"(?<![\w])([0-9]{1,3})%", text)]
    if not values:
        raise ValueError("pactl returned no volume percentage")
    return clamp_percent(sum(values) / len(values))


def parse_mute(text: str) -> bool:
    match = re.search(r"^\s*Mute:\s*(yes|no)\s*$", text, re.IGNORECASE | re.MULTILINE)
    if not match:
        raise ValueError("pactl returned no mute state")
    return match.group(1).lower() == "yes"


class PactlVolume:
    def __init__(
        self,
        run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
        which: Callable[[str], str | None] = shutil.which,
        timeout: float = 2.0,
    ) -> None:
        self._run = run
        self._which = which
        self.timeout = timeout

    def read(self) -> ControlReading:
        executable = self._which("pactl")
        if not executable:
            return ControlReading(None, error="pactl is not installed or not on PATH")
        volume = self._execute([executable, "get-sink-volume", "@DEFAULT_SINK@"])
        if volume.returncode != 0:
            return ControlReading(None, error=_command_error("pactl volume query", volume))
        mute = self._execute([executable, "get-sink-mute", "@DEFAULT_SINK@"])
        if mute.returncode != 0:
            return ControlReading(None, error=_command_error("pactl mute query", mute))
        try:
            return ControlReading(parse_volume(volume.stdout), parse_mute(mute.stdout))
        except ValueError as exc:
            return ControlReading(None, error=str(exc))

    def set_volume(self, value: float | int) -> ControlReading:
        return self._change(["set-sink-volume", "@DEFAULT_SINK@", f"{clamp_percent(value)}%"], "volume change")

    def toggle_mute(self) -> ControlReading:
        return self._change(["set-sink-mute", "@DEFAULT_SINK@", "toggle"], "mute toggle")

    def _change(self, args: Sequence[str], operation: str) -> ControlReading:
        executable = self._which("pactl")
        if not executable:
            return ControlReading(None, error="pactl is not installed or not on PATH")
        result = self._execute([executable, *args])
        if result.returncode != 0:
            return ControlReading(None, error=_command_error(operation, result))
        return self.read()

    def _execute(self, args: list[str]) -> subprocess.CompletedProcess:
        try:
            return self._run(args, capture_output=True, text=True, timeout=self.timeout, check=False, shell=False)
        except FileNotFoundError:
            return subprocess.CompletedProcess(args, 127, "", "command not found")
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(args, 124, "", "command timed out")
        except OSError as exc:
            return subprocess.CompletedProcess(args, 1, "", str(exc))


def _command_error(operation: str, result: subprocess.CompletedProcess) -> str:
    detail = (result.stderr or result.stdout or "no details").strip()
    return f"{operation} unavailable: {detail}"
