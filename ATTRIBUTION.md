# Asset and dependency attribution inventory

## Reused project material

| Material | Source | Permission status | Included in CyberMint HUD? |
|---|---|---|---|
| CyberArch-Shell code and repository assets | <https://github.com/ARCANGEL0/CyberArch-Shell> | No license file was present in the audited checkout. No redistribution permission was established. | **No** |
| Cyberpunk 2077 artwork, logos, UI captures, sounds, and other game material | CD PROJEKT RED | No permission established. | **No** |

CyberMint HUD is independently written. It contains no copied or translated CyberArch-Shell source and
no bundled fonts, icons, cursors, sounds, wallpapers, screenshots or game assets. All visuals are drawn
in code (Cairo shapes and text). The project name and the colour and style direction are descriptive
inspiration only; no game logo or artwork is included. The absence of an upstream license is not treated
as permission to copy it. A license for CyberMint HUD itself still has to be chosen before publication.

## Runtime dependencies (all supplied by the system, none bundled)

| Dependency | Use | License / source |
|---|---|---|
| Python 3 standard library | Configuration, procfs/sysfs reads, timers, logging, tests | Python Software Foundation License |
| GTK 3 | Windows and widgets | LGPL-2.1-or-later, <https://www.gtk.org/> |
| PyGObject / GObject Introspection (incl. Gio, GLib, Pango) | Python bindings, app registry, D-Bus | LGPL-2.1-or-later, <https://pygobject.gnome.org/> |
| PyCairo / Cairo | 2D drawing of cards and meters | LGPL-2.1 / MPL-1.1, <https://www.cairographics.org/> |
| psutil (optional) | Only imported if `/proc` is missing (non-Linux development); not needed on Linux | BSD-3-Clause, distribution/pip package, not bundled |
| Cinnamon / Muffin and cinnamon-settings-daemon | Existing desktop; optional brightness D-Bus route | Linux Mint system components; not bundled or modified |

## Optional external tools (called only if present, never installed by this project)

| Tool | Use | Source |
|---|---|---|
| `pactl` (PulseAudio / PipeWire-pulse) | Read and set default output volume and mute | Distribution package |
| `brightnessctl` | Read and set screen brightness | Distribution package |

## Fonts

Fonts are referenced by name only (DejaVu Sans Mono, JetBrains Mono, Courier New, generic `monospace`)
with fallbacks. None are distributed with this project.
