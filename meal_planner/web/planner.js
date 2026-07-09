    const HK_TZ = "Asia/Hong_Kong";
    const MONTHS_EN = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    const MEALS = ["早餐", "午餐", "小食", "晚餐"];
    const MEAL_EN = { "早餐": "Breakfast", "午餐": "Lunch", "小食": "Snack", "晚餐": "Dinner" };
    let lastData = null;
    let currentFocusedDate = null;
    let columnWidths = {};
    let memoryPayload = { headers: [], indicator_rows: {}, nutrient_keys: [], days: [] };
    let shoppingCatalogByName = {};
    let targetPayload = { headers: [], indicator_rows: {}, nutrient_keys: [], profile: {} };
    let nutritionCatalogPayload = { nutrient_keys: [], rows: [] };
    let targetEditorWidth = null;
    let targetColumnWidths = {};
    let catalogColumnWidths = {};
    let formColumnWidths = {};
    let catalogCursorRowIndex = null;
    let activeRosterMonthIndex = 0;
    let showPast = true;
    let sidebarWidth = 260;
    let activePanel = "planner";
    let activeConfigView = "targets";
    let activeMenuPath = ["top", "planner"];
    let shoppingRiceConfig = null;
    let detailSettingsPayload = { rice: {}, roster_code_definitions: [] };
    let maintSheets = [];
    let activeMaintSheetKey = null;
    let maintSheetPayload = { sheet_key: null, display_name: "", rows: [] };
    let rosterReportSources = { payroll_times: [], overtime: [], wake_alarms: [], public_holidays: [], medical_appointments: [] };
    let googleCalendarSync = { enabled: false, write: false, client_secret_file: "", token_file: "", service_account_file: "", nonwork_calendar_id: "", work_calendar_id: "", alarm_calendar_id: "", wake_offset_hours: 3 };
    let googleCalendarAuth = { authenticated: false, status: "" };
    let generateBusy = false;
    let plannerDefaultDateIso = "";
    let plannerDateInputsTouched = false;
    let unsavedChanges = false;
    let unsavedArea = "";
    let unsavedAreaKey = "";
    let menuOrder = {
      top: ["config", "maint", "planner", "shopping"],
      config: ["target", "catalog", "details"],
      maint: [],
      reports: ["shift_code_analysis"],
    };
    let menuLabels = {};
    let menuHiddenKeys = [];
    let menuTreeOpen = { config: true, maint: false, reports: false };
    let menuDragState = null;
    const MAINT_SHEET_LABELS = {
      roster: "Roster",
      wake_alarms: "起身表",
      overtime: "Overtime",
      payroll_times: "Shift Times",
      public_holidays: "Public Holidays",
      medical_appointments: "Medical Appointments",
      meal_times: "Meal Times",
      restaurant: "Restaurants",
      schedule_grid: "Schedule Grid",
      mtr_doors: "地鐵車門",
    };
    const MENU_TREE_KEYS = ["config", "maint", "reports"];
    const MENU_STATIC_LEAF_KEYS = ["planner", "shopping", "target", "catalog", "details", "shift_code_analysis"];
    const REMOVED_MENU_KEYS = new Set(["runtime_import", "diagnostics", "wake_alarms", "alarm_sync"]);
    const MENU_DEFAULT_GROUPS = {
      planner: "top",
      shopping: "top",
      target: "config",
      catalog: "config",
      details: "config",
      shift_code_analysis: "reports",
    };

    function ymdNow() {
      const fmt = new Intl.DateTimeFormat("en-CA", { timeZone: HK_TZ, year: "numeric", month: "2-digit", day: "2-digit" });
      const p = fmt.formatToParts(new Date());
      return {
        y: +p.find((x) => x.type === "year").value,
        m: +p.find((x) => x.type === "month").value,
        d: +p.find((x) => x.type === "day").value,
      };
    }
    function ymdAddDays(ymd, days) {
      const dt = new Date(Date.UTC(ymd.y, ymd.m - 1, ymd.d + days, 12, 0, 0));
      return { y: dt.getUTCFullYear(), m: dt.getUTCMonth() + 1, d: dt.getUTCDate() };
    }
    function isoFromYmd(ymd) {
      return `${ymd.y}-${String(ymd.m).padStart(2, "0")}-${String(ymd.d).padStart(2, "0")}`;
    }
    function daysInMonth(year, month) {
      return new Date(Date.UTC(year, month, 0, 12, 0, 0)).getUTCDate();
    }
    function nextMonthYmd(year, month) {
      return month === 12 ? { y: year + 1, m: 1 } : { y: year, m: month + 1 };
    }
    function expandPlannerDateSegment(segment, year, month) {
      const match = String(segment || "").trim().match(/^(\d{1,2})\s*-\s*(\d{1,2})$/);
      if (!match) throw new Error("Invalid date range.");
      const start = Number(match[1]);
      const end = Number(match[2]);
      const out = [];
      if (start <= end) {
        const last = daysInMonth(year, month);
        for (let day = start; day <= end; day += 1) {
          if (day < 1 || day > last) throw new Error("Date is outside this month.");
          out.push({ y: year, m: month, d: day });
        }
        return out;
      }
      const lastCurrent = daysInMonth(year, month);
      for (let day = start; day <= lastCurrent; day += 1) {
        if (day < 1) throw new Error("Date is outside this month.");
        out.push({ y: year, m: month, d: day });
      }
      const next = nextMonthYmd(year, month);
      const lastNext = daysInMonth(next.y, next.m);
      for (let day = 1; day <= end; day += 1) {
        if (day > lastNext) throw new Error("Date is outside next month.");
        out.push({ y: next.y, m: next.m, d: day });
      }
      return out;
    }
    function plannerDatesFromInput() {
      const year = Number(document.getElementById("year")?.value);
      const month = Number(document.getElementById("month")?.value);
      const expr = String(document.getElementById("dates_expr")?.value || "").trim();
      if (!Number.isInteger(year) || !Number.isInteger(month) || month < 1 || month > 12 || !expr) return [];
      const tokens = expr.includes(",")
        ? expr.split(",").map((part) => part.trim()).filter(Boolean)
        : expr.split(/\s+/).map((part) => part.trim()).filter(Boolean);
      if (expr.includes(",") && tokens.some((part) => /\s/.test(part))) throw new Error("Invalid comma date expression.");

      let currentYear = year;
      let currentMonth = month;
      let lastDay = 0;
      const out = [];
      for (const token of tokens) {
        const range = token.match(/^(\d{1,2})\s*-\s*(\d{1,2})$/);
        if (range) {
          const startDay = Number(range[1]);
          if (startDay < lastDay) {
            const next = nextMonthYmd(currentYear, currentMonth);
            currentYear = next.y;
            currentMonth = next.m;
          }
          const segmentDates = expandPlannerDateSegment(token, currentYear, currentMonth);
          out.push(...segmentDates);
          if (segmentDates.length) {
            const last = segmentDates[segmentDates.length - 1];
            currentYear = last.y;
            currentMonth = last.m;
            lastDay = last.d;
          }
          continue;
        }
        if (/^\d{1,2}$/.test(token)) {
          const day = Number(token);
          if (day < lastDay) {
            const next = nextMonthYmd(currentYear, currentMonth);
            currentYear = next.y;
            currentMonth = next.m;
          }
          if (day < 1 || day > daysInMonth(currentYear, currentMonth)) throw new Error("Date is outside this month.");
          out.push({ y: currentYear, m: currentMonth, d: day });
          lastDay = day;
          continue;
        }
        throw new Error("Invalid date expression.");
      }
      return Array.from(new Set(out.map(isoFromYmd)));
    }
    function storedMealPlanDay(iso) {
      const days = Array.isArray(memoryPayload.days) ? memoryPayload.days : [];
      return days.find((day) => day && String(day.date || "") === iso) || null;
    }
    function mealTimeMinutes(raw) {
      const match = String(raw || "").match(/\b(\d{1,2}):(\d{2})\b/);
      if (!match) return null;
      const hour = Number(match[1]);
      const minute = Number(match[2]);
      if (!Number.isInteger(hour) || !Number.isInteger(minute) || hour > 23 || minute > 59) return null;
      return hour * 60 + minute;
    }
    function firstMealMinutesForDay(day) {
      const mealPlan = day && typeof day.meal_plan === "object" ? day.meal_plan : null;
      if (!mealPlan) return null;
      const resolved = mealPlan.meal_times_resolved && typeof mealPlan.meal_times_resolved === "object" ? mealPlan.meal_times_resolved : {};
      const primary = mealPlan.primary_rule && typeof mealPlan.primary_rule === "object" ? mealPlan.primary_rule : {};
      const values = [];
      for (const meal of MEALS) {
        let minutes = mealTimeMinutes(resolved[meal]);
        if (minutes == null) minutes = mealTimeMinutes(primary[meal]);
        if (minutes != null) values.push(minutes);
      }
      return values.length ? Math.min(...values) : null;
    }
    function currentMinutesHK() {
      const parts = new Intl.DateTimeFormat("en-GB", {
        timeZone: HK_TZ,
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).formatToParts(new Date());
      const hour = Number(parts.find((x) => x.type === "hour")?.value || "0");
      const minute = Number(parts.find((x) => x.type === "minute")?.value || "0");
      return hour * 60 + minute;
    }
    function canRegenerateExistingToday(iso) {
      const day = storedMealPlanDay(iso);
      if (!day) return true;
      const firstMeal = firstMealMinutesForDay(day);
      return firstMeal != null && currentMinutesHK() < firstMeal;
    }
    function generateBlockReasonForDate(iso) {
      const today = isoFromYmd(ymdNow());
      if (iso < today) return "past";
      if (iso === today && !canRegenerateExistingToday(iso)) return "today_after_first_meal";
      return "";
    }
    function generateBlockedDatesFromInput() {
      return plannerDatesFromInput().filter((iso) => generateBlockReasonForDate(iso));
    }
    function generateBlockedReasonFromState() {
      let blockedReason = "";
      let blockedDates = [];
      try {
        blockedDates = generateBlockedDatesFromInput();
      } catch (_) {
        blockedDates = [];
      }
      if (blockedDates.length) {
        blockedReason = `今日第一餐後及過去餐單不可重新生成：${blockedDates.join(", ")}`;
      } else if (currentFocusedDate && generateBlockReasonForDate(currentFocusedDate)) {
        blockedReason = `目前 cursor 日期 ${currentFocusedDate} 不可重新生成`;
      }
      return blockedReason;
    }
    function updateGenerateButtonState() {
      const btn = document.getElementById("go");
      if (!btn) return "";
      const blockedReason = generateBlockedReasonFromState();
      btn.disabled = generateBusy || !!blockedReason;
      btn.title = blockedReason || "Generate meal plan";
      return blockedReason;
    }
    function defaultPlannerDateYmd() {
      const today = ymdNow();
      const todayIso = isoFromYmd(today);
      return generateBlockReasonForDate(todayIso) ? ymdAddDays(today, 1) : today;
    }
    function currentPlannerInputIso() {
      try {
        const dates = plannerDatesFromInput();
        return dates.length === 1 ? dates[0] : "";
      } catch (_) {
        return "";
      }
    }
    function setPlannerDateInputs(ymd) {
      document.getElementById("year").value = ymd.y;
      document.getElementById("month").value = ymd.m;
      document.getElementById("dates_expr").value = String(ymd.d);
      plannerDefaultDateIso = isoFromYmd(ymd);
    }
    function applyDefaultPlannerDate({ preserveUserInput = false } = {}) {
      if (preserveUserInput && plannerDateInputsTouched) return;
      if (preserveUserInput) {
        const currentIso = currentPlannerInputIso();
        if (currentIso && currentIso !== plannerDefaultDateIso) return;
      }
      setPlannerDateInputs(defaultPlannerDateYmd());
      updateGenerateButtonState();
    }
    function markPlannerDateInputsTouched() {
      plannerDateInputsTouched = true;
    }
    function formatClockDateHK() {
      const parts = new Intl.DateTimeFormat("en-GB", {
        timeZone: HK_TZ,
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        weekday: "short",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
      }).formatToParts(new Date());
      const d = parts.find((x) => x.type === "day")?.value || "--";
      const m = parts.find((x) => x.type === "month")?.value || "--";
      const y = parts.find((x) => x.type === "year")?.value || "----";
      const wd = parts.find((x) => x.type === "weekday")?.value || "---";
      const hh = parts.find((x) => x.type === "hour")?.value || "--";
      const mm = parts.find((x) => x.type === "minute")?.value || "--";
      const ss = parts.find((x) => x.type === "second")?.value || "--";
      return `${d}/${m}/${y} ${wd} ${hh}:${mm}:${ss}`;
    }
    function startTopRightClock() {
      const el = document.getElementById("clock-top-right");
      if (!el) return;
      const tick = () => {
        el.textContent = formatClockDateHK();
      };
      tick();
      applyClockPosition();
      attachClockDrag();
      window.setInterval(tick, 1000);
    }
    function clockPosition() {
      const left = Number(formColumnWidths.clock_left);
      const top = Number(formColumnWidths.clock_top);
      return Number.isFinite(left) && Number.isFinite(top) ? { left, top } : null;
    }
    function applyClockPosition() {
      const el = document.getElementById("clock-top-right");
      if (!el) return;
      const pos = clockPosition();
      if (!pos) {
        el.style.left = "";
        el.style.top = "";
        el.style.right = "";
        return;
      }
      const maxLeft = Math.max(0, window.innerWidth - el.offsetWidth - 4);
      const maxTop = Math.max(0, window.innerHeight - el.offsetHeight - 4);
      const left = Math.max(4, Math.min(maxLeft, pos.left));
      const top = Math.max(4, Math.min(maxTop, pos.top));
      el.style.left = `${left}px`;
      el.style.top = `${top}px`;
      el.style.right = "auto";
    }
    function resetClockPosition() {
      delete formColumnWidths.clock_left;
      delete formColumnWidths.clock_top;
      applyClockPosition();
      persistColumnWidths();
    }
    function attachClockDrag() {
      const el = document.getElementById("clock-top-right");
      if (!el || el.dataset.clockDragBound === "1") return;
      el.dataset.clockDragBound = "1";
      el.title = "Drag to move; double-click to reset";
      el.addEventListener("mousedown", (ev) => {
        if (ev.button != null && ev.button !== 0) return;
        ev.preventDefault();
        const rect = el.getBoundingClientRect();
        const startX = ev.clientX;
        const startY = ev.clientY;
        const startLeft = rect.left;
        const startTop = rect.top;
        document.body.classList.add("is-dnd-dragging");
        const onMove = (mv) => {
          const maxLeft = Math.max(0, window.innerWidth - el.offsetWidth - 4);
          const maxTop = Math.max(0, window.innerHeight - el.offsetHeight - 4);
          formColumnWidths.clock_left = Math.max(4, Math.min(maxLeft, startLeft + mv.clientX - startX));
          formColumnWidths.clock_top = Math.max(4, Math.min(maxTop, startTop + mv.clientY - startY));
          applyClockPosition();
        };
        const onUp = () => {
          window.removeEventListener("mousemove", onMove);
          window.removeEventListener("mouseup", onUp);
          document.body.classList.remove("is-dnd-dragging");
          persistColumnWidths();
        };
        window.addEventListener("mousemove", onMove);
        window.addEventListener("mouseup", onUp);
      });
      el.addEventListener("dblclick", resetClockPosition);
      window.addEventListener("resize", applyClockPosition);
    }
    (function init() {
      applyDefaultPlannerDate();
      window.setInterval(() => {
        applyDefaultPlannerDate({ preserveUserInput: true });
        updateGenerateButtonState();
      }, 30000);
    })();

    function esc(s) {
      if (s == null) return "";
      return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    function br(s) {
      return esc(s).replace(/\n/g, "<br />");
    }

    function setSaveButtonVisible(id, visible) {
      const buttons = [document.getElementById(id)].filter(Boolean);
      if (!buttons.length) return;
      if (id === "maint-save") {
        buttons.forEach((btn) => {
          btn.style.display = "";
          btn.style.visibility = "visible";
          btn.disabled = !visible;
          btn.setAttribute("aria-disabled", visible ? "false" : "true");
        });
        return;
      }
      const btn = buttons[0];
      btn.style.display = visible ? "" : "none";
    }

    function activeMaintDisplayName() {
      const key = activeMaintSheetKey || (maintSheetPayload && maintSheetPayload.sheet_key) || "";
      const sheet = (maintSheets || []).find((item) => item && item.sheet_key === key);
      return (sheet && sheet.display_name) || (maintSheetPayload && maintSheetPayload.display_name) || (key ? menuLabel(key) : "");
    }

    function setUnsavedChanges(area = "資料") {
      unsavedChanges = true;
      unsavedAreaKey = area;
      const label = area === "餐單參數" ? (activeMaintDisplayName() || area) : (area || "資料");
      unsavedArea = label;
      if (area === "目標") {
        setSaveButtonVisible("target-save", true);
        setSaveButtonVisible("planner-target-save", true);
        if (typeof setTargetStatus === "function") setTargetStatus(`${label}未儲存`);
      } else if (area === "營養清單") {
        setSaveButtonVisible("catalog-save", true);
        if (typeof setCatalogStatus === "function") setCatalogStatus(`${label}未儲存`);
      } else if (area === "系統參數") {
        setSaveButtonVisible("detail-save", true);
        if (typeof setDetailStatus === "function") setDetailStatus(`${label}未儲存`);
      } else if (area === "餐單參數") {
        setSaveButtonVisible("maint-save", true);
        if (typeof setMaintStatus === "function") setMaintStatus(`${label}未儲存`);
      }
    }

    function clearUnsavedChanges(area = "") {
      if (!area || unsavedAreaKey === area || unsavedArea === area) {
        unsavedChanges = false;
        unsavedArea = "";
        unsavedAreaKey = "";
      }
      if (!area || area === "目標") {
        setSaveButtonVisible("target-save", false);
        setSaveButtonVisible("planner-target-save", false);
      }
      if (!area || area === "營養清單") setSaveButtonVisible("catalog-save", false);
      if (!area || area === "系統參數") setSaveButtonVisible("detail-save", false);
      if (!area || area === "餐單參數") setSaveButtonVisible("maint-save", false);
    }

    function showUnsavedDialog() {
      return new Promise((resolve) => {
        const backdrop = document.getElementById("unsaved-dialog");
        const message = document.getElementById("unsaved-message");
        const save = document.getElementById("unsaved-save");
        const ignore = document.getElementById("unsaved-ignore");
        const cancel = document.getElementById("unsaved-cancel");
        if (!backdrop || !save || !ignore || !cancel) {
          resolve("cancel");
          return;
        }
        if (message) message.textContent = `${unsavedArea || "資料"}有未儲存更新。`;
        backdrop.hidden = false;
        const cleanup = (choice) => {
          backdrop.hidden = true;
          save.disabled = false;
          ignore.disabled = false;
          cancel.disabled = false;
          save.removeEventListener("click", onSave);
          ignore.removeEventListener("click", onIgnore);
          cancel.removeEventListener("click", onCancel);
          document.removeEventListener("keydown", onKey);
          resolve(choice);
        };
        const onSave = () => {
          save.disabled = true;
          ignore.disabled = true;
          cancel.disabled = true;
          cleanup("save");
        };
        const onIgnore = () => cleanup("ignore");
        const onCancel = () => cleanup("cancel");
        const onKey = (ev) => {
          if (ev.key === "Escape") cleanup("cancel");
        };
        save.addEventListener("click", onSave);
        ignore.addEventListener("click", onIgnore);
        cancel.addEventListener("click", onCancel);
        document.addEventListener("keydown", onKey);
        save.focus();
      });
    }

    async function resolveUnsavedBeforeLeaving() {
      if (!unsavedChanges) return true;
      const choice = await showUnsavedDialog();
      if (choice === "cancel") return false;
      if (choice === "ignore") {
        clearUnsavedChanges();
        return true;
      }
      try {
        await saveActiveEditor();
        return !unsavedChanges;
      } catch (_) {
        return false;
      }
    }

    function editableAreaName(el) {
      if (!el || !el.closest) return "";
      if (el.closest(".maint-filter-select")) return "";
      if (el.closest(".target-config-blocks") || el.closest("#out input[data-target-source='planner']")) return "目標";
      if (el.closest("#catalog-editor")) return "營養清單";
      if (el.closest(".detail-editor")) return "系統參數";
      if (el.closest("#maint-editor")) return "餐單參數";
      return "";
    }

    function playGenerateChime() {
      try {
        const Ctx = window.AudioContext || window.webkitAudioContext;
        if (!Ctx) return;
        const ctx = new Ctx();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = "sine";
        osc.frequency.setValueAtTime(880, ctx.currentTime);
        gain.gain.setValueAtTime(0.0001, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.08, ctx.currentTime + 0.01);
        gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.18);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(ctx.currentTime);
        osc.stop(ctx.currentTime + 0.2);
        osc.onended = () => {
          try { ctx.close(); } catch (_) {}
        };
      } catch (_) {}
    }

    /** @param {string} iso */
    function dateDMY(iso) {
      const [y, m, d] = iso.split("-").map(Number);
      return `${d}-${MONTHS_EN[m - 1]}`;
    }

    /** @param {string} iso */
    function dowZh(iso) {
      const [y, m, d] = iso.split("-").map(Number);
      const dt = new Date(y, m - 1, d);
      return ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][dt.getDay()];
    }

    function getColumnKeys(nutrientKeys) {
      const nk = Array.isArray(nutrientKeys) && nutrientKeys.length ? nutrientKeys : [
        "kcal","protein_g","carb_g","sugar_g","cholesterol_mg","sodium_mg","calcium_mg","fat_total_g","fat_sat_g","fat_trans_g"
      ];
      return ["date", "dow", "code", "time", "content", ...nk];
    }

    function defaultColWidth(key) {
      if (key === "date") return 84;
      if (key === "dow") return 54;
      if (key === "code") return 72;
      if (key === "time") return 84;
      if (key === "content") return 460;
      return 72;
    }

    function colWidthPx(key) {
      const v = columnWidths[key];
      if (typeof v === "number" && Number.isFinite(v) && v >= 36) return v;
      return defaultColWidth(key);
    }

    function colGroupHtml(nutrientKeys) {
      return `<colgroup>${getColumnKeys(nutrientKeys).map((k) => `<col data-col-key="${k}" style="width:${colWidthPx(k)}px">`).join("")}</colgroup>`;
    }

    function columnWidthTotalPx(nutrientKeys) {
      return getColumnKeys(nutrientKeys).reduce((total, key) => total + colWidthPx(key), 0);
    }

    function applyColumnWidths() {
      document.querySelectorAll("col[data-col-key]").forEach((col) => {
        const key = col.getAttribute("data-col-key");
        col.style.width = `${colWidthPx(key)}px`;
      });
      document.querySelectorAll("table.sheet:not(.shopping-table)").forEach((table) => {
        const width = Array.from(table.querySelectorAll("col[data-col-key]"))
          .reduce((total, col) => total + colWidthPx(col.getAttribute("data-col-key")), 0);
        if (width > 0) table.style.width = `${width}px`;
      });
      document.querySelectorAll("col[data-shop-col-key]").forEach((col) => {
        const key = col.getAttribute("data-shop-col-key");
        col.style.width = `${shopColWidthPx(key)}px`;
      });
      document.querySelectorAll("table.sheet.shopping-table").forEach((table) => {
        table.style.width = `${shoppingColumnWidthTotalPx()}px`;
      });
    }

    function applySidebarWidth() {
      const el = document.getElementById("sidebar");
      if (!el) return;
      const w = Number(sidebarWidth);
      el.style.width = `${Math.max(120, Math.min(520, Number.isFinite(w) ? w : 260))}px`;
    }

    function attachSidebarResizer() {
      const grip = document.getElementById("sidebar-resizer");
      const sidebar = document.getElementById("sidebar");
      const shell = document.querySelector(".app-shell");
      if (!grip || !sidebar || !shell) return;
      if (grip.dataset.bound === "1") return;
      grip.dataset.bound = "1";
      grip.addEventListener("mousedown", (ev) => {
        ev.preventDefault();
        const shellRect = shell.getBoundingClientRect();
        const onMove = (mv) => {
          sidebarWidth = Math.max(120, Math.min(520, mv.clientX - shellRect.left));
          applySidebarWidth();
        };
        const onUp = () => {
          window.removeEventListener("mousemove", onMove);
          window.removeEventListener("mouseup", onUp);
          persistColumnWidths();
        };
        window.addEventListener("mousemove", onMove);
        window.addEventListener("mouseup", onUp);
      });
    }

    function bindPanelScrollSync() {
      const top = document.querySelector(".panel-top");
      const bottom = document.querySelector(".panel-bottom");
      if (!top || !bottom) return;
      let syncing = false;
      top.addEventListener("scroll", () => {
        if (syncing) return;
        syncing = true;
        bottom.scrollLeft = top.scrollLeft;
        syncing = false;
      });
      bottom.addEventListener("scroll", () => {
        if (syncing) return;
        syncing = true;
        top.scrollLeft = bottom.scrollLeft;
        syncing = false;
      });
    }

    function syncPanelGutter() {
      const top = document.querySelector(".panel-top");
      const bottom = document.querySelector(".panel-bottom");
      if (!top || !bottom) return;
      const gutter = Math.max(0, bottom.offsetWidth - bottom.clientWidth);
      top.style.paddingRight = `${gutter}px`;
    }

    function attachColumnResizers() {
      const hdr = document.querySelector("tr.hdr-labels");
      if (!hdr) return;
      hdr.querySelectorAll("td[data-col-key]").forEach((cell) => {
        if (cell.querySelector(".col-resizer")) return;
        const key = cell.getAttribute("data-col-key");
        const grip = document.createElement("div");
        grip.className = "col-resizer";
        grip.addEventListener("mousedown", (ev) => {
          ev.preventDefault();
          const startX = ev.clientX;
          const startW = colWidthPx(key);
          const onMove = (mv) => {
            columnWidths[key] = Math.max(36, startW + (mv.clientX - startX));
            applyColumnWidths();
          };
          const onUp = () => {
            window.removeEventListener("mousemove", onMove);
            window.removeEventListener("mouseup", onUp);
            persistColumnWidths();
          };
          window.addEventListener("mousemove", onMove);
          window.addEventListener("mouseup", onUp);
        });
        cell.appendChild(grip);
      });
    }

    function setActivePanel(panel, persist = true) {
      const planner = document.getElementById("planner-panel");
      const config = document.getElementById("config-panel");
      const maint = document.getElementById("maint-panel");
      const reports = document.getElementById("reports-panel");
      const shopping = document.getElementById("shopping-panel");
      const mPlanner = document.getElementById("menu-planner");
      const mConfig = document.getElementById("menu-config");
      const mConfigTarget = document.getElementById("menu-config-target");
      const mConfigCatalog = document.getElementById("menu-config-catalog");
      const mConfigDetails = document.getElementById("menu-config-details");
      const mMaint = document.getElementById("menu-maint");
      const mReports = document.getElementById("menu-reports");
      const mShiftCodeAnalysis = document.getElementById("menu-report-shift-code-analysis");
      const mShopping = document.getElementById("menu-shopping");
      const target = panel || "planner";
      activePanel = ["planner", "config", "maint", "shopping", "reports"].includes(target) ? target : "planner";
      planner.style.display = activePanel === "planner" ? "" : "none";
      config.style.display = activePanel === "config" ? "" : "none";
      maint.style.display = activePanel === "maint" ? "" : "none";
      reports.style.display = activePanel === "reports" ? "" : "none";
      shopping.style.display = activePanel === "shopping" ? "" : "none";
      mPlanner.classList.toggle("active", activePanel === "planner");
      mConfig.classList.toggle("active", activePanel === "config");
      mConfigTarget.classList.remove("active");
      mConfigCatalog.classList.remove("active");
      mConfigDetails.classList.remove("active");
      mMaint.classList.toggle("active", activePanel === "maint");
      document.querySelectorAll("[data-maint-sheet-key]").forEach((btn) => {
        btn.classList.toggle("active", activePanel === "maint" && btn.dataset.maintSheetKey === activeMaintSheetKey);
      });
      mReports.classList.toggle("active", activePanel === "reports");
      mShiftCodeAnalysis.classList.toggle("active", activePanel === "reports");
      mShopping.classList.toggle("active", activePanel === "shopping");
      if (persist) persistColumnWidths();
      return true;
    }

    function setConfigMenuTreeOpen(open, persist = true) {
      const tree = document.getElementById("config-menu-tree");
      const toggle = document.getElementById("menu-config");
      const isOpen = !!open;
      menuTreeOpen.config = isOpen;
      if (!tree || !toggle) return;
      tree.classList.toggle("is-open", isOpen);
      toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
      if (persist) persistMenuTreeOpen();
    }

    function setMaintMenuTreeOpen(open, persist = true) {
      const tree = document.getElementById("maint-menu-tree");
      const toggle = document.getElementById("menu-maint");
      const isOpen = !!open;
      menuTreeOpen.maint = isOpen;
      if (!tree || !toggle) return;
      tree.classList.toggle("is-open", isOpen);
      toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
      if (persist) persistMenuTreeOpen();
    }

    function setReportsMenuTreeOpen(open, persist = true) {
      const tree = document.getElementById("reports-menu-tree");
      const toggle = document.getElementById("menu-reports");
      const isOpen = !!open;
      menuTreeOpen.reports = isOpen;
      if (!tree || !toggle) return;
      tree.classList.toggle("is-open", isOpen);
      toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
      if (persist) persistMenuTreeOpen();
    }

    function applyMenuTreeOpen() {
      setConfigMenuTreeOpen(menuTreeOpen.config !== false, false);
      setMaintMenuTreeOpen(!!menuTreeOpen.maint, false);
      setReportsMenuTreeOpen(!!menuTreeOpen.reports, false);
      Object.keys(menuTreeOpen || {}).forEach((key) => {
        if (!MENU_TREE_KEYS.includes(key) && typeof setCustomMenuTreeOpen === "function") {
          setCustomMenuTreeOpen(key, !!menuTreeOpen[key], false);
        }
      });
    }

    function maintSheetKeys() {
      return (maintSheets || []).map((sheet) => sheet.sheet_key).filter(Boolean);
    }

    function allMenuLeafKeys() {
      return MENU_STATIC_LEAF_KEYS.concat(maintSheetKeys());
    }

    function allMenuKeys() {
      return MENU_TREE_KEYS.concat(allMenuLeafKeys());
    }

    function defaultMenuGroup(key) {
      if (MENU_DEFAULT_GROUPS[key]) return MENU_DEFAULT_GROUPS[key];
      if (maintSheetKeys().includes(key)) return "maint";
      return "top";
    }

    function isMenuTreeKey(key) {
      return MENU_TREE_KEYS.includes(key) || (key && menuOrder && Array.isArray(menuOrder[key]) && !menuNodeHasContent(key));
    }

    function menuNodeHasContent(key) {
      return MENU_STATIC_LEAF_KEYS.includes(key) || maintSheetKeys().includes(key);
    }

    function isRemovedMenuKey(key) {
      return REMOVED_MENU_KEYS.has(String(key || ""));
    }
