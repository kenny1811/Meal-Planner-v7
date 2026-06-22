# One Shot Alarm

Android alarm companion for Meal Planner. It can still set a manual one-shot alarm, and it can also receive a daily alarm plan from the Meal Planner web UI via:

```text
oneshotalarm://sync?payload=...
```

The synced plan can contain multiple same-day shift alarms from the roster and schedule grid. Each alarm clears itself after it fires. A cleanup alarm is also scheduled for two hours after the shift end, and that cleanup cancels all remaining synced alarms for the day.

## Sync from Meal Planner

1. Import the latest roster, overtime, and schedule-grid data in Meal Planner.
2. Open the Meal Planner website on the Android phone, or open it from a browser that can hand custom links to the phone.
3. Tap `Sync Phone Alarms`.
4. Android may ask for exact-alarm and notification permissions the first time.

## Build

Open this folder in Android Studio and run the `app` configuration, or run Gradle if it is installed:

```powershell
gradle assembleDebug
```

The app uses `setAlarmClock()` for a real clock-style exact alarm. Android 12 may require the user to grant exact alarm access; Android 13 or later uses `USE_EXACT_ALARM`, which is intended for alarm clock apps.
