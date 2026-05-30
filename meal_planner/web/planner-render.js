    /** Meal-time column: show HH:MM only; fallback to — */
    function mealTimeCell(timeRule) {
      if (timeRule == null || timeRule === "") return "—";
      const s = String(timeRule).trim();
      if (!s) return "—";
      const m = s.match(/\b(\d{1,2}:\d{2})\b/);
      if (m) return m[1];
      return "—";
    }

    function riceSideNote(pats, riceNote) {
      if (riceNote && String(riceNote).trim() !== "") {
        return String(riceNote);
      }
      const t = Object.values(pats || {}).join(" ");
      if (/糙米/.test(t)) return "Brown rice cooked weight (--g) = raw weight --g\nWater = --g";
      if (/米|藜麥|飯/.test(t)) return "Mixed quinoa rice cooked weight (--g) = raw weight --g\nWater = --g";
      return "(Rice note: fill after meal allocation)";
    }

    function totalLabel(isWork) {
      if (isWork === true) return "Total (Workday)";
      if (isWork === false) return "Total (Non-workday)";
      return "Total (—)";
    }

    function hkTimestamp() {
      return new Date().toLocaleString("zh-HK", {
        timeZone: HK_TZ,
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
      });
    }

    function stampDays(days) {
      const ts = hkTimestamp();
      for (const d of (Array.isArray(days) ? days : [])) {
        if (!d || !d.meal_plan || typeof d.meal_plan !== "object") continue;
        d.meal_plan.summary_timestamp = ts;
      }
    }

    function analysisList(items, key = "label") {
      const arr = Array.isArray(items) ? items : [];
      return arr.map((x) => {
        const text = x && typeof x === "object" ? x[key] : x;
        return String(text || "").trim();
      }).filter(Boolean);
    }

    function renderConstraintAnalysisRows(day, optimization) {
      const analysis = optimization && typeof optimization.constraint_analysis === "object"
        ? optimization.constraint_analysis
        : null;
      const hardFeasible = optimization && optimization.hard_feasible;
      const hardViolations = Array.isArray(optimization && optimization.hard_violations)
        ? optimization.hard_violations
        : [];
      const analysisStatus = analysis && analysis.status ? String(analysis.status) : "";
      const shouldShow =
        hardFeasible === false ||
        hardViolations.length > 0 ||
        analysisStatus === "infeasible";
      if (!shouldShow) {
        return "";
      }

      const summary = analysis && analysis.summary
        ? String(analysis.summary)
        : "Current ingredients, portion limits, and nutrition targets cannot all be satisfied at the same time.";
      const violations = analysisList(analysis && analysis.violations);
      const binding = analysisList(analysis && analysis.binding_limits);
      const paramChanges = analysisList(analysis && analysis.existing_parameter_changes);
      const targetOptions = analysisList(analysis && analysis.target_options);
      const chunks = [summary];
      if (violations.length) chunks.push(`Red-flag reasons: ${violations.join("; ")}`);
      if (binding.length) chunks.push(`Binding limits: ${binding.join("; ")}`);
      if (analysis && analysis.manual_override_note) {
        chunks.push(String(analysis.manual_override_note));
      }
      if (paramChanges.length) {
        chunks.push(`Reference only if changing global catalog parameters: ${paramChanges.join("; ")}`);
      }
      if (targetOptions.length) {
        chunks.push(`If ingredient parameters stay unchanged, consider target changes: ${targetOptions.join("; ")}`);
      }
      chunks.push("Adding or replacing ingredients is not recommended; follow medical/FODMAP guidance and review only existing available ingredients and portion limits.");
      const body = chunks.map(esc).join("<br />");
      return `<tr class="rec constraint-analysis" data-day="${esc(day.date)}">
        <td class="rec-lbl" colspan="5">Feasibility</td>
        <td class="rec-body" colspan="10">${body}</td>
      </tr>`;
    }

    /**
     * @param {object} day
     * @param {string[]|null} headers
     */
    function renderDayRows(day, headers, nutrientKeys) {
      const mp = day.meal_plan || {};
      const pr = mp.primary_rule;
      const pats = mp.meal_patterns || {};
      const ingredientsByMeal = mp.meal_ingredients || {};
      const mealNutrients = mp.meal_nutrients || {};
      const summary = mp.summary || {};
      const summaryTimestamp = mp.summary_timestamp ? String(mp.summary_timestamp) : "";
      const riceNote = mp.rice_note || "";
      const rl = mp.restaurant_lunch;
      const resolved = mp.meal_times_resolved || {};
      const nCol = (headers && headers.length) || 10;
      const nk = Array.isArray(nutrientKeys) && nutrientKeys.length ? nutrientKeys : [
        "kcal","protein_g","carb_g","sugar_g","cholesterol_mg","sodium_mg","calcium_mg","fat_total_g","fat_sat_g","fat_trans_g"
      ];
      const headStyle = "background:#99CCFF !important;color:#000 !important;";

      let body = "";
      let shownMealCount = 0;
      let dateRowRendered = false;
      let riceHintInserted = false;
      for (const meal of MEALS) {
        const timeRule = pr ? pr[meal] : null;
        const rCell = resolved[meal];
        const timeCell =
          rCell != null && String(rCell).trim() !== "" ? String(rCell).trim() : mealTimeCell(timeRule);
        // 有時間先顯示該餐
        if (timeCell === "—") {
          continue;
        }

        let hasMealContent = false;
        let line;
        if (meal === "午餐" && day.is_work_day === true && rl && timeCell !== "—") {
          line = `Lunch — "${rl.choice || "—"}" (${rl.store || "—"})`;
          hasMealContent = true;
        } else {
          const ingredients = Array.isArray(ingredientsByMeal[meal]) ? ingredientsByMeal[meal] : [];
          const joined = ingredients.map((x) => String(x).trim()).filter((x) => x !== "").join("+");
          const text = joined || (pats[meal] != null && pats[meal] !== "" ? String(pats[meal]) : "—");
          line = `${MEAL_EN[meal] || meal} - ${text}`;
          hasMealContent = text !== "—";
        }
        const hasMealTime = timeCell !== "—";

        // 規則：真係「冇餐」（冇內容 + 冇時間）先唔顯示
        if (!hasMealContent && !hasMealTime) {
          continue;
        }

        let first3;
        if (!dateRowRendered) {
          const weekday = dowZh(day.date);
          const isToday = day.date === todayIsoHK();
          const isSunday = weekday === "Sun";
          const dateClasses = ["c-center", "col-d", isToday ? "today-cell" : "", isSunday ? "sunday-cell" : ""].filter(Boolean).join(" ");
          const weekdayClasses = ["c-center", "col-w", isToday ? "today-cell" : "", isSunday ? "sunday-cell" : ""].filter(Boolean).join(" ");
          first3 = `<td class="${dateClasses}">${esc(dateDMY(day.date))}</td><td class="${weekdayClasses}">${esc(weekday)}</td><td class="c-center col-code">${esc(day.roster_code ?? "—")}</td>`;
          dateRowRendered = true;
        } else if (!riceHintInserted) {
          first3 = `<td colspan="3" class="rice-hint">${br(riceSideNote(pats, riceNote))}</td>`;
          riceHintInserted = true;
        } else {
          first3 = `<td class="c-center col-d"></td><td class="c-center col-w"></td><td class="c-center col-code"></td>`;
        }

        body += `<tr class="meal-row" data-day="${esc(day.date)}">
          ${first3}
          <td class="col-time">${esc(timeCell)}</td>
          <td class="col-content editable-content" contenteditable="true" data-date="${esc(day.date)}" data-meal="${esc(meal)}">${esc(line)}</td>
          ${nutCellsFromValues(nk.map((k) => (mealNutrients[meal] && mealNutrients[meal][k] != null ? mealNutrients[meal][k] : null)))}
        </tr>`;
        shownMealCount += 1;
      }

      const rowStyle = "background:#99CCFF !important;color:#000 !important;";
      const totals = Array.isArray(summary.totals) ? summary.totals : Array.from({ length: nCol }, () => null);
      const errors = Array.isArray(summary.errors) ? summary.errors : Array.from({ length: nCol }, () => null);
      const totalRed = Array.isArray(summary.total_red_flags) ? summary.total_red_flags : [];
      const errorRed = Array.isArray(summary.error_red_flags) ? summary.error_red_flags : [];
      const footNums = nutCellsFromValues(totals, rowStyle, totalRed);
      const errNums = nutCellsFromValues(errors, rowStyle, errorRed);
      const optimization = mp.optimization || {};
      const manualRecalc = optimization.mode === "manual_recalc";
      const recs = Array.isArray(optimization.recommendations) ? optimization.recommendations : [];
      const relaxPlan = Array.isArray(optimization.relaxation_plan) ? optimization.relaxation_plan : [];
      const relaxEval = optimization.relaxation_plan_eval || null;
      const relaxRounds = Array.isArray(optimization.relaxation_plan_rounds) ? optimization.relaxation_plan_rounds : [];
      const paramChanges = Array.isArray(optimization.parameter_changes) ? optimization.parameter_changes : [];
      const replacement = optimization.replacement_search || null;
      const replacementApplied = optimization.replacement_applied === true;
      const hardFeasible = optimization.hard_feasible;
      const autoRetryUsed = optimization.auto_retry_used === true;
      const solverMode = optimization.mode || "—";
      const solverStatus = optimization.status || optimization.solver_status || "—";

      if (shownMealCount === 0) {
        const noteText = mp.note ? String(mp.note) : "無餐單資料 / 缺乏更表";
        const dMy = dateDMY(day.date);
        const wDay = dowZh(day.date);
        const isToday = day.date === todayIsoHK();
        const isSunday = wDay === "Sun";
        const dateClasses = ["c-center", "col-d", isToday ? "today-cell" : "", isSunday ? "sunday-cell" : ""].filter(Boolean).join(" ");
        const weekdayClasses = ["c-center", "col-w", isToday ? "today-cell" : "", isSunday ? "sunday-cell" : ""].filter(Boolean).join(" ");
        
        return `<tr class="meal-row" data-day="${esc(day.date)}">
          <td class="${dateClasses}">${esc(dMy)}</td>
          <td class="${weekdayClasses}">${esc(wDay)}</td>
          <td class="c-center col-code">—</td>
          <td class="col-time">—</td>
          <td class="col-content" style="color:#d9534f; font-weight:bold;">${esc(noteText)}</td>
          ${nutCellsFromValues(Array.from({ length: nk.length }, () => null))}
        </tr>`;
      }

      const recRows = renderConstraintAnalysisRows(day, optimization);

      return `${body}
        <tr class="sum" data-day="${esc(day.date)}">
          <td class="lbl" colspan="5" style="${rowStyle}">${esc(totalLabel(day.is_work_day))}</td>
          ${footNums}
        </tr>
        <tr class="sum-err" data-day="${esc(day.date)}">
          <td class="lbl" colspan="5" style="${rowStyle}">${esc(summaryTimestamp ? `Error [${summaryTimestamp}]` : "Error")}</td>
          ${errNums}
        </tr>
        ${recRows}`;
    }

    /**
     * 連續日子只出一次 header；全段共用一張表，欄寬由全表最闊內容決定。
     * @param {object[]} days
     * @param {string[]|null} headers
     */
    function renderPeriodTable(days, headers, nutrientKeys, indicatorRows) {
      const headStyle = "background:#99CCFF !important;color:#000 !important;";
      const nk = Array.isArray(nutrientKeys) && nutrientKeys.length ? nutrientKeys : [
        "kcal","protein_g","carb_g","sugar_g","cholesterol_mg","sodium_mg","calcium_mg","fat_total_g","fat_sat_g","fat_trans_g"
      ];
      const workRow = indicatorRows && Array.isArray(indicatorRows.workday) ? indicatorRows.workday : [];
      const nonworkRow = indicatorRows && Array.isArray(indicatorRows.nonworkday) ? indicatorRows.nonworkday : [];
      let rows = "";
      for (const d of days || []) {
        rows += renderDayRows(d, headers, nutrientKeys);
      }
      return `<div class="day-wrap">
        <div class="period-panels">
          <div class="panel-top">
            <table class="sheet" style="width:${columnWidthTotalPx(nk)}px">
              ${colGroupHtml(nk)}
              <tbody>
            <tr class="indicator-head">
              <td class="c-center col-d no-grid" style="${headStyle}"></td>
              <td class="c-center col-w no-grid" style="${headStyle}"></td>
              <td class="c-center col-code no-grid" style="${headStyle}"></td>
              <td class="c-center col-time no-grid" style="${headStyle}"></td>
              <td class="ind-label col-content" style="${headStyle}">Target</td>
              ${nutHeaderCells(headers, headStyle)}
            </tr>
            <tr class="indicator-values">
              <td class="c-center col-d no-grid"></td>
              <td class="c-center col-w no-grid"></td>
              <td class="c-center col-code no-grid"></td>
              <td class="c-center col-time no-grid"></td>
              <td class="ind-label col-content">Workday</td>
              ${nutTargetInputCells("workday", workRow)}
            </tr>
            <tr class="indicator-values">
              <td class="c-center col-d no-grid"></td>
              <td class="c-center col-w no-grid"></td>
              <td class="c-center col-code no-grid"></td>
              <td class="c-center col-time no-grid"></td>
              <td class="ind-label col-content">Non-workday</td>
              ${nutTargetInputCells("nonworkday", nonworkRow)}
            </tr>
            <tr class="hdr-labels">
              <td data-col-key="date" class="c-center col-d" style="${headStyle}">Date</td>
              <td data-col-key="dow" class="c-center col-w" style="${headStyle}">Weekday</td>
              <td data-col-key="code" class="c-center col-code" style="${headStyle}">Code</td>
              <td data-col-key="time" class="c-center col-time" style="${headStyle}">Meal Time</td>
              <td data-col-key="content" class="col-content" style="${headStyle}">Content</td>
              ${nk.map((k, i) => `<td data-col-key="${k}" class="nut nut-h" style="${headStyle}">${esc((headers && headers[i]) || k)}</td>`).join("")}
            </tr>
          </tbody>
        </table>
      </div>
      <div class="panel-bottom">
        <table class="sheet" style="width:${columnWidthTotalPx(nk)}px">
          ${colGroupHtml(nk)}
          <tbody>
            ${rows}
          </tbody>
        </table>
      </div>
      </div>
      </div>`;
    }

    function replaceDayRowsInPlace(dayObj, headers, nutrientKeys) {
      if (!dayObj || !dayObj.date) return false;
      const tbody = document.querySelector(".panel-bottom table.sheet tbody");
      if (!tbody) return false;
      const existing = Array.from(tbody.querySelectorAll(`tr[data-day="${dayObj.date}"]`));
      if (!existing.length) return false;
      const first = existing[0];
      const anchor = first.nextSibling;
      const tpl = document.createElement("template");
      tpl.innerHTML = renderDayRows(dayObj, headers, nutrientKeys);
      const freshRows = Array.from(tpl.content.querySelectorAll("tr"));
      if (!freshRows.length) return false;
      // Remove old rows only after we've prepared replacement rows.
      existing.forEach((r) => r.remove());
      const frag = document.createDocumentFragment();
      for (const r of freshRows) frag.appendChild(r);
      if (anchor && anchor.parentNode === tbody) {
        tbody.insertBefore(frag, anchor);
      } else {
        tbody.appendChild(frag);
      }
      return true;
    }

    function sortDaysByDate(days) {
      return [...(Array.isArray(days) ? days : [])].sort((a, b) => String(a.date || "").localeCompare(String(b.date || "")));
    }

    function mergeDaysByDate(existingDays, incomingDays) {
      const m = new Map();
      for (const d of (existingDays || [])) {
        if (d && d.date) m.set(String(d.date), d);
      }
      for (const d of (incomingDays || [])) {
        if (d && d.date) m.set(String(d.date), d);
      }
      return sortDaysByDate(Array.from(m.values()));
    }

    function todayIsoHK() {
      const { y, m, d } = ymdNow();
      const mm = String(m).padStart(2, "0");
      const dd = String(d).padStart(2, "0");
      return `${y}-${mm}-${dd}`;
    }

    function visibleDays() {
      const days = Array.isArray(memoryPayload.days) ? memoryPayload.days : [];
      if (showPast) return sortDaysByDate(days);
      const today = todayIsoHK();
      return sortDaysByDate(days.filter((d) => String(d.date || "") >= today));
    }

    function captureViewportAnchor(referenceRatio = 0.5) {
      const panel = document.querySelector(".panel-bottom");
      if (!panel) return null;
      const rows = Array.from(panel.querySelectorAll("tr[data-day]"));
      const probeY = panel.scrollTop + panel.clientHeight * referenceRatio;
      let best = null;
      let bestDist = Infinity;
      for (const r of rows) {
        const top = r.offsetTop;
        const bottom = r.offsetTop + r.offsetHeight;
        if (top <= probeY && bottom >= probeY) {
          return {
            date: r.getAttribute("data-day"),
            delta: probeY - r.offsetTop,
            left: panel.scrollLeft,
            referenceRatio,
          };
        }
        const center = top + r.offsetHeight / 2;
        const dist = Math.abs(center - probeY);
        if (dist < bestDist) {
          bestDist = dist;
          best = r;
        }
      }
      if (best) {
        return {
          date: best.getAttribute("data-day"),
          delta: probeY - best.offsetTop,
          left: panel.scrollLeft,
          referenceRatio,
        };
      }
      return null;
    }

    function restoreViewportAnchor(anchor) {
      if (!anchor) return;
      const panel = document.querySelector(".panel-bottom");
      if (!panel) return;
      const row = panel.querySelector(`tr[data-day="${anchor.date}"]`);
      if (!row) return;
      const ratio = typeof anchor.referenceRatio === "number" ? anchor.referenceRatio : 0.5;
      panel.scrollTop = Math.max(0, row.offsetTop + (anchor.delta || 0) - panel.clientHeight * ratio);
      panel.scrollLeft = anchor.left || 0;
    }

    function renderFromMemory(anchor = null) {
      const out = document.getElementById("out");
      const days = visibleDays();
      const headers = memoryPayload.headers && memoryPayload.headers.length
        ? memoryPayload.headers
        : (targetPayload.headers || []);
      const nutrientKeys = memoryPayload.nutrient_keys && memoryPayload.nutrient_keys.length
        ? memoryPayload.nutrient_keys
        : (targetPayload.nutrient_keys || []);
      const indicatorRows = memoryPayload.indicator_rows && Object.keys(memoryPayload.indicator_rows).length
        ? memoryPayload.indicator_rows
        : (targetPayload.indicator_rows || {});
      out.innerHTML = renderPeriodTable(days, headers, nutrientKeys, indicatorRows);
      applyColumnWidths();
      attachColumnResizers();
      bindPanelScrollSync();
      syncPanelGutter();
      applyPlannerOffset();
      attachPlannerDrag();
      restoreViewportAnchor(anchor);
    }

    function plannerOffsetPx() {
      const v = Number(formColumnWidths.planner_offset);
      return Number.isFinite(v) ? v : 0;
    }

    function applyPlannerOffset() {
      document.querySelectorAll("#out .day-wrap").forEach((el) => {
        el.style.marginLeft = `${plannerOffsetPx()}px`;
      });
    }

    function attachPlannerDrag() {
      const handle = document.querySelector("#planner-panel h1");
      if (!handle || handle.dataset.plannerDragBound === "1") return;
      handle.dataset.plannerDragBound = "1";
      handle.classList.add("planner-drag-handle");
      handle.title = "Drag left or right to move planner";
      handle.addEventListener("mousedown", (ev) => {
        if (ev.button != null && ev.button !== 0) return;
        ev.preventDefault();
        const startX = ev.clientX;
        const startOffset = plannerOffsetPx();
        const onMove = (mv) => {
          formColumnWidths.planner_offset = startOffset + (mv.clientX - startX);
          applyPlannerOffset();
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
        formColumnWidths.planner_offset = 0;
        applyPlannerOffset();
        persistColumnWidths();
      });
    }

    function currentDateFromFocusOrViewport() {
      const selDate = (() => {
        try {
          const sel = window.getSelection ? window.getSelection() : null;
          if (!sel || !sel.anchorNode) return null;
          let n = sel.anchorNode;
          if (n.nodeType === 3) n = n.parentElement;
          if (!n || !n.closest) return null;
          const td = n.closest("td.editable-content[data-date]");
          return td ? td.getAttribute("data-date") : null;
        } catch (_) {
          return null;
        }
      })();
      if (selDate) return selDate;
      const ae = document.activeElement;
      if (ae && ae.matches && ae.matches("td.editable-content[data-date]")) {
        const d = ae.getAttribute("data-date");
        if (d) return d;
      }
      if (currentFocusedDate) return currentFocusedDate;
      const a = captureViewportAnchor();
      if (a && a.date) return a.date;
      return null;
    }
