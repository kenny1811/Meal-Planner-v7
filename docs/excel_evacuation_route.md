# Excel Evacuation Route

## Runtime dependency map

| Workbook surface | Current runtime use | Owner after first evacuation slice |
| --- | --- | --- |
| `餐單v5` top indicator rows | Legacy bootstrap for nutrition targets | SQLite `nutrition_targets` |
| `營養清單` | Legacy bootstrap for optimizer catalog and shopping categories | SQLite `nutrition_catalog` |
| `飯時` A:E | Meal time rules by roster code | SQLite `reference_meal_time_rules` |
| `飯時` G:H | Meal patterns by meal | SQLite `reference_meal_patterns` |
| `餐廳選擇` | Restaurant lunch rule and nutrient values | SQLite `reference_restaurant_rows` |
| `行位表` | Schedule events used to resolve meal clock times | SQLite `reference_schedule_rows` |
| `更表` | Monthly day-to-roster-code input | Workbook runtime input |
| `加班表` | Date-specific start/end override input | Workbook runtime input |
| `更時表` | Required and reloaded for workbook parity; no planning reader yet | Workbook pending classification |
| `公眾假期` | Required and reloaded for workbook parity; no planning reader yet | Workbook pending classification |

## First slice

The first slice treats `飯時`, `餐廳選擇`, and `行位表` as planning reference sheets. They bootstrap into SQLite when the reference tables are empty, and `build_meal_planning_cache()` now reads those SQLite tables after that bootstrap.

This does not remove the workbook from preview generation yet. The preview still opens and validates the workbook because `更表` and `加班表` remain live operational inputs and the legacy workbook structure check still covers all configured sheets.

## Runtime input import

`更表` and `加班表` are now treated as live operational inputs backed by SQLite:

- `GET /api/runtime-inputs` reports their SQLite import status.
- `POST /api/runtime-inputs/import` imports only `更表` and `加班表` from the workbook, without requiring the full workbook structure used by legacy/bootstrap paths.
- Preview reads the SQLite copies through `load_roster_map()` and `build_meal_planning_cache()` rather than opening the workbook per request.

The generic maintenance editor endpoints remain available for manual updates:

- `GET /api/maint/sheets/{sheet_key}`
- `POST /api/maint/sheets/{sheet_key}`
- `POST /api/maint/sheets/{sheet_key}/import`

For runtime inputs, use `sheet_key` values `roster` and `overtime`.

## Next extraction points

1. Decide whether `更時表` and `公眾假期` are unused legacy parity checks or should become modeled inputs.
2. Narrow full workbook validation to legacy/bootstrap paths only; runtime input import is already sheet-scoped.
