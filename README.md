# Desktop_Assistant

A desktop assistant written in Python and PyQt6.

A draggable robot icon residing on the desktop with a speech bubble, a system tray menu and a compact dashboard. The dashboard shows CPU, RAM, disk and battery telemetry, the top resource and power consumers (with an End button), Windows power plans with matching screen brightness (Power Saver 35%, Balanced 65%, Performance 100%), one-click workspace profiles from `data/workspaces.json`, quotes and Google Calendar reminders. The robot smiles after successful actions.

## Power Saver and battery health

On battery power, Power Saver caps the processor performance state at 85%, turns off the display after 2 minutes of inactivity, and puts the PC to sleep after 3 minutes of inactivity. The assistant selects Power Saver automatically at 20% charge or below while unplugged.

The dashboard shows estimated battery health based on the full-charge capacity and design capacity that Windows reports. For a charging limit, use the device manufacturer's Smart charging or Battery Care setting when available.

## Google Calendar

In Google Calendar open Settings → your calendar → Integrate calendar and copy the **Secret address in iCal format**. Paste it under Upcoming Events in the dashboard and press Connect. Events refresh every 10 minutes and are cached for offline use. The address is stored only in `data/calendar.json`, which is ignored by git.

## Run

```powershell
py -3 -m pip install -r requirements.txt
py -3 main.py
```

Drag the icon to move it. Left click opens the dashboard, right click opens the menu. Quit from the tray or the right-click menu.
