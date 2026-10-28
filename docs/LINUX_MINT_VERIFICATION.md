# Linux Mint verification checklist (v0.2.0)

Use this on a real Linux Mint Cinnamon machine. Nothing here has been checked on Mint yet.

## 1. Prerequisites

```bash
dpkg -l | grep -E "python3-gi|gir1.2-gtk-3.0"
which pactl brightnessctl     # pactl is needed for volume; brightnessctl is optional
sudo apt install python3 python3-gi python3-gi-cairo gir1.2-gtk-3.0   # only if something is missing
sudo apt install brightnessctl                                         # optional, laptops
```

## 2. Tests and environment report

```bash
cd ~/CyberMint-HUD
python3 -m unittest discover -s . -t . -v      # expect: Ran 40 tests ... OK
python3 -m cybermint_hud --check
```

Expect GTK 3.24+, Cairo available, Cinnamon 6.2+ (or "unknown"), session X11.

## 3. Launch

```bash
python3 -m cybermint_hud
cat ~/.local/state/cybermint-hud/hud.log
```

## 4. Checklist

### Look
- [ ] Chrono, Telemetry and Controls windows appear, none overlapping at defaults
- [ ] Angled card corners show cleanly (if you see black/white patches in the corners, RGBA transparency is not working: report it)
- [ ] Cyan labels, red `×` and slider handles, segmented meters; meter turns red above 75%

### Telemetry
- [ ] CPU roughly matches `top`; RAM matches `free -h`; root disk matches `df -h /`
- [ ] Laptop: battery shows percentage and status. Desktop/VM: "No battery hardware detected"

### Controls
- [ ] Volume slider changes the real output volume; the HUD follows when you change volume elsewhere (within ~2 s)
- [ ] MUTE button mutes and unmutes; label switches MUTE / MUTED
- [ ] Brightness slider changes the real screen brightness (laptop). On a desktop it shows N/A with a reason
- [ ] If `brightnessctl` is not installed, note whether the Cinnamon D-Bus fallback works (log line says which backend)
- [ ] With `pactl` missing or failing, the Controls window stays a normal size and shows a short reason

### Launcher
- [ ] `python3 -m cybermint_hud --toggle-launcher` (second terminal) shows the launcher; running it again hides it
- [ ] Typing filters apps, Up/Down move the selection, Enter starts the app, Esc hides it
- [ ] The launcher's `×` hides only the launcher; the rest of the HUD keeps running
- [ ] The search box gets keyboard focus when the launcher opens (Muffin may behave differently than expected)
- [ ] Custom shortcut works: command `python3 /home/YOURNAME/CyberMint-HUD/cybermint_hud/run.py --toggle-launcher`

### Windows and config
- [ ] HUD windows stay above normal windows (or not, if `always_on_top` is false)
- [ ] `×` on a HUD window and `Esc` while focused both exit the whole HUD
- [ ] `"scale": 1.25` in the config rescales everything; changed `positions` are honoured on X11

## 5. Report back

Send the output of step 2, the contents of `hud.log`, and which checklist items failed.
