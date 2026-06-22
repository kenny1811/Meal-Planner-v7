/* API and persistence helpers for the meal planner UI. */
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
        const data = await r.json().catch(() => ({}));
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
        if (data && ["planner", "config", "maint", "shopping", "alarm_sync"].includes(data.active_panel)) {
          activePanel = data.active_panel;
        }
        const hasServerConfigView = data && ["targets", "catalog", "details"].includes(data.active_config_view);
        if (hasServerConfigView) {
          activeConfigView = data.active_config_view;
        }
        if (data && Array.isArray(data.active_menu_path) && data.active_menu_path.length) {
          activeMenuPath = data.active_menu_path.map((part) => String(part)).filter(Boolean);
        }
        try {
          const savedMenuPath = String(window.localStorage.getItem("mealplanner_active_menu_path") || "").trim();
          const path = savedMenuPath.split("/").map((part) => part.trim()).filter(Boolean);
          if (path.length) activeMenuPath = path;
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
          menuOrder = {
            top: Array.isArray(data.menu_order.top) ? data.menu_order.top : menuOrder.top,
            config: Array.isArray(data.menu_order.config) ? data.menu_order.config : menuOrder.config,
            maint: Array.isArray(data.menu_order.maint) ? data.menu_order.maint : menuOrder.maint,
          };
        }
        if (data && typeof data.menu_labels === "object" && data.menu_labels) {
          menuLabels = data.menu_labels;
        }
        if (data && Array.isArray(data.menu_hidden_keys)) {
          menuHiddenKeys = data.menu_hidden_keys;
        }
        if (data && typeof data.menu_tree_open === "object" && data.menu_tree_open) {
          menuTreeOpen = {
            config: data.menu_tree_open.config !== false,
            maint: !!data.menu_tree_open.maint,
          };
        }
      } catch (_) {}
    }

    async function persistColumnWidths() {
      try {
        await fetch("/api/ui-state", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
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
          }),
        });
      } catch (_) {}
    }

    async function persistActiveConfigViewState() {
      try {
        await fetch("/api/ui-state", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ active_config_view: activeConfigView }),
        });
      } catch (_) {}
    }

    async function persistActiveMenuPathState() {
      try {
        await fetch("/api/ui-state", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ active_menu_path: activeMenuPath }),
        });
      } catch (_) {}
    }

    async function persistMenuOrder() {
      try {
        if (typeof cleanMenuOrder === "function") cleanMenuOrder();
        await fetch("/api/ui-state", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ menu_order: menuOrder, menu_hidden_keys: menuHiddenKeys }),
        });
      } catch (_) {}
    }

    async function persistMenuLabels() {
      try {
        await fetch("/api/ui-state", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ menu_labels: menuLabels }),
        });
      } catch (_) {}
    }

    async function persistMenuTreeOpen() {
      try {
        await fetch("/api/ui-state", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ menu_tree_open: menuTreeOpen }),
        });
      } catch (_) {}
    }

    async function persistMenuLayout() {
      try {
        if (typeof cleanMenuOrder === "function") cleanMenuOrder();
        await fetch("/api/ui-state", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            menu_order: menuOrder,
            menu_labels: menuLabels,
            menu_hidden_keys: menuHiddenKeys,
            menu_tree_open: menuTreeOpen,
          }),
        });
      } catch (_) {}
    }

    async function loadMemoryPayload() {
      try {
        const r = await fetch("/api/memory-list");
        const data = await r.json().catch(() => ({}));
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
        const data = await r.json().catch(() => ({}));
        if (!r.ok) return;
        const raw = (data && data.by_name) || {};
        shoppingCatalogByName = typeof raw === "object" && raw ? raw : {};
        shoppingRiceConfig = data && typeof data.rice === "object" && data.rice ? data.rice : null;
      } catch (_) {}
    }

    async function loadDetailSettings() {
      const r = await fetch("/api/detail-settings");
      const data = await r.json().catch(() => ({}));
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
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "Save detail settings failed.", r.status));
      }
      return data || {};
    }

    async function loadTargets() {
      const r = await fetch("/api/targets");
      const data = await r.json().catch(() => ({}));
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
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "Save targets failed.", r.status));
      }
      return data || {};
    }

    async function loadNutritionCatalog() {
      const r = await fetch("/api/nutrition-catalog");
      const data = await r.json().catch(() => ({}));
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
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "Save nutrition catalog failed.", r.status));
      }
      return data || {};
    }

    async function loadMaintSheets() {
      const r = await fetch("/api/maint/sheets");
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "Load maintenance sheets failed.", r.status));
      }
      return data || {};
    }

    async function loadMaintSheet(sheetKey) {
      const r = await fetch(`/api/maint/sheets/${encodeURIComponent(sheetKey)}`);
      const data = await r.json().catch(() => ({}));
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
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "Save maintenance sheet failed.", r.status));
      }
      return data || {};
    }

    async function importMaintSheet(sheetKey) {
      const r = await fetch(`/api/maint/sheets/${encodeURIComponent(sheetKey)}/import`, {
        method: "POST",
      });
      const data = await r.json().catch(() => ({}));
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
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "Import schedule_grid XML failed.", r.status));
      }
      return data || {};
    }

    async function importDefaultScheduleGridXml() {
      const r = await fetch("/api/maint/sheets/schedule_grid/import-default-xml", {
        method: "POST",
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "Import schedule_grid.xml failed.", r.status));
      }
      return data || {};
    }

    async function importScheduleGridFromAdbPhone() {
      const r = await fetch("/api/maint/sheets/schedule_grid/preview-from-phone-ip", {
        method: "POST",
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "Preview phone schedule_grid by IP failed.", r.status));
      }
      return data || {};
    }

    async function confirmScheduleGridFromPhoneIp() {
      const r = await fetch("/api/maint/sheets/schedule_grid/confirm-phone-ip-import", {
        method: "POST",
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "Confirm phone schedule_grid import failed.", r.status));
      }
      return data || {};
    }

    async function loadAlarmPlan(dateIso) {
      const params = new URLSearchParams();
      if (dateIso) params.set("date_iso", dateIso);
      const r = await fetch(`/api/alarm-plan${params.toString() ? `?${params}` : ""}`);
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "Load alarm plan failed.", r.status));
      }
      return data || {};
    }

    async function publishAlarmPlan(dateIso, device, autoServer) {
      const params = new URLSearchParams();
      if (dateIso) params.set("date_iso", dateIso);
      if (device) params.set("device", device);
      if (autoServer) params.set("auto_server", autoServer);
      const r = await fetch(`/api/alarm-plan/publish${params.toString() ? `?${params}` : ""}`, {
        method: "POST",
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "Publish alarm plan failed.", r.status));
      }
      return data || {};
    }

    async function sendAlarmPlanUsb(dateIso) {
      const params = new URLSearchParams();
      if (dateIso) params.set("date_iso", dateIso);
      const r = await fetch(`/api/alarm-plan/send-usb${params.toString() ? `?${params}` : ""}`, {
        method: "POST",
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "Send alarm plan by USB failed.", r.status));
      }
      return data || {};
    }

    async function exportScheduleGridXml() {
      const r = await fetch("/api/maint/sheets/schedule_grid/export-xml");
      if (!r.ok) {
        const data = await r.json().catch(() => ({}));
        throw new Error(apiErrorMessage(data, "Export schedule_grid XML failed.", r.status));
      }
      return r;
    }

    async function exportScheduleGridXmlToDataFolder() {
      const r = await fetch("/api/maint/sheets/schedule_grid/export-xml-to-file", {
        method: "POST",
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "Export schedule_grid XML to data folder failed.", r.status));
      }
      return data || {};
    }
