# 餐單生成 — Changelog

Web app version history (X.Y.Z). The top entry is the current version shown in the sidebar.
Z = fix/tweak, Y = feature, X = major redesign. The version and this log follow commits:
an entry ships in the same commit as its change; work-in-progress never shows here.

## 7.13.33 — 14/10/2026
- On typhoon days, disabled phone schedule rows keep their original start times alongside the active actual start.

## 7.13.32 — 14/10/2026
- Nutrition Catalog rows can be moved by long press, buttons or Alt+arrow keys without changing saved meal references; nutrient values show two decimal places.
- The meal planner's today highlight follows the 30-hour day, and cooked-rice notes no longer count corn kernels as rice.
- On/off-duty time changes update duty reports and phone schedules; sent actions stay locked, and desktop form links follow the latest phone changes.
- Phone schedule editors refresh imported plans and prevent older edits from overwriting a newer schedule.
- The Meal Planner server restarts automatically after an interruption.

## 7.12.31 — 22/09/2026 15:19
- Weekly ingredient quotas (config.yaml `weekly_ingredient_rules`): brown rice now comes
  up 2 days a week and salmon twice a week, counted Sunday to Saturday. The planner picks
  the days with the most room to absorb them, and skips one rather than push a nutrient
  into the red.

## 7.11.31 — 22/09/2026 00:10
- Dropped the /apkdl chunked-download page. It existed because the meshnet link dropped every
  ~34 seconds on csl; measured tonight, SmarTone holds the tunnel with zero drops and Kenny is
  cutting the csl line. Installing from the phone now goes through the in-app updater (tap the
  title) or /apk.

## 7.11.30 — 21/09/2026 23:45
- Google Calendar and the roster-grid check now start from the business day, not the calendar day:
  working through the small hours no longer makes the shift you are still on count as "past" and
  disappear from the calendar.
- Phone app 7.6: dismissing on the watch only silences the same alarm. A second alarm going off
  within 30 seconds keeps ringing until you dismiss it yourself.

## 7.11.29 — 21/09/2026 13:10
- Phone app 7.5: disabled rows stay silent after a reboot / app update; the 05:00 / 05:30 daily import
  chain survives the process being killed; "today", cached-roster copies and the time editor follow the
  30-hour clock (hours 24-29 accepted); "Watch OFF" really stops the watch ringing; deleting the last
  row no longer wipes the meal cache; no more /health polling after the app is closed.
- Watch app 7.5: schedule tile dims past rows correctly after midnight, prev/next skip disabled rows,
  duplicate dismiss messages are ignored, and the app no longer kills its own process after an alarm.
- Watch face 7.2: same look, rebuilt with colour transforms (2177 -> 487 lines); companion apps 1.1.

## 7.11.28 — 21/09/2026 13:20
- Maint panel: if the remembered sheet is gone, the first sheet opens instead of an empty panel.
- Leaving Typhoon via any sidebar entry (Maint sheets, custom menus) now saves the typhoon state.
- Midnight rollover no longer discards a meal cell you are still editing.
- Schedule grid: disabling / enabling a row recalculates durations on the 30-hour clock, same as the editor.
- 30-hour clock: meal times 00:00-05:59 count as 24:00-29:59 in the first-meal check.
- Sidebar drag-and-drop is pointer-only (the dead native drag path is gone); menu tree open state and the
  active config view now follow the server, with browser storage only as a fallback.

## 7.11.27 — 21/09/2026 12:50
- Weight history: saving the profile no longer wipes records older than the 30 shown on screen.
- Meal-plan version history keeps every generation, even two within the same second.
- 30-hour clock fixes: "today" for generate / out-of-stock re-solve, first-meal time,
  ReportNormal slots and OnOff_Duty auto-submit after 24:00, and which day's schedule the
  phone receives between 00:00 and 05:59.
- Detail Settings save only touches the sections it was given (no more accidental clearing).
- Typhoon panel calendar preview now uses the same schedule-grid times as the real sync.
- OnOff_Duty hold-send cannot double-send the same ReportNormal message.

## 7.11.26 — 21/09/2026 04:10
- Phone app 7.4: the phone's own HTTP port (schedule-grid push, watch capture) now requires a
  per-phone token. The phone hands the token to the PC on every request; anyone else on the
  network calling the port gets 401. Watch screenshots are now fetched through the PC at
  `/api/phone/capture-watch`.

## 7.10.26 — 21/09/2026 03:55
- Phone app 7.3: "use cached roster as today's schedule" now keeps disabled rows disabled
  instead of silently re-enabling them.

## 7.10.25 — 19/09/2026 15:30
- Meal Times: breakfast / lunch / snack / dinner cells accept `900`, `0900`, `09:00` or `9:00`
  and are tidied to `HH:MM` when you leave the cell.
- A cell that is not a valid time (or blank, or a rule phrase 開工前／收工後／跟行位表) turns red
  and keeps focus until fixed; Escape restores the old value. Save is refused while such a cell exists.

## 7.9.25 — 17/09/2026 22:28
- Schedule grid: a row starting with `*` (e.g. `* 飯 55`) keeps the duration you typed,
  and the next row moves to start right after it — on the web editor and the phone.
- Schedule grid editor: Disable / Enable Row is now in the right-click menu instead of
  its own column.

## 7.8.25 — 07/09/2026 17:30
- Watch face companion (phone): removed the stale "Sunrise/sunset syncs from HKO daily
  at 04:00" line — the watch face works out sun times on its own, nothing is synced.

## 7.8.24 — 27/08/2026 24:40
- Yesterday's last meal can still be re-generated (out of stock or swap), for dinners
  eaten after midnight. Everything earlier in the past stays locked.

## 7.8.23 — 26/08/2026 25:01
- Past days can no longer be re-generated by right-clicking a meal — marking something
  out of stock or swapping an ingredient there used to re-roll meals you had already
  eaten. Today and future days are unchanged: right-click a meal and it re-solves from
  that meal onwards.

## 7.8.22 — 23/08/2026 13:29
- Phone app: the next alarm (time and label) can now be read by another launcher's
  widget, so the shift alarm shows up on the home screen without opening the app.

## 7.7.22 — 23/08/2026 13:28
- Fix: On/Off Duty and Typhoon now stay open after a refresh instead of bouncing back
  to the meal plan.

## 7.7.21 — 23/08/2026 13:22
- Fix: one rice per day survived swapping. Re-generating after a swap could leave lunch
  and dinner on different rices (and the rice note then quoted the wrong grams). The
  rice slot also only offers the rice an earlier, already-eaten meal had.

## 7.7.20 — 20/08/2026 14:25
- Right-click a meal → "Swap → 指定食材": pick one or more slots, choose the ingredient
  you want in each, then Re-Generate. Amounts are still worked out for you, and nothing
  gets marked out of stock.

## 7.6.20 — 20/08/2026 14:22
- The plan table rolls over on its own at 24:00 — the first row becomes the new day and
  the blue "today" box moves with it, without reloading the page.

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
