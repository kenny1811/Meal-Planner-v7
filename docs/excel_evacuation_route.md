# Excel Evacuation — done

The workbook (`.xlsm`) is fully retired. SQLite (`meal_planner.sqlite3`) is the only
data source at runtime; nothing opens Excel, and there is no workbook fallback anywhere.

## Where the old workbook sheets live now

| Former workbook sheet | Owner today |
| --- | --- |
| `餐單v5` top indicator rows | SQLite `nutrition_targets` |
| `營養清單` | SQLite `nutrition_catalog` |
| `飯時` A:E | `maintenance_sheet_rows` (`meal_times`) |
| `飯時` G:H | `maintenance_sheet_rows` (`meal_patterns`) |
| `餐廳選擇` | `maintenance_sheet_rows` (`restaurant`) |
| `行位表` | `maintenance_sheet_rows` (`schedule_grid`) |
| `更表` | `maintenance_sheet_rows` (`roster`) |
| `加班表` | `maintenance_sheet_rows` (`overtime`) |
| `更時表` | `maintenance_sheet_rows` (`payroll_times`) |
| `公眾假期` | `maintenance_sheet_rows` (`public_holidays`) |

## Editing and importing

Maintenance rows are edited in the Config → 餐單參數 editor:

- `GET /api/maint/sheets/{sheet_key}`
- `POST /api/maint/sheets/{sheet_key}`

The only remaining import path is 行位表 from the phone
(`preview-from-phone-ip` / `confirm-from-phone-ip`, plus the XML import endpoints).
Every other sheet is edited directly — an empty maintenance sheet raises
`MaintenanceDatabaseError` instead of silently falling back to anything.
