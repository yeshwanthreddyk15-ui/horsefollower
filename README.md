# Horse Pointer

Horse Pointer is a small Windows desktop companion. An animated horse follows
your mouse pointer across the desktop, even while you use other applications.
The horse overlay is transparent and click-through so it won't block your
normal desktop interaction.

## Features

- 48-frame galloping animation.
- Clickable controls at the bottom-left of the desktop.
- Adjust the horse size from 50% to 200% and follow speed from 60 to 900 px/s.
- Stop the horse, resume following, or send it home to its stable.
- Size and speed choices are saved between launches.
- Global keyboard shortcuts:
  - `Ctrl+Alt+A` — Stop
  - `Ctrl+Alt+F` — Start following
  - `Ctrl+Alt+Q` — Quit

## Requirements

- Windows
- Python
- `pygame-ce`

## Run

Keep `po.py` and `horse_gallop.png` together in the same folder. Install the
dependency and start the overlay from PowerShell:

```powershell
python -m pip install pygame-ce
python po.py
```

The control panel appears at the bottom-left. Use **Start** and **Stop** to
control following, **Home** to send the horse to its stable, and the sliders to
change its size and speed.

## Saved settings

The size and speed settings are stored in:

```text
%LOCALAPPDATA%\HorsePointerOverlay\settings.json
```

The app uses its defaults the first time it runs, then restores your saved
choices on later launches.
