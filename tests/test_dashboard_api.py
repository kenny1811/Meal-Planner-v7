"""門前 Dashboard 專用 endpoint（app.py「Dashboard 專用」section）。

呢兩條 endpoint 嘅 JSON shape 係同 D:\\Projects\\Dashboard 嘅合約——欄名、型別、null 規則、排序
都唔可以隨便改；呢度嘅 assert 就係嗰份合約。
"""

import os
import tempfile
import unittest
from datetime import date

from fastapi.testclient import TestClient

from meal_planner.app import app
from meal_planner.maintenance_db import (
    save_roster_code_definitions,
    save_roster_post_mapping,
    save_sheet_rows,
)
from meal_planner.settings import clear_settings_cache, get_settings
from meal_planner.storage import save_plan_versions

# 2026-09-25 五、09-26 六、09-27 日、09-28 一
FRI, SAT, SUN, MON = "2026-09-25", "2026-09-26", "2026-09-27", "2026-09-28"

GRID_HEADER = ["更碼", "時間", "內容", "時長", "生效日期", "停用"]
GRID_ROWS = [
    GRID_HEADER,
    # EleB：三個版本——冇日期、2026-09-01、2026-09-10；夾埋停用行、marker 行、星號行、(日-四)/(五六)
    ["EleB", "10:00", "報開工 舊版", "60", "", ""],
    ["EleB", "10:30", "報開工 九月版", "30", "2026-09-01", ""],
    ["EleB", "10:45", "報開工 15", "15", "2026-09-10", ""],
    ["EleB", "11:00", "衫 120", "120", "2026-09-10", ""],
    ["EleB", "12:00", "- 統計人流", "", "2026-09-10", ""],
    ["EleB", "13:00", "* 飯 55", "", "2026-09-10", ""],
    ["EleB", "13:55", "停用咗嘅行", "5", "2026-09-10", "1"],
    ["EleB", "21:30", "報收工 (日-四) 30", "30", "2026-09-10", ""],
    ["EleB", "22:00", "報收工 (五六) 0", "0", "2026-09-10", ""],
    ["EleB", "01:30", "凌晨行 10", "10", "2026-09-10", ""],
    # VPP：淨係得停用行——known 都係 true，但 rows 空
    ["VPP", "09:45", "報開工", "35", "", "停用"],
]
ROSTER_ROWS = [["2026年9月 25 SB 26 EleB 27 EleB 28 EleB 29 SH11"]]
CODE_DEFS = [
    {"pattern": "WL*", "label": "週假"},
    {"pattern": "SH*", "label": "勞工假"},
    {"pattern": "AL*", "label": "年假"},
    {"pattern": "SB", "label": "Stand by"},
    {"pattern": "其他", "label": "返工日"},
]
POSTS = [
    {"code": "EleB", "post": "ELEB - Chanel 圓方"},
    {"code": "VPP", "post": "V-PP 金鐘太古廣場"},
]


def _day(date_iso: str, roster_code: str, is_work_day: bool, **meal_plan_extra):
    meal_plan = {
        "meal_ingredients": {
            "早餐": ["燕麥(60g)", "奇亞籽粉 (15g)", "冇括號食材"],
            "午餐": [],
            "小食": [],
            "晚餐": ["雞胸肉(80g)"],
        },
        "meal_times_resolved": {"早餐": "07:30", "午餐": "13:30", "小食": None, "晚餐": "22:00", "_skipped": {}},
        "meal_nutrients": {
            "早餐": {"kcal": 523.5},
            "午餐": {"kcal": 500},
            "小食": {"kcal": 0},
            "晚餐": {"kcal": 419.15},
        },
        "restaurant_lunch": {"keyword": "Ele*", "store": "Elements", "hours": "11:00 - 21:00", "choice": "Alimente", "address": ""},
        "rice_note": "藜麥米(熟)(390g)=生重148g",
        "note": None,
        "summary": {
            "totals": [1371.4, 82.2, 163.7, 28.1, 51, 290, 1046.5, 45.6, 6.5, 0],
            "errors": [0, 0, 0, -6.9, -149, -1410, 46.5, -0.1, -4.2, -1.5],
            "total_red_flags": [False, False, False, False, False, False, True, False, False, False],
            "error_red_flags": [False, True, False, False, False, False, False, False, False, False],
        },
    }
    meal_plan.update(meal_plan_extra)
    return {
        "date": date_iso,
        "roster_code": roster_code,
        "is_work_day": is_work_day,
        "nutrient_indicators": {
            "kcal": {"kind": "range", "lo": 1338, "hi": 1538, "raw": "1338-1538"},
            "protein_g": {"kind": "range", "lo": 77, "hi": 107, "raw": "77-107"},
        },
        "meal_plan": meal_plan,
    }


class DashboardApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_root = os.environ.get("MENU_PROJECT_ROOT")
        os.environ["MENU_PROJECT_ROOT"] = self.tmp.name
        clear_settings_cache()
        settings = get_settings()
        save_sheet_rows("schedule_grid", [list(r) for r in GRID_ROWS], settings)
        save_sheet_rows("roster", [list(r) for r in ROSTER_ROWS], settings)
        save_roster_code_definitions(CODE_DEFS, settings)
        save_roster_post_mapping(POSTS, settings)
        self.client = TestClient(app)

    def tearDown(self):
        if self.old_root is None:
            os.environ.pop("MENU_PROJECT_ROOT", None)
        else:
            os.environ["MENU_PROJECT_ROOT"] = self.old_root
        clear_settings_cache()
        self.tmp.cleanup()

    def grid(self, start: str, end: str | None = None, **params):
        r = self.client.get("/api/dashboard/schedule-grid", params={"start": start, "end": end or start, **params})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def meal(self, date_iso: str):
        r = self.client.get("/api/dashboard/meal", params={"date": date_iso})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    # ---- schedule-grid ----

    def test_grid_normal_day_shape(self):
        payload = self.grid(MON)
        self.assertEqual(payload["start"], MON)
        self.assertEqual(payload["end"], MON)
        self.assertEqual(len(payload["days"]), 1)
        day = payload["days"][0]
        self.assertEqual(sorted(day.keys()), ["codes", "date", "duties"])
        self.assertEqual(day["date"], MON)
        self.assertEqual(day["codes"], ["EleB"])
        duty = day["duties"][0]
        self.assertEqual(sorted(duty.keys()), ["code", "effectiveFrom", "known", "place", "rows"])
        self.assertEqual(duty["code"], "EleB")
        self.assertEqual(duty["effectiveFrom"], "2026-09-10")
        self.assertTrue(duty["known"])
        # post 前綴同更碼一樣就剝走（唔分大小寫）
        self.assertEqual(duty["place"], "Chanel 圓方")
        for row in duty["rows"]:
            self.assertEqual(sorted(row.keys()), ["content", "duration", "marker", "time"])
        # 星期一：(日-四) 出、(五六) 唔出；停用行唔出；次序照表
        self.assertEqual(
            [r["content"] for r in duty["rows"]],
            ["報開工 15", "衫 120", "- 統計人流", "* 飯 55", "報收工 (日-四) 30", "凌晨行 10"],
        )

    def test_grid_marker_star_disabled_and_30h_rows(self):
        rows = {r["content"]: r for r in self.grid(MON)["days"][0]["duties"][0]["rows"]}
        marker = rows["- 統計人流"]
        self.assertTrue(marker["marker"])
        self.assertIsNone(marker["duration"])   # 時長欄空 → null
        star = rows["* 飯 55"]
        self.assertFalse(star["marker"])
        self.assertEqual(star["duration"], 55)    # 星號行：時長欄空就用內容尾數
        self.assertEqual(rows["報開工 15"]["duration"], 15)
        self.assertEqual(rows["凌晨行 10"]["time"], "25:30")   # 30 小時制
        self.assertNotIn("停用咗嘅行", rows)

    def test_grid_weekday_filter(self):
        def tails(date_iso):
            return [r["content"] for r in self.grid(date_iso, code="EleB")["days"][0]["duties"][0]["rows"] if "報收工" in r["content"]]

        self.assertEqual(tails(MON), ["報收工 (日-四) 30"])
        self.assertEqual(tails(SUN), ["報收工 (日-四) 30"])
        self.assertEqual(tails(FRI), ["報收工 (五六) 0"])
        self.assertEqual(tails(SAT), ["報收工 (五六) 0"])

    def test_grid_effective_date_picks_version(self):
        def first(date_iso):
            duty = self.grid(date_iso, code="EleB")["days"][0]["duties"][0]
            return duty["effectiveFrom"], duty["rows"][0]["content"]

        self.assertEqual(first("2026-08-20"), (None, "報開工 舊版"))          # 冇任何已生效版本 → 冇日期嗰版
        self.assertEqual(first("2026-09-01"), ("2026-09-01", "報開工 九月版"))  # 生效當日已算
        self.assertEqual(first("2026-09-09"), ("2026-09-01", "報開工 九月版"))
        self.assertEqual(first("2026-09-10"), ("2026-09-10", "報開工 15"))

    def test_grid_code_override_range_and_unknown_code(self):
        payload = self.grid(FRI, MON, code="VPP")
        self.assertEqual([d["date"] for d in payload["days"]], [FRI, SAT, SUN, MON])
        for day in payload["days"]:
            self.assertEqual(day["codes"], ["VPP"])
            duty = day["duties"][0]
            self.assertFalse(duty["known"])         # 表入面得停用行 → 當呢個更碼唔存在（同以前 Dashboard JS 一樣）
            self.assertEqual(duty["rows"], [])
            self.assertIsNone(duty["effectiveFrom"])
            self.assertEqual(duty["place"], "V-PP 金鐘太古廣場")   # 前綴 V-PP ≠ VPP，唔剝
        unknown = self.grid(MON, code="ZZZ")["days"][0]["duties"][0]
        self.assertEqual(unknown, {"code": "ZZZ", "place": None, "effectiveFrom": None, "rows": [], "known": False})
        # 更碼夾行位表唔分大小寫，但 code 照傳入嘅出、崗位表係 exact key（同以前 Dashboard JS 一樣）
        lower = self.grid(MON, code="eleb")["days"][0]["duties"][0]
        self.assertEqual((lower["code"], lower["known"], lower["place"], lower["effectiveFrom"]), ("eleb", True, None, "2026-09-10"))

    def test_grid_day_without_roster_code(self):
        # 更表冇 9 月 30 日；SB 日更表有更碼但行位表冇（known false、rows 空）
        self.assertEqual(self.grid("2026-09-30")["days"][0], {"date": "2026-09-30", "codes": [], "duties": []})
        sb = self.grid(FRI)["days"][0]
        self.assertEqual(sb["codes"], ["SB"])
        self.assertEqual(sb["duties"][0]["known"], False)
        self.assertEqual(sb["duties"][0]["rows"], [])
        # 更表整張唔存在都要照答（codes 空），唔好 500
        with tempfile.TemporaryDirectory() as tmp2:
            os.environ["MENU_PROJECT_ROOT"] = tmp2
            clear_settings_cache()
            save_sheet_rows("schedule_grid", [list(r) for r in GRID_ROWS], get_settings())
            self.assertEqual(self.grid(MON)["days"][0]["codes"], [])
            self.assertEqual(self.grid(MON, code="EleB")["days"][0]["duties"][0]["known"], True)

    def test_grid_validation(self):
        self.assertEqual(self.client.get("/api/dashboard/schedule-grid", params={"start": "bad", "end": MON}).status_code, 400)
        self.assertEqual(self.client.get("/api/dashboard/schedule-grid", params={"start": MON, "end": FRI}).status_code, 400)
        self.assertEqual(self.client.get("/api/dashboard/schedule-grid", params={"start": "2026-01-01", "end": "2026-12-31"}).status_code, 400)
        self.assertEqual(self.client.get("/api/dashboard/schedule-grid", params={"start": MON}).status_code, 422)

    # ---- meal ----

    def test_meal_normal_work_day(self):
        save_plan_versions([_day(SAT, "EleB", True), _day(SUN, "EleB", True)])
        payload = self.meal(SAT)
        self.assertEqual(
            sorted(payload.keys()),
            ["date", "generatedAt", "isWorkDay", "meals", "nextDate", "note", "nutrition", "prevDate", "riceNote", "rosterCode", "rosterLabel"],
        )
        self.assertEqual(payload["date"], SAT)
        self.assertIsNone(payload["prevDate"])
        self.assertEqual(payload["nextDate"], SUN)
        self.assertEqual(payload["rosterCode"], "EleB")
        self.assertEqual(payload["rosterLabel"], "Work day")   # 冇夾到定義 → 其他 → 返工日 → 英文
        self.assertTrue(payload["isWorkDay"])
        self.assertEqual(payload["riceNote"], "藜麥米(熟)(390g)=生重148g")
        self.assertIsNone(payload["note"])
        # 餐次：小食冇嘢食就唔出；午餐冇 items 但有排時間 → 餐廳午餐
        self.assertEqual([m["name"] for m in payload["meals"]], ["早餐", "午餐", "晚餐"])
        bf = payload["meals"][0]
        self.assertEqual(sorted(bf.keys()), ["items", "kcal", "name", "restaurant", "skipped", "time"])
        self.assertEqual(bf["time"], "07:30")
        self.assertEqual(
            bf["items"],
            [{"name": "燕麥", "amount": "60g"}, {"name": "奇亞籽粉", "amount": "15g"}, {"name": "冇括號食材", "amount": ""}],
        )
        self.assertEqual(bf["kcal"], 524)   # JS Math.round：523.5 → 524
        self.assertIsNone(bf["restaurant"])
        self.assertIsNone(bf["skipped"])
        lunch = payload["meals"][1]
        self.assertEqual(lunch["items"], [])
        self.assertEqual(lunch["restaurant"], {"choice": "Alimente", "store": "Elements", "hours": "11:00 - 21:00"})
        self.assertEqual(lunch["kcal"], 500)
        self.assertEqual(payload["meals"][2]["kcal"], 419)
        # 營養 10 項固定次序；target 冇 indicator 就 ''；紅旗照 summary
        n = payload["nutrition"]
        self.assertEqual(len(n), 10)
        self.assertEqual([x["key"] for x in n], ["kcal", "protein_g", "carb_g", "sugar_g", "cholesterol_mg", "sodium_mg", "calcium_mg", "fat_total_g", "fat_sat_g", "fat_trans_g"])
        self.assertEqual([x["name"] for x in n], ["卡路里", "蛋白質", "碳水", "天然糖", "膽固醇", "鈉", "鈣", "總脂肪", "飽和脂肪", "反式脂肪"])
        self.assertEqual([x["unit"] for x in n], ["kCal", "g", "g", "g", "mg", "mg", "mg", "g", "g", "g"])
        self.assertEqual(n[0], {"key": "kcal", "name": "卡路里", "unit": "kCal", "total": 1371.4, "error": 0, "target": "1338-1538", "totalRed": False, "errorRed": False})
        self.assertEqual(n[1]["errorRed"], True)
        self.assertEqual(n[6]["totalRed"], True)
        self.assertEqual(n[2]["target"], "")

    def test_meal_non_work_day_labels_and_neighbours(self):
        save_plan_versions([_day(FRI, "SB", False), _day(SAT, "EleB", True), _day(MON, "SH11", False)])
        fri = self.meal(FRI)
        self.assertEqual((fri["rosterLabel"], fri["isWorkDay"]), ("Non-working day", False))
        self.assertEqual((fri["prevDate"], fri["nextDate"]), (None, SAT))
        mon = self.meal(MON)
        self.assertEqual((mon["rosterLabel"], mon["isWorkDay"]), ("Statutory holiday", False))   # SH* wildcard
        self.assertEqual((mon["prevDate"], mon["nextDate"]), (SAT, None))
        sat = self.meal(SAT)
        self.assertEqual((sat["prevDate"], sat["nextDate"]), (FRI, MON))

    def test_meal_missing_day(self):
        save_plan_versions([_day(FRI, "SB", False), _day(MON, "EleB", True)])
        self.assertEqual(self.meal(SUN), {"date": SUN, "missing": True, "prevDate": FRI, "nextDate": MON})
        self.assertEqual(self.meal("2026-01-01"), {"date": "2026-01-01", "missing": True, "prevDate": None, "nextDate": FRI})
        self.assertEqual(self.meal("2026-12-31"), {"date": "2026-12-31", "missing": True, "prevDate": MON, "nextDate": None})
        self.assertEqual(self.client.get("/api/dashboard/meal", params={"date": "2026-9-1"}).status_code, 400)

    def test_meal_uses_latest_version_and_restaurant_needs_time(self):
        first = save_plan_versions([_day(SAT, "EleB", True)])
        second = save_plan_versions([
            _day(SAT, "EleM", True, meal_times_resolved={"早餐": "07:30", "午餐": None, "小食": None, "晚餐": "22:00", "_skipped": {"午餐": "行位表13:15個飯位喺開工 13:40 之前，食唔到"}})
        ])
        self.assertNotEqual(first["timestamp"], second["timestamp"])
        payload = self.meal(SAT)
        self.assertEqual(payload["generatedAt"], second["timestamp"])
        self.assertEqual(payload["rosterCode"], "EleM")
        lunch = next(m for m in payload["meals"] if m["name"] == "午餐")
        self.assertIsNone(lunch["time"])
        self.assertIsNone(lunch["restaurant"])   # 午餐冇排時間 → 唔算餐廳午餐
        self.assertEqual(lunch["skipped"], "行位表13:15個飯位喺開工 13:40 之前，食唔到")   # 但有 skipped 原因就照出

    def test_meal_tolerates_sparse_day_json(self):
        save_plan_versions([{"date": SUN, "roster_code": None, "meal_plan": None}])
        payload = self.meal(SUN)
        self.assertIsNone(payload["rosterCode"])
        self.assertIsNone(payload["rosterLabel"])
        self.assertFalse(payload["isWorkDay"])
        self.assertEqual(payload["meals"], [])
        self.assertEqual(len(payload["nutrition"]), 10)
        self.assertEqual(payload["nutrition"][0]["total"], None)
        self.assertEqual(payload["nutrition"][0]["target"], "")


if __name__ == "__main__":
    unittest.main()
