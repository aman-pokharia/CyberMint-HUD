# CyberMint HUD

CyberMint HUD is an independent, early-stage cyberpunk-style desktop HUD for **Linux Mint Cinnamon**,
written in Python with GTK 3 and Cairo. It runs as an ordinary user application: it does not replace
the Cinnamon panel, Muffin, the login manager or the lock screen, needs no `sudo`, and installs nothing.

It is *inspired by* the look of the Hyprland project CyberArch-Shell, but it is a from-scratch
implementation: no code, assets, fonts, icons or sounds from that project or from Cyberpunk 2077 are
included (see [ATTRIBUTION.md](ATTRIBUTION.md)).

> **Status:** version 0.2.0. Developed and tested with unit tests and a headless X11 display only.
> It has **not yet been verified on a real Linux Mint machine**. Use
> [docs/LINUX_MINT_VERIFICATION.md](docs/LINUX_MINT_VERIFICATION.md) to check it.

## Features

| Window | What it shows or does |
|---|---|
| **Chrono** | Live clock and date |
| **Telemetry** | CPU load, RAM, root-disk use and battery (only if a battery exists), read directly from `/proc`, `/sys` and `statvfs` |
| **Controls** | Volume slider + mute button (via `pactl`), screen brightness slider (via `brightnessctl`, or Cinnamon's D-Bus power service as a fallback) |
| **Launcher** | Searchable list of installed apps (from the desktop's application registry); toggled on demand |

- Chamfered "tech" cards and segmented meters drawn with Cairo; cyan normal range, red above 75%.
- **No invented readings.** If a source, tool or device is missing, the metric or control shows `N/A`
  with the real reason, the reason is logged once, and the HUD keeps running.
- Configurable colours, opacity, UI scale, window positions, refresh interval and always-on-top.

## Requirements

- Linux Mint 22.x (or 21.x) with Cinnamon 6.2+, an **X11** session recommended
- Python 3.10+, GTK 3.24+, PyGObject and PyCairo. On a normal Mint desktop these are already installed;
  on a minimal install: `sudo apt install python3 python3-gi python3-gi-cairo gir1.2-gtk-3.0`
- Optional, for the Controls window: `pactl` (volume; package `pulseaudio-utils`, normally already installed on Mint) and `brightnessctl` (brightness; `sudo apt install brightnessctl` if you want it)

Cinnamon on Wayland does not let ordinary GTK apps choose their window position, so saved X/Y
positions are best-effort there. The HUD is a normal app window, not a compositor layer-shell surface,
so stacking and focus are decided by Cinnamon.

## Run

From the project folder:

```bash
python3 -m cybermint_hud --check     # environment report, opens no windows
python3 -m cybermint_hud             # start the HUD
```

Close with the red `×` on any HUD window, `Esc` while a HUD window is focused, or `Ctrl+C` in the
launching terminal. There is no autostart; launch it manually while testing.

### Launcher and keyboard shortcut

```bash
python3 -m cybermint_hud --toggle-launcher
```

If the HUD is already running, this shows or hides the launcher in the running instance (and starts the
HUD if it is not running). In the launcher: type to filter, `Up`/`Down` to choose, `Enter` to start the
app, `Esc` or the launcher's own `×` to hide it (neither quits the HUD).

To bind it to a key, open **System Settings → Keyboard → Shortcuts → Custom Shortcuts**, add a shortcut,
and use the **absolute path** as the command, because shortcuts do not run from the project folder:

```text
python3 /home/YOURNAME/CyberMint-HUD/cybermint_hud/run.py --toggle-launcher
```

The HUD never changes Cinnamon settings by itself.

## Configuration

On first run the HUD creates `${XDG_CONFIG_HOME:-~/.config}/cybermint-hud/config.json` with defaults.
Edit it while the HUD is stopped. Invalid configuration is logged and defaults are used for that run;
the file is never overwritten. Logs go to `${XDG_STATE_HOME:-~/.local/state}/cybermint-hud/hud.log`
(size-limited rotation).

```json
{
  "version": 1,
  "appearance": {
    "accent_primary": "#ff2a4b",
    "accent_secondary": "#00f0ff",
    "surface": "#0d0e15",
    "opacity": 0.92,
    "scale": 1.0
  },
  "positions": {
    "clock": { "x": 32, "y": 32 },
    "system": { "x": 32, "y": 180 },
    "controls": { "x": 320, "y": 32 }
  },
  "behavior": { "refresh_interval_seconds": 2, "always_on_top": true }
}
```

| Setting | Range | Notes |
|---|---|---|
| `appearance.accent_primary` | `#RRGGBB` | Borders, close buttons, slider handles, high-load segments |
| `appearance.accent_secondary` | `#RRGGBB` | Labels, brackets, normal meter segments |
| `appearance.surface` | `#RRGGBB` | Card background |
| `appearance.opacity` | 0.65 to 1.0 | Card background opacity |
| `appearance.scale` | 0.75 to 2.5 | Scales fonts, padding, meters and the default window positions |
| `positions.*` | integers 0 to 10000 | Pixels from the top-left of the screen (applied on X11). Positions you change are used exactly as written; untouched defaults scale with `appearance.scale` |
| `behavior.refresh_interval_seconds` | 1 to 60 | Telemetry refresh. Controls are polled every 2 s |
| `behavior.always_on_top` | true/false | Keeps HUD windows above normal windows |

The launcher always opens centred on the screen. Older config files without `controls` keep working.

## Development

The logic modules are plain Python and are tested without GTK, a display or Linux hardware:

```bash
python3 -m unittest discover -s . -t . -v          # Linux / macOS
python -m unittest discover -s CyberMint-HUD -t CyberMint-HUD -v   # Windows, from the parent folder
```

These tests do **not** exercise GTK, Cinnamon, audio or backlight hardware, window placement or the
real display session. Passing them (on any OS) does not verify Linux Mint compatibility.

```text
CyberMint-HUD/
├── cybermint_hud/
│   ├── __main__.py        entry point: --check, --toggle-launcher
│   ├── run.py             path-based entry point for keyboard shortcuts
│   ├── ui.py              GTK windows, CSS, event handling, background workers
│   ├── drawing.py         Cairo geometry and painting (cards, meters)
│   ├── monitoring.py      CPU / RAM / disk / battery readers
│   ├── volume.py          pactl adapter (parsing, clamping, errors)
│   ├── brightness.py      brightnessctl + Cinnamon D-Bus adapter, with retry back-off
│   ├── applications.py    app discovery, search filter, launch
│   ├── config.py          defaults, validation, effective window positions
│   ├── compat.py          GTK / Cairo / Cinnamon / session report
│   └── logging_setup.py   user-level rotating log
├── docs/  ARCHITECTURE.md  LINUX_MINT_VERIFICATION.md
├── tests/
├── ATTRIBUTION.md
└── README.md
```

## Known limitations

- Not verified on real Linux Mint. In particular unverified: Cinnamon stacking, RGBA transparency (the
  angled card corners rely on it), launcher keyboard focus under Muffin, and the real `pactl`,
  `brightnessctl` and Cinnamon D-Bus behaviour.
- The Cinnamon D-Bus brightness route (`org.cinnamon.SettingsDaemon.Power.Screen`) was written without a
  Cinnamon session to check it against. It validates the interface at runtime and falls back cleanly.
- Volume is limited to 0 to 100%. Only the default output device is controlled.
- No notifications, media (MPRIS) controls, autostart or installer.
- Battery is hidden when the kernel reports no battery. Disk use reports the filesystem containing `/`.
