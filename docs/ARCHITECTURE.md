# CyberMint HUD architecture (v0.2.0)

CyberMint HUD is an ordinary, unprivileged GTK 3 + Cairo application for Linux Mint Cinnamon. It does not
inject into Muffin or Cinnamon, replace the shell, run as root, or modify desktop settings.

```text
                    ┌──────────────────────── ui.py ────────────────────────┐
                    │ Gtk.Application (single instance, command line)       │
                    │ windows: Chrono · Telemetry · Controls · Launcher     │
                    │ CSS from config · Cairo card background on each window│
                    │ ThreadPoolExecutor for anything that can block        │
                    └─┬────────┬─────────┬──────────┬──────────┬────────────┘
                      │        │         │          │          │
               drawing.py  monitoring.py volume.py brightness.py applications.py
               (Cairo      (/proc, /sys, (pactl)   (brightnessctl, (Gio.AppInfo
                geometry)   statvfs)                Cinnamon D-Bus)  search/launch)
                      │
              config.py · compat.py · logging_setup.py
```

## Component responsibilities

- **`ui.py`** is the only module that builds widgets. It owns window lifecycle, CSS, the refresh timers and the
  worker threads. Every call that can block (pactl, brightnessctl, D-Bus, listing or launching apps) runs on a
  worker thread; results return to the GTK main loop with `GLib.idle_add`. It never executes shell strings.
- **`drawing.py`** is pure geometry and Cairo painting (chamfered polygon, meter segments, colour conversion),
  testable without a display.
- **`monitoring.py`** reads CPU (two-sample `/proc/stat` delta), memory (`MemAvailable`), root-disk use and
  battery. Each source fails independently and reports a reason instead of a made-up value.
- **`volume.py`** wraps `pactl get/set-sink-volume`, `get/set-sink-mute` on the default sink. Parsing and clamping
  (0 to 100) are separate, testable functions. Command execution goes through an injectable runner.
- **`brightness.py`** tries `brightnessctl` first, then the Cinnamon D-Bus power interface. Before using D-Bus it
  checks the interface's introspection data. If no backend works it remembers that for 30 s instead of probing
  every poll.
- **`applications.py`** lists apps with `Gio.AppInfo` (skipping entries that should not be shown), filters by name
  and keywords, and launches with `AppInfo.launch()`.
- **`config.py`** holds defaults and validation. `effective_position()` scales untouched default window positions
  with `appearance.scale` so the default layout does not overlap. Invalid files are never overwritten.
- **`compat.py`** reports GTK, Cairo, Cinnamon (via `CINNAMON_VERSION` or `cinnamon --version`) and session type.
- **`logging_setup.py`** writes size-limited logs under `$XDG_STATE_HOME`.

## Single instance and launcher toggle

`Gtk.Application` is registered with `HANDLES_COMMAND_LINE`. A second `python3 -m cybermint_hud --toggle-launcher`
(or `cybermint_hud/run.py`, for shortcuts that do not run from the project folder) is forwarded over the session
bus to the running instance, which runs the `toggle-launcher` action, then the second process exits. This needs a
session D-Bus, which every normal Cinnamon session has.

## Rules the code follows

1. No invented values: unavailable means `N/A` plus a logged reason.
2. Errors are logged once per change, not on every poll.
3. While the user drags a slider, background polls do not overwrite it.
4. Window background drawing is separate from widgets, so the look can change without touching logic.

## Not covered by automated tests

GTK widgets, Cinnamon/Muffin behaviour, real audio and backlight hardware, and window placement. See
`LINUX_MINT_VERIFICATION.md`.
