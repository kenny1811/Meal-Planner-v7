import sqlite3
conn = sqlite3.connect('d:/Projects/餐單生成v6/meal_planner.sqlite3')
conn.execute("DELETE FROM maintenance_sheets WHERE sheet_key='meal_times'")
conn.execute("DELETE FROM maintenance_sheet_rows WHERE sheet_key='meal_times'")
conn.commit()
conn.close()
print('DB cleared for meal_times')
