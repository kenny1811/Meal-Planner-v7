# 餐單生成 — Changelog

Web app version history (X.Y.Z). The top entry is the current version shown in the sidebar.
Z = fix/tweak, Y = feature, X = major redesign. The version and this log follow commits:
an entry ships in the same commit as its change; work-in-progress never shows here.

## 7.2.5 — 23/07/2026 23:14
- Version and changelog now follow commits: the sidebar version and this dialog read the
  last committed CHANGELOG.md, so uncommitted work-in-progress no longer bumps the version.
- Changelog dialog: wrapped entry lines are shown in full (no more cut-off sentences).

## 7.1.0 — 23/07/2026 21:55
- Version source of truth moved to this file: bumps on every change, no commit needed.
- Click the sidebar version number to view this changelog.

## 7.0.0 — 23/07/2026
- Sidebar shows the real versionName.
- Out of stock: right-click a meal cell to pause an item and re-solve the remaining meals.
