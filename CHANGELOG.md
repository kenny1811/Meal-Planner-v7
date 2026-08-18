# 餐單生成 — Changelog

Web app version history (X.Y.Z). The top entry is the current version shown in the sidebar.
Z = fix/tweak, Y = feature, X = major redesign. The version and this log follow commits:
an entry ships in the same commit as its change; work-in-progress never shows here.

## 7.6.19 — 18/08/2026 25:52
- Phone app: swiping between days in the meal view no longer re-downloads the whole
  month, so the day flips right away instead of sitting on "Updating..." when you are
  out on mobile data.
- Phone app: when the PC cannot be reached it now retries by itself within seconds
  instead of every 30s, so the plan fills in and the status returns to Online without
  leaving and re-entering the page.

## 7.6.18 — 17/08/2026 18:10
- Protein is now spread evenly across the day's meals instead of piling into breakfast
  (e.g. 51 / 36 / 15g becomes 34 / 34 / 34g). Daily totals and calories stay the same.

## 7.5.18 — 16/08/2026 29:10
- Fix: turning a schedule-grid row OFF on the phone did not stop the watch — the phone
  pushed the OFF flag straight away but the watch still set the alarm. The watch now
  skips OFF rows (still shown dimmed in its list) and re-arms the rest.

## 7.5.17 — 15/08/2026 21:45
- Fix: a safety report failed with "Group not found" when the WhatsApp group title has
  a leading/trailing space (e.g. 時代廣場). The mapping trimmed the name on save but the
  send matched it exactly — both sides now ignore leading/trailing spaces.

## 7.5.16 — 14/08/2026 15:31
- On Duty / Off Duty: after a Send now, the chip and the prefilled form link show the
  actual sent time instead of the originally scheduled one.

## 7.5.15 — 14/08/2026 15:27
- Watch: the alarm screen (overlay and app) now centres the time and label as one
  block in the middle of the round face, instead of the time hugging the top.

## 7.5.14 — 13/08/2026 23:25
- Fix: "Send now" fired twice — the On/Off Duty form and the WhatsApp report were each
  sent once by Send now and once by the scheduler it woke up. Send now now carries out
  the scheduled run itself instead of handing it back.

## 7.5.13 — 12/08/2026 24:01
- Watch: lowering your wrist during an alarm no longer silences it — the vibration
  restarts within half a second and keeps going until dismissed.
- Phone: an alarm ringing in a dark pocket no longer lights the screen, so a pocket
  touch can't dismiss it (and kill the watch alarm) anymore. Take the phone out into
  light and the alarm screen appears instantly — one tap to dismiss, as before.

## 7.5.12 — 11/08/2026 25:45
- Fix: on mobile data the phone app no longer fails the first tap with "after 2500ms" —
  the meshnet server now gets up to 9 s to answer while the tunnel wakes up, so one tap
  is enough.

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
