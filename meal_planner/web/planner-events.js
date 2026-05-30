
    let rerollNonce = 0;

    document.getElementById("go").addEventListener("click", async () => {
      const err = document.getElementById("err");
      const go = document.getElementById("go");
      err.style.display = "none";
      err.textContent = "";
      go.disabled = true;
      rerollNonce += 1;
      const body = {
        year: +document.getElementById("year").value,
        month: +document.getElementById("month").value,
        dates_expr: document.getElementById("dates_expr").value.trim(),
        skip_date_validation: document.getElementById("skip").checked,
        reroll_nonce: rerollNonce,
        fast_mode: document.getElementById("fast_mode").checked,
      };
      try {
        const r = await fetch("/api/preview", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) {
          err.textContent = apiErrorMessage(data, "Generate failed.", r.status);
          err.style.display = "block";
          return;
        }
        document.getElementById("cutoff").textContent = data.cutoff
          ? "Cutoff date: " + data.cutoff + " (Hong Kong)"
          : "";
        const headers = data.headers || [];
        const indicatorRows = data.indicator_rows || {};
        const nutrientKeys = data.nutrient_keys || [];
        const days = data.days || [];
        stampDays(days);
        lastData = data;
        const anchor = captureViewportAnchor();
        memoryPayload.headers = headers;
        memoryPayload.indicator_rows = indicatorRows;
        memoryPayload.nutrient_keys = nutrientKeys;
        memoryPayload.days = mergeDaysByDate(memoryPayload.days || [], days);
        renderFromMemory(anchor);
        seedShoppingDateRange();
        await saveMemoryPayload();
        playGenerateChime();
        currentFocusedDate = (days[0] && days[0].date) || null;
      } catch (x) {
        err.textContent = String(x);
        err.style.display = "block";
      } finally {
        go.disabled = false;
      }
    });

    document.addEventListener("focusin", (ev) => {
      const t = ev.target;
      if (t && t.matches && t.matches("td.editable-content[data-date]")) {
        currentFocusedDate = t.getAttribute("data-date");
      }
    });

    document.addEventListener("mousedown", (ev) => {
      const t = ev.target && ev.target.closest ? ev.target.closest("td.editable-content[data-date]") : null;
      if (t) currentFocusedDate = t.getAttribute("data-date");
    });

    document.getElementById("recalc").addEventListener("click", async () => {
      const err = document.getElementById("err");
      const btn = document.getElementById("recalc");
      err.style.display = "none";
      err.textContent = "";
      if (!memoryPayload || !Array.isArray(memoryPayload.days) || !memoryPayload.days.length) {
        err.textContent = 'Please click "Generate" first.';
        err.style.display = "block";
        return;
      }
      btn.disabled = true;
      try {
        const targetDate = currentDateFromFocusOrViewport() || ((memoryPayload.days || [])[0] && (memoryPayload.days || [])[0].date);
        const srcDay = (memoryPayload.days || []).find((d) => d.date === targetDate);
        if (!srcDay) {
          err.textContent = "Cannot find selected day for recalculation.";
          err.style.display = "block";
          return;
        }
        const beforePanel = document.querySelector(".panel-bottom");
        const prevTop = beforePanel ? beforePanel.scrollTop : 0;
        const prevLeft = beforePanel ? beforePanel.scrollLeft : 0;
        const payloadDays = [srcDay].map((d) => {
          const edited = {};
          for (const meal of MEALS) {
            const sel = `td.editable-content[data-date="${d.date}"][data-meal="${meal}"]`;
            const td = document.querySelector(sel);
            if (!td) continue;
            edited[meal] = (td.textContent || "").trim();
          }
          return {
            date: d.date,
            nutrient_indicators: d.nutrient_indicators || {},
            meal_plan: d.meal_plan || {},
            edited_lines: edited,
          };
        });
        const r = await fetch("/api/recalc", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ days: payloadDays }),
        });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) {
          err.textContent = apiErrorMessage(data, "Recalculation failed.", r.status);
          err.style.display = "block";
          return;
        }
        const byDate = {};
        for (const d of (data.days || [])) {
          if (d && d.meal_plan) d.meal_plan.summary_timestamp = hkTimestamp();
          byDate[d.date] = d.meal_plan;
        }
        for (const d of (memoryPayload.days || [])) {
          if (byDate[d.date]) d.meal_plan = byDate[d.date];
        }
        renderFromMemory(null);
        const afterPanel = document.querySelector(".panel-bottom");
        if (afterPanel) {
          afterPanel.scrollTop = prevTop;
          afterPanel.scrollLeft = prevLeft;
        }
        currentFocusedDate = targetDate;
        await saveMemoryPayload();
      } catch (x) {
        err.textContent = String(x);
        err.style.display = "block";
      } finally {
        btn.disabled = false;
      }
    });

    document.getElementById("show_past").addEventListener("change", async (ev) => {
      showPast = !!ev.target.checked;
      const anchor = captureViewportAnchor();
      renderFromMemory(anchor);
      await persistColumnWidths();
    });
    document.addEventListener("input", (ev) => {
      const area = editableAreaName(ev.target);
      if (area) setUnsavedChanges(area);
    });
    document.addEventListener("change", (ev) => {
      const area = editableAreaName(ev.target);
      if (area) setUnsavedChanges(area);
    });
    window.addEventListener("beforeunload", (ev) => {
      if (!unsavedChanges) return;
      ev.preventDefault();
      ev.returnValue = "";
    });

    document.getElementById("menu-planner").addEventListener("click", async () => {
      if (await resolveUnsavedBeforeLeaving()) setActivePanel("planner");
    });
    document.getElementById("menu-config").addEventListener("click", async () => {
      if (!(await resolveUnsavedBeforeLeaving())) return;
      const tree = document.getElementById("config-menu-tree");
      const wasOpen = !!(tree && tree.classList.contains("is-open"));
      openConfigChild("targets");
      setConfigMenuTreeOpen(!wasOpen);
    });
    document.getElementById("menu-config-target").addEventListener("click", () => openConfigChild("targets"));
    document.getElementById("menu-config-catalog").addEventListener("click", () => openConfigChild("catalog"));
    document.getElementById("menu-config-details").addEventListener("click", () => openConfigChild("details"));
    document.getElementById("menu-maint").addEventListener("click", async () => {
      if (!(await resolveUnsavedBeforeLeaving())) return;
      const tree = document.getElementById("maint-menu-tree");
      const wasOpen = !!(tree && tree.classList.contains("is-open"));
      if (wasOpen) {
        setMaintMenuTreeOpen(false);
        setActivePanel("maint");
        return;
      }
      setMaintMenuTreeOpen(true);
      if (activeMaintSheetKey) {
        openMaintSheet(activeMaintSheetKey);
      } else if (maintSheets.length) {
        openMaintSheet(maintSheets[0].sheet_key);
      } else {
        setActivePanel("maint");
      }
    });
    document.getElementById("menu-shopping").addEventListener("click", async () => {
      if (!(await resolveUnsavedBeforeLeaving())) return;
      setActivePanel("shopping");
      seedShoppingDateRange();
      if (!Object.keys(shoppingCatalogByName).length) loadShoppingCatalog();
    });
    document.getElementById("menu-diagnostics").addEventListener("click", async () => {
      if (!(await resolveUnsavedBeforeLeaving())) return;
      setActivePanel("diagnostics");
      refreshDiagnostics();
    });
    document.getElementById("diagnostics-refresh").addEventListener("click", refreshDiagnostics);
    document.getElementById("shop_start").addEventListener("change", () => {
      shoppingStartWasAuto = false;
      syncDefaultShoppingEnd();
    });
    document.getElementById("shop_end").addEventListener("change", () => {
      shoppingEndWasAuto = false;
    });
    document.getElementById("shop_generate").addEventListener("click", generateShoppingList);
    document.getElementById("target-save").addEventListener("click", () => saveTargetEditor("config"));
    document.getElementById("planner-target-save").addEventListener("click", () => saveTargetEditor("planner"));
    document.getElementById("catalog-save").addEventListener("click", saveNutritionCatalog);
    document.getElementById("detail-save").addEventListener("click", saveDetailSettings);
    document.getElementById("maint-save").addEventListener("click", saveMaintEditor);
    document.getElementById("runtime-import").addEventListener("click", importLiveRuntimeInputs);
    document.getElementById("detail-code-definitions").addEventListener("contextmenu", (ev) => {
      const row = ev.target && ev.target.closest ? ev.target.closest("tr[data-detail-code-row]") : null;
      const idx = row ? Number(row.getAttribute("data-detail-code-row")) : -1;
      showDetailRowMenu(ev, Number.isInteger(idx) ? idx : -1);
    });
    document.getElementById("detail-row-menu").addEventListener("click", (ev) => {
      const action = ev.target && ev.target.closest ? ev.target.closest("[data-detail-row-action]") : null;
      const menu = document.getElementById("detail-row-menu");
      if (!action || !menu) return;
      const idx = Number(menu.getAttribute("data-detail-row-index"));
      hideDetailRowMenu();
      applyDetailRowAction(action.getAttribute("data-detail-row-action"), Number.isInteger(idx) ? idx : -1);
    });
    document.getElementById("maint-row-menu").addEventListener("click", (ev) => {
      const action = ev.target && ev.target.closest ? ev.target.closest("[data-maint-row-action]") : null;
      const menu = document.getElementById("maint-row-menu");
      if (!action || !menu) return;
      const idx = Number(menu.getAttribute("data-maint-row-index"));
      hideMaintRowMenu();
      applyMaintRowAction(action.getAttribute("data-maint-row-action"), Number.isInteger(idx) ? idx : -1);
    });
    document.getElementById("catalog-filter").addEventListener("input", applyCatalogFilter);
    document.getElementById("catalog-editor").addEventListener("focusin", (ev) => {
      const row = ev.target && ev.target.closest ? ev.target.closest("tr[data-catalog-index]") : null;
      const idx = row ? Number(row.getAttribute("data-catalog-index")) : NaN;
      if (Number.isInteger(idx) && idx >= 0) catalogCursorRowIndex = idx;
    });
    document.getElementById("catalog-editor").addEventListener("focusout", (ev) => {
      if (ev.target && ev.target.matches && ev.target.matches("input.catalog-cell-input")) {
        endCatalogCellEdit(ev.target);
      }
    });
    document.getElementById("catalog-editor").addEventListener("keydown", (ev) => {
      const input = ev.target && ev.target.matches && ev.target.matches("#catalog-editor td input") ? ev.target : null;
      if (!input) return;
      if (input.type === "checkbox") {
        if (moveCatalogActiveCell(input, ev.key)) ev.preventDefault();
        return;
      }
      if (input.dataset.catalogEditing === "1") {
        if (ev.key === "Escape" || ev.key === "Enter") {
          ev.preventDefault();
          endCatalogCellEdit(input);
          input.focus();
        }
        return;
      }
      if (moveCatalogActiveCell(input, ev.key)) {
        ev.preventDefault();
        return;
      }
      if (ev.key === "F2") {
        ev.preventDefault();
        beginCatalogCellEdit(input);
        return;
      }
      if ((ev.key.length === 1 || ev.key === "Process") && !ev.ctrlKey && !ev.altKey && !ev.metaKey) {
        beginCatalogCellEdit(input, true);
      }
    });
    document.getElementById("catalog-editor").addEventListener("dblclick", (ev) => {
      const input = ev.target && ev.target.matches && ev.target.matches("input.catalog-cell-input") ? ev.target : null;
      beginCatalogCellEdit(input);
    });
    document.getElementById("catalog-editor").addEventListener("compositionstart", (ev) => {
      const input = ev.target && ev.target.matches && ev.target.matches("input.catalog-cell-input") ? ev.target : null;
      if (input && input.readOnly) beginCatalogCellEdit(input, true);
    });
    document.getElementById("catalog-editor").addEventListener("copy", (ev) => {
      const input = ev.target && ev.target.matches && ev.target.matches("#catalog-editor td input") ? ev.target : null;
      if (!input || input.dataset.catalogEditing === "1" || !ev.clipboardData) return;
      ev.preventDefault();
      ev.clipboardData.setData("text/plain", catalogInputClipboardValue(input));
    });
    document.getElementById("catalog-editor").addEventListener("paste", (ev) => {
      const input = ev.target && ev.target.matches && ev.target.matches("#catalog-editor td input") ? ev.target : null;
      if (!input || input.dataset.catalogEditing === "1" || !ev.clipboardData) return;
      ev.preventDefault();
      pasteCatalogClipboard(input, ev.clipboardData.getData("text/plain"));
    });
    document.getElementById("catalog-editor").addEventListener("contextmenu", (ev) => {
      const row = ev.target && ev.target.closest ? ev.target.closest("tr[data-catalog-index]") : null;
      const idx = row ? Number(row.getAttribute("data-catalog-index")) : NaN;
      if (!Number.isInteger(idx) || idx < 0) return;
      ev.preventDefault();
      showCatalogRowMenu(ev, idx);
    });
    document.getElementById("catalog-row-menu").addEventListener("click", (ev) => {
      const action = ev.target && ev.target.closest ? ev.target.closest("[data-catalog-row-action]") : null;
      const menu = document.getElementById("catalog-row-menu");
      const idx = Number(menu && menu.getAttribute("data-catalog-index"));
      if (!action || !Number.isInteger(idx) || idx < 0) return;
      catalogCursorRowIndex = idx;
      hideCatalogRowMenu();
      if (action.getAttribute("data-catalog-row-action") === "insert") {
        insertNutritionCatalogRow();
      } else if (action.getAttribute("data-catalog-row-action") === "delete") {
        removeNutritionCatalogRow(idx);
      }
    });
    document.addEventListener("mousedown", (ev) => {
      if (!ev.target || !ev.target.closest || !ev.target.closest("#catalog-row-menu")) hideCatalogRowMenu();
      if (!ev.target || !ev.target.closest || !ev.target.closest("#maint-row-menu")) hideMaintRowMenu();
      if (!ev.target || !ev.target.closest || !ev.target.closest("#detail-row-menu")) hideDetailRowMenu();
    });
    document.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape") hideCatalogRowMenu();
      if (ev.key === "Escape") hideMaintRowMenu();
      if (ev.key === "Escape") hideDetailRowMenu();
    });
    document.getElementById("catalog-editor").addEventListener("scroll", hideCatalogRowMenu);
    document.getElementById("maint-editor").addEventListener("scroll", hideMaintRowMenu);
    document.querySelector(".detail-editor")?.addEventListener("scroll", hideDetailRowMenu);
    document.addEventListener("keydown", (ev) => {
      if ((ev.ctrlKey || ev.metaKey) && !ev.altKey && String(ev.key).toLowerCase() === "s") {
        ev.preventDefault();
        saveActiveEditor();
      }
    });

    (async function bootUi() {
      await loadUiState();
      applyMenuOrder();
      applyMenuTreeOpen();
      attachMenuDragHandles();
      await loadMemoryPayload();
      await loadShoppingCatalog();
      await refreshTargetEditor();
      await refreshNutritionCatalog();
      await refreshDetailSettings();
      await refreshMaintSheets();
      await loadCutoffInline();
      document.getElementById("show_past").checked = !!showPast;
      renderFromMemory(null);
      seedShoppingDateRange();
      setActivePanel(activePanel, false);
      if (activePanel === "maint" && activeMaintSheetKey) await openMaintSheet(activeMaintSheetKey, false);
      if (activePanel === "diagnostics") await refreshDiagnostics();
      applyTableOffsets();
      attachTableDragHandles();
      applyMenuOrder();
      applyMenuTreeOpen();
      attachMenuDragHandles();
      applySidebarWidth();
      attachSidebarResizer();
      window.addEventListener("resize", syncPanelGutter);
      startTopRightClock();
    })();

    // Auto format 4-digit time and Auto-save
    let globalAutoSaveTimer = null;
    document.addEventListener("focusout", (ev) => {
      const el = ev.target;
      if (!el || (el.tagName !== "INPUT" && el.tagName !== "TEXTAREA" && el.tagName !== "SELECT")) return;

      // 1. Auto format 4 digits to hh:mm
      if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") {
        const val = el.value.trim();
        if (/^\d{4}$/.test(val)) {
          const h = Number(val.slice(0, 2));
          const m = Number(val.slice(2, 4));
          if (h >= 0 && h <= 23 && m >= 0 && m <= 59) {
            el.value = `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
            el.dispatchEvent(new Event("input", { bubbles: true }));
          }
        }
      }

      // 2. Auto save
      if (el.closest("#maint-editor, #target-editor, #catalog-editor, .detail-editor, .target-editor-host")) {
        clearTimeout(globalAutoSaveTimer);
        globalAutoSaveTimer = setTimeout(() => {
          if (typeof saveActiveEditor === "function") saveActiveEditor();
        }, 500);
      } else if (el.closest("#planner-out")) {
        clearTimeout(globalAutoSaveTimer);
        globalAutoSaveTimer = setTimeout(() => {
          if (typeof saveMemoryPayload === "function") saveMemoryPayload();
        }, 500);
      }
    });
