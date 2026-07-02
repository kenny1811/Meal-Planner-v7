# 餐單生成 v7 — 專案備忘

## 專案概覽
- `meal_planner/`：Python FastAPI 後端 + 網頁前端（`meal_planner/web/`）。根據更表/飯時/行位表/加班表生成每日餐單，用 LP（pulp）配食材命中營養目標；有餐廳午餐、米類備註、購物清單、Google Calendar 同步。
- `android_alarm_app/`：手機 + Wear OS 鬧鐘（由餐單網頁經 `oneshotalarm://` 收每日班次鬧鐘）。手機同手錶各自本地排程，只在 dismiss 時互相通知（慳電）。
- `android_watchface_app/`：自訂 Wear OS 錶面。
- Live 資料庫：專案根目錄 `meal_planner.sqlite3`（`.gitignore` 已排除，備份亦然）。

## 測試
- `pytest`（需 venv 裝齊 fastapi / pulp / openpyxl / pyyaml）。
- 不依賴 fastapi/pulp 的模組可用 `python -m unittest tests.<name>` 單獨跑。

## Cowork 編輯注意（重要 workaround）
本機 Cowork sandbox 有 mount cache bug：用 Edit/Write 工具（host 側寫入）改過的檔，
Linux sandbox 會讀到**過時／被截斷／含 null bytes** 的內容，令 `pytest` 及 `git add/commit`
拿到錯版本，需要重啟 app 才恢復。

→ 做法：**凡需要在同一 session 內測試或 commit 的改動，一律用 bash/shell 工具改檔**
（例如 python 精準字串替換），bash 是 sandbox 側寫入，兩邊即時 coherent，毋須重啟。
純粹交由用戶自行檢視、不需即時測試/commit 的改動，用 Edit 工具亦可（host 檔本身正確）。
