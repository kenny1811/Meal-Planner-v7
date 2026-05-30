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
        if (data && ["planner", "config", "maint", "shopping", "diagnostics"].includes(data.active_panel)) {
          activePanel = data.active_panel;
        }
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
          }),
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

    async function loadCutoffInline() {
      try {
        const r = await fetch("/api/cutoff");
        const data = await r.json().catch(() => ({}));
        if (!r.ok) return;
        const cutoff = data && data.cutoff ? String(data.cutoff) : "";
        document.getElementById("cutoff").textContent = cutoff
          ? `Cutoff date: ${cutoff} (Hong Kong)`
          : "";
      } catch (_) {}
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

    async function loadDiagnostics() {
      const r = await fetch("/api/diagnostics");
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        throw new Error(apiErrorMessage(data, "Load diagnostics failed.", r.status));
      }
      return data || {};
    }
