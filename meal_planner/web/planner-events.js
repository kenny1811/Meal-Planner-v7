
    const DESKTOP_LAN_SERVER = "http://192.168.15.125:8765";
    let rerollNonce = 0;

    document.addEventListener("contextmenu", (ev) => {
      if (!ev.target || !ev.target.closest) return;
      const menuItem = ev.target.closest(".sidebar .menu-item[data-menu-key]");
      if (menuItem && typeof showMenuContextMenu === "function") {
        showMenuContextMenu(ev, menuItem);
        return;
      }
      const customContextMenuArea = ev.target.closest(
        "#maint-editor, #catalog-editor, #detail-code-definitions, #maint-row-menu, #catalog-row-menu, #detail-row-menu"
      );
      if (customContextMenuArea) return;
      const insideApp = ev.target.closest(".app-shell") || ev.target.closest("#menu-context-menu");
      if (!insideApp) return;
      ev.preventDefault();
      ev.stopPropagation();
    }, true);

    document.getElementById("go").addEventListener("click", async () => {
      const err = document.getElementById("err");
      const go = document.getElementById("go");
      err.style.display = "none";
      err.textContent = "";
      const blockedReason = updateGenerateButtonState();
      if (blockedReason) {
        err.textContent = blockedReason;
        err.style.display = "block";
        return;
      }
      generateBusy = true;
      go.disabled = true;
      rerollNonce += 1;
      const body = {
        year: +document.getElementById("year").value,
        month: +document.getElementById("month").value,
        dates_expr: document.getElementById("dates_expr").value.trim(),
        reroll_nonce: rerollNonce,
        fast_mode: document.getElementById("fast_mode").checked,
      };
      try {
        const r = await fetch("/api/preview", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const data = await parseJsonSafe(r);
        if (!r.ok) {
          err.textContent = apiErrorMessage(data, "Generate failed.", r.status);
          err.style.display = "block";
          return;
        }
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
        await saveMemoryPayload();
        renderFromMemory(anchor);
        seedShoppingDateRange();
        playGenerateChime();
        currentFocusedDate = (days[0] && days[0].date) || null;
        updateGenerateButtonState();
      } catch (x) {
        err.textContent = String(x);
        err.style.display = "block";
      } finally {
        generateBusy = false;
        updateGenerateButtonState();
      }
    });

    document.addEventListener("focusin", (ev) => {
      const t = ev.target;
      if (t && t.matches && t.matches("td.editable-content[data-date]")) {
        currentFocusedDate = t.getAttribute("data-date");
        updateGenerateButtonState();
      } else if (t && t.closest && t.closest("#planner-panel .top")) {
        currentFocusedDate = null;
        updateGenerateButtonState();
      }
    });

    document.addEventListener("mousedown", (ev) => {
      const t = ev.target && ev.target.closest ? ev.target.closest("td.editable-content[data-date]") : null;
      if (t) {
        currentFocusedDate = t.getAttribute("data-date");
        updateGenerateButtonState();
      } else if (ev.target && ev.target.closest && ev.target.closest("#planner-panel .top")) {
        currentFocusedDate = null;
        updateGenerateButtonState();
      }
    });

    ["year", "month", "dates_expr"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.addEventListener("input", () => {
        markPlannerDateInputsTouched();
        updateGenerateButtonState();
      });
      if (el) el.addEventListener("change", () => {
        markPlannerDateInputsTouched();
        updateGenerateButtonState();
      });
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
        const data = await parseJsonSafe(r);
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
    function isCleanMaintBaselineEvent(target) {
      if (!target || !target.closest || !target.closest("#maint-editor") || !target.dataset) return false;
      if (!Object.prototype.hasOwnProperty.call(target.dataset, "maintSavedValue")) return false;
      return String(target.value ?? "") === String(target.dataset.maintSavedValue ?? "");
    }

    document.addEventListener("input", (ev) => {
      const area = editableAreaName(ev.target);
      if (area) {
        if (isCleanMaintBaselineEvent(ev.target)) return;
        if (ev.target && ev.target.dataset) ev.target.dataset.autosaveDirty = "1";
        setUnsavedChanges(area);
      }
    });
    document.addEventListener("change", (ev) => {
      const area = editableAreaName(ev.target);
      if (area) {
        if (isCleanMaintBaselineEvent(ev.target)) return;
        if (ev.target && ev.target.dataset) ev.target.dataset.autosaveDirty = "1";
        setUnsavedChanges(area);
      }
    });
    window.addEventListener("beforeunload", (ev) => {
      if (!unsavedChanges) return;
      ev.preventDefault();
      ev.returnValue = "";
    });

    document.getElementById("menu-planner").addEventListener("click", async () => {
      if (await resolveUnsavedBeforeLeaving()) {
        const anchor = captureViewportAnchor();
        await loadMemoryPayload();
        renderFromMemory(anchor);
        seedShoppingDateRange();
        setActiveMenuPathForKey("planner");
        setActivePanel("planner");
      }
    });
    document.getElementById("menu-config").addEventListener("click", async () => {
      if (!(await resolveUnsavedBeforeLeaving())) return;
      const tree = document.getElementById("config-menu-tree");
      const wasOpen = !!(tree && tree.classList.contains("is-open"));
      if (wasOpen) {
        setConfigMenuTreeOpen(false);
        activeMenuPath = ["top", "config"];
        persistActiveMenuPathState();
        setActivePanel("config");
        return;
      }
      setConfigMenuTreeOpen(true);
      activeMenuPath = ["top", "config"];
      persistActiveMenuPathState();
      setActivePanel("config");
      await applyActiveConfigView(true);
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
        activeMenuPath = ["top", "maint"];
        persistActiveMenuPathState();
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
    document.getElementById("menu-reports").addEventListener("click", async () => {
      if (!(await resolveUnsavedBeforeLeaving())) return;
      const tree = document.getElementById("reports-menu-tree");
      const wasOpen = !!(tree && tree.classList.contains("is-open"));
      if (wasOpen) {
        setReportsMenuTreeOpen(false);
        activeMenuPath = ["top", "reports"];
        persistActiveMenuPathState();
        setActivePanel("reports");
        return;
      }
      await openShiftCodeAnalysisReport();
    });
    document.getElementById("menu-report-shift-code-analysis").addEventListener("click", openShiftCodeAnalysisReport);
    document.getElementById("menu-duty-report").addEventListener("click", async () => {
      if (!(await resolveUnsavedBeforeLeaving())) return;
      await openDutyReportPanel();
    });
    document.getElementById("menu-onoffduty").addEventListener("click", async () => {
      if (!(await resolveUnsavedBeforeLeaving())) return;
      await openOnOffDutyPanel();
    });
    document.getElementById("menu-shopping").addEventListener("click", async () => {
      if (!(await resolveUnsavedBeforeLeaving())) return;
      setActiveMenuPathForKey("shopping");
      setActivePanel("shopping");
      seedShoppingDateRange();
      if (!Object.keys(shoppingCatalogByName).length) loadShoppingCatalog();
    });
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
    const maintImport = document.getElementById("maint-import");
    if (maintImport) maintImport.addEventListener("click", importActiveMaintSheet);
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
    document.getElementById("maint-editor").addEventListener("copy", (ev) => {
      const input = ev.target && ev.target.matches && ev.target.matches("#maint-editor [data-maint-row][data-maint-col]") ? ev.target : null;
      if (!input || input.dataset.maintEditing === "1" || !ev.clipboardData) return;
      ev.preventDefault();
      ev.clipboardData.setData("text/plain", maintInputClipboardValue(input));
    });
    document.getElementById("maint-editor").addEventListener("paste", (ev) => {
      const input = ev.target && ev.target.matches && ev.target.matches("#maint-editor [data-maint-row][data-maint-col]") ? ev.target : null;
      if (!input || input.dataset.maintEditing === "1" || !ev.clipboardData) return;
      ev.preventDefault();
      pasteMaintClipboard(input, ev.clipboardData.getData("text/plain"));
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
        if (ev.key === "Escape" || ev.key === "Enter" || ev.key === "ArrowUp" || ev.key === "ArrowDown") {
          ev.preventDefault();
          const next = ev.key === "Enter"
            ? catalogCellInputFrom(input, 0, 1)
            : (ev.key === "ArrowUp" || ev.key === "ArrowDown" ? catalogCellInputFrom(input, ev.key === "ArrowUp" ? -1 : 1, 0) : null);
          if (next && input.dataset) input.dataset.skipAutosaveOnce = "1";
          endCatalogCellEdit(input, { cancel: ev.key === "Escape" });
          focusCatalogCell(next || input);
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
      if (ev.key === "Process" && !ev.ctrlKey && !ev.altKey && !ev.metaKey) {
        beginCatalogCellEdit(input, true);
        return;
      }
      if (ev.key.length === 1 && !ev.ctrlKey && !ev.altKey && !ev.metaKey) {
        beginCatalogCellEdit(input, true);
      }
    });
    document.getElementById("catalog-editor").addEventListener("dblclick", (ev) => {
      const input = ev.target && ev.target.matches && ev.target.matches("input.catalog-cell-input") ? ev.target : null;
      beginCatalogCellEdit(input);
    });
    document.getElementById("catalog-editor").addEventListener("compositionstart", (ev) => {
      const input = ev.target && ev.target.matches && ev.target.matches("input.catalog-cell-input") ? ev.target : null;
      if (!input) return;
      if (input && input.readOnly) {
        beginCatalogCellEdit(input, true);
      }
      const timer = catalogDirectKeyTimers.get(input);
      if (timer) {
        clearTimeout(timer);
        catalogDirectKeyTimers.delete(input);
      }
      delete input.dataset.catalogPendingDirectKey;
      delete input.dataset.catalogReplaceOnComposition;
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
    document.addEventListener("keydown", async (ev) => {
      if ((ev.ctrlKey || ev.metaKey) && !ev.altKey && String(ev.key).toLowerCase() === "s") {
        ev.preventDefault();
        await saveActiveEditor();
      }
    });
    document.addEventListener("keydown", async (ev) => {
      const isReloadKey = ev.key === "F5"
        || ((ev.ctrlKey || ev.metaKey) && !ev.altKey && String(ev.key).toLowerCase() === "r");
      if (!isReloadKey || !unsavedChanges) return;
      ev.preventDefault();
      if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
      if (await resolveUnsavedBeforeLeaving()) {
        window.location.reload();
      }
    });

    function closePickupLists(except = null) {
      document.querySelectorAll(".pickup-select-menu").forEach((menu) => {
        if (menu !== except) {
          clearPickupActive(menu);
          menu.hidden = true;
        }
      });
      document.querySelectorAll(".pickup-select-button[aria-expanded='true']").forEach((button) => {
        const menu = button.parentElement && button.parentElement.querySelector(".pickup-select-menu");
        if (menu !== except) button.setAttribute("aria-expanded", "false");
      });
    }

    function pickupSelectedText(select) {
      const option = select && select.selectedOptions && select.selectedOptions[0];
      return option ? option.textContent : "";
    }

    function positionPickupMenu(wrapper, button, menu) {
      const rect = button.getBoundingClientRect();
      const width = Math.max(rect.width, 120);
      menu.style.minWidth = `${width}px`;
      const maxHeight = Math.max(120, window.innerHeight - rect.bottom - 10);
      menu.style.maxHeight = `${maxHeight}px`;
      const selected = menu.querySelector(".pickup-select-option.is-selected");
      if (selected) selected.scrollIntoView({ block: "nearest" });
    }

    function pickupFocusableItems(menu) {
      return Array.from(menu?.querySelectorAll(".pickup-select-option:not(:disabled)") || []);
    }

    function clearPickupActive(menu) {
      if (!menu) return;
      menu.classList.remove("has-active");
      menu.querySelectorAll(".pickup-select-option.is-active").forEach((item) => {
        item.classList.remove("is-active");
        item.setAttribute("aria-selected", item.classList.contains("is-selected") ? "true" : "false");
      });
    }

    function focusPickupItem(item) {
      if (!item) return;
      const menu = item.closest(".pickup-select-menu");
      clearPickupActive(menu);
      item.classList.add("is-active");
      item.setAttribute("aria-selected", "true");
      if (menu) menu.classList.add("has-active");
      item.focus({ preventScroll: true });
      item.scrollIntoView({ block: "nearest" });
    }

    function pickupSelectedItemPosition(select, items) {
      const selectedIdx = Array.from(select.options || []).findIndex((option) => option.selected && !option.disabled);
      return items.findIndex((item) => Number(item.dataset.pickupIndex) === selectedIdx);
    }

    function openPickupList(select, wrapper, button, menu) {
      syncPickupList(select);
      menu.hidden = false;
      button.setAttribute("aria-expanded", "true");
      positionPickupMenu(wrapper, button, menu);
      const items = pickupFocusableItems(menu);
      const selectedPos = pickupSelectedItemPosition(select, items);
      focusPickupItem(items[selectedPos] || items[0]);
    }

    function repositionOpenPickupLists() {
      document.querySelectorAll(".pickup-select-menu:not([hidden])").forEach((menu) => {
        const wrapper = menu.closest(".pickup-select");
        const button = wrapper && wrapper.querySelector(".pickup-select-button");
        if (!wrapper || !button) return;
        positionPickupMenu(wrapper, button, menu);
      });
    }

    function schedulePickupListReposition() {
      if (window.__pickupListRepositionPending) return;
      window.__pickupListRepositionPending = true;
      window.requestAnimationFrame(() => {
        window.__pickupListRepositionPending = false;
        repositionOpenPickupLists();
      });
    }

    function syncPickupList(select) {
      if (!select || select.tagName !== "SELECT") return;
      const wrapper = select.closest(".pickup-select");
      if (!wrapper) return;
      const button = wrapper.querySelector(".pickup-select-button");
      const menu = wrapper.querySelector(".pickup-select-menu");
      if (!button || !menu) return;
      button.textContent = pickupSelectedText(select);
      menu.innerHTML = "";
      Array.from(select.options || []).forEach((option, idx) => {
        const item = document.createElement("button");
        item.type = "button";
        item.className = "pickup-select-option";
        item.textContent = option.textContent || "";
        item.disabled = !!option.disabled;
        item.dataset.pickupValue = option.value;
        item.dataset.pickupIndex = String(idx);
        item.classList.toggle("is-selected", option.selected);
        item.setAttribute("role", "option");
        item.setAttribute("aria-selected", option.selected ? "true" : "false");
        item.addEventListener("click", () => {
          if (item.disabled) return;
          const oldValue = select.value;
          select.selectedIndex = idx;
          syncPickupList(select);
          closePickupLists();
          select.dispatchEvent(new MouseEvent("click", { bubbles: true }));
          if (select.value !== oldValue) {
            select.dispatchEvent(new Event("input", { bubbles: true }));
            select.dispatchEvent(new Event("change", { bubbles: true }));
          }
          select.focus({ preventScroll: true });
        });
        menu.appendChild(item);
      });
    }

      function setPickupSelectedIndex(select, idx, { close = false, focusNative = false } = {}) {
      if (!select || select.tagName !== "SELECT") return;
      const option = select.options && select.options[idx];
      if (!option || option.disabled) return;
      const oldValue = select.value;
      select.selectedIndex = idx;
      syncPickupList(select);
      if (close) closePickupLists();
      if (focusNative) select.focus({ preventScroll: true });
      if (select.value === oldValue) return;
      select.dispatchEvent(new Event("input", { bubbles: true }));
      select.dispatchEvent(new Event("change", { bubbles: true }));
    }

    function handlePickupKeydown(select, wrapper, button, menu, ev) {
      if (ev.key === "Escape") {
        ev.preventDefault();
        closePickupLists();
        button.focus({ preventScroll: true });
        return;
      }
      if (ev.key !== "ArrowDown" && ev.key !== "ArrowUp" && ev.key !== "Enter" && ev.key !== " ") return;
      ev.preventDefault();
      if (menu.hidden) openPickupList(select, wrapper, button, menu);
      const items = pickupFocusableItems(menu);
      if (!items.length) return;
      const active = document.activeElement;
      const markedActive = menu.querySelector(".pickup-select-option.is-active");
      const activePos = items.indexOf(markedActive || active);
      if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
        const selectedPos = pickupSelectedItemPosition(select, items);
        const basePos = activePos >= 0 ? activePos : selectedPos;
        const nextItem = ev.key === "ArrowDown"
          ? (items[basePos + 1] || items[0])
          : (items[basePos - 1] || items[items.length - 1]);
        focusPickupItem(nextItem);
        return;
      }
      const selectedItem = activePos >= 0
        ? items[activePos]
        : (menu.querySelector(".pickup-select-option.is-selected") || items[0]);
      setPickupSelectedIndex(select, Number(selectedItem && selectedItem.dataset.pickupIndex), { close: true });
      if (select.id === "target-profile-gender" && typeof moveTargetProfileEnter === "function") {
        moveTargetProfileEnter(select);
      } else {
        button.focus({ preventScroll: true });
      }
    }

    function enhancePickupList(select) {
      if (!select || select.tagName !== "SELECT" || select.multiple || select.dataset.pickupEnhanced === "1") return;
      const wrapper = document.createElement("span");
      wrapper.className = "pickup-select";
      wrapper.dataset.pickupFor = select.id || "";
      ["marginLeft", "marginRight", "marginTop", "marginBottom", "width", "minWidth", "maxWidth"].forEach((name) => {
        if (select.style[name]) wrapper.style[name] = select.style[name];
      });
      if (!wrapper.style.width) {
        const rect = select.getBoundingClientRect();
        if (rect.width > 0) wrapper.style.width = `${rect.width}px`;
      }
      select.parentNode.insertBefore(wrapper, select);
      wrapper.appendChild(select);
      select.dataset.pickupEnhanced = "1";
      select.classList.add("pickup-native");
      select.tabIndex = -1;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "pickup-select-button";
      button.setAttribute("aria-haspopup", "listbox");
      button.setAttribute("aria-expanded", "false");
      const menu = document.createElement("div");
      menu.className = "pickup-select-menu";
      menu.hidden = true;
      menu.setAttribute("role", "listbox");
      wrapper.appendChild(button);
      wrapper.appendChild(menu);
      wrapper.addEventListener("pointerdown", (ev) => ev.stopPropagation());
      wrapper.addEventListener("mousedown", (ev) => ev.stopPropagation());
      wrapper.addEventListener("click", (ev) => ev.stopPropagation());
      button.addEventListener("click", () => {
        const willOpen = menu.hidden;
        closePickupLists(menu);
        if (willOpen) {
          openPickupList(select, wrapper, button, menu);
        } else {
          menu.hidden = true;
          button.setAttribute("aria-expanded", "false");
        }
      });
      button.addEventListener("keydown", (ev) => {
        if (
          select.id === "target-profile-gender"
          && ev.key === "Enter"
          && menu.hidden
          && !ev.shiftKey
          && !ev.ctrlKey
          && !ev.altKey
          && !ev.metaKey
          && !ev.isComposing
        ) {
          ev.preventDefault();
          if (typeof moveTargetProfileEnter === "function") moveTargetProfileEnter(select);
          return;
        }
        handlePickupKeydown(select, wrapper, button, menu, ev);
      });
      menu.addEventListener("keydown", (ev) => handlePickupKeydown(select, wrapper, button, menu, ev));
      select.addEventListener("change", () => syncPickupList(select));
      syncPickupList(select);
    }

    function enhancePickupLists(root = document) {
      if (!root || !root.querySelectorAll) return;
      root.querySelectorAll("select").forEach(enhancePickupList);
    }

    function startPickupListObserver() {
      if (window.__pickupListObserverStarted) return;
      window.__pickupListObserverStarted = true;
      const observer = new MutationObserver((mutations) => {
        for (const mutation of mutations) {
          mutation.addedNodes.forEach((node) => {
            if (!node || node.nodeType !== 1) return;
            if (node.tagName === "SELECT") enhancePickupList(node);
            enhancePickupLists(node);
          });
        }
      });
      observer.observe(document.body, { childList: true, subtree: true });
      document.addEventListener("mousedown", (ev) => {
        if (!ev.target || !ev.target.closest || !ev.target.closest(".pickup-select")) closePickupLists();
      });
      document.addEventListener("keydown", (ev) => {
        if (ev.key === "Escape") closePickupLists();
      });
      window.addEventListener("resize", schedulePickupListReposition);
      window.addEventListener("scroll", schedulePickupListReposition, true);
    }

    (async function bootUi() {
      await loadUiState();
      applyMenuOrder();
      applyMenuTreeOpen();
      attachMenuDragHandles();
      await loadMemoryPayload();
      applyDefaultPlannerDate({ preserveUserInput: true });
      updateGenerateButtonState();
      await loadShoppingCatalog();
      await refreshTargetEditor();
      await refreshNutritionCatalog();
      await refreshDetailSettings();
      await refreshMaintSheets();
      document.getElementById("show_past").checked = !!showPast;
      renderFromMemory(null);
      seedShoppingDateRange();
      applyActiveMenuPathToState();
      setActivePanel(activePanel, false);
      applyActiveMenuPathTree();
      if (activePanel === "config") applyActiveConfigView(false);
      if (activePanel === "maint" && activeMaintSheetKey) {
        try {
          await openMaintSheet(activeMaintSheetKey, false);
        } catch (_) {
          if (maintSheets.length) await openMaintSheet(maintSheets[0].sheet_key, false);
        }
      }
      if (activePanel === "reports") await openShiftCodeAnalysisReport();
      if (activePanel === "duty_report") await refreshDutyReport();
      applyTableOffsets();
      attachTableDragHandles();
      applyFormColumnWidths();
      attachFormColumnResizers();
      applyMenuOrder();
      applyMenuTreeOpen();
      attachMenuDragHandles();
      applySidebarWidth();
      attachSidebarResizer();
      enhancePickupLists(document);
      startPickupListObserver();
      window.addEventListener("resize", syncPanelGutter);
      startTopRightClock();
    })();

    document.addEventListener("focusout", (ev) => {
      const el = ev.target;
      if (!el || (el.tagName !== "INPUT" && el.tagName !== "TEXTAREA" && el.tagName !== "SELECT")) return;
      if (el.dataset) delete el.dataset.skipAutosaveOnce;
    });
