import sqlite3
from pathlib import Path

root = Path(__file__).resolve().parent
conn = sqlite3.connect(root / "meal_planner.sqlite3")
conn.execute("DELETE FROM maintenance_sheets WHERE sheet_key='meal_times'")
conn.execute("DELETE FROM maintenance_sheet_rows WHERE sheet_key='meal_times'")
conn.commit()
conn.close()
print('DB cleared for meal_times')
