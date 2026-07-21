/* API and persistence helpers for the meal planner UI. */
    // 共用：安全解析 JSON response（失敗回退空物件），取代重覆嘅 r.json().catch(() => ({}))。
    async function parseJsonSafe(r) {
      try {
        return await r.json();
      } catch (_) {
        return {};
      }
    }

    function apiErrorMessage(data, fallback, status = null) {
      const envelopeMessage = data && data.error && data.error.message;
      if (envelopeMessage) return String(envelopeMessage);
      if (data && typeof data.detail === "string" && data.detail) return data.detail;
      const detailMessage = data && data.detail && (data.detail.message || data.detail.error);
      if (detailMessage) return String(detailMessage);
      const suffix = status ? ` (HTTP ${status})` : "";
      return `${fallback || "Request failed."}${suffix}`;
    }

    async function loadUiState() {
      try {
        const r = await fetch("/api/ui-state");
        const data = await parseJsonSafe(r);
        if (data && typeof data.column_widths === "object" && data.column_widths) {
          columnWidths = data.column_widths;
        }
        if (data && data.sidebar_width != null) {
          const w = Number(data.sidebar_width);
          if (Number.isFinite(w)) sidebarWidth = w;
        }
        if (data && data.target_editor_width != null) {
          const w = Number(data.target_editor_width);
          if (Number.isFinite(w)) targetEditorWidth = w;
        }
        if (data && typeof data.target_column_widths === "object" && data.target_column_widths) {
          targetColumnWidths = data.target_column_widths;
        }
        if (data && typeof data.catalog_column_widths === "object" && data.catalog_column_widths) {
          catalogColumnWidths = data.catalog_column_widths;
        }
        if (data && typeof data.form_column_widths === "object" && data.form_column_widths) {
          formColumnWidths = data.form_column_widths;
        }
        if (data && typeof data.show_past === "boolean") {
          showPast = data.show_past;
        }
        if (data && ["planner", "config", "maint", "shopping", "reports", "duty_report"].includes(data.active_panel)) {
          activePanel = data.active_panel;
        }
        const hasServerConfigView = data && ["targets", "catalog", "details"].includes(data.active_config_view);
        if (hasServerConfigView) {
          activeConfigView = data.active_config_view;
        }
        if (data && Array.isArray(data.active_menu_path) && data.active_menu_path.length) {
          activeMenuPath = data.active_menu_path.map((part) => String(part)).filter(Boolean);
          if (activeMenuPath.some((part) => typeof isRemovedMenuKey === "function" && isRemovedMenuKey(part))) {
            activeMenuPath = ["top", "planner"];
          }
        }
        try {
          const savedMenuPath = String(window.localStorage.getItem("mealplanner_active_menu_path") || "").trim();
          const path = savedMenuPath.split("/").map((part) => part.trim()).filter(Boolean);
          if (path.length && !path.some((part) => typeof isRemovedMenuKey === "function" && isRemovedMenuKey(part))) {
            activeMenuPath = path;
          }
        } catch (_) {}
        if (!hasServerConfigView) {
          let hasLocalConfigView = false;
          try {
            const savedConfigView = String(window.localStorage.getItem("mealplanner_active_config_view") || "").trim();
            if (["targets", "catalog", "details"].includes(savedConfigView)) {
              activeConfigView = savedConfigView;
              hasLocalConfigView = true;
            }
          } catch (_) {}
          if (!hasLocalConfigView && activePanel === "config") activeConfigView = "catalog";
        }
        try {
          const savedMaintSheet = String(window.localStorage.getItem("mealplanner_active_maint_sheet") || "").trim();
          if (savedMaintSheet) activeMaintSheetKey = savedMaintSheet;
        } catch (_) {}
        if (data && typeof data.menu_order === "object" && data.menu_order) {
          const cleanOrder = (items) => (Array.isArray(items) ? items.filter((key) => !(typeof isRemovedMenuKey === "function" && isRemovedMenuKey(key))) : null);
          menuOrder = {
            top: cleanOrder(data.menu_order.top) || menuOrder.top,
            config: cleanOrder(data.menu_order.config) || menuOrder.config,
            maint: cleanOrder(data.menu_order.maint) || menuOrder.maint,
            reports: cleanOrder(data.menu_order.reports) || menuOrder.reports,
          };
          Object.entries(data.menu_order).forEach(([group, items]) => {
            if (group && !(group in menuOrder)) {
              menuOrder[group] = cleanOrder(items) || [];
            }
          });
        }
        if (data && typeof data.menu_labels === "object" && data.menu_labels) {
          menuLabels = Object.fromEntries(
            Object.entries(data.menu_labels).filter(([key]) => !(typeof isRemovedMenuKey === "function" && isRemovedMenuKey(key)))
          );
        }
        if (data && Array.isArray(data.menu_hidden_keys)) {
          menuHiddenKeys = data.menu_hidden_keys.filter((key) => !(typeof isRemovedMenuKey === "function" && isRemovedMenuKey(key)));
        }
        if (data && typeof data.menu_tree_open === "object" && data.menu_tree_open) {
          menuTreeOpen = {
            config: data.menu_tree_open.config !== false,
            maint: !!data.menu_tree_open.maint,
            reports: !!data.menu_tree_open.reports,
          };
          Object.entries(data.menu_tree_open).forEach(([key, value]) => {
            if (key && !(key in menuTreeOpen)) menuTreeOpen[key] = !!value;
          });
        }
        if (data && typeof data.google_calendar_sync === "object" && data.google_calendar_sync) {
          googleCalendarSync = {
            enabled: !!data.google_calendar_sync.enabled,
            write: !!data.google_calendar_sync.write,
            client_secret_file: String(data.google_calendar_sync.client_secret_file || ""),
            token_file: String(data.google_calendar_sync.token_file || ""),
            service_account_file: String(data.google_calendar_sync.service_account_file || ""),
            nonwork_calendar_id: String(data.google_calendar_sync.nonwork_calendar_id || ""),
          };
        }
      } catch (_) {}
    }

    // 共用：POST 一個 patch 去 /api/ui-state（吞錯誤，與原行為一致）。
    async function persistUiState(patch) {
      try {
        await fetch("/api/ui-state", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(patch),
        });
      } catch (_) {}
    }

    async function persistColumnWidths() {
      await persistUiState({
        column_widths: columnWidths,
        sidebar_width: sidebarWidth,
        target_editor_width: targetEditorWidth,
        target_column_widths: targetColumnWidths,
        catalog_column_widths: catalogColumnWidths,
        form_column_widths: formColumnWidths,
        show_past: showPast,
        active_panel: activePanel,
        active_config_view: activeConfigView,
        active_menu_path: activeMenuPath,
      });
    }

    async function persistActiveConfigViewState() {
      await persistUiState({ active_config_view: activeConfigView });
    }

    async function persistActiveMenuPathState() {
      await persistUiState({ active_menu_path: activeMenuPath });
    }

    async function persistMenuOrder() {
      if (typeof cleanMenuOrder === "function") cleanMenuOrder();
      await persistUiState({ menu_order: menuOrder, menu_hidden_keys: menuHiddenKeys });
    }

    async function persistMenuLabels() {
      await persistUiState({ menu_labels: menuLabels });
    }

    async function persistMenuTreeOpen() {
      await persistUiState({ menu_tree_open: menuTreeOpen });
    }

    async function persistMenuLayout() {
      if (typeof cleanMenuOrder === "function") cleanMenuOrder();
      await persistUiState({
        menu_order: menuOrder,
        menu_labels: menuLabels,
        menu_hidden_keys: menuHiddenKeys,
        menu_tree_open: menuTreeOpen,
      });
    }

    async function persistGoogleCalendarSync() {
      await persistUiState({ google_calendar_sync: googleCalendarSync });
    }

    async function connectGoogleCalendar() {
      const r = await fetch("/api/google-calendar/auth", { method: "POST" });
      const data = await parseJsonSafe(r);
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "Google Calendar login failed.", r.status));
      }
      return data || {};
    }

    async function loadGoogleCalendarAuthStatus() {
      const r = await fetch("/api/google-calendar/auth-status");
      const data = await parseJsonSafe(r);
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "Google Calendar auth status failed.", r.status));
      }
      return data || {};
    }

    async function syncGoogleCalendarRoster() {
      const r = await fetch("/api/google-calendar/roster-sync", { method: "POST" });
      const data = await parseJsonSafe(r);
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "Google Calendar roster sync failed.", r.status));
      }
      return data || {};
    }

    async function loadMemoryPayload() {
      try {
        const r = await fetch("/api/memory-list");
        const data = await parseJsonSafe(r);
        if (!r.ok) return;
        const p = (data && data.payload) || {};
        memoryPayload = {
          headers: Array.isArray(p.headers) ? p.headers : [],
          indicator_rows: p && typeof p.indicator_rows === "object" && p.indicator_rows ? p.indicator_rows : {},
          nutrient_keys: Array.isArray(p.nutrient_keys) ? p.nutrient_keys : [],
          days: Array.isArray(p.days) ? p.days : [],
        };
      } catch (_) {}
    }

    async function saveMemoryPayload() {
      try {
        await fetch("/api/memory-list", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ payload: memoryPayload }),
        });
      } catch (_) {}
    }

    async function loadShoppingCatalog() {
      try {
        const r = await fetch("/api/shopping-catalog");
        const data = await parseJsonSafe(r);
        if (!r.ok) return;
        const raw = (data && data.by_name) || {};
        shoppingCatalogByName = typeof raw === "object" && raw ? raw : {};
        shoppingRiceConfig = data && typeof data.rice === "object" && data.rice ? data.rice : null;
      } catch (_) {}
    }

    async function loadDetailSettings() {
      const r = await fetch("/api/detail-settings");
      const data = await parseJsonSafe(r);
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "Load detail settings failed.", r.status));
      }
      return data || {};
    }

    async function persistDetailSettings(payload) {
      const r = await fetch("/api/detail-settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload || {}),
      });
      const data = await parseJsonSafe(r);
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "Save detail settings failed.", r.status));
      }
      return data || {};
    }

    async function loadTargets() {
      const r = await fetch("/api/targets");
      const data = await parseJsonSafe(r);
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "Load targets failed.", r.status));
      }
      return data || {};
    }

    async function persistTargets(payload) {
      const r = await fetch("/api/targets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload || {}),
      });
      const data = await parseJsonSafe(r);
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "Save targets failed.", r.status));
      }
      return data || {};
    }

    async function loadNutritionCatalog() {
      const r = await fetch("/api/nutrition-catalog");
      const data = await parseJsonSafe(r);
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "Load nutrition catalog failed.", r.status));
      }
      return data || {};
    }

    async function persistNutritionCatalog(payload) {
      const r = await fetch("/api/nutrition-catalog", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload || {}),
      });
      const data = await parseJsonSafe(r);
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "Save nutrition catalog failed.", r.status));
      }
      return data || {};
    }

    async function loadMaintSheets() {
      const r = await fetch("/api/maint/sheets");
      const data = await parseJsonSafe(r);
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "Load maintenance sheets failed.", r.status));
      }
      return data || {};
    }

    async function loadMaintSheet(sheetKey) {
      const r = await fetch(`/api/maint/sheets/${encodeURIComponent(sheetKey)}`);
      const data = await parseJsonSafe(r);
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "Load maintenance sheet failed.", r.status));
      }
      return data || {};
    }

    async function persistMaintSheet(sheetKey, rows) {
      const r = await fetch(`/api/maint/sheets/${encodeURIComponent(sheetKey)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rows: rows || [] }),
      });
      const data = await parseJsonSafe(r);
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "Save maintenance sheet failed.", r.status));
      }
      return data || {};
    }

    async function checkRosterLine(text) {
      return checkRosterCodes({ text: String(text || "") });
    }

    async function checkRosterRows(rows) {
      return checkRosterCodes({ rows: rows || [] });
    }

    async function checkRosterCodes(payload) {
      const r = await fetch("/api/maint/roster/check-line", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await parseJsonSafe(r);
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "Check roster line failed.", r.status));
      }
      return data || {};
    }

    async function loadDutyReportPlan(dateIso) {
      const url = dateIso ? `/api/duty-report/plan?date_iso=${encodeURIComponent(dateIso)}` : "/api/duty-report/plan";
      const r = await fetch(url);
      const data = await parseJsonSafe(r);
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "Load duty report plan failed.", r.status));
      }
      return data || {};
    }

    async function loadOnOffDutyPlan(dateIso) {
      const url = dateIso ? `/api/onoffduty/plan?date_iso=${encodeURIComponent(dateIso)}` : "/api/onoffduty/plan";
      const r = await fetch(url);
      const data = await parseJsonSafe(r);
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "Load OnOffDuty plan failed.", r.status));
      }
      return data || {};
    }

    async function postOnOffDutyLog(kind, dateIso, status) {
      const r = await fetch("/api/onoffduty/log", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind, status: status || "opened", source: "web", date_iso: dateIso || null }),
      });
      const data = await parseJsonSafe(r);
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "OnOffDuty log failed.", r.status));
      }
      return data || {};
    }

    async function postOnOffDutyLateOff(action, note) {
      const r = await fetch("/api/onoffduty/lateoff", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, note: note || "" }),
      });
      const data = await parseJsonSafe(r);
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "OnOffDuty late-off failed.", r.status));
      }
      return data || {};
    }

    async function postOnOffDutyConfig(payload) {
      const r = await fetch("/api/onoffduty/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload || {}),
      });
      const data = await parseJsonSafe(r);
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "OnOffDuty config failed.", r.status));
      }
      return data || {};
    }

    async function postDutyReportOverride(payload) {
      const r = await fetch("/api/duty-report/override", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload || {}),
      });
      const data = await parseJsonSafe(r);
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "Duty report override failed.", r.status));
      }
      return data || {};
    }

    async function postDutyReportSend(slotId, dateIso) {
      const r = await fetch("/api/duty-report/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slot_id: slotId, source: "web", date_iso: dateIso || null }),
      });
      const data = await parseJsonSafe(r);
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "Duty report send failed.", r.status));
      }
      return data || {};
    }

    async function postDutyReportConfig(payload) {
      const r = await fetch("/api/duty-report/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload || {}),
      });
      const data = await parseJsonSafe(r);
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "Duty report config failed.", r.status));
      }
      return data || {};
    }

    async function importMaintSheet(sheetKey) {
      const r = await fetch(`/api/maint/sheets/${encodeURIComponent(sheetKey)}/import`, {
        method: "POST",
      });
      const data = await parseJsonSafe(r);
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "Import maintenance sheet failed.", r.status));
      }
      return data || {};
    }

    async function importScheduleGridXml(file) {
      const form = new FormData();
      form.append("file", file);
      const r = await fetch("/api/maint/sheets/schedule_grid/import-xml", {
        method: "POST",
        body: form,
      });
      const data = await parseJsonSafe(r);
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "Import schedule_grid XML failed.", r.status));
      }
      return data || {};
    }

    async function importDefaultScheduleGridXml() {
      const r = await fetch("/api/maint/sheets/schedule_grid/import-default-xml", {
        method: "POST",
      });
      const data = await parseJsonSafe(r);
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "Import schedule_grid.xml failed.", r.status));
      }
      return data || {};
    }

    async function importScheduleGridFromAdbPhone() {
      const r = await fetch("/api/maint/sheets/schedule_grid/preview-from-phone-ip", {
        method: "POST",
      });
      const data = await parseJsonSafe(r);
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "Preview phone schedule_grid by IP failed.", r.status));
      }
      return data || {};
    }

    async function confirmScheduleGridFromPhoneIp() {
      const r = await fetch("/api/maint/sheets/schedule_grid/confirm-phone-ip-import", {
        method: "POST",
      });
      const data = await parseJsonSafe(r);
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "Confirm phone schedule_grid import failed.", r.status));
      }
      return data || {};
    }

    async function exportScheduleGridXml() {
      const r = await fetch("/api/maint/sheets/schedule_grid/export-xml");
      if (!r.ok) {
        const data = await parseJsonSafe(r);
        throw new Error(apiErrorMessage(data, "Export schedule_grid XML failed.", r.status));
      }
      return r;
    }

    async function exportScheduleGridXmlToDataFolder() {
      const r = await fetch("/api/maint/sheets/schedule_grid/export-xml-to-file", {
        method: "POST",
      });
      const data = await parseJsonSafe(r);
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "Export schedule_grid XML to data folder failed.", r.status));
      }
      return data || {};
    }
