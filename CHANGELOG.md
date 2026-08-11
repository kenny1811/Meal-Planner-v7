# 餐單生成 — Changelog

Web app version history (X.Y.Z). The top entry is the current version shown in the sidebar.
Z = fix/tweak, Y = feature, X = major redesign. The version and this log follow commits:
an entry ships in the same commit as its change; work-in-progress never shows here.

## 7.5.11 — 11/08/2026 25:05
- On Duty / Off Duty now always submits at the shift time — the Semi / Auto switch is gone
  (web and phone). Opening a form is only a shortcut: it is kept in the history and never
  stops the automatic submission.

## 7.4.11 — 11/08/2026 14:55
- Fix: with auto-send on, the On Duty / Off Duty chip now shows your latest action
  (opened / sent / hold) without that changing what gets sent — opening a form after a
  slot was sent no longer re-sends it, and opening one after a missed slot no longer
  flips the record back.

## 7.4.10 — 11/08/2026 13:25
- Fix: with auto-send on, On Duty / Off Duty no longer skips a slot just because the form
  was opened at some point — it sends on time, and still flags a slot it could not send.
  Semi (auto-send off) is unchanged: opening the form records the time and keeps the slot
  off the missed list.

## 7.4.9 — 10/08/2026 26:40
- Fix: Typhoon marked a schedule-grid row missed just for sitting before the 報開工 row
  (e.g. 簽簿 / 著衫). A row is missed only when you cannot get there in time — signal down
  plus the travel rule.
- Fix: Typhoon's meal plan follows the work day the panel picked, not the date typed in
  the box (signal today, shift tomorrow showed the wrong day's meals).
- Fix: "earliest" showed a broken clock (-14:40) when the signal came down the day before.
- Typhoon's Length column matches the schedule grid: plain number, right-aligned.
- Typhoon's storm name refreshes from the Observatory each time the panel opens.

## 7.4.8 — 05/08/2026 15:15
- Typhoon handling.

## 7.3.8 — 03/08/2026 20:15
- Fix: the watch could lose an alarm without a sound. The phone re-sent the whole
  schedule grid every time an alarm rang or was dismissed, and that wiped the watch's
  own pending alarm for that minute. The grid now goes out only when it actually
  changes — the 05:00 / 05:30 import, or when you edit it.
- The watch no longer asks the phone for the grid every minute. It runs off the copy
  it already has, which saves battery on both.

## 7.3.7 — 28/07/2026 27:10
- Typhoon panel: simulate a signal-down day (schedule grid, meal plan, safety reports,
  on/off-duty forms, overtime, calendar) and apply it everywhere in one press — the
  phone is pushed straight away so its alarms follow without waiting for the 05:00 import.
- 30-hour clock everywhere: 00:00–05:59 is entered, stored and shown as 24:00–29:59 —
  on the computer, the phone and the watch.

## 7.2.7 — 24/07/2026 29:42
- Fix: the schedule grid sent to the phone lost each row's duration when the grid
  version came from a phone push. Labels now always carry it (e.g. "M 75").

## 7.2.6 — 23/07/2026 26:20
- Rice conversion: removed the hidden default ratio — no fallback anywhere. Rice that
  matches no conversion row now shows it plainly: the rice note says the ratio is not
  configured, and the shopping list marks the item "no rice conversion row".

## 7.2.5 — 23/07/2026 23:02
- Maint sheets: Append Row keeps a single trailing blank row.

## 7.2.4 — 23/07/2026 22:58
- Nutrition catalog: removed the Filter box.

## 7.1.4 — 23/07/2026 22:40
- Fix: Delete Row next to a blank row removed the wrong row (Detail Settings tables).

## 7.1.3 — 23/07/2026 22:35
- Fix: saving Detail Settings broke config.yaml (bad path quoting).

## 7.1.2 — 23/07/2026 22:25
- Rice conversion is now an editable table (right-click to insert/delete rows).

## 7.1.1 — 23/07/2026 22:15
- Partial re-solve keeps the one-rice-per-day rule.

## 7.1.0 — 23/07/2026 21:55
- Version source of truth moved to this file: bumps on every change, no commit needed.
- Click the sidebar version number to view this changelog.

## 7.0.0 — 23/07/2026
- Sidebar shows the real versionName.
- Out of stock: right-click a meal cell to pause an item and re-solve the remaining meals.
