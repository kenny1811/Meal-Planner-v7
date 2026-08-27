
    let rerollNonce = 0;

    document.addEventListener("contextmenu", (ev) => {
      if (!ev.target || !ev.target.closest) return;
      const menuItem = ev.target.closest(".sidebar .menu-item[data-menu-key]");
      if (menuItem && typeof showMenuContextMenu === "function") {
        showMenuContextMenu(ev, menuItem);
        return;
      }
      const mealCell = ev.target.closest("td.editable-content[data-date][data-meal]");
      if (mealCell) {
        ev.preventDefault();
        ev.stopPropagation();
        showOosMenu(ev, mealCell);
        return;
      }
      const customContextMenuArea = ev.target.closest(
        "#maint-editor, #catalog-editor, #detail-code-definitions, #detail-post-mapping, #detail-rice-conversions, #maint-row-menu, #catalog-row-menu, #detail-row-menu, #detail-post-row-menu, #detail-rice-row-menu, #oos-menu"
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
        playGenerateChime();
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

    // ---- 冇貨標記 + partial-day re-solve（右 click 餐格）----
    // 唔理時間：right click 邊餐就由嗰餐起重算，之前嘅餐鎖住原封不動。
    // （後端會自動略過該日冇顯示嘅餐名。）
    function lockedMealsBefore(meal) {
      const idx = MEALS.indexOf(meal);
      return idx > 0 ? MEALS.slice(0, idx) : [];
    }

    // 前一日最後一餐（通常係晚餐）：過咗 24:00 先食，喺用戶嚟講仲未食，所以照准。
    function isYesterdayLastMeal(dateIso, meal, mealPlan) {
      const yesterday = isoFromYmd(ymdAddDays(ymdNow(), -1));
      if (String(dateIso) !== yesterday || !meal) return false;
      const resolved = (mealPlan && mealPlan.meal_times_resolved) || {};
      const visible = MEALS.filter((m) => String(resolved[m] == null ? "" : resolved[m]).trim() !== "");
      return visible.length > 0 && meal === visible[visible.length - 1];
    }

    function hideOosMenu() {
      const menu = document.getElementById("oos-menu");
      if (menu) menu.remove();
      hideSwapPicker();
    }

    function oosMenuNote(menu, text) {
      const note = document.createElement("div");
      note.className = "oos-menu-title";
      note.textContent = text;
      menu.appendChild(note);
    }

    // 指定食材：{item_index: {row, name}}。每次開 menu 重新嚟過，唔會跨餐殘留。
    let pendingSwaps = {};
    let itemCandidatesCache = null;

    async function loadItemCandidates() {
      if (itemCandidatesCache) return itemCandidatesCache;
      const r = await fetch("/api/item-candidates");
      const data = await parseJsonSafe(r);
      if (!r.ok) throw new Error(apiErrorMessage(data, "Load item candidates failed.", r.status));
      itemCandidatesCache = (data && data.meals) || {};
      return itemCandidatesCache;
    }

    function hideSwapPicker() {
      const el = document.getElementById("oos-swap-picker");
      if (el) el.remove();
    }

    function placeMenu(menu, x, y) {
      const pad = 6;
      const left = Math.min(x, window.innerWidth - menu.offsetWidth - pad);
      const top = Math.min(y, window.innerHeight - menu.offsetHeight - pad);
      menu.style.left = `${Math.max(pad, left)}px`;
      menu.style.top = `${Math.max(pad, top)}px`;
    }

    // 撳「Swap」入面一格 → 彈出嗰格揀得嘅食材。後端 candidate 已經同 solver 同一條路，
    // 所以缺貨（暫停）嗰啲根本唔會出現。
    async function showSwapPicker(anchorBtn, meal, itemIndex, currentRow, onPick, lockedRiceRow) {
      hideSwapPicker();
      let slots;
      try {
        slots = (await loadItemCandidates())[meal] || [];
      } catch (x) {
        const errBox = document.getElementById("err");
        errBox.textContent = String(x);
        errBox.style.display = "block";
        return;
      }
      const slot = slots.find((s) => Number(s.item_index) === Number(itemIndex));
      const picker = document.createElement("div");
      picker.id = "oos-swap-picker";
      picker.className = "catalog-row-menu";
      oosMenuNote(picker, slot ? `${slot.label} →` : "揀食材");
      let choices = ((slot && slot.candidates) || []).filter((c) => Number(c.row) !== Number(currentRow));
      // 一日一米：之前嗰餐（已食、鎖住咗）已經有米就改唔到，所以米格只准揀返同一款。
      if (slot && slot.is_rice && lockedRiceRow != null) {
        choices = choices.filter((c) => Number(c.row) === Number(lockedRiceRow));
      }
      if (!choices.length) {
        oosMenuNote(picker, slot && slot.is_rice && lockedRiceRow != null ? "一日一米：跟已食嗰餐" : "冇其他候選");
      }
      for (const c of choices) {
        const b = document.createElement("button");
        b.type = "button";
        b.textContent = String(c.name || "");
        b.addEventListener("click", () => {
          hideSwapPicker();
          onPick({ row: Number(c.row), name: String(c.name || "") });
        });
        picker.appendChild(b);
      }
      document.body.appendChild(picker);
      const box = anchorBtn.getBoundingClientRect();
      placeMenu(picker, box.right + 2, box.top);
    }

    async function showOosMenu(ev, cell) {
      hideOosMenu();
      pendingSwaps = {};
      const openAt = { x: ev.clientX, y: ev.clientY };
      const dateIso = cell.getAttribute("data-date");
      const meal = cell.getAttribute("data-meal");
      const day = storedMealPlanDay(dateIso);
      const mealPlan = day && day.meal_plan ? day.meal_plan : null;
      if (!mealPlan) return;

      // 過去嘅日子唔可以再郁：嗰啲餐已經食咗，重算只會洗走食過乜嘅記錄。
      // 例外：前一日嘅最後一餐照准——過咗 24:00 先食晚餐，喺你嚟講嗰餐仲未食。
      // 今日同將來完全冇限制，撳邊餐就由嗰餐起重算。
      if (String(dateIso) < isoFromYmd(ymdNow()) && !isYesterdayLastMeal(dateIso, meal, mealPlan)) {
        const menu = document.createElement("div");
        menu.id = "oos-menu";
        menu.className = "catalog-row-menu";
        oosMenuNote(menu, "過去嘅日子唔可以重算");
        oosMenuNote(menu, "（呢日食過乜係記錄，唔好改）");
        document.body.appendChild(menu);
        placeMenu(menu, openAt.x, openAt.y);
        return;
      }

      const items = (mealPlan.meal_items && Array.isArray(mealPlan.meal_items[meal]) ? mealPlan.meal_items[meal] : [])
        .filter((it) => it && it.row != null);

      // 指定食材要跟「而家個 pattern」嘅格位，唔可以用餐單入面嘅位置——舊餐單可能
      // 係用另一個 pattern 生成（例如晚餐有兩款蛋白，格數對唔上），照位置數就會
      // 指錯格（第 2 個 item 係雞胸肉，但 pattern 第 2 格其實係蔬菜）。
      let slots = [];
      try {
        slots = (await loadItemCandidates())[meal] || [];
      } catch (_) {
        slots = [];
      }

      // 已食（鎖住）嘅餐如果已經有米，米格就唔可以再揀第二款——嗰餐改唔到，
      // 一日一米數學上做唔到。
      let lockedRiceRow = null;
      const riceSlot = slots.find((s) => s && s.is_rice);
      if (riceSlot) {
        const riceRows = new Set((riceSlot.candidates || []).map((c) => Number(c.row)));
        for (const before of lockedMealsBefore(meal)) {
          const arr = (mealPlan.meal_items && mealPlan.meal_items[before]) || [];
          const hit = arr.find((it) => it && it.row != null && riceRows.has(Number(it.row)));
          if (hit) {
            lockedRiceRow = Number(hit.row);
            break;
          }
        }
      }

      const menu = document.createElement("div");
      menu.id = "oos-menu";
      menu.className = "catalog-row-menu";

      oosMenuNote(menu, "Out of stock → Re-Generate");
      if (!items.length) {
        oosMenuNote(menu, "No markable item in this meal");
      } else {
        for (const it of items) {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.textContent = String(it.name || "");
          btn.addEventListener("click", async () => {
            hideOosMenu();
            await runOosResolve(dateIso, meal, it);
          });
          menu.appendChild(btn);
        }
      }

      // 冇可標記 item ＝ 嗰餐唔係由 solver 話事（例如餐廳午餐係固定營養，
      // 根本唔入 LP），指定食材做唔到嘢，所以連個段都唔好出。
      if (slots.length && items.length) {
        const swapTitle = document.createElement("div");
        swapTitle.className = "oos-menu-title oos-menu-section";
        swapTitle.textContent = "Swap → 指定食材";
        menu.appendChild(swapTitle);
        const runBtn = document.createElement("button");
        for (const slot of slots) {
          const rows = new Set((slot.candidates || []).map((c) => Number(c.row)));
          const current = items.find((it) => rows.has(Number(it.row)));
          const base = current ? String(current.name || "") : String(slot.label || "");
          const idx = Number(slot.item_index);
          const btn = document.createElement("button");
          btn.type = "button";
          const paint = () => {
            const picked = pendingSwaps[idx];
            btn.textContent = picked ? `${base} → ${picked.name}` : base;
            btn.classList.toggle("oos-menu-picked", !!picked);
          };
          paint();
          btn.addEventListener("click", async () => {
            await showSwapPicker(btn, meal, idx, current ? current.row : null, (pick) => {
              if (current && Number(pick.row) === Number(current.row)) delete pendingSwaps[idx];
              else pendingSwaps[idx] = pick;
              paint();
              runBtn.disabled = !Object.keys(pendingSwaps).length;
            }, lockedRiceRow);
          });
          menu.appendChild(btn);
        }
        runBtn.type = "button";
        runBtn.className = "oos-menu-run";
        runBtn.textContent = "Re-Generate with swaps";
        runBtn.disabled = true;
        runBtn.addEventListener("click", async () => {
          const swaps = Object.keys(pendingSwaps).map((idx) => ({
            meal,
            item_index: Number(idx),
            row_index: Number(pendingSwaps[idx].row),
          }));
          if (!swaps.length) return;
          hideOosMenu();
          await runOosResolve(dateIso, meal, null, swaps);
        });
        menu.appendChild(runBtn);
      }

      const resolveOnly = document.createElement("button");
      resolveOnly.type = "button";
      resolveOnly.className = "oos-menu-none";
      resolveOnly.textContent = "Re-Generate only";
      resolveOnly.addEventListener("click", async () => {
        hideOosMenu();
        await runOosResolve(dateIso, meal, null);
      });
      menu.appendChild(resolveOnly);
      document.body.appendChild(menu);
      placeMenu(menu, openAt.x, openAt.y);
    }

    document.addEventListener("click", (ev) => {
      const inMenu = ev.target && ev.target.closest
        && (ev.target.closest("#oos-menu") || ev.target.closest("#oos-swap-picker"));
      if (!inMenu) hideOosMenu();
    });
    document.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape") hideOosMenu();
    });

    async function runOosResolve(dateIso, meal, item, swaps = []) {
      const err = document.getElementById("err");
      err.style.display = "none";
      err.textContent = "";
      const day = storedMealPlanDay(dateIso);
      if (!day || !day.meal_plan) return;
      const locked = lockedMealsBefore(meal);
      const beforePanel = document.querySelector(".panel-bottom");
      const prevTop = beforePanel ? beforePanel.scrollTop : 0;
      const prevLeft = beforePanel ? beforePanel.scrollLeft : 0;
      try {
        const r = await fetch("/api/oos-resolve", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            date: dateIso,
            row_index: item ? Number(item.row) : null,
            locked_meals: locked,
            nutrient_indicators: day.nutrient_indicators || {},
            meal_plan: day.meal_plan || {},
            swaps,
            meal,
          }),
        });
        const data = await parseJsonSafe(r);
        if (!r.ok) {
          err.textContent = apiErrorMessage(data, "Out-of-stock re-solve failed.", r.status);
          err.style.display = "block";
          return;
        }
        if (data && data.meal_plan) {
          data.meal_plan.summary_timestamp = hkTimestamp();
          day.meal_plan = data.meal_plan;
        }
        renderFromMemory(null);
        const afterPanel = document.querySelector(".panel-bottom");
        if (afterPanel) {
          afterPanel.scrollTop = prevTop;
          afterPanel.scrollLeft = prevLeft;
        }
        currentFocusedDate = dateIso;
        await saveMemoryPayload();
        playGenerateChime();
        // 後端已暫停該食材；靜靜重載營養清單，令 Catalog 頁「暫停」剔號同步。
        try {
          renderNutritionCatalog(await loadNutritionCatalog());
        } catch (_) {}
      } catch (x) {
        err.textContent = String(x);
        err.style.display = "block";
      }
    }
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
    // 撳任何 menu 離開 Typhoon 畫面之前，先存低嗰版嘢。
    document.querySelectorAll(".menu-item").forEach((item) => {
      item.addEventListener("mousedown", () => {
        if (typeof leaveTyphoonPanel === "function") leaveTyphoonPanel();
      });
    });
    document.getElementById("menu-typhoon").addEventListener("click", async () => {
      if (!(await resolveUnsavedBeforeLeaving())) return;
      await openTyphoonPanel();
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
    document.getElementById("detail-post-mapping").addEventListener("contextmenu", (ev) => {
      const row = ev.target && ev.target.closest ? ev.target.closest("tr[data-detail-post-row]") : null;
      const idx = row ? Number(row.getAttribute("data-detail-post-row")) : -1;
      showDetailPostRowMenu(ev, Number.isInteger(idx) ? idx : -1);
    });
    document.getElementById("detail-post-row-menu").addEventListener("click", (ev) => {
      const action = ev.target && ev.target.closest ? ev.target.closest("[data-detail-post-row-action]") : null;
      const menu = document.getElementById("detail-post-row-menu");
      if (!action || !menu) return;
      const idx = Number(menu.getAttribute("data-detail-post-row-index"));
      hideDetailPostRowMenu();
      applyDetailPostRowAction(action.getAttribute("data-detail-post-row-action"), Number.isInteger(idx) ? idx : -1);
    });
    document.getElementById("detail-rice-conversions").addEventListener("contextmenu", (ev) => {
      const row = ev.target && ev.target.closest ? ev.target.closest("tr[data-detail-rice-row]") : null;
      const idx = row ? Number(row.getAttribute("data-detail-rice-row")) : -1;
      showDetailRiceRowMenu(ev, Number.isInteger(idx) ? idx : -1);
    });
    document.getElementById("detail-rice-row-menu").addEventListener("click", (ev) => {
      const action = ev.target && ev.target.closest ? ev.target.closest("[data-detail-rice-row-action]") : null;
      const menu = document.getElementById("detail-rice-row-menu");
      if (!action || !menu) return;
      const idx = Number(menu.getAttribute("data-detail-rice-row-index"));
      hideDetailRiceRowMenu();
      applyDetailRiceRowAction(action.getAttribute("data-detail-rice-row-action"), Number.isInteger(idx) ? idx : -1);
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
      if (!ev.target || !ev.target.closest || !ev.target.closest("#detail-post-row-menu")) hideDetailPostRowMenu();
      if (!ev.target || !ev.target.closest || !ev.target.closest("#detail-rice-row-menu")) hideDetailRiceRowMenu();
    });
    document.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape") hideCatalogRowMenu();
      if (ev.key === "Escape") hideMaintRowMenu();
      if (ev.key === "Escape") hideDetailRowMenu();
      if (ev.key === "Escape") hideDetailPostRowMenu();
      if (ev.key === "Escape") hideDetailRiceRowMenu();
    });
    document.getElementById("catalog-editor").addEventListener("scroll", hideCatalogRowMenu);
    // capture=true：scroll event 唔 bubble，資料而家喺 .maint-sheet-body 內捲，要用 capture 先截到。
    document.getElementById("maint-editor").addEventListener("scroll", hideMaintRowMenu, true);
    document.querySelector(".detail-editor")?.addEventListener("scroll", hideDetailRowMenu);
    document.querySelector(".detail-editor")?.addEventListener("scroll", hideDetailRiceRowMenu);
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
      // 闊度/margin 已搬去 wrapper；清走 select 本身嘅 inline 值，免得蓋過 .pickup-native 收埋佢嘅 CSS。
      ["marginLeft", "marginRight", "marginTop", "marginBottom", "width", "minWidth", "maxWidth"].forEach((name) => {
        if (select.style[name]) select.style[name] = "";
      });
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

    // Refresh 之後返返去上次嗰個畫面：panel key → point 返佢自己嗰個「開返佢」。
    // 冇 entry（planner／shopping）＝畫面本身已經有嘢睇，唔使再載。
    // 加新 panel 就喺 PANEL_KEYS 加個 key，喺呢度加返一行，兩處對齊。
    const PANEL_RESTORE = {
      config: () => applyActiveConfigView(false),
      maint: async () => {
        if (!activeMaintSheetKey) return;
        try {
          await openMaintSheet(activeMaintSheetKey, false);
        } catch (_) {
          // 嗰張表冇咗（改過名／刪咗）就開返第一張，唔好卡喺度乜都冇。
          if (maintSheets.length) await openMaintSheet(maintSheets[0].sheet_key, false);
        }
      },
      reports: () => openShiftCodeAnalysisReport(),
      duty_report: () => refreshDutyReport(),
      onoffduty: () => openOnOffDutyPanel(),
      typhoon: () => openTyphoonPanel(),
    };

    async function restoreActivePanel(panel) {
      const restore = PANEL_RESTORE[panel];
      if (restore) await restore();
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
      await restoreActivePanel(activePanel);
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
