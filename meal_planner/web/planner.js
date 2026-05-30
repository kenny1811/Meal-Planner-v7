    const HK_TZ = "Asia/Hong_Kong";
    const MONTHS_EN = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    const MEALS = ["早餐", "午餐", "小食", "晚餐"];
    const MEAL_EN = { "早餐": "Breakfast", "午餐": "Lunch", "小食": "Snack", "晚餐": "Dinner" };
    let lastData = null;
    let currentFocusedDate = null;
    let columnWidths = {};
    let memoryPayload = { headers: [], indicator_rows: {}, nutrient_keys: [], days: [] };
    let shoppingCatalogByName = {};
    let targetPayload = { headers: [], indicator_rows: {}, nutrient_keys: [] };
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
    let shoppingRiceConfig = null;
    let detailSettingsPayload = { rice: {}, roster_code_definitions: [] };
    let maintSheets = [];
    let activeMaintSheetKey = null;
    let maintSheetPayload = { sheet_key: null, display_name: "", rows: [] };
    let rosterReportSources = { payroll_times: [], overtime: [], public_holidays: [], medical_appointments: [] };
    let diagnosticsPayload = null;
    let unsavedChanges = false;
    let unsavedArea = "";
    let menuOrder = {
      top: ["config", "maint", "planner", "shopping", "diagnostics"],
      config: ["target", "catalog", "details"],
      maint: [],
    };
    let menuLabels = {};
    let menuHiddenKeys = [];
    let menuTreeOpen = { config: true, maint: false };
    let menuDragState = null;
    const MAINT_SHEET_LABELS = {
      roster: "Roster",
      overtime: "Overtime",
      payroll_times: "Shift Times",
      public_holidays: "Public Holidays",
      medical_appointments: "Medical Appointments",
      meal_times: "Meal Times",
      restaurant: "Restaurants",
      schedule_grid: "Schedule Grid",
    };
    const MENU_TREE_KEYS = ["config", "maint"];
    const MENU_STATIC_LEAF_KEYS = ["planner", "shopping", "diagnostics", "target", "catalog", "details"];
    const MENU_DEFAULT_GROUPS = {
      planner: "top",
      shopping: "top",
      diagnostics: "top",
      target: "config",
      catalog: "config",
      details: "config",
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
      window.setInterval(tick, 1000);
    }
    (function init() {
      const { y, m, d } = ymdNow();
      document.getElementById("year").value = y;
      document.getElementById("month").value = m;
      document.getElementById("dates_expr").value = String(d);
    })();

    function esc(s) {
      if (s == null) return "";
      return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    function br(s) {
      return esc(s).replace(/\n/g, "<br />");
    }

    function setSaveButtonVisible(id, visible) {
      const btn = document.getElementById(id);
      if (btn) btn.style.display = visible ? "" : "none";
    }

    function setUnsavedChanges(area = "資料") {
      unsavedChanges = true;
      unsavedArea = area;
      const label = area || "資料";
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
      if (!area || unsavedArea === area) {
        unsavedChanges = false;
        unsavedArea = "";
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
      if (el.closest("#target-editor") || el.closest("#out input[data-target-source='planner']")) return "目標";
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
      const shopping = document.getElementById("shopping-panel");
      const diagnostics = document.getElementById("diagnostics-panel");
      const mPlanner = document.getElementById("menu-planner");
      const mConfig = document.getElementById("menu-config");
      const mConfigTarget = document.getElementById("menu-config-target");
      const mConfigCatalog = document.getElementById("menu-config-catalog");
      const mConfigDetails = document.getElementById("menu-config-details");
      const mMaint = document.getElementById("menu-maint");
      const mShopping = document.getElementById("menu-shopping");
      const mDiagnostics = document.getElementById("menu-diagnostics");
      const target = panel || "planner";
      activePanel = ["planner", "config", "maint", "shopping", "diagnostics"].includes(target) ? target : "planner";
      planner.style.display = activePanel === "planner" ? "" : "none";
      config.style.display = activePanel === "config" ? "" : "none";
      maint.style.display = activePanel === "maint" ? "" : "none";
      shopping.style.display = activePanel === "shopping" ? "" : "none";
      diagnostics.style.display = activePanel === "diagnostics" ? "" : "none";
      mPlanner.classList.toggle("active", activePanel === "planner");
      mConfig.classList.toggle("active", activePanel === "config");
      mConfigTarget.classList.remove("active");
      mConfigCatalog.classList.remove("active");
      mConfigDetails.classList.remove("active");
      mMaint.classList.toggle("active", activePanel === "maint");
      document.querySelectorAll("[data-maint-sheet-key]").forEach((btn) => {
        btn.classList.toggle("active", activePanel === "maint" && btn.dataset.maintSheetKey === activeMaintSheetKey);
      });
      mShopping.classList.toggle("active", activePanel === "shopping");
      mDiagnostics.classList.toggle("active", activePanel === "diagnostics");
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

    function applyMenuTreeOpen() {
      setConfigMenuTreeOpen(menuTreeOpen.config !== false, false);
      setMaintMenuTreeOpen(!!menuTreeOpen.maint, false);
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
      return MENU_TREE_KEYS.includes(key);
    }

    function menuButtonForKey(key) {
      if (key === "planner") return document.getElementById("menu-planner");
      if (key === "shopping") return document.getElementById("menu-shopping");
      if (key === "diagnostics") return document.getElementById("menu-diagnostics");
      if (key === "target") return document.getElementById("menu-config-target");
      if (key === "catalog") return document.getElementById("menu-config-catalog");
      if (key === "details") return document.getElementById("menu-config-details");
      if (maintSheetKeys().includes(key)) {
        const sheetBtn = document.querySelector(`.menu-item[data-maint-sheet-key="${CSS.escape(key)}"]`);
        if (sheetBtn) return sheetBtn;
      }
      return document.querySelector(`.menu-item[data-menu-key="${CSS.escape(key)}"]`);
    }

    function existingMenuNodeForKey(key) {
      if (key === "config") return document.getElementById("config-menu-tree");
      if (key === "maint") return document.getElementById("maint-menu-tree");
      return menuButtonForKey(key);
    }

    function createCustomMenuButton(key) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "menu-item menu-custom-item";
      btn.setAttribute("data-menu-key", key);
      btn.setAttribute("data-menu-custom", "1");
      btn.innerHTML = `<span class="menu-drag-handle" draggable="true" title="Drag to reorder" aria-hidden="true"></span><span class="menu-item-label"></span>`;
      return btn;
    }

    function defaultMenuLabel(key) {
      if (key === "config") return "Config";
      if (key === "maint") return "Maint";
      if (key === "planner") return "Menu Planner";
      if (key === "shopping") return "Shopping List";
      if (key === "diagnostics") return "Diagnostics";
      if (key === "target") return "Target";
      if (key === "catalog") return "Catalog";
      if (key === "details") return "Detail Settings";
      const sheet = (maintSheets || []).find((item) => item && item.sheet_key === key);
      if (sheet) return MAINT_SHEET_LABELS[key] || sheet.display_name || key;
      return String(menuLabels[key] || key);
    }

    function menuLabel(key) {
      const custom = menuLabels && typeof menuLabels === "object" ? String(menuLabels[key] || "").trim() : "";
      return custom || defaultMenuLabel(key);
    }

    function applyMenuLabels() {
      document.querySelectorAll(".menu-item[data-menu-key]").forEach((item) => {
        const key = item.getAttribute("data-menu-key");
        const label = item.querySelector(".menu-item-label");
        if (key && label) label.textContent = menuLabel(key);
      });
    }

    function menuNodeForKey(key) {
      if (key === "config") return document.getElementById("config-menu-tree");
      if (key === "maint") return document.getElementById("maint-menu-tree");
      return menuButtonForKey(key) || createCustomMenuButton(key);
    }

    function menuContainerForGroup(group) {
      if (group === "config") return document.querySelector("#config-menu-tree .menu-tree-children");
      if (group === "maint") return document.getElementById("maint-menu-children");
      return document.querySelector(".sidebar .menu-list");
    }

    function removeDuplicateMenuNodes(preferredByKey = {}) {
      const seen = new Map();
      document.querySelectorAll(".menu-item[data-menu-key]").forEach((item) => {
        const key = item.getAttribute("data-menu-key");
        if (!key) return;
        const preferred = preferredByKey[key];
        if (preferred && item !== preferred) {
          item.remove();
          return;
        }
        if (!seen.has(key)) {
          seen.set(key, item);
          return;
        }
        item.remove();
      });
    }

    function cleanMenuOrder() {
      const validLeafKeys = allMenuLeafKeys();
      const validKeys = MENU_TREE_KEYS.concat(validLeafKeys);
      const used = new Set();
      const next = { top: [], config: [], maint: [] };
      const hidden = new Set(Array.isArray(menuHiddenKeys) ? menuHiddenKeys.map(String) : []);

      const add = (group, key) => {
        if (used.has(key) || hidden.has(key)) return;
        if (isMenuTreeKey(key) && group !== "top") group = "top";
        next[group].push(key);
        used.add(key);
      };

      for (const group of ["top", "config", "maint"]) {
        const saved = Array.isArray(menuOrder[group]) ? menuOrder[group] : [];
        saved.forEach((key) => add(group, String(key)));
      }
      validKeys.forEach((key) => add(defaultMenuGroup(key), key));
      menuOrder = next;
      return next;
    }

    function removeKeyFromMenuOrder(key) {
      for (const group of ["top", "config", "maint"]) {
        menuOrder[group] = (Array.isArray(menuOrder[group]) ? menuOrder[group] : []).filter((item) => item !== key);
      }
    }

    function menuGroupForKey(key) {
      const order = cleanMenuOrder();
      for (const group of ["top", "config", "maint"]) {
        if (order[group].includes(key)) return group;
      }
      return defaultMenuGroup(key);
    }

    function setMenuItemGroupClass(item, group) {
      if (!item) return;
      item.setAttribute("data-menu-group", group);
      item.classList.toggle("menu-child", group !== "top");
    }

    function normalizeMenuOrder(group, keys) {
      const saved = Array.isArray(menuOrder[group]) ? menuOrder[group].filter((key) => keys.includes(key)) : [];
      return saved.concat(keys.filter((key) => !saved.includes(key)));
    }

    function applyMenuOrder() {
      const order = cleanMenuOrder();
      removeDuplicateMenuNodes();
      const visible = new Set(["top", "config", "maint"].flatMap((group) => order[group] || []));
      const hidden = new Set(Array.isArray(menuHiddenKeys) ? menuHiddenKeys.map(String) : []);
      hidden.forEach((key) => {
        const node = existingMenuNodeForKey(key);
        if (node) node.style.display = "none";
      });
      document.querySelectorAll(".menu-custom-item[data-menu-key]").forEach((item) => {
        const key = item.getAttribute("data-menu-key");
        if (!key || !visible.has(key)) item.remove();
      });
      for (const group of ["top", "config", "maint"]) {
        const container = menuContainerForGroup(group);
        if (!container) continue;
        order[group].forEach((key) => {
          const node = menuNodeForKey(key);
          if (!node) return;
          node.style.display = "";
          if (!isMenuTreeKey(key)) setMenuItemGroupClass(node, group);
          container.appendChild(node);
        });
      }
      applyMenuLabels();
      attachMenuDragHandles();
    }

    function menuDropPosition(item, clientY) {
      if (!item || !Number.isFinite(clientY)) return "before";
      const rect = item.getBoundingClientRect();
      return clientY > rect.top + rect.height / 2 ? "after" : "before";
    }

    function markMenuDropTarget(item, position) {
      document.querySelectorAll(".menu-item.is-menu-drag-over,.menu-item.is-menu-drop-after").forEach((el) => {
        el.classList.remove("is-menu-drag-over", "is-menu-drop-after");
      });
      if (!item) return;
      item.classList.add(position === "after" ? "is-menu-drop-after" : "is-menu-drag-over");
    }

    function moveMenuItem(fromKey, toGroup, toKey = null, position = "before") {
      if (!fromKey || !toGroup || !["top", "config", "maint"].includes(toGroup)) return;
      if (isMenuTreeKey(fromKey)) toGroup = "top";
      const order = cleanMenuOrder();
      for (const group of ["top", "config", "maint"]) {
        order[group] = order[group].filter((key) => key !== fromKey);
      }
      const targetOrder = order[toGroup];
      const toIdx = toKey ? targetOrder.indexOf(toKey) : -1;
      if (toIdx >= 0) {
        targetOrder.splice(position === "after" ? toIdx + 1 : toIdx, 0, fromKey);
      } else {
        targetOrder.push(fromKey);
      }
      menuOrder = order;
      applyMenuOrder();
      persistMenuOrder();
    }

    function hideMenuContextMenu() {
      const menu = document.getElementById("menu-context-menu");
      if (!menu) return;
      menu.hidden = true;
      menu.removeAttribute("data-menu-key");
      menu.removeAttribute("data-menu-group");
    }

    function showMenuContextMenu(ev, item) {
      const menu = document.getElementById("menu-context-menu");
      if (!menu || !item) return;
      ev.preventDefault();
      ev.stopPropagation();
      menu.hidden = false;
      menu.setAttribute("data-menu-key", item.getAttribute("data-menu-key") || "");
      menu.setAttribute("data-menu-group", item.getAttribute("data-menu-group") || "top");
      menu.style.left = `${ev.clientX}px`;
      menu.style.top = `${ev.clientY}px`;
    }

    function renameMenuItem(key) {
      const current = menuLabel(key);
      const next = window.prompt("Menu display name", current);
      if (next == null) return;
      const clean = String(next).trim();
      if (clean && clean !== defaultMenuLabel(key)) {
        menuLabels[key] = clean;
      } else {
        delete menuLabels[key];
      }
      applyMenuLabels();
      persistMenuLayout();
    }

    function hiddenMenuChoicesText() {
      const hidden = Array.isArray(menuHiddenKeys) ? menuHiddenKeys.filter(Boolean) : [];
      if (!hidden.length) return "";
      return `\nHidden: ${hidden.map((key) => `${menuLabel(key)} (${key})`).join(", ")}`;
    }

    function resolveInsertedMenuKey(input) {
      const clean = String(input || "").trim();
      if (!clean) return "";
      const hidden = Array.isArray(menuHiddenKeys) ? menuHiddenKeys.map(String) : [];
      const lower = clean.toLowerCase();
      const match = hidden.find((key) => key.toLowerCase() === lower || menuLabel(key).toLowerCase() === lower);
      if (match) {
        menuHiddenKeys = hidden.filter((key) => key !== match);
        return match;
      }
      const key = `custom_${Date.now()}`;
      menuLabels[key] = clean;
      return key;
    }

    function insertMenuItemNear(anchorKey, anchorGroup, position) {
      const input = window.prompt(`Item name or hidden item key${hiddenMenuChoicesText()}`, "");
      const key = resolveInsertedMenuKey(input);
      if (!key) return;
      moveMenuItem(key, anchorGroup || "top", anchorKey, position);
      persistMenuLayout();
    }

    function deleteMenuItem(key) {
      if (!key) return;
      removeKeyFromMenuOrder(key);
      if (key.startsWith("custom_")) {
        delete menuLabels[key];
      } else if (!menuHiddenKeys.includes(key)) {
        menuHiddenKeys.push(key);
      }
      applyMenuOrder();
      persistMenuLayout();
    }

    function attachMenuContextMenuActions() {
      const menu = document.getElementById("menu-context-menu");
      if (!menu || menu.dataset.bound === "1") return;
      menu.dataset.bound = "1";
      menu.addEventListener("click", (ev) => {
        const btn = ev.target && ev.target.closest ? ev.target.closest("[data-menu-context-action]") : null;
        if (!btn) return;
        const action = btn.getAttribute("data-menu-context-action");
        const key = menu.getAttribute("data-menu-key");
        const group = menu.getAttribute("data-menu-group") || menuGroupForKey(key);
        hideMenuContextMenu();
        if (action === "insert-before") insertMenuItemNear(key, group, "before");
        if (action === "insert-after") insertMenuItemNear(key, group, "after");
        if (action === "rename") renameMenuItem(key);
        if (action === "delete") deleteMenuItem(key);
      });
      document.addEventListener("mousedown", (ev) => {
        if (!ev.target || !ev.target.closest || !ev.target.closest("#menu-context-menu")) hideMenuContextMenu();
      });
      document.addEventListener("keydown", (ev) => {
        if (ev.key === "Escape") hideMenuContextMenu();
      });
    }

    function createMenuDragGhost(item, ev) {
      const ghost = document.createElement("div");
      ghost.className = "menu-drag-ghost";
      ghost.textContent = item.textContent.trim();
      ghost.style.width = `${Math.min(260, Math.max(120, item.getBoundingClientRect().width))}px`;
      document.body.appendChild(ghost);
      moveMenuDragGhost(ghost, ev);
      return ghost;
    }

    function moveMenuDragGhost(ghost, ev) {
      if (!ghost) return;
      ghost.style.transform = `translate(${ev.clientX + 14}px, ${ev.clientY + 12}px)`;
    }

    function startPointerMenuDrag(handle, ev) {
      const item = handle.closest(".menu-item[data-menu-group][data-menu-key]");
      if (!item || (ev.button != null && ev.button !== 0)) return;
      ev.preventDefault();
      ev.stopPropagation();
      const group = item.getAttribute("data-menu-group");
      const fromKey = item.getAttribute("data-menu-key");
      let targetItem = item;
      let targetGroup = group;
      let targetKey = fromKey;
      let targetPosition = "before";
      menuDragState = { group, key: fromKey };
      item.classList.add("is-menu-dragging");
      const ghost = createMenuDragGhost(item, ev);
      const onMove = (mv) => {
        mv.preventDefault();
        moveMenuDragGhost(ghost, mv);
        const hit = document.elementFromPoint(mv.clientX, mv.clientY);
        const next = hit && hit.closest ? hit.closest(".menu-item[data-menu-group][data-menu-key]") : null;
        const container = hit && hit.closest ? hit.closest("[data-menu-drop-group]") : null;
        if (next) {
          targetItem = next;
          targetGroup = next.getAttribute("data-menu-group");
          targetKey = next.getAttribute("data-menu-key");
          targetPosition = menuDropPosition(next, mv.clientY);
          markMenuDropTarget(next, targetPosition);
        } else if (container) {
          targetItem = null;
          targetGroup = container.getAttribute("data-menu-drop-group") || "top";
          targetKey = null;
          targetPosition = "before";
          markMenuDropTarget(null, targetPosition);
        }
      };
      const onUp = (up) => {
        up.preventDefault();
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
        document.querySelectorAll(".menu-item.is-menu-dragging,.menu-item.is-menu-drag-over,.menu-item.is-menu-drop-after").forEach((el) => {
          el.classList.remove("is-menu-dragging", "is-menu-drag-over", "is-menu-drop-after");
        });
        ghost.remove();
        menuDragState = null;
        moveMenuItem(fromKey, targetGroup, targetKey, targetPosition);
      };
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    }

    function attachMenuDragHandles(root = document) {
      attachMenuContextMenuActions();
      root.querySelectorAll(".menu-drag-handle").forEach((handle) => {
        if (handle.dataset.menuDragBound === "1") return;
        handle.dataset.menuDragBound = "1";
        handle.addEventListener("click", (ev) => {
          ev.preventDefault();
          ev.stopPropagation();
        });
        handle.addEventListener("mousedown", (ev) => {
          startPointerMenuDrag(handle, ev);
        });
        handle.addEventListener("dragstart", (ev) => {
          const item = handle.closest(".menu-item[data-menu-group][data-menu-key]");
          if (!item || !ev.dataTransfer) return;
          ev.stopPropagation();
          menuDragState = {
            group: item.getAttribute("data-menu-group"),
            key: item.getAttribute("data-menu-key"),
          };
          ev.dataTransfer.effectAllowed = "move";
          ev.dataTransfer.setData("application/x-menu-group", menuDragState.group);
          ev.dataTransfer.setData("application/x-menu-key", menuDragState.key);
        });
        handle.addEventListener("dragend", () => {
          menuDragState = null;
          document.querySelectorAll(".menu-item.is-menu-drag-over").forEach((el) => el.classList.remove("is-menu-drag-over"));
        });
      });
      root.querySelectorAll(".menu-item[data-menu-group][data-menu-key]").forEach((item) => {
        if (item.dataset.menuDropBound === "1") return;
        item.dataset.menuDropBound = "1";
        item.addEventListener("dragover", (ev) => {
          const fromKey = menuDragState && menuDragState.key;
          if (fromKey) {
            ev.preventDefault();
            if (ev.dataTransfer) ev.dataTransfer.dropEffect = "move";
            markMenuDropTarget(item, menuDropPosition(item, ev.clientY));
          }
        });
        item.addEventListener("dragleave", () => {
          item.classList.remove("is-menu-drag-over", "is-menu-drop-after");
        });
        item.addEventListener("drop", (ev) => {
          const fromKey = (menuDragState && menuDragState.key) || (ev.dataTransfer && ev.dataTransfer.getData("application/x-menu-key"));
          const toGroup = item.getAttribute("data-menu-group");
          const position = menuDropPosition(item, ev.clientY);
          item.classList.remove("is-menu-drag-over", "is-menu-drop-after");
          menuDragState = null;
          if (!fromKey || !toGroup) return;
          ev.preventDefault();
          moveMenuItem(fromKey, toGroup, item.getAttribute("data-menu-key"), position);
        });
        item.addEventListener("contextmenu", (ev) => {
          showMenuContextMenu(ev, item);
        });
      });
    }

    function setConfigView(viewName) {
      document.querySelectorAll(".config-view[data-config-view]").forEach((view) => {
        view.style.display = view.getAttribute("data-config-view") === viewName ? "" : "none";
      });
    }

    async function openConfigChild(viewName) {
      if (!(await resolveUnsavedBeforeLeaving())) return;
      setActivePanel("config");
      setConfigMenuTreeOpen(true);
      setConfigView(viewName);
      document.getElementById("menu-config").classList.remove("active");
      document.getElementById("menu-config-target").classList.toggle("active", viewName === "targets");
      document.getElementById("menu-config-catalog").classList.toggle("active", viewName === "catalog");
      document.getElementById("menu-config-details").classList.toggle("active", viewName === "details");
      if (viewName === "targets") refreshTargetEditor();
      if (viewName === "catalog") refreshNutritionCatalog();
      if (viewName === "details") refreshDetailSettings();
    }

    function setMaintStatus(message) {
      const status = document.getElementById("maint-status");
      if (status) status.textContent = message || "";
    }

    function showMaintError(message) {
      const err = document.getElementById("maint-err");
      if (!err) return;
      err.textContent = message || "";
      err.style.display = message ? "block" : "none";
    }

    function renderMaintMenu() {
      const box = document.getElementById("maint-menu-children");
      if (!box) return;
      const byKey = new Map((maintSheets || []).map((sheet) => [sheet.sheet_key, sheet]));
      const preferredByKey = {};
      for (const sheet of (maintSheets || [])) {
        if (!sheet || !sheet.sheet_key) continue;
        let btn = document.querySelector(`.menu-item[data-maint-sheet-key="${CSS.escape(sheet.sheet_key)}"]`)
          || document.querySelector(`.menu-item[data-menu-key="${CSS.escape(sheet.sheet_key)}"]`);
        if (!btn) {
          btn = document.createElement("button");
          btn.type = "button";
          btn.className = "menu-item";
          btn.innerHTML = `<span class="menu-drag-handle" draggable="true" title="Drag to reorder" aria-hidden="true"></span><span class="menu-item-label"></span>`;
          box.appendChild(btn);
        }
        btn.classList.remove("menu-custom-item");
        btn.removeAttribute("data-menu-custom");
        btn.setAttribute("data-maint-sheet-key", sheet.sheet_key);
        btn.setAttribute("data-menu-key", sheet.sheet_key);
        preferredByKey[sheet.sheet_key] = btn;
        btn.querySelector(".menu-item-label").textContent = menuLabel(sheet.sheet_key);
      }
      removeDuplicateMenuNodes(preferredByKey);
      document.querySelectorAll("[data-maint-sheet-key]").forEach((btn) => {
        const key = btn.getAttribute("data-maint-sheet-key");
        if (key && !byKey.has(key)) btn.remove();
      });
      document.querySelectorAll("[data-maint-sheet-key]").forEach((btn) => {
        if (btn.dataset.maintClickBound === "1") return;
        btn.dataset.maintClickBound = "1";
        btn.addEventListener("click", () => openMaintSheet(btn.getAttribute("data-maint-sheet-key")));
      });
      applyMenuOrder();
      attachMenuDragHandles();
      setActivePanel(activePanel, false);
    }

    function maintColumnCount(rows) {
      const n = (rows || []).reduce((max, row) => Math.max(max, Array.isArray(row) ? row.length : 0), 0);
      return Math.max(1, n);
    }

    function formColumnWidthPx(key, fallback = 120) {
      const saved = Number(formColumnWidths[key]);
      if (Number.isFinite(saved)) return saved;
      return fallback;
    }

    function autoResizeTextarea(el) {
      if (!el || el.tagName !== "TEXTAREA") return;
      if (el.offsetParent === null) return; // Skip if hidden (e.g., filtered out)
      const cell = el.closest("td");
      if (cell) {
        const style = getComputedStyle(cell);
        const padX = parseFloat(style.paddingLeft || "0") + parseFloat(style.paddingRight || "0");
        el.style.width = `${Math.max(0, cell.clientWidth - padX)}px`;
      }
      el.style.height = "0px";
      el.style.height = `${el.scrollHeight}px`;
    }

    function autoResizeTextareas(root = document) {
      root.querySelectorAll("textarea[data-auto-row-height]").forEach(autoResizeTextarea);
    }

    function applyFormColumnWidths(root = document) {
      root.querySelectorAll("col[data-form-col-key]").forEach((col) => {
        const key = col.getAttribute("data-form-col-key");
        const fallback = Number(col.getAttribute("data-form-col-default")) || 120;
        col.style.width = `${formColumnWidthPx(key, fallback)}px`;
      });
      root.querySelectorAll("table[data-form-table]").forEach((table) => {
        let total = 0;
        table.querySelectorAll("col[data-form-col-key]").forEach((col) => {
          const key = col.getAttribute("data-form-col-key");
          const fallback = Number(col.getAttribute("data-form-col-default")) || 120;
          total += formColumnWidthPx(key, fallback);
        });
        if (total > 0) table.style.width = `${total}px`;
      });
    }

    function formOffsetPx(key) {
      const saved = Number(formColumnWidths[key]);
      return Number.isFinite(saved) ? saved : 0;
    }

    function applyTableOffsets(root = document) {
      const targets = [
        ["#target-editor", "table_offset_target"],
        ["#catalog-editor table.catalog-table", "table_offset_catalog"],
        [".detail-editor", "table_offset_detail"],
        ["#detail-code-definitions table.detail-code-table", "table_offset_detail_codes"],
        ["#maint-editor table.maint-table", "table_offset_maint_sheet"],
        ["#maint-editor table.maint-roster-table", "table_offset_maint_roster"],
        ["#shopping-out table.shopping-table", "table_offset_shopping"],
        ["#diagnostics-out .diag-report-body", "table_offset_diagnostics"],
      ];
      for (const [selector, key] of targets) {
        document.querySelectorAll(selector).forEach((el) => {
          if (root !== document && !root.contains(el) && el !== root) return;
          el.style.marginLeft = `${formOffsetPx(key)}px`;
        });
      }
      applyRosterReportOffset();
    }

    function attachHorizontalDragHandle(handle, key, applyFn) {
      if (!handle || handle.dataset.horizontalDragBound === "1") return;
      handle.dataset.horizontalDragBound = "1";
      handle.classList.add("table-drag-handle");
      handle.title = handle.title || "Drag left or right to move table";
      handle.addEventListener("mousedown", (ev) => {
        if (ev.button != null && ev.button !== 0) return;
        const interactive = ev.target && ev.target.closest
          ? ev.target.closest("button,input,textarea,select,a,.target-col-resizer,.catalog-col-resizer,.form-col-resizer,.col-resizer,.shop-col-resizer")
          : null;
        if (interactive) return;
        ev.preventDefault();
        const startX = ev.clientX;
        const startOffset = formOffsetPx(key);
        const onMove = (mv) => {
          formColumnWidths[key] = startOffset + (mv.clientX - startX);
          applyFn();
        };
        const onUp = () => {
          window.removeEventListener("mousemove", onMove);
          window.removeEventListener("mouseup", onUp);
          persistColumnWidths();
        };
        window.addEventListener("mousemove", onMove);
        window.addEventListener("mouseup", onUp);
      });
      handle.addEventListener("dblclick", () => {
        formColumnWidths[key] = 0;
        applyFn();
        persistColumnWidths();
      });
    }

    function attachTableDragHandles(root = document) {
      const configs = [
        ['.config-view[data-config-view="targets"] h2', "table_offset_target"],
        ['.config-view[data-config-view="catalog"] h2', "table_offset_catalog"],
        ['.config-view[data-config-view="details"] h2', "table_offset_detail"],
        ["#maint-editor .maint-sheet-title", "table_offset_maint_sheet"],
        ["#maint-editor .maint-roster-pane:first-child .maint-pane-title", "table_offset_maint_roster"],
        ["#shopping-panel h1", "table_offset_shopping"],
        ["#diagnostics-out .diag-report-title", "table_offset_diagnostics"],
      ];
      for (const [selector, key] of configs) {
        document.querySelectorAll(selector).forEach((handle) => {
          if (root !== document && !root.contains(handle) && handle !== root) return;
          attachHorizontalDragHandle(handle, key, () => applyTableOffsets(root));
        });
      }
    }

    function attachFormColumnResizers(root = document) {
      root.querySelectorAll("th[data-form-col-key], td[data-form-col-key]").forEach((cell) => {
        if (cell.querySelector(".form-col-resizer")) return;
        const key = cell.getAttribute("data-form-col-key");
        const grip = document.createElement("span");
        grip.className = "form-col-resizer";
        grip.title = "Drag to resize column";
        grip.addEventListener("mousedown", (ev) => {
          ev.preventDefault();
          ev.stopPropagation();
          const startX = ev.clientX;
          const startW = cell.getBoundingClientRect().width;
          const onMove = (mv) => {
            formColumnWidths[key] = Math.max(0, startW + (mv.clientX - startX));
            applyFormColumnWidths(root);
            autoResizeTextareas(root);
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

    function bindAutoRowHeight(root = document) {
      root.querySelectorAll("textarea[data-auto-row-height]").forEach((ta) => {
        if (ta.dataset.autoHeightBound !== "1") {
          ta.dataset.autoHeightBound = "1";
          ta.addEventListener("input", () => autoResizeTextarea(ta));
        }
        autoResizeTextarea(ta);
      });
    }

