# Desktop_Assistant

A low-footprint desktop assistant written in Python and PyQt6.

A draggable robot icon lives on the desktop with a speech bubble, a system tray menu and a compact dashboard. The dashboard shows CPU, RAM, disk and battery telemetry, the top resource and power consumers (with an End button), Windows power plans with matching screen brightness (Power Saver 35%, Balanced 65%, Performance 100%), one-click workspace profiles from `data/workspaces.json`, quotes and Google Calendar reminders. The robot smiles after successful actions.

## Google Calendar

In Google Calendar open Settings → your calendar → Integrate calendar and copy the **Secret address in iCal format**. Paste it under Upcoming Events in the dashboard and press Connect. Events refresh every 10 minutes and are cached for offline use. The address is stored only in `data/calendar.json`, which is ignored by git.

## Run

```powershell
py -3 -m pip install -r requirements.txt
py -3 main.py
```

Drag the icon to move it. Left click opens the dashboard, right click opens the menu. Quit from the tray or the right-click menu.
