# 餐單生成 — Changelog

Web app version history (X.Y.Z). The top entry is the current version shown in the sidebar.
Z = fix/tweak, Y = feature, X = major redesign. The version and this log follow commits:
an entry ships in the same commit as its change; work-in-progress never shows here.

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
