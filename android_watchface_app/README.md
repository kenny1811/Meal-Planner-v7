# Kenny Digital Watch Face

This folder is the Watch Face subproject for the Meal Planner repository. It is kept as a standalone Gradle project so the existing Meal Planner Python/web code and `android_alarm_app` stay independent.

Wear OS Watch Face Format (WFF) project with a companion pair for phone battery sync.

## Build

Open this folder in Android Studio and run the `watchface` module, or build from PowerShell:

```powershell
.\build_debug.bat
```

Debug APKs are created at:

```text
watchface/build/outputs/apk/debug/watchface-debug.apk
phone/build/outputs/apk/debug/phone-debug.apk
wear-companion/build/outputs/apk/debug/wear-companion-debug.apk
```

## Design

The watch face shows:

- Digital time in 30-hour mode: 00:00-05:59 is shown as 24:00-29:59, then 06:00 returns to 06:00.
- Smaller top-aligned seconds.
- Date.
- Watch battery.
- Phone battery from the companion complication.
- Red battery text when either battery is below 30%.
- Ambient mode that keeps only a thinner time display.

## Phone Battery Sync

Install `phone-debug.apk` on the Android phone and `wear-companion-debug.apk` on the watch. Both companion modules use the same application ID, `com.kenny.watchface.wear`, so Wear OS Data Layer can sync private app data between them.

The watch companion requests the phone battery when the phone battery complication is asked for data, such as when the watch face becomes active. Wear OS schedules the complication at a 5-minute update period, and phone requests are also throttled locally. The phone companion does not run a foreground service; it wakes through Wear OS Data Layer, reads the current phone battery once, then sends a small Data Layer update back to the watch.
