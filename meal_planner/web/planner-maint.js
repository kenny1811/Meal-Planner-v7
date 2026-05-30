    function emptyMaintRow(rows = null) {
      if (activeMaintSheetKey === "roster") return [""];
      const cols = maintColumnCount(rows || collectMaintRows());
      return Array.from({ length: cols }, () => "");
    }

    function setMaintRowsAndRender(rows) {
      maintSheetPayload.rows = rows;
      renderMaintEditor();
    }

    function showMaintRowMenu(ev, rowIndex) {
      const menu = document.getElementById("maint-row-menu");
      if (!menu) return;
      ev.preventDefault();
      menu.hidden = false;
      menu.setAttribute("data-maint-row-index", Number.isInteger(rowIndex) ? String(rowIndex) : "-1");
      menu.style.left = `${ev.clientX}px`;
      menu.style.top = `${ev.clientY}px`;
    }

    function hideMaintRowMenu() {
      const menu = document.getElementById("maint-row-menu");
      if (!menu) return;
      menu.hidden = true;
      menu.removeAttribute("data-maint-row-index");
    }

    function applyMaintRowAction(action, rowIndex) {
      const rows = collectMaintRows();
      const idx = Number.isInteger(rowIndex) && rowIndex >= 0 ? rowIndex : rows.length;
      if (action === "insert") {
        rows.splice(Math.min(idx, rows.length), 0, emptyMaintRow(rows));
      } else if (action === "delete") {
        if (idx < rows.length) rows.splice(idx, 1);
      } else if (action === "append") {
        rows.push(emptyMaintRow(rows));
      }
      setUnsavedChanges("餐單參數");
      setMaintRowsAndRender(rows);
    }

    function parseRosterMaintLine(text) {
      const s = String(text || "").trim().replace(/\u00a0/g, " ");
      const m = s.match(/^(\d{4})年(\d{1,2})月\s*(.*)$/);
      if (!m) return null;
      const tokens = m[3].trim().split(/\s+/).filter(Boolean);
      const days = [];
      for (let i = 0; i + 1 < tokens.length; i += 2) {
        const day = Number(tokens[i]);
        if (!Number.isInteger(day) || day < 1 || day > 31) break;
        days.push({ day, code: tokens[i + 1] });
      }
      return {
        year: Number(m[1]),
        month: Number(m[2]),
        label: `${m[1]}-${String(Number(m[2])).padStart(2, "0")}`,
        days,
      };
    }

    function parseYmd(value) {
      const s = String(value || "").trim();
      let m = s.match(/^(\d{2,4})-(\d{1,2})-(\d{1,2})/);
      if (m) {
        let y = Number(m[1]);
        if (y < 100) y += 2000;
        return { year: y, month: Number(m[2]), day: Number(m[3]) };
      }
      m = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2,4})(?:\b.*)?$/);
      if (m) {
        let y = Number(m[3]);
        if (y < 100) y += 2000;
        return { year: y, month: Number(m[2]), day: Number(m[1]) };
      }
      m = s.match(/^(\d{2})(\d{2})(\d{2}|\d{4})$/);
      if (m) {
        let y = Number(m[3]);
        if (y < 100) y += 2000;
        return { year: y, month: Number(m[2]), day: Number(m[1]) };
      }
      m = s.match(/^(\d{1,2})\/(\d{1,2})$/);
      if (m) {
        return { year: new Date().getFullYear(), month: Number(m[2]), day: Number(m[1]) };
      }
      return null;
    }

    function dateKey(year, month, day) {
      return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    }

    function dateDmy(year, month, day) {
      return `${String(day).padStart(2, "0")}/${String(month).padStart(2, "0")}/${year}`;
    }

    function weekdayLabel(year, month, day) {
      const d = new Date(year, month - 1, day);
      return ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][d.getDay()] || "";
    }

    function normalTime(value) {
      const s = String(value || "").trim();
      const compact = s.match(/^(\d{1,2})(\d{2})$/);
      if (compact) return `${String(Number(compact[1])).padStart(2, "0")}:${compact[2]}`;
      const m = s.match(/(\d{1,2}):(\d{2})/);
      if (!m) return "";
      return `${String(Number(m[1])).padStart(2, "0")}:${m[2]}`;
    }

    function timeMinutes(value) {
      const t = normalTime(value);
      if (!t) return null;
      const [h, m] = t.split(":").map(Number);
      return h * 60 + m;
    }

    function minutesBetween(start, end) {
      const a = timeMinutes(start);
      let b = timeMinutes(end);
      if (a == null || b == null) return null;
      if (b < a) b += 24 * 60;
      return b - a;
    }

    function minutesLabel(minutes) {
      if (minutes == null || !Number.isFinite(minutes)) return "";
      const sign = minutes < 0 ? "-" : "";
      const n = Math.abs(Math.round(minutes));
      return `${sign}${Math.floor(n / 60)}:${String(n % 60).padStart(2, "0")}`;
    }

    function rosterCodeMatches(pattern, code) {
      const p = String(pattern || "").trim();
      const c = String(code || "").trim();
      if (!p || !c) return false;
      if (p.endsWith("*")) return c.startsWith(p.slice(0, -1));
      return p === c;
    }

    function payrollRowsByCode(rows) {
      const out = [];
      (rows || []).slice(1).forEach((row) => {
        if (!Array.isArray(row)) return;
        const code = String(row[0] || "").trim();
        if (!code) return;
        out.push({
          code,
          start: normalTime(row[1]),
          end: normalTime(row[2]),
          applies: String(row[3] || "").trim(),
          priority: Number(row[4] || 0),
        });
      });
      return out.sort((a, b) => (b.priority || 0) - (a.priority || 0));
    }

    function overtimeRowsByDate(rows) {
      const out = new Map();
      (rows || []).slice(1).forEach((row) => {
        if (!Array.isArray(row)) return;
        const d = parseYmd(row[0]);
        if (!d) return;
        out.set(dateKey(d.year, d.month, d.day), {
          start: normalTime(row[1]),
          end: normalTime(row[2]),
          note: String(row[3] || "").trim(),
        });
      });
      return out;
    }

    function holidayRowsByDate(rows) {
      const out = new Map();
      (rows || []).slice(1).forEach((row) => {
        if (!Array.isArray(row)) return;
        const d = parseYmd(row[0]);
        const name = String(row[1] || "").trim();
        if (!d || !name) return;
        out.set(dateKey(d.year, d.month, d.day), name);
      });
      return out;
    }

    function medicalRowsByDate(rows) {
      const out = new Map();
      (rows || []).slice(1).forEach((row) => {
        if (!Array.isArray(row)) return;
        const dateIdx = row.findIndex((cell) => !!parseYmd(cell));
        if (dateIdx < 0) return;
        const d = parseYmd(row[dateIdx]);
        if (!d) return;
        const key = dateKey(d.year, d.month, d.day);
        const timeIdx = row.findIndex((cell, idx) => idx !== dateIdx && !!normalTime(cell));
        const time = timeIdx >= 0 ? normalTime(row[timeIdx]) : "";
        const details = row
          .map((cell, idx) => ({ cell: String(cell || "").trim(), idx }))
          .filter(({ cell, idx }) => cell && idx !== dateIdx && idx !== timeIdx)
          .map(({ cell }) => cell);
        const text = ["醫療行程", time, ...details].filter(Boolean).join(" ");
        if (!out.has(key)) out.set(key, []);
        out.get(key).push(text);
      });
      return out;
    }

    function shiftForCode(code) {
      const rows = payrollRowsByCode(rosterReportSources.payroll_times);
      return rows.find((row) => rosterCodeMatches(row.code, code)) || null;
    }

    function rosterDefinitionMap(rows) {
      return collectRosterCodeDefinitions().concat(
        (detailSettingsPayload.roster_code_definitions || []).filter((row) => row && row.pattern && row.label)
      ).filter((row, idx, all) => all.findIndex((x) => x.pattern === row.pattern) === idx);
    }

    function rosterDefinitionForCode(code, defs) {
      const s = String(code || "").trim();
      for (const def of defs || []) {
        if (def.pattern.endsWith("*") && s.startsWith(def.pattern.slice(0, -1))) return def.label;
        if (def.pattern === s) return def.label;
      }
      return "Workday";
    }

    function renderRosterMaintReport(rows) {
      const overtimeByDate = overtimeRowsByDate(rosterReportSources.overtime);
      const holidaysByDate = holidayRowsByDate(rosterReportSources.public_holidays);
      const medicalByDate = medicalRowsByDate(rosterReportSources.medical_appointments);
      const todayKey = todayIsoHK();
      const reportRows = [];
      let totalDuration = 0;
      let totalOvertime = 0;
      let totalPay = 0;
      const sourceRows = [];
      const activeIdx = Number.isInteger(activeRosterMonthIndex) ? activeRosterMonthIndex : 0;
      const selected = (rows || [])[activeIdx];
      if (selected) sourceRows.push(selected);
      (sourceRows || []).forEach((row) => {
        const parsed = parseRosterMaintLine(Array.isArray(row) ? row[0] : "");
        if (!parsed) return;
        parsed.days.forEach((item) => {
          const key = dateKey(parsed.year, parsed.month, item.day);
          const ot = overtimeByDate.get(key) || {};
          const shift = shiftForCode(item.code) || {};
          const plannedStart = shift.start || "";
          const plannedEnd = shift.end || "";
          const start = ot.start || plannedStart;
          const end = ot.end || plannedEnd;
          const duration = minutesBetween(start, end);
          const overtime = duration != null && duration > 615 ? duration - 600 : null;
          const overtimePay = overtime ? overtime : null;
          if (duration != null) totalDuration += duration;
          if (overtime != null) totalOvertime += overtime;
          if (overtimePay != null) totalPay += overtimePay;
          const notes = [];
          const holiday = holidaysByDate.get(key);
          if (holiday) notes.push(holiday);
          const medical = medicalByDate.get(key) || [];
          notes.push(...medical);
          if (ot.note) notes.push(ot.note);
          const weekday = weekdayLabel(parsed.year, parsed.month, item.day);
          const isToday = key === todayKey;
          const isSunday = weekday === "Sun";
          const dateClasses = ["report-date-cell", isToday ? "report-today-cell" : "", (isSunday || holiday) ? "report-red" : ""].filter(Boolean).join(" ");
          const weekdayClasses = ["report-weekday-cell", isToday ? "report-today-cell" : "", (isSunday || holiday) ? "report-red" : ""].filter(Boolean).join(" ");
          const noteClasses = ["report-note-cell", isToday && holiday ? "report-today-cell" : ""].filter(Boolean).join(" ");
          reportRows.push(`<tr class="${isToday ? "report-today-row" : ""}">
            <td class="${dateClasses}">${esc(dateDmy(parsed.year, parsed.month, item.day))}</td>
            <td class="${weekdayClasses}">${esc(weekday)}</td>
            <td>${esc(item.code)}</td>
            <td>${esc(start)}</td>
            <td>${esc(end)}</td>
            <td>${esc(minutesLabel(duration))}</td>
            <td>${esc(overtime ? minutesLabel(overtime) : "")}</td>
            <td>${esc(overtimePay ? overtimePay.toFixed(0) : "")}</td>
            <td class="${noteClasses}">${esc(notes.join(" / "))}</td>
          </tr>`);
        });
      });
      return `<table class="maint-report-table" data-form-table>
        <colgroup>
          <col data-form-col-key="maint_roster_report_date" data-form-col-default="110" />
          <col data-form-col-key="maint_roster_report_weekday" data-form-col-default="70" />
          <col data-form-col-key="maint_roster_report_code" data-form-col-default="110" />
          <col data-form-col-key="maint_roster_report_start" data-form-col-default="80" />
          <col data-form-col-key="maint_roster_report_end" data-form-col-default="80" />
          <col data-form-col-key="maint_roster_report_duration" data-form-col-default="80" />
          <col data-form-col-key="maint_roster_report_overtime" data-form-col-default="80" />
          <col data-form-col-key="maint_roster_report_overtime_pay" data-form-col-default="90" />
          <col data-form-col-key="maint_roster_report_note" data-form-col-default="220" />
        </colgroup>
        <thead><tr><th data-form-col-key="maint_roster_report_date">日期</th><th data-form-col-key="maint_roster_report_weekday">星期</th><th data-form-col-key="maint_roster_report_code">更碼</th><th data-form-col-key="maint_roster_report_start">開工</th><th data-form-col-key="maint_roster_report_end">收工</th><th data-form-col-key="maint_roster_report_duration">時長</th><th data-form-col-key="maint_roster_report_overtime">加班</th><th data-form-col-key="maint_roster_report_overtime_pay">加班費</th><th data-form-col-key="maint_roster_report_note">備註</th></tr></thead>
        <tbody>${reportRows.join("") || '<tr><td colspan="9" class="maint-empty">No roster data</td></tr>'}</tbody>
        <tfoot><tr><th colspan="5">Total</th><th>${esc(minutesLabel(totalDuration))}</th><th>${esc(minutesLabel(totalOvertime))}</th><th>${esc(totalPay ? totalPay.toFixed(0) : "")}</th><th></th></tr></tfoot>
      </table>`;
    }

    function refreshRosterMaintReport() {
      const report = document.getElementById("maint-roster-report");
      if (!report) return;
      report.innerHTML = renderRosterMaintReport(collectMaintRows());
      applyFormColumnWidths(report);
      attachFormColumnResizers(report);
      applyRosterReportOffset();
      attachRosterReportDrag();
    }

    function rosterReportOffsetPx() {
      const v = Number(formColumnWidths.maint_roster_report_offset);
      return Number.isFinite(v) ? v : 0;
    }

    function applyRosterReportOffset() {
      const report = document.getElementById("maint-roster-report");
      if (!report) return;
      report.style.marginLeft = `${rosterReportOffsetPx()}px`;
    }

    function attachRosterReportDrag() {
      const pane = document.getElementById("maint-roster-report-pane");
      const report = document.getElementById("maint-roster-report");
      if (!pane || !report || pane.dataset.reportDragBound === "1") return;
      pane.dataset.reportDragBound = "1";
      const startDrag = (ev) => {
        if (ev.button != null && ev.button !== 0) return;
        ev.preventDefault();
        const startX = ev.clientX;
        const startOffset = rosterReportOffsetPx();
        const onMove = (mv) => {
          formColumnWidths.maint_roster_report_offset = startOffset + (mv.clientX - startX);
          applyRosterReportOffset();
        };
        const onUp = () => {
          window.removeEventListener("mousemove", onMove);
          window.removeEventListener("mouseup", onUp);
          persistColumnWidths();
        };
        window.addEventListener("mousemove", onMove);
        window.addEventListener("mouseup", onUp);
      };
      pane.querySelector(".maint-pane-title")?.addEventListener("mousedown", startDrag);
    }
    function savedRosterMonthIndex(rows) {
      const n = Number(formColumnWidths.maint_roster_month_index);
      return Number.isInteger(n) && n >= 0 ? Math.min(n, Math.max(0, (rows || []).length - 1)) : 0;
    }

    function setActiveRosterMonthIndex(idx) {
      const rows = collectMaintRows();
      const next = Number.isInteger(idx) && idx >= 0 ? Math.min(idx, Math.max(0, rows.length - 1)) : 0;
      activeRosterMonthIndex = next;
      formColumnWidths.maint_roster_month_index = next;
      document.querySelectorAll(".maint-roster-table tr[data-maint-row-index]").forEach((tr) => {
        tr.classList.toggle("active-roster-row", Number(tr.getAttribute("data-maint-row-index")) === activeRosterMonthIndex);
      });
      refreshRosterMaintReport();
      persistColumnWidths();
    }

    function attachRosterSplitResizer(editor) {
      const grip = editor.querySelector("#maint-roster-report-resizer");
      const split = editor.querySelector(".maint-roster-split");
      if (!grip || !split || grip.dataset.bound === "1") return;
      grip.dataset.bound = "1";
      grip.addEventListener("mousedown", (ev) => {
        ev.preventDefault();
        const rect = split.getBoundingClientRect();
        const onMove = (mv) => {
          const topHeight = Math.max(0, Math.min(rect.height - 6, mv.clientY - rect.top));
          formColumnWidths.maint_roster_top_height = topHeight;
          split.style.gridTemplateRows = `${topHeight}px 6px 1fr`;
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

    function renderRosterMaintEditor() {
      const editor = document.getElementById("maint-editor");
      if (!editor) return;
      const rows = Array.isArray(maintSheetPayload.rows) ? maintSheetPayload.rows : [];
      activeRosterMonthIndex = savedRosterMonthIndex(rows);
      const monthRows = rows.map((row, rIdx) => {
        const text = Array.isArray(row) ? row[0] : "";
        const parsed = parseRosterMaintLine(text);
        const label = parsed ? parsed.label : `Row ${rIdx + 1}`;
        return `<tr data-maint-row-index="${rIdx}" class="${rIdx === activeRosterMonthIndex ? "active-roster-row" : ""}">
          <td data-form-col-key="maint_roster_text"><textarea data-auto-row-height data-maint-roster-row="${rIdx}" aria-label="${esc(label)}" spellcheck="false">${esc(text ?? "")}</textarea></td>
        </tr>`;
      }).join("");
      const topHeight = Number(formColumnWidths.maint_roster_top_height);
      const splitStyle = Number.isFinite(topHeight) ? ` style="grid-template-rows:${Math.max(0, topHeight)}px 6px 1fr"` : "";
      editor.innerHTML = `<div class="maint-sheet-title">Roster</div>
        <div class="maint-roster-split"${splitStyle}>
          <section class="maint-roster-pane">
            <div class="maint-pane-title">Monthly roster</div>
            <table class="maint-roster-table" data-form-table>
              <colgroup>
                <col data-form-col-key="maint_roster_text" data-form-col-default="760" />
              </colgroup>
              <tbody>${monthRows || '<tr><td class="maint-empty">No roster months</td></tr>'}</tbody>
            </table>
          </section>
          <div id="maint-roster-report-resizer" class="maint-roster-report-resizer" title="Drag to resize report height"></div>
          <section class="maint-roster-pane" id="maint-roster-report-pane">
            <div class="maint-pane-title" title="Drag left or right to move report">Roster report</div>
            <div id="maint-roster-report">${renderRosterMaintReport(rows)}</div>
          </section>
        </div>`;
      editor.querySelectorAll("textarea[data-maint-roster-row]").forEach((input) => {
        input.addEventListener("focus", () => setActiveRosterMonthIndex(Number(input.getAttribute("data-maint-roster-row"))));
        input.addEventListener("mousedown", () => setActiveRosterMonthIndex(Number(input.getAttribute("data-maint-roster-row"))));
        input.addEventListener("input", () => {
          activeRosterMonthIndex = Number(input.getAttribute("data-maint-roster-row"));
          setUnsavedChanges("餐單參數");
          refreshRosterMaintReport();
        });
      });
      editor.querySelectorAll(".maint-roster-table tr[data-maint-row-index]").forEach((row) => {
        row.addEventListener("mousedown", () => setActiveRosterMonthIndex(Number(row.getAttribute("data-maint-row-index"))));
      });
      bindMaintContextMenu(editor);
      applyFormColumnWidths(editor);
      attachFormColumnResizers(editor);
      bindAutoRowHeight(editor);
      attachRosterSplitResizer(editor);
      applyTableOffsets(editor);
      attachTableDragHandles(editor);
      applyRosterReportOffset();
      attachRosterReportDrag();
      const activeInput = editor.querySelector(`textarea[data-maint-roster-row="${activeRosterMonthIndex}"]`);
      activeInput?.focus({ preventScroll: true });
      activeInput?.closest("tr")?.scrollIntoView({ block: "nearest", inline: "nearest" });
    }

    function formatMaintTimeValue(sheetKey, rowIndex, colIndex, value, isInputEvent = false) {
      if (rowIndex === 0) return value;
      const s = String(value ?? "").trim();
      if (!s) return "";

      if (sheetKey === "overtime") {
        if (colIndex === 0) {
          if (isInputEvent) return value;
          const d = parseYmd(s);
          if (d) return dateDmy(d.year, d.month, d.day);
        } else if (colIndex === 1 || colIndex === 2) {
          if (isInputEvent) return value;
          const colon = s.match(/^(\d{1,2}):(\d{2})$/);
          if (colon) {
            const h = Number(colon[1]);
            const m = Number(colon[2]);
            if (h >= 0 && h <= 23 && m >= 0 && m <= 59) {
              return `${String(h).padStart(2, "0")}${String(m).padStart(2, "0")}`;
            }
          }
          const compact = s.match(/^(\d{1,4})$/);
          if (compact) {
            const raw = compact[1].padStart(4, "0");
            const h = Number(raw.slice(0, 2));
            const m = Number(raw.slice(2, 4));
            if (h >= 0 && h <= 23 && m >= 0 && m <= 59) {
              return `${String(h).padStart(2, "0")}${String(m).padStart(2, "0")}`;
            }
          }
        }
        return s;
      }

      if (sheetKey === "medical_appointments" && colIndex === 2) {
        if (isInputEvent) return value;
        const colon = s.match(/^(\d{1,2}):(\d{2})$/);
        if (colon) {
          const h = Number(colon[1]);
          const m = Number(colon[2]);
          if (h >= 0 && h <= 23 && m >= 0 && m <= 59) {
            return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
          }
        }
        const compact = s.match(/^(\d{1,4})$/);
        if (compact) {
          const raw = compact[1].padStart(4, "0");
          const h = Number(raw.slice(0, 2));
          const m = Number(raw.slice(2, 4));
          if (h >= 0 && h <= 23 && m >= 0 && m <= 59) {
            return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
          }
        }
      }

      return value;
    }

    function isMaintMoneyColumn(sheetKey, rowIndex, colIndex) {
      return sheetKey === "medical_appointments" && rowIndex > 0 && (colIndex === 4 || colIndex === 5);
    }

    function isPlainMoneyValue(value) {
      return /^\s*\d+(?:,\d{3})*(?:\.\d+)?\s*$/.test(String(value ?? ""));
    }

    function maintCellClass(sheetKey, rowIndex, colIndex, value) {
      const classes = [];
      if (isMaintMoneyColumn(sheetKey, rowIndex, colIndex) && isPlainMoneyValue(value)) {
        classes.push("maint-money-cell");
      }
      return classes.length ? ` class="${classes.join(" ")}"` : "";
    }

    function updateMaintInputFormatting(input, isInputEvent = false) {
      if (!input) return;
      const rowIndex = Number(input.getAttribute("data-maint-row"));
      const colIndex = Number(input.getAttribute("data-maint-col"));
      if (!Number.isInteger(rowIndex) || !Number.isInteger(colIndex)) return;
      input.value = formatMaintTimeValue(activeMaintSheetKey, rowIndex, colIndex, input.value, isInputEvent);
      const cell = input.closest("td");
      if (cell) {
        cell.classList.toggle("maint-money-cell", isMaintMoneyColumn(activeMaintSheetKey, rowIndex, colIndex) && isPlainMoneyValue(input.value));
      }
    }

    let currentMaintFilter = "";

    function renderMaintEditor() {
      const editor = document.getElementById("maint-editor");
      if (!editor) return;
      if (maintSheetPayload.sheet_key === "roster") {
        currentMaintFilter = "";
        renderRosterMaintEditor();
        return;
      }
      const rows = Array.isArray(maintSheetPayload.rows) ? maintSheetPayload.rows : [];
      const cols = maintColumnCount(rows);
      const title = MAINT_SHEET_LABELS[maintSheetPayload.sheet_key] || maintSheetPayload.display_name || "Sheet";
      const formKey = `maint_${maintSheetPayload.sheet_key || "sheet"}`;
      const colGroup = Array.from(
        { length: cols },
        (_, i) => `<col data-form-col-key="${formKey}_col_${i}" data-form-col-default="160" />`
      ).join("");
      const isShiftCodeCol = (cIdx) => {
        return rows.length > 0 && Array.isArray(rows[0]) && String(rows[0][cIdx]).trim() === "更碼";
      };
      
      let shiftCodeColIdx = undefined;
      for (let i = 0; i < cols; i++) {
        if (isShiftCodeCol(i)) {
          shiftCodeColIdx = i;
          break;
        }
      }

      let filterHtml = "";
      if (shiftCodeColIdx !== undefined) {
        const uniqueCodes = new Set();
        for (let i = 1; i < rows.length; i++) {
          if (Array.isArray(rows[i]) && rows[i][shiftCodeColIdx]) {
            uniqueCodes.add(String(rows[i][shiftCodeColIdx]).trim());
          }
        }
        const codes = Array.from(uniqueCodes).filter(Boolean).sort();
        filterHtml = `<select id="maint-table-filter" class="maint-filter-select" style="margin-left: 16px; padding: 4px 8px; font-size: 0.9em; border-radius: 4px; border: 1px solid var(--border); background: var(--bg); color: inherit; cursor: pointer;">
          <option value="">全部更碼 (All)</option>
          ${codes.map(c => `<option value="${esc(c)}" ${c === currentMaintFilter ? "selected" : ""}>${esc(c)}</option>`).join("")}
        </select>`;
      } else {
        currentMaintFilter = "";
      }

      const body = rows.map((row, rIdx) => {
        const cells = Array.from({ length: cols }, (_, cIdx) => {
          const value = formatMaintTimeValue(maintSheetPayload.sheet_key, rIdx, cIdx, Array.isArray(row) ? row[cIdx] : "");
          const resizeKey = rIdx === 0 ? ` data-form-col-key="${formKey}_col_${cIdx}"` : "";
          if (rIdx > 0 && isShiftCodeCol(cIdx)) {
            return `<td${resizeKey}${maintCellClass(maintSheetPayload.sheet_key, rIdx, cIdx, value)}><input type="text" data-maint-shift-code="1" data-maint-row="${rIdx}" data-maint-col="${cIdx}" value="${esc(value ?? "")}" spellcheck="false" autocomplete="off" /></td>`;
          }
          return `<td${resizeKey}${maintCellClass(maintSheetPayload.sheet_key, rIdx, cIdx, value)}><textarea data-auto-row-height data-maint-row="${rIdx}" data-maint-col="${cIdx}" spellcheck="false">${esc(value ?? "")}</textarea></td>`;
        }).join("");
        return `<tr data-maint-row-index="${rIdx}">${cells}</tr>`;
      }).join("");
      editor.innerHTML = `<div class="maint-sheet-title" style="display:flex;align-items:center;"><span>${esc(title)}</span>${filterHtml}</div>
        <table class="maint-table" data-form-table>
          <colgroup>${colGroup}</colgroup>
          <tbody>${body}</tbody>
        </table>`;
      bindMaintContextMenu(editor);
      applyFormColumnWidths(editor);
      attachFormColumnResizers(editor);
      bindAutoRowHeight(editor);
      editor.querySelectorAll("textarea[data-maint-row][data-maint-col], input[data-maint-row][data-maint-col]").forEach((input) => {
        input.addEventListener("input", () => updateMaintInputFormatting(input, true));
        input.addEventListener("blur", () => {
          updateMaintInputFormatting(input, false);
          if (input.tagName.toLowerCase() === "textarea") autoResizeTextarea(input);
        });
      });
      
      const filterSelect = editor.querySelector("#maint-table-filter");
      if (filterSelect && shiftCodeColIdx !== undefined) {
        const applyFilter = () => {
          const val = filterSelect.value;
          currentMaintFilter = val;
          editor.querySelectorAll("tr[data-maint-row-index]").forEach(tr => {
            const idx = Number(tr.getAttribute("data-maint-row-index"));
            if (idx === 0) return;
            if (!val) {
              tr.style.display = "";
              setTimeout(() => {
                tr.querySelectorAll("textarea[data-auto-row-height]").forEach(autoResizeTextarea);
              }, 0);
            } else {
              const input = tr.querySelector(`[data-maint-row="${idx}"][data-maint-col="${shiftCodeColIdx}"]`);
              const codeVal = input ? String(input.value).trim() : "";
              if (codeVal === val || codeVal === "") {
                tr.style.display = "";
                // Delay auto resize to ensure browser has applied display: "" and reflowed
                setTimeout(() => {
                  tr.querySelectorAll("textarea[data-auto-row-height]").forEach(autoResizeTextarea);
                }, 0);
              } else {
                tr.style.display = "none";
              }
            }
          });
        };
        filterSelect.addEventListener("change", applyFilter);
        if (currentMaintFilter) applyFilter();
      }

      applyTableOffsets(editor);
      attachTableDragHandles(editor);
    }

    function bindMaintContextMenu(editor) {
      if (!editor || editor.dataset.maintContextBound === "1") return;
      editor.dataset.maintContextBound = "1";
      editor.addEventListener("contextmenu", (ev) => {
        const row = ev.target && ev.target.closest ? ev.target.closest("tr[data-maint-row-index]") : null;
        const idx = row ? Number(row.getAttribute("data-maint-row-index")) : -1;
        showMaintRowMenu(ev, Number.isInteger(idx) ? idx : -1);
      });
    }

    function collectMaintRows() {
      const rows = Array.isArray(maintSheetPayload.rows) ? maintSheetPayload.rows.map((row) => Array.isArray(row) ? [...row] : []) : [];
      if (maintSheetPayload.sheet_key === "roster") {
        const rosterRows = [];
        document.querySelectorAll("#maint-editor textarea[data-maint-roster-row]").forEach((input) => {
          const r = Number(input.getAttribute("data-maint-roster-row"));
          if (!Number.isInteger(r) || r < 0) return;
          while (rosterRows.length <= r) rosterRows.push([]);
          rosterRows[r][0] = input.value;
        });
        while (rosterRows.length && !rosterRows[rosterRows.length - 1].some((cell) => cell != null && String(cell).trim() !== "")) rosterRows.pop();
        return rosterRows;
      }
      document.querySelectorAll("#maint-editor [data-maint-row][data-maint-col]").forEach((input) => {
        const r = Number(input.getAttribute("data-maint-row"));
        const c = Number(input.getAttribute("data-maint-col"));
        if (!Number.isInteger(r) || !Number.isInteger(c) || r < 0 || c < 0) return;
        while (rows.length <= r) rows.push([]);
        rows[r][c] = formatMaintTimeValue(activeMaintSheetKey, r, c, input.value);
      });
      for (const row of rows) {
        while (row.length && (row[row.length - 1] == null || String(row[row.length - 1]).trim() === "")) row.pop();
      }
      while (rows.length && !rows[rows.length - 1].some((cell) => cell != null && String(cell).trim() !== "")) rows.pop();
      return rows;
    }

    async function refreshMaintSheets() {
      try {
        const data = await loadMaintSheets();
        maintSheets = Array.isArray(data.sheets) ? data.sheets : [];
        renderMaintMenu();
        if (!activeMaintSheetKey && maintSheets.length) activeMaintSheetKey = maintSheets[0].sheet_key;
      } catch (e) {
        showMaintError(String(e.message || e));
      }
    }

    async function openMaintSheet(sheetKey, openTree = true) {
      if (!sheetKey) return;
      if (sheetKey !== activeMaintSheetKey && !(await resolveUnsavedBeforeLeaving())) return;
      setActivePanel("maint");
      if (openTree) setMaintMenuTreeOpen(true);
      activeMaintSheetKey = sheetKey;
      showMaintError("");
      setMaintStatus("Loading...");
      try {
        maintSheetPayload = await loadMaintSheet(sheetKey);
        if (!Array.isArray(maintSheetPayload.rows)) maintSheetPayload.rows = [];
        if (sheetKey === "roster") {
          const [payroll, overtime, holidays, medical] = await Promise.all([
            loadMaintSheet("payroll_times").catch(() => ({ rows: [] })),
            loadMaintSheet("overtime").catch(() => ({ rows: [] })),
            loadMaintSheet("public_holidays").catch(() => ({ rows: [] })),
            loadMaintSheet("medical_appointments").catch(() => ({ rows: [] })),
          ]);
          rosterReportSources = {
            payroll_times: Array.isArray(payroll.rows) ? payroll.rows : [],
            overtime: Array.isArray(overtime.rows) ? overtime.rows : [],
            public_holidays: Array.isArray(holidays.rows) ? holidays.rows : [],
            medical_appointments: Array.isArray(medical.rows) ? medical.rows : [],
          };
        }
        renderMaintEditor();
        clearUnsavedChanges("餐單參數");
        setMaintStatus(`${maintSheetPayload.rows.length} rows`);
      } catch (e) {
        showMaintError(String(e.message || e));
        setMaintStatus("");
      }
      setActivePanel("maint", false);
    }

    async function saveMaintEditor() {
      if (!activeMaintSheetKey) return;
      showMaintError("");
      setMaintStatus("Saving...");
      try {
        const rows = collectMaintRows();
        const result = await persistMaintSheet(activeMaintSheetKey, rows);
        maintSheetPayload.rows = rows;
        clearUnsavedChanges("餐單參數");
        setMaintStatus(`Save ${menuLabel(activeMaintSheetKey)} ${new Date().toLocaleTimeString("en-GB")}`);
        await refreshMaintSheets();
      } catch (e) {
        showMaintError(String(e.message || e));
        setMaintStatus("");
      }
    }

    async function importActiveMaintSheet() {
      if (!activeMaintSheetKey) return;
      showMaintError("");
      setMaintStatus("Importing...");
      try {
        maintSheetPayload = await importMaintSheet(activeMaintSheetKey);
        if (!Array.isArray(maintSheetPayload.rows)) maintSheetPayload.rows = [];
        renderMaintEditor();
        clearUnsavedChanges("餐單參數");
        setMaintStatus(`Imported ${maintSheetPayload.rows.length} rows`);
        await refreshMaintSheets();
      } catch (e) {
        showMaintError(String(e.message || e));
        setMaintStatus("");
      }
    }

    async function importLiveRuntimeInputs() {
      const btn = document.getElementById("runtime-import");
      if (btn) btn.disabled = true;
      showMaintError("");
      setMaintStatus("Importing live inputs...");
      try {
        const payload = await importRuntimeInputs();
        await refreshMaintSheets();
        if (activeMaintSheetKey === "roster" || activeMaintSheetKey === "overtime") {
          await openMaintSheet(activeMaintSheetKey, false);
        }
        clearUnsavedChanges("餐單參數");
        const counts = (payload.sheets || [])
          .map((sheet) => `${menuLabel(sheet.sheet_key)} ${sheet.row_count || 0}`)
          .join(", ");
        setMaintStatus(`Imported ${counts || "live inputs"}`);
      } catch (e) {
        showMaintError(String(e.message || e));
        setMaintStatus("");
      } finally {
        if (btn) btn.disabled = false;
      }
    }

    function diagnosticMark(ok) {
      return ok ? "OK" : "Missing";
    }

    function diagnosticMarkClass(ok) {
      return ok ? "diag-ok" : "diag-missing";
    }

    function diagnosticRequirementCell(row, key, patternKey) {
      if (row && row.requires_shift_schedule === false) {
        return '<td class="diag-na">N/A</td>';
      }
      const ok = !!(row && row[key]);
      const pattern = row && row[patternKey] ? row[patternKey] : "";
      const patterns = Array.isArray(pattern) ? pattern.join(", ") : pattern;
      return `<td class="${diagnosticMarkClass(ok)}">${diagnosticMark(ok)}${patterns ? ` (${esc(patterns)})` : ""}</td>`;
    }

    function renderDiagnostics(data) {
      const box = document.getElementById("diagnostics-out");
      if (!box) return;
      const summary = data && data.summary ? data.summary : {};
      const tables = Array.isArray(data && data.tables) ? data.tables : [];
      const issues = Array.isArray(data && data.issues) ? data.issues : [];
      const coverage = Array.isArray(data && data.code_coverage) ? data.code_coverage : [];
      const months = data && data.roster && Array.isArray(data.roster.months) ? data.roster.months : [];
      const status = String(summary.status || "unknown");
      const tableRows = tables.map((row) => `<tr>
        <td>${esc(row.display_name || row.sheet_key)}</td>
        <td>${esc(row.sheet_key)}</td>
        <td>${esc(row.row_count)}</td>
        <td>${esc(row.updated_at || "")}</td>
      </tr>`).join("");
      const monthRows = months.map((row) => `<tr>
        <td>${esc(row.label)}</td>
        <td>${esc(row.days_found)}</td>
        <td>${esc(row.days_expected)}</td>
        <td>${esc((row.missing_days || []).join(", "))}</td>
      </tr>`).join("");
      const issueRows = issues.map((row) => `<tr>
        <td class="diag-severity-${esc(row.severity)}">${esc(row.severity)}</td>
        <td>${esc(row.area)}</td>
        <td>${esc(row.message)}</td>
      </tr>`).join("");
      const coverageRows = coverage.map((row) => `<tr>
        <td>${esc(row.code)}</td>
        <td>${esc(row.days)}</td>
        <td class="${diagnosticMarkClass(row.meal_time)}">${diagnosticMark(row.meal_time)}${row.meal_time_pattern ? ` (${esc(row.meal_time_pattern)})` : ""}</td>
        ${diagnosticRequirementCell(row, "payroll_time", "payroll_time_pattern")}
        ${diagnosticRequirementCell(row, "schedule_grid", "schedule_grid_patterns")}
      </tr>`).join("");
      const colGroup = (prefix, widths) => `<colgroup>${widths.map((width, idx) => `<col data-form-col-key="${prefix}_${idx}" data-form-col-default="${width}" />`).join("")}</colgroup>`;
      const th = (key, text) => `<th data-form-col-key="${key}">${text}</th>`;
      box.innerHTML = `<div class="diag-summary diag-status-${esc(status)}">
          <div><strong>Status</strong><span>${esc(status.toUpperCase())}</span></div>
          <div><strong>Issues</strong><span>${esc(summary.issues || 0)}</span></div>
          <div><strong>Errors</strong><span>${esc(summary.errors || 0)}</span></div>
          <div><strong>Warnings</strong><span>${esc(summary.warnings || 0)}</span></div>
          <div><strong>Roster codes</strong><span>${esc(summary.roster_codes || 0)}</span></div>
          <div><strong>Missing shift times</strong><span>${esc(summary.missing_payroll_time_codes || 0)}</span></div>
          <div><strong>Missing schedules</strong><span>${esc(summary.missing_schedule_grid_codes || 0)}</span></div>
        </div>
        <div class="diag-report-body">
          <h2 class="diag-report-title">Roster Code Coverage</h2>
          <table class="diag-table" data-form-table>${colGroup("diag_coverage", [150, 90, 230, 260, 360])}<thead><tr>${th("diag_coverage_0", "Code")}${th("diag_coverage_1", "Days")}${th("diag_coverage_2", "Meal Time")}${th("diag_coverage_3", "Shift Time")}${th("diag_coverage_4", "Schedule Grid")}</tr></thead><tbody>${coverageRows || '<tr><td colspan="5" class="maint-empty">No roster codes</td></tr>'}</tbody></table>
          <h2 class="diag-report-title">Issues</h2>
          <table class="diag-table" data-form-table>${colGroup("diag_issues", [120, 180, 520])}<thead><tr>${th("diag_issues_0", "Severity")}${th("diag_issues_1", "Area")}${th("diag_issues_2", "Message")}</tr></thead><tbody>${issueRows || '<tr><td colspan="3" class="maint-empty">No issues</td></tr>'}</tbody></table>
          <h2 class="diag-report-title">Roster Months</h2>
          <table class="diag-table" data-form-table>${colGroup("diag_months", [140, 120, 130, 360])}<thead><tr>${th("diag_months_0", "Month")}${th("diag_months_1", "Days Found")}${th("diag_months_2", "Days Expected")}${th("diag_months_3", "Missing Days")}</tr></thead><tbody>${monthRows || '<tr><td colspan="4" class="maint-empty">No roster months</td></tr>'}</tbody></table>
          <h2 class="diag-report-title">SQLite Tables</h2>
          <table class="diag-table" data-form-table>${colGroup("diag_tables", [170, 180, 90, 210])}<thead><tr>${th("diag_tables_0", "Table")}${th("diag_tables_1", "Key")}${th("diag_tables_2", "Rows")}${th("diag_tables_3", "Updated")}</tr></thead><tbody>${tableRows}</tbody></table>
        </div>`;
      applyFormColumnWidths(box);
      attachFormColumnResizers(box);
      applyTableOffsets(box);
      attachTableDragHandles(box);
    }

    async function refreshDiagnostics() {
      const status = document.getElementById("diagnostics-status");
      const err = document.getElementById("diagnostics-err");
      if (status) status.textContent = "Loading...";
      if (err) {
        err.textContent = "";
        err.style.display = "none";
      }
      try {
        diagnosticsPayload = await loadDiagnostics();
        renderDiagnostics(diagnosticsPayload);
        if (status) status.textContent = diagnosticsPayload.generated_at ? `Updated ${diagnosticsPayload.generated_at}` : "";
      } catch (e) {
        if (err) {
          err.textContent = String(e.message || e);
          err.style.display = "block";
        }
        if (status) status.textContent = "";
      }
    }

