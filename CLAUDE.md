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

## 近期進度／現狀（2026-07-03 交接）

由 Codex 轉到 Claude 接手後，做咗一輪重覆清理 + 手機/手錶 alarm 修復。分支 `master`，全部已 commit。

**重覆清理（餐單）**
- A：刪 `preview.py` 內冇人用嘅 `_reload_all_sources`（每 request 重覆讀 7 張 SQLite 表）。
- B：抽 `_visible_meals_from_resolved` / `_clear_restaurant_lunch_items` / `_apply_rice_note_and_summary` 三個共用 helper。
- D：`web/api.js` 8 個 persist* 合併成 `persistUiState(patch)`；`await r.json().catch(()=>({}))`（31 處）抽成 `parseJsonSafe(r)`。
- F：`import re` 移上 module 層；清走 root 下 debug 快照 + 停用嘅 `meal_planner/meal_planner.sqlite3` + 舊 DB 備份。
- C（app.py schedule 邏輯）：評估後**冇改**——判定係 orchestration 唔係真重覆，風險大收益細。

**Android alarm（去中心化設計，慳電）**
- E(a)：`AlarmReceiver` 響鬧時**唔再** `WatchBridge.sendAlarm` push 去手錶（手錶自己本地排程）；保留 `sendTileState` + dismiss 互通。
- E(b)：開機後如錯過當日 05:00/05:30 匯入，`AlarmBootReceiver` 即刻補跑 `catchUpMissedDailyImport`。
- 手機/手錶 install 腳本嚴格用 `ro.build.characteristics` 分 phone/watch，唔會裝錯機。
- **wear `versionCode` 由 1 → 2 對齊 phone**：杜絕 `install -r` downgrade → 以後唔使 uninstall → 權限/complication 唔會再甩（根因修復，取代之前嘅 uninstall self-heal）。
- 手錶 app 正常開啟時會自己 request battery-optimization 豁免（`WatchAlarmActivity.maybeRequestBatteryExemption`）。

**已知 known-good / 排錯心得**
- 手錶 alarm 準時 depends on：battery-opt 豁免（`exempt_watch_doze.bat`），否則 Samsung Doze 會延遲送遞 1~2 秒。
- 手錶全螢幕鬧鐘 depends on `SYSTEM_ALERT_WINDOW` + `POST_NOTIFICATIONS`（uninstall 會清，`grant_watch_permissions.bat` 還原）。
- 手錶 complication（prev/next）由自訂錶面 `com.kenny.watchface` 嘅 WFF `DefaultProviderPolicy` 綁 `com.example.oneshotalarm` 提供；uninstall alarm app 會令 slot orphan，要 clean reinstall 錶面 app + reselect 先 rebind。

**Helper 腳本（`android_alarm_app/` 及 `android_watchface_app/`，double-click）**
- `start_auto_build.bat`（watcher）、`update_phone.bat`、`update_watch.bat`、`update_watchface.bat`、`reset_watchface.bat`
- `capture_watch.bat`（screencap）、`reboot_watch.bat`、`grant_watch_permissions.bat`、`exempt_watch_doze.bat`、`check_clocks.bat`
- 註：喺 Claude Code Local 模式可直接跑 adb/gradle/pytest，唔一定要靠呢啲 bat；bat 係 Cowork sandbox 掂唔到 adb 時嘅中轉。

**待驗證**
- 用戶部機跑 `pytest` 做完整回歸（Cowork sandbox 裝唔到 pulp/fastapi，只跑到 stdlib unittest 子集，已綠）。

## 用戶慣例（重要）
- **時間一律用 30 小時制**：凌晨 00:00–05:59 當作前一日嘅 24:00–29:59。
  例如實際 2026-07-05 00:16，用戶視為「2026-07-04 24:16」，即當日仍屬 7/4，
  返嗰更亦係 7/4 嘅更（TSB），唔係系統日曆嘅 7/5。
  → 判斷「今日」返邊更 / 睇行位表時，必須先按 30 小時制換算日期先啱。
- 全程用廣東話、輕鬆口氣回應；唔用政府做資訊來源（除非搵唔到其他）；唔干涉用戶喜好。
- 10 個營養值固定次序：卡路里 kCal、蛋白質 g、碳水 g、天然糖 g、膽固醇 mg、
  鈉 mg、鈣 mg、總脂肪 g、飽和脂肪 g、反式脂肪 g。
- **回覆格式**：每個「回應」（整個 reply）**尾**加 CRLF + timestamp，格式 `[dd/mm/yyyy ddd hh:mm:ss]`（連 `[]`）；唔係每句都加。
  timestamp 亦按 30 小時制（00:00–05:59 顯示為前一日 24:00–29:59）。
