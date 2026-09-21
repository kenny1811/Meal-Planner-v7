# One Shot Alarm (門前直樹)

Phone + Wear OS alarm companion for Meal Planner. The phone pulls the day's shift
schedule (行位表) from the Meal Planner PC and schedules one exact alarm per row with
`setAlarmClock()`. The watch keeps its own copy of the table and schedules its own local
alarms, so it rings on time even when the phone is out of reach; phone and watch only
talk to each other to forward a dismiss.

## How the schedule reaches the phone

- **Daily import (automatic).** At 05:00 and again at 05:30 the phone calls
  `GET /api/maint/sheets/schedule_grid/export-all` on the PC (LAN first, NordVPN Meshnet
  as fallback), stores every roster variant, and schedules alarms for the current one.
  If the phone was off at both slots, the boot receiver catches up as soon as it starts.
- **Manual import.** The `import` button on the 行位表 tab runs the same pull.
- **Push from the PC.** The PC can call the phone's local HTTP server
  (`POST http://<phone>:8765/push/schedule-grid`) to trigger the same pull immediately,
  e.g. after editing the grid on the PC. Every request except `/health` must carry the
  `X-Alarm-Token` header; the phone reports its token to the PC on every API call it makes.
- **Phone → PC.** `to Computer` on the 行位表 tab posts the edited table back to the PC
  (`/api/maint/sheets/schedule_grid/import-phone-push`).

There is no `oneshotalarm://` URL scheme and no browser hand-off any more.

## Watch

- Whenever the phone's plan changes it pushes a tile state (schedule rows + prev/next) to
  the watch over the Wear data layer; the watch reschedules its local alarms from that.
- `手錶ON/OFF` on the 行位表 tab: ON pushes the full table to the watch, OFF pushes an
  empty table so the watch does not ring.
- Dismissing on either device forwards the dismiss to the other one.
- The watch app provides prev/next complications for the custom watch face
  (`android_watchface_app/`).

## Build

```powershell
.\gradlew.bat :app:assembleDebug :wear:assembleDebug
```

or double-click `update_phone.bat` / `update_watch.bat` to build and install on the
connected device (phone vs watch is detected from `ro.build.characteristics`).

Android 12 may ask the user to grant exact-alarm access; Android 13+ uses
`USE_EXACT_ALARM`, which is intended for alarm clock apps. The watch also needs
`SYSTEM_ALERT_WINDOW` and `POST_NOTIFICATIONS` (`grant_watch_permissions.bat`) and a
battery-optimisation exemption (`exempt_watch_doze.bat`) to ring on time.
