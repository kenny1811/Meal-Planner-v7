# Excel Evacuation Route

## Runtime dependency map

| Workbook surface | Current runtime use | Owner after first evacuation slice |
| --- | --- | --- |
| `餐單v5` top indicator rows | Legacy bootstrap for nutrition targets | SQLite `nutrition_targets` |
| `營養清單` | Legacy bootstrap for optimizer catalog and shopping categories | SQLite `nutrition_catalog` |
| `飯時` A:E | Meal time rules by roster code | SQLite `maintenance_sheet_rows` (`meal_times`) |
| `飯時` G:H | Meal patterns by meal | SQLite `maintenance_sheet_rows` (`meal_patterns`) |
| `餐廳選擇` | Restaurant lunch rule and nutrient values | SQLite `maintenance_sheet_rows` (`restaurant`) |
| `行位表` | Schedule events used to resolve meal clock times | SQLite `maintenance_sheet_rows` (`schedule_grid`) |
| `更表` | Monthly day-to-roster-code input | SQLite `maintenance_sheet_rows` (`roster`) |
| `加班表` | Date-specific start/end override input | SQLite `maintenance_sheet_rows` (`overtime`) |
| `更時表` | SQLite maintenance/reporting input for roster report views | SQLite `maintenance_sheet_rows` (`payroll_times`) |
| `公眾假期` | SQLite maintenance/reporting input for roster report context | SQLite `maintenance_sheet_rows` (`public_holidays`) |

## First slice

Generate/preview now reads current SQLite maintenance rows for `更表`, `飯時表`, `Pattern`, `餐廳選擇`, `加班表`, and `行位表`. It does not open Excel or fall back to legacy reference tables.

## Maintenance input import

The generic maintenance editor endpoints remain available for manual updates:

- `GET /api/maint/sheets/{sheet_key}`
- `POST /api/maint/sheets/{sheet_key}`
- `POST /api/maint/sheets/{sheet_key}/import`

For roster and overtime inputs, use `sheet_key` values `roster` and `overtime`.

## Workbook validation scope

Full workbook validation now covers the core planning/import sheets only:

- `更表`
- `飯時`
- `餐廳選擇`
- `加班表`
- `行位表`

`更時表` and `公眾假期` are no longer core planning validation requirements. They can be imported and edited independently through the maintenance endpoints. Single-sheet maintenance imports are sheet-scoped, so importing `公眾假期` does not require unrelated workbook sheets to exist.

## Next extraction points

1. Decide whether `醫療行程` should remain reporting-only or feed meal-time visibility in a future rule.
