    const SCHEDULE_GRID_NEW_SHIFT_FILTER = "__new_shift_code__";
    let scheduleGridNewShiftBatchId = "";
    let scheduleGridNewShiftStartIndex = -1;
    let scheduleGridNewShiftCount = 0;
    let scheduleGridSkipNextRenderSort = false;
    let shiftAnalysisSuppressNextClickClear = false;
    let shiftCodeAnalysisRows = [];
    const maintDirectKeyTimers = new WeakMap();

    function emptyMaintRow(rows = null) {
      if (activeMaintSheetKey === "roster") return [""];
      const cols = maintColumnCount(rows || collectMaintRows());
      return Array.from({ length: cols }, () => "");
    }

    function setMaintRowsAndRender(rows, options = {}) {
      if (activeMaintSheetKey === "schedule_grid" && options.preserveOrder) {
        scheduleGridSkipNextRenderSort = true;
      }
      maintSheetPayload.rows = rows;
      renderMaintEditor();
    }

    function showMaintRowMenu(ev, rowIndex) {
      const menu = document.getElementById("maint-row-menu");
      if (!menu) return;
      ev.preventDefault();
      menu.hidden = false;
      menu.setAttribute("data-maint-row-index", Number.isInteger(rowIndex) ? String(rowIndex) : "-1");
      const newVersion = menu.querySelector('[data-maint-row-action="new-version"]');
      const deleteVersion = menu.querySelector('[data-maint-row-action="delete-version"]');
      const addShiftCode = menu.querySelector('[data-maint-row-action="add-shift-code"]');
      const versionActionVisible = activeMaintSheetKey === "schedule_grid" && Number.isInteger(rowIndex) && rowIndex > 0;
      const scheduleGridVisible = activeMaintSheetKey === "schedule_grid";
      if (addShiftCode) {
        addShiftCode.style.display = scheduleGridVisible ? "" : "none";
      }
      if (newVersion) {
        newVersion.style.display = versionActionVisible ? "" : "none";
      }
      if (deleteVersion) {
        deleteVersion.style.display = versionActionVisible ? "" : "none";
      }
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
      if (action === "new-version") {
        createScheduleGridVersion(rowIndex);
        return;
      }
      if (action === "delete-version") {
        deleteScheduleGridVersion(rowIndex);
        return;
      }
      if (action === "add-shift-code") {
        addScheduleGridShiftCodeRows(rowIndex);
        return;
      }
      if (activeMaintSheetKey === "schedule_grid" && (action === "insert" || action === "append")) {
        applyScheduleGridRowAction(action, rowIndex);
        return;
      }
      // Append 上限一行空行：已有尾部空行就唔加新行，cursor 直接跳過去（save 時先 trim）。
      if (action === "append") {
        const blankIdx = trailingBlankMaintRowIndex();
        if (blankIdx >= 0) {
          const input = document.querySelector(
            `#maint-editor tr[data-maint-row-index="${blankIdx}"] textarea, #maint-editor tr[data-maint-row-index="${blankIdx}"] input`
          );
          if (input) {
            if (activeMaintSheetKey === "roster") beginRosterCellEdit(input);
            else input.focus();
          }
          return;
        }
      }
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
      if (activeMaintSheetKey === "roster") {
        const focusIdx = action === "append"
          ? rows.length - 1
          : Math.max(0, Math.min(idx, rows.length - 1));
        activeRosterMonthIndex = focusIdx;
        formColumnWidths.maint_roster_month_index = focusIdx;
        setMaintRowsAndRender(rows);
        const input = document.querySelector(`#maint-editor textarea[data-maint-roster-row="${focusIdx}"]`);
        if (input && (action === "insert" || action === "append")) {
          beginRosterCellEdit(input);
        } else if (input) {
          input.focus();
        }
        return;
      }
      if (activeMaintSheetKey === "schedule_grid" && action === "delete") {
        setMaintRowsAndRender(rows, { preserveOrder: true });
        return;
      }
      if (!applyMaintRowsFast(rows, action, idx)) setMaintRowsAndRender(rows);
    }

    function scheduleGridFilledEmptyRow(rows, insertAt, sourceRowIndex = null) {
      const row = emptyMaintRow(rows);
      const cols = scheduleGridColumnIndexes(rows);
      if (cols.code < 0) return row;
      const references = [];
      if (Number.isInteger(sourceRowIndex) && sourceRowIndex > 0 && Array.isArray(rows[sourceRowIndex])) {
        references.push(rows[sourceRowIndex]);
      }
      if (Array.isArray(rows[insertAt]) && insertAt > 0) references.push(rows[insertAt]);
      if (Array.isArray(rows[insertAt - 1]) && insertAt - 1 > 0) references.push(rows[insertAt - 1]);
      const ref = references.find((item) => String(item[cols.code] || "").trim()) || null;
      if (ref) {
        row[cols.code] = String(ref[cols.code] || "").trim();
        if (cols.effective >= 0) row[cols.effective] = String(ref[cols.effective] || "").trim();
      }
      if (!ref && currentMaintFilter && currentMaintFilter !== SCHEDULE_GRID_NEW_SHIFT_FILTER) {
        row[cols.code] = currentMaintFilter;
        if (cols.effective >= 0) {
          if (currentMaintEffectiveFilter) {
            row[cols.effective] = currentMaintEffectiveFilter === "__blank__" ? "" : currentMaintEffectiveFilter;
          } else {
            const sameCodeRef = rows
              .slice(1, insertAt)
              .reverse()
              .find((item) => Array.isArray(item) && String(item[cols.code] || "").trim() === currentMaintFilter);
            if (sameCodeRef) row[cols.effective] = String(sameCodeRef[cols.effective] || "").trim();
          }
        }
      }
      return row;
    }

    function scheduleGridAppendIndex(rows, cols) {
      if (!currentMaintFilter || currentMaintFilter === SCHEDULE_GRID_NEW_SHIFT_FILTER || cols.code < 0) return rows.length;
      let lastMatch = -1;
      const filterEffective = currentMaintEffectiveFilter || "";
      for (let i = 1; i < rows.length; i++) {
        const row = rows[i];
        if (!Array.isArray(row)) continue;
        if (String(row[cols.code] || "").trim() !== currentMaintFilter) continue;
        if (filterEffective && cols.effective >= 0) {
          const rowEffective = String(row[cols.effective] || "").trim() || "__blank__";
          if (rowEffective !== filterEffective) continue;
        }
        lastMatch = i;
      }
      return lastMatch >= 0 ? lastMatch + 1 : rows.length;
    }

    function applyScheduleGridRowAction(action, rowIndex) {
      const rows = collectMaintRows();
      const cols = scheduleGridColumnIndexes(rows);
      const idx = Number.isInteger(rowIndex) && rowIndex >= 0 ? rowIndex : rows.length;
      const insertAt = action === "append" ? scheduleGridAppendIndex(rows, cols) : Math.max(1, Math.min(idx, rows.length));
      const sourceRowIndex = action === "insert" ? idx : null;
      const newRow = scheduleGridFilledEmptyRow(rows, insertAt, sourceRowIndex);
      const inNewShiftBatch = scheduleGridNewShiftBatchId
        && insertAt >= scheduleGridNewShiftStartIndex
        && insertAt <= scheduleGridNewShiftStartIndex + scheduleGridNewShiftCount;
      rows.splice(insertAt, 0, newRow);
      if (inNewShiftBatch) scheduleGridNewShiftCount += 1;
      setUnsavedChanges("餐單參數");
      setMaintRowsAndRender(rows, { preserveOrder: true });
      if (inNewShiftBatch) {
        markScheduleGridNewShiftBatch(scheduleGridNewShiftStartIndex, scheduleGridNewShiftCount, scheduleGridNewShiftBatchId, false);
      }
      const focusCol = cols.time >= 0 ? cols.time : Math.max(cols.code, 0);
      const focus = scheduleGridInput(insertAt, focusCol);
      if (focus) focusMaintCell(focus, true);
    }

    // 行位表「停用」欄係 logical field：唔會當一般欄 render，改為每行一粒 toggle + 成行 dim。
    const SCHEDULE_GRID_DISABLED_HEADER = "停用";

    function scheduleGridDisabledColIdx() {
      if (maintSheetPayload.sheet_key !== "schedule_grid") return -1;
      const header = Array.isArray(maintSheetPayload.rows && maintSheetPayload.rows[0]) ? maintSheetPayload.rows[0] : [];
      return header.findIndex((cell) => String(cell || "").trim() === SCHEDULE_GRID_DISABLED_HEADER);
    }

    function isScheduleGridRowDisabled(row) {
      const idx = scheduleGridDisabledColIdx();
      if (idx < 0 || !Array.isArray(row)) return false;
      return String(row[idx] || "").trim() !== "";
    }

    function maintRowHtml(row, rIdx, cols, formKey, isShiftCodeCol) {
      const disabledColIdx = scheduleGridDisabledColIdx();
      const toggleCell = disabledColIdx < 0
        ? ""
        : (rIdx === 0
          ? `<td data-form-col-key="${formKey}_col_off"></td>`
          : `<td class="maint-off-cell"><button type="button" class="maint-off-toggle" data-maint-disable-row="${rIdx}" title="停用／啟用呢格行位（停用＝當日冇咗，時長會自動吸收）">${isScheduleGridRowDisabled(row) ? "Enable" : "Disable"}</button></td>`);
      return toggleCell + Array.from({ length: cols }, (_, cIdx) => {
        if (cIdx === disabledColIdx) return "";
        const value = formatMaintTimeValue(maintSheetPayload.sheet_key, rIdx, cIdx, Array.isArray(row) ? row[cIdx] : "");
        const resizeKey = rIdx === 0 ? ` data-form-col-key="${formKey}_col_${cIdx}"` : "";
        if (rIdx > 0 && isShiftCodeCol(cIdx)) {
          return `<td${resizeKey}${maintCellClass(maintSheetPayload.sheet_key, rIdx, cIdx, value)}><input type="text" data-maint-shift-code="1" data-maint-row="${rIdx}" data-maint-col="${cIdx}" value="${esc(value ?? "")}" spellcheck="false" autocomplete="off" readonly /></td>`;
        }
        return `<td${resizeKey}${maintCellClass(maintSheetPayload.sheet_key, rIdx, cIdx, value)}><textarea data-auto-row-height data-maint-row="${rIdx}" data-maint-col="${cIdx}" spellcheck="false" readonly>${esc(value ?? "")}</textarea></td>`;
      }).join("");
    }

    function bindMaintRowInputs(root) {
      root.querySelectorAll("textarea[data-maint-row][data-maint-col], input[data-maint-row][data-maint-col]").forEach((input) => {
        input.readOnly = true;
        const cell = input.closest("td");
        if (cell && cell.dataset.maintCellFocusBound !== "1") {
          cell.dataset.maintCellFocusBound = "1";
          cell.addEventListener("mousedown", (ev) => {
            if (ev.target !== cell) return;
            const cellInput = cell.querySelector("[data-maint-row][data-maint-col]");
            if (!cellInput) return;
            ev.preventDefault();
            focusMaintCell(cellInput, true);
          });
        }
        input.addEventListener("input", () => {
          updateMaintInputFormatting(input, true);
          if (activeMaintSheetKey === "schedule_grid") setUnsavedChanges("餐單參數");
        });
        input.addEventListener("blur", () => {
          endMaintCellEdit(input);
          updateMaintInputFormatting(input, false);
          if (input.tagName.toLowerCase() === "textarea") autoResizeTextarea(input);
        });
        input.addEventListener("mousedown", (ev) => {
          if (ev.detail >= 2) beginMaintCellEdit(input);
        });
        input.addEventListener("dblclick", () => beginMaintCellEdit(input));
        input.addEventListener("compositionstart", () => {
          if (input.readOnly) {
            beginMaintCellEdit(input, true);
          } else if (input.dataset.maintKeyboardSelected === "1" && input.dataset.maintEditing !== "1") {
            beginMaintCellEdit(input, true);
          }
          const timer = maintDirectKeyTimers.get(input);
          if (timer) {
            clearTimeout(timer);
            maintDirectKeyTimers.delete(input);
          }
          delete input.dataset.maintPendingDirectKey;
          delete input.dataset.maintReplaceOnComposition;
        });
        input.addEventListener("beforeinput", (ev) => {
          if (input.dataset.maintKeyboardSelected !== "1" || input.dataset.maintEditing === "1") return;
          if (String(ev.inputType || "").startsWith("insert")) {
            beginMaintCellEdit(input, true);
          }
        });
        input.addEventListener("keydown", handleMaintCellKeydown);
      });
      bindAutoRowHeight(root);
    }

    function maintCellInputFrom(input, rowDelta, colDelta) {
      const row = input && input.closest ? input.closest("tr[data-maint-row-index]") : null;
      const cell = input && input.closest ? input.closest("td") : null;
      if (!row || !cell) return null;
      const rows = Array.from(document.querySelectorAll("#maint-editor tr[data-maint-row-index]"))
        .filter((item) => item.style.display !== "none");
      const rowPos = rows.indexOf(row);
      const targetRow = rows[rowPos + rowDelta];
      const targetCell = (targetRow || row).cells[cell.cellIndex + colDelta];
      return targetCell ? targetCell.querySelector("[data-maint-row][data-maint-col]") : null;
    }

    function focusMaintCell(input, fromKeyboard = false) {
      if (!input) return;
      delete input.dataset.maintEditing;
      delete input.dataset.maintReplaceOnComposition;
      delete input.dataset.maintPendingDirectKey;
      if (fromKeyboard) {
        input.readOnly = false;
        input.dataset.maintKeyboardSelected = "1";
      } else {
        input.readOnly = true;
        delete input.dataset.maintKeyboardSelected;
      }
      input.focus();
      input.scrollIntoView({ block: "nearest", inline: "nearest" });
    }

    function textareaCaretTop(input, position) {
      const style = window.getComputedStyle(input);
      const mirror = document.createElement("div");
      [
        "boxSizing", "fontFamily", "fontSize", "fontWeight", "fontStyle", "letterSpacing",
        "lineHeight", "paddingTop", "paddingRight", "paddingBottom", "paddingLeft",
        "borderTopWidth", "borderRightWidth", "borderBottomWidth", "borderLeftWidth",
        "textTransform", "wordSpacing", "textIndent", "tabSize", "wordBreak", "overflowWrap",
      ].forEach((name) => {
        mirror.style[name] = style[name];
      });
      mirror.style.position = "absolute";
      mirror.style.visibility = "hidden";
      mirror.style.left = "-9999px";
      mirror.style.top = "0";
      mirror.style.width = `${input.clientWidth}px`;
      mirror.style.whiteSpace = "pre-wrap";
      mirror.style.overflow = "hidden";
      mirror.textContent = String(input.value || "").slice(0, position).replace(/\n$/, "\n ");
      const marker = document.createElement("span");
      marker.textContent = "\u200b";
      mirror.appendChild(marker);
      document.body.appendChild(mirror);
      const top = marker.offsetTop;
      mirror.remove();
      return top;
    }

    // roster 編輯器（planner-maint-editor.js）都共用呢對 caret helper。
    function textareaShouldKeepArrow(input, key) {
      if (!input || !input.tagName || input.tagName.toLowerCase() !== "textarea") return false;
      if (input.selectionStart !== input.selectionEnd) return true;
      const pos = Number.isInteger(input.selectionStart) ? input.selectionStart : 0;
      const firstTop = textareaCaretTop(input, 0);
      const caretTop = textareaCaretTop(input, pos);
      const lastTop = textareaCaretTop(input, String(input.value || "").length);
      const style = window.getComputedStyle(input);
      const fontSize = parseFloat(style.fontSize) || 16;
      const lineHeight = parseFloat(style.lineHeight) || fontSize * 1.2;
      const tolerance = Math.max(2, lineHeight * 0.25);
      if (key === "ArrowUp") return caretTop > firstTop + tolerance;
      if (key === "ArrowDown") return caretTop < lastTop - tolerance;
      return false;
    }

    function maintInputClipboardValue(input) {
      return input ? String(input.value ?? "") : "";
    }

    function pasteMaintInputValue(input, value) {
      if (!input) return false;
      input.value = value == null ? "" : String(value);
      updateMaintInputFormatting(input, false);
      syncScheduleGridNewShiftBatchFromCell(input);
      syncScheduleGridEffectiveDateFromCell(input);
      updateScheduleGridDurationsFromCell(input);
      if (input.tagName.toLowerCase() === "textarea") autoResizeTextarea(input);
      input.dispatchEvent(new Event("input", { bubbles: true }));
      return true;
    }

    function pasteMaintClipboard(startInput, text) {
      const matrix = clipboardMatrix(text);
      if (!matrix.length) return;
      let lastInput = startInput;
      matrix.forEach((values, rowIdx) => {
        values.forEach((value, colIdx) => {
          const input = maintCellInputFrom(startInput, rowIdx, colIdx);
          if (!input) return;
          if (pasteMaintInputValue(input, value)) lastInput = input;
        });
      });
      focusMaintCell(lastInput);
    }

    function beginMaintCellEdit(input, replaceValue = false) {
      if (!input) return;
      delete input.dataset.maintKeyboardSelected;
      const rowIndex = Number(input.getAttribute("data-maint-row"));
      const colIndex = Number(input.getAttribute("data-maint-col"));
      input.dataset.maintOriginalValue = input.value;
      if (activeMaintSheetKey === "schedule_grid") {
        const rows = Array.isArray(maintSheetPayload.rows) ? maintSheetPayload.rows : [];
        const cols = scheduleGridColumnIndexes(rows);
        const row = Number.isInteger(rowIndex) && Array.isArray(rows[rowIndex]) ? rows[rowIndex] : null;
        if (row && (colIndex === cols.code || colIndex === cols.effective)) {
          input.dataset.maintOriginalGroupCode = String(row[cols.code] || "").trim();
          input.dataset.maintOriginalGroupEffective = scheduleGridRowEffective(row, cols);
        }
      }
      if (isScheduleGridEffectiveCol(colIndex)) {
        input.dataset.maintOriginalEffective = normaliseScheduleGridEffectiveValue(input.value);
      }
      input.readOnly = false;
      input.dataset.maintEditing = "1";
      input.dataset.maintReplaceOnComposition = replaceValue ? "1" : "";
      input.focus();
      if (replaceValue) input.value = "";
      if (typeof input.setSelectionRange === "function") {
        const pos = replaceValue ? 0 : String(input.value || "").length;
        input.setSelectionRange(pos, pos);
      }
    }

    function endMaintCellEdit(input, options = {}) {
      if (!input) return;
      const wasEditing = input.dataset.maintEditing === "1";
      if (!wasEditing) {
        if (input.tagName.toLowerCase() === "textarea") autoResizeTextarea(input);
        return;
      }
      if (options.cancel) {
        input.value = input.dataset.maintOriginalValue || "";
        input.readOnly = true;
        delete input.dataset.maintEditing;
        delete input.dataset.maintOriginalValue;
        delete input.dataset.maintOriginalEffective;
        delete input.dataset.maintOriginalGroupCode;
        delete input.dataset.maintOriginalGroupEffective;
        delete input.dataset.maintReplaceOnComposition;
        delete input.dataset.maintPendingDirectKey;
        const timer = maintDirectKeyTimers.get(input);
        if (timer) clearTimeout(timer);
        maintDirectKeyTimers.delete(input);
        if (input.tagName.toLowerCase() === "textarea") autoResizeTextarea(input);
        return;
      }
      updateMaintInputFormatting(input, false);
      syncScheduleGridNewShiftBatchFromCell(input);
      syncScheduleGridEffectiveDateFromCell(input);
      updateScheduleGridDurationsFromCell(input);
      input.readOnly = true;
      delete input.dataset.maintEditing;
      delete input.dataset.maintOriginalValue;
      delete input.dataset.maintOriginalEffective;
      delete input.dataset.maintOriginalGroupCode;
      delete input.dataset.maintOriginalGroupEffective;
      delete input.dataset.maintReplaceOnComposition;
      delete input.dataset.maintPendingDirectKey;
      const timer = maintDirectKeyTimers.get(input);
      if (timer) clearTimeout(timer);
      maintDirectKeyTimers.delete(input);
      if (input.tagName.toLowerCase() === "textarea") autoResizeTextarea(input);
    }

    function moveMaintActiveCell(input, key) {
      const delta = {
        ArrowUp: [-1, 0],
        ArrowDown: [1, 0],
        ArrowLeft: [0, -1],
        ArrowRight: [0, 1],
      }[key];
      if (!delta) return false;
      const next = maintCellInputFrom(input, delta[0], delta[1]);
      if (!next) return false;
      if (input.dataset) input.dataset.skipAutosaveOnce = "1";
      focusMaintCell(next, true);
      return true;
    }

    function handleMaintCellKeydown(ev) {
      const input = ev.currentTarget;
      if (!input) return;
      if (input.dataset.maintEditing === "1") {
        if (ev.key === "Enter") {
          ev.preventDefault();
          const next = maintCellInputFrom(input, 1, 0);
          if (next && input.dataset) input.dataset.skipAutosaveOnce = "1";
          endMaintCellEdit(input);
          focusMaintCell(next || input, true);
        } else if (ev.key === "Escape") {
          ev.preventDefault();
          endMaintCellEdit(input, { cancel: true });
          input.focus();
        } else if (ev.key === "Tab") {
          ev.preventDefault();
          const next = maintCellInputFrom(input, 0, ev.shiftKey ? -1 : 1) || maintCellInputFrom(input, ev.shiftKey ? -1 : 1, 0);
          if (input.dataset) input.dataset.skipAutosaveOnce = "1";
          endMaintCellEdit(input);
          focusMaintCell(next || input, true);
        } else if (ev.key === "ArrowUp" || ev.key === "ArrowDown") {
          if (textareaShouldKeepArrow(input, ev.key)) return;
          ev.preventDefault();
          const next = maintCellInputFrom(input, ev.key === "ArrowUp" ? -1 : 1, 0);
          if (next && input.dataset) input.dataset.skipAutosaveOnce = "1";
          endMaintCellEdit(input);
          focusMaintCell(next || input, true);
        }
        return;
      }
      if (ev.key === "Tab") {
        ev.preventDefault();
        const next = maintCellInputFrom(input, 0, ev.shiftKey ? -1 : 1) || maintCellInputFrom(input, ev.shiftKey ? -1 : 1, 0);
        if (input.dataset) input.dataset.skipAutosaveOnce = "1";
        focusMaintCell(next || input, true);
        return;
      }
      if (moveMaintActiveCell(input, ev.key)) {
        ev.preventDefault();
        return;
      }
      if (ev.key === "F2") {
        ev.preventDefault();
        beginMaintCellEdit(input);
        return;
      }
      if (ev.key === "Delete") {
        ev.preventDefault();
        input.value = "";
        updateMaintInputFormatting(input, false);
        if (input.tagName.toLowerCase() === "textarea") autoResizeTextarea(input);
        input.dispatchEvent(new Event("input", { bubbles: true }));
        return;
      }
      if (ev.key === "Enter") {
        ev.preventDefault();
        const next = maintCellInputFrom(input, 1, 0);
        if (next && input.dataset) input.dataset.skipAutosaveOnce = "1";
        if (next) focusMaintCell(next, true);
        return;
      }
      if ((ev.isComposing || ev.key === "Process") && !ev.ctrlKey && !ev.altKey && !ev.metaKey) {
        beginMaintCellEdit(input, true);
        return;
      }
      if (input.dataset.maintKeyboardSelected === "1" && ev.key.length === 1 && !ev.ctrlKey && !ev.altKey && !ev.metaKey) {
        return;
      }
      if (ev.key.length === 1 && !ev.ctrlKey && !ev.altKey && !ev.metaKey) {
        beginMaintCellEdit(input, true);
      }
    }

    function reindexMaintRowsFrom(startIdx) {
      document.querySelectorAll("#maint-editor tr[data-maint-row-index]").forEach((tr) => {
        const oldIdx = Number(tr.getAttribute("data-maint-row-index"));
        if (!Number.isInteger(oldIdx) || oldIdx < startIdx) return;
        const prevCount = tr.previousElementSibling
          ? Number(tr.previousElementSibling.getAttribute("data-maint-row-index")) + 1
          : oldIdx;
        const nextIdx = Number.isInteger(prevCount) ? prevCount : oldIdx;
        tr.setAttribute("data-maint-row-index", String(nextIdx));
        tr.querySelectorAll("[data-maint-row]").forEach((input) => input.setAttribute("data-maint-row", String(nextIdx)));
      });
    }

    function trailingBlankMaintRowIndex() {
      const trs = document.querySelectorAll("#maint-editor tr[data-maint-row-index]");
      const last = trs[trs.length - 1];
      if (!last) return -1;
      const inputs = last.querySelectorAll("[data-maint-row][data-maint-col], textarea[data-maint-roster-row]");
      if (!inputs.length) return -1;
      for (const input of inputs) {
        if (String(input.value || "").trim() !== "") return -1;
      }
      const idx = Number(last.getAttribute("data-maint-row-index"));
      return Number.isInteger(idx) && idx > 0 ? idx : -1;
    }

    function applyMaintRowsFast(rows, action, idx) {
      if (activeMaintSheetKey === "roster") return false;
      const table = document.querySelector("#maint-editor table.maint-table");
      const tbody = table && table.tBodies ? table.tBodies[0] : null;
      if (!tbody) return false;
      const formKey = `maint_${maintSheetPayload.sheet_key || "sheet"}`;
      const cols = maintColumnCount(rows);
      const currentCols = table.querySelectorAll("col[data-form-col-key]").length || cols;
      if (cols !== currentCols) return false;
      const header = Array.isArray(rows[0]) ? rows[0] : [];
      const shiftCodeColIdx = header.findIndex((cell) => String(cell || "").trim() === "更碼");
      const isShiftCodeCol = (cIdx) => cIdx === shiftCodeColIdx;
      maintSheetPayload.rows = rows;

      if (action === "delete") {
        const tr = tbody.querySelector(`tr[data-maint-row-index="${idx}"]`);
        if (!tr) return false;
        tr.remove();
        reindexMaintRowsFrom(idx);
        return true;
      }

      const targetIdx = action === "append" ? rows.length - 1 : Math.min(idx, rows.length - 1);
      const tr = document.createElement("tr");
      tr.setAttribute("data-maint-row-index", String(targetIdx));
      tr.innerHTML = maintRowHtml(rows[targetIdx], targetIdx, cols, formKey, isShiftCodeCol);
      const before = action === "insert" ? tbody.querySelector(`tr[data-maint-row-index="${targetIdx}"]`) : null;
      tbody.insertBefore(tr, before);
      reindexMaintRowsFrom(targetIdx);
      bindMaintRowInputs(tr);
      applyFormColumnWidths(tr);
      autoResizeTextareas(tr);
      const first = tr.querySelector("textarea,input");
      if (first) first.focus();
      return true;
    }

    function scheduleGridColumnIndexes(rows) {
      const header = Array.isArray(rows[0]) ? rows[0].map((cell) => String(cell || "").trim()) : [];
      return {
        code: header.indexOf("更碼"),
        time: header.indexOf("時間"),
        content: header.indexOf("內容"),
        duration: header.indexOf("時長"),
        effective: header.findIndex((cell) => cell === "生效日期" || cell === "生效" || cell === "Effective From"),
      };
    }

    function scheduleGridInput(rowIndex, colIndex) {
      return document.querySelector(`#maint-editor [data-maint-row="${rowIndex}"][data-maint-col="${colIndex}"]`);
    }

    function setScheduleGridCellValue(rowIndex, colIndex, value) {
      const input = scheduleGridInput(rowIndex, colIndex);
      if (!input) return;
      input.value = value == null ? "" : String(value);
      updateMaintInputFormatting(input, false);
      if (input.tagName.toLowerCase() === "textarea") autoResizeTextarea(input);
    }

    function replaceTrailingDuration(text, minutes) {
      const s = String(text ?? "");
      if (!s.trim()) return s;
      if (s.trimStart().startsWith("-")) return s;
      if (!Number.isFinite(minutes)) return s.replace(/\s+\d+\s*$/, "").trimEnd();
      const rounded = Math.round(minutes);
      if (/\s+\d+\s*$/.test(s)) return s.replace(/\s+\d+\s*$/, ` ${rounded}`);
      return `${s.trimEnd()} ${rounded}`;
    }

    function isScheduleGridMarkerRow(row, cols) {
      if (!Array.isArray(row) || cols.content < 0) return false;
      return String(row[cols.content] || "").trimStart().startsWith("-");
    }

    function scheduleGridGroupKey(row, cols) {
      if (!Array.isArray(row) || !cols || cols.code < 0) return "";
      const code = String(row[cols.code] || "").trim();
      if (!code) return "";
      const effective = cols.effective >= 0 ? String(row[cols.effective] || "").trim() : "";
      return `${code}\u0000${effective}`;
    }

    function recalculateScheduleGridDurations(rows, onlyGroupKey = "") {
      const cols = scheduleGridColumnIndexes(rows);
      if (cols.code < 0 || cols.time < 0 || cols.duration < 0) return rows;
      const groups = new Map();
      rows.forEach((row, idx) => {
        if (idx === 0 || !Array.isArray(row)) return;
        const key = scheduleGridGroupKey(row, cols);
        if (!key || (onlyGroupKey && key !== onlyGroupKey)) return;
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push({ row, idx });
      });
      groups.forEach((group) => {
        group.forEach((item, pos) => {
          const isMarker = isScheduleGridMarkerRow(item.row, cols);
          const next = group.slice(pos + 1).find((candidate) => !isScheduleGridMarkerRow(candidate.row, cols));
          const duration = !isMarker && next ? minutesBetween(item.row[cols.time], next.row[cols.time]) : null;
          const durationText = duration == null ? "" : String(Math.round(duration));
          item.row[cols.duration] = durationText;
          setScheduleGridCellValue(item.idx, cols.duration, durationText);
          if (cols.content >= 0) {
            const nextContent = replaceTrailingDuration(item.row[cols.content], duration);
            if (nextContent !== item.row[cols.content]) {
              item.row[cols.content] = nextContent;
              setScheduleGridCellValue(item.idx, cols.content, nextContent);
            }
          }
        });
      });
      return rows;
    }

    function updateScheduleGridDurationsFromCell(input) {
      if (activeMaintSheetKey !== "schedule_grid" || !input) return;
      const changedCol = Number(input.getAttribute("data-maint-col"));
      const rows = collectMaintRows();
      const cols = scheduleGridColumnIndexes(rows);
      if (changedCol !== cols.time && changedCol !== cols.content) return;
      if (cols.code < 0 || cols.time < 0 || cols.duration < 0) return;
      const changedRow = Number(input.getAttribute("data-maint-row"));
      const changed = Number.isInteger(changedRow) ? rows[changedRow] : null;
      recalculateScheduleGridDurations(rows, scheduleGridGroupKey(changed, cols));
      maintSheetPayload.rows = rows;
      setUnsavedChanges("餐單參數");
    }

    function normaliseEffectiveDateInput(value) {
      const parsed = parseYmd(value);
      if (!parsed) return "";
      return dateKey(parsed.year, parsed.month, parsed.day);
    }

    function normaliseScheduleGridEffectiveValue(value) {
      return normaliseEffectiveDateInput(value) || String(value || "").trim();
    }

    function scheduleGridRowEffective(row, cols) {
      return cols.effective >= 0 ? normaliseScheduleGridEffectiveValue(row && row[cols.effective]) : "";
    }

    function scheduleGridNewShiftBatchRows(input) {
      if (activeMaintSheetKey !== "schedule_grid" || !input) return [];
      const tr = input.closest ? input.closest("tr[data-schedule-new-shift-batch]") : null;
      if (!tr) return [];
      const batch = tr.getAttribute("data-schedule-new-shift-batch");
      if (!batch) return [];
      return Array.from(document.querySelectorAll("#maint-editor tr[data-schedule-new-shift-batch]"))
        .filter((row) => row.getAttribute("data-schedule-new-shift-batch") === batch);
    }

    function scheduleGridCodeExistsOutsideBatch(rows, cols, code, batchRows) {
      if (!code || cols.code < 0) return false;
      const batchIndexes = new Set(batchRows.map((tr) => Number(tr.getAttribute("data-maint-row-index"))));
      return rows.some((row, idx) => {
        if (idx === 0 || batchIndexes.has(idx) || !Array.isArray(row)) return false;
        return String(row[cols.code] || "").trim() === code;
      });
    }

    function restoreScheduleGridChangedCell(input, rows, cols, changedRow, changedCol) {
      let value = input.dataset.maintOriginalValue || "";
      if (changedCol === cols.effective) {
        value = input.dataset.maintOriginalEffective || normaliseScheduleGridEffectiveValue(value);
      }
      if (Array.isArray(rows[changedRow])) rows[changedRow][changedCol] = value;
      setScheduleGridCellValue(changedRow, changedCol, value);
      maintSheetPayload.rows = rows;
    }

    function syncScheduleGridNewShiftBatchFromCell(input) {
      const batchRows = scheduleGridNewShiftBatchRows(input);
      if (!batchRows.length) return false;
      const changedCol = Number(input.getAttribute("data-maint-col"));
      const rows = collectMaintRows();
      const payloadRows = Array.isArray(maintSheetPayload.rows) ? maintSheetPayload.rows : [];
      while (rows.length < payloadRows.length) {
        const source = payloadRows[rows.length];
        rows.push(Array.isArray(source) ? [...source] : []);
      }
      const cols = scheduleGridColumnIndexes(rows);
      if (cols.code < 0) return false;
      const canSyncCode = changedCol === cols.code;
      const canSyncEffective = cols.effective >= 0 && changedCol === cols.effective;
      if (!canSyncCode && !canSyncEffective) return false;
      const changedRow = Number(input.getAttribute("data-maint-row"));
      const changed = rows[changedRow];
      if (!Array.isArray(changed)) return false;
      if (canSyncCode) {
        const code = String(changed[cols.code] || "").trim();
        if (!code) return false;
        if (scheduleGridCodeExistsOutsideBatch(rows, cols, code, batchRows)) {
          window.alert(`Shift code "${code}" already exists. Use New Version for an existing shift code.`);
          restoreScheduleGridChangedCell(input, rows, cols, changedRow, changedCol);
          return true;
        }
        batchRows.forEach((tr) => {
          const idx = Number(tr.getAttribute("data-maint-row-index"));
          if (!Array.isArray(rows[idx])) return;
          rows[idx][cols.code] = code;
          setScheduleGridCellValue(idx, cols.code, code);
        });
      }
      if (canSyncEffective) {
        const effective = normaliseScheduleGridEffectiveValue(changed[cols.effective]);
        batchRows.forEach((tr) => {
          const idx = Number(tr.getAttribute("data-maint-row-index"));
          if (!Array.isArray(rows[idx])) return;
          rows[idx][cols.effective] = effective;
          setScheduleGridCellValue(idx, cols.effective, effective);
        });
        currentMaintEffectiveFilter = effective || "__blank__";
        saveMaintFilterState("schedule_grid");
      }
      currentMaintFilter = SCHEDULE_GRID_NEW_SHIFT_FILTER;
      applyScheduleGridNewShiftFilter();
      maintSheetPayload.rows = rows;
      setUnsavedChanges("餐單參數");
      return true;
    }

    function syncScheduleGridEffectiveDateFromCell(input) {
      if (activeMaintSheetKey !== "schedule_grid" || !input) return false;
      if (scheduleGridNewShiftBatchRows(input).length) return false;
      const changedCol = Number(input.getAttribute("data-maint-col"));
      const rows = collectMaintRows();
      const cols = scheduleGridColumnIndexes(rows);
      if (cols.code < 0) return false;
      const canSyncCode = changedCol === cols.code;
      const canSyncEffective = cols.effective >= 0 && changedCol === cols.effective;
      if (!canSyncCode && !canSyncEffective) return false;
      const changedRow = Number(input.getAttribute("data-maint-row"));
      const changed = rows[changedRow];
      if (!Array.isArray(changed)) return false;
      const originalRows = Array.isArray(maintSheetPayload.rows) ? maintSheetPayload.rows : [];
      const originalChanged = Array.isArray(originalRows[changedRow]) ? originalRows[changedRow] : changed;
      const oldCode = input.dataset.maintOriginalGroupCode !== undefined
        ? input.dataset.maintOriginalGroupCode
        : String(originalChanged[cols.code] || "").trim();
      const oldEffective = input.dataset.maintOriginalGroupEffective !== undefined
        ? input.dataset.maintOriginalGroupEffective
        : scheduleGridRowEffective(originalChanged, cols);
      const newCode = String(changed[cols.code] || "").trim();
      const newEffective = scheduleGridRowEffective(changed, cols);
      if (!oldCode || !newCode) return false;
      if (oldCode === newCode && oldEffective === newEffective) return false;
      const targetIndexes = originalRows
        .map((row, idx) => ({ row, idx }))
        .filter(({ row, idx }) => {
          if (idx === 0 || !Array.isArray(row)) return false;
          const rowCode = String(row[cols.code] || "").trim();
          const rowEffective = scheduleGridRowEffective(row, cols);
          return rowCode === oldCode && rowEffective === oldEffective;
        })
        .map(({ idx }) => idx);
      if (!targetIndexes.includes(changedRow)) targetIndexes.push(changedRow);
      let updated = false;
      for (const idx of targetIndexes) {
        const row = rows[idx];
        if (!Array.isArray(row)) continue;
        row[cols.code] = newCode;
        setScheduleGridCellValue(idx, cols.code, newCode);
        if (cols.effective >= 0) {
          row[cols.effective] = newEffective;
          setScheduleGridCellValue(idx, cols.effective, newEffective);
        }
        updated = true;
      }
      if (!updated) return false;
      maintSheetPayload.rows = rows;
      currentMaintFilter = newCode;
      if (cols.effective >= 0) currentMaintEffectiveFilter = newEffective || "__blank__";
      saveMaintFilterState("schedule_grid");
      setUnsavedChanges("餐單參數");
      return true;
    }

    function ensureScheduleGridNewShiftFilterOption() {
      const select = document.getElementById("maint-table-filter");
      if (!select) return;
      let option = Array.from(select.options).find((item) => item.value === SCHEDULE_GRID_NEW_SHIFT_FILTER);
      if (!option) {
        option = document.createElement("option");
        option.value = SCHEDULE_GRID_NEW_SHIFT_FILTER;
        option.textContent = "<new shift code>";
        const afterAll = select.options.length > 0 ? select.options[1] || null : null;
        select.insertBefore(option, afterAll);
      }
      select.value = SCHEDULE_GRID_NEW_SHIFT_FILTER;
      select.disabled = false;
      currentMaintFilter = SCHEDULE_GRID_NEW_SHIFT_FILTER;
    }

    function applyScheduleGridNewShiftFilter() {
      ensureScheduleGridNewShiftFilterOption();
      const effectiveSelect = document.getElementById("maint-effective-filter");
      const yearSelect = document.getElementById("maint-year-filter");
      if (effectiveSelect) effectiveSelect.value = "";
      if (yearSelect) yearSelect.value = "";
      document.querySelectorAll("#maint-editor tr[data-maint-row-index]").forEach((tr) => {
        const idx = Number(tr.getAttribute("data-maint-row-index"));
        const isBatch = tr.getAttribute("data-schedule-new-shift-batch") === scheduleGridNewShiftBatchId;
        tr.style.display = idx === 0 || isBatch ? "" : "none";
      });
      setTimeout(() => {
        document.querySelectorAll("#maint-editor tr[data-schedule-new-shift-batch] textarea[data-auto-row-height]").forEach(autoResizeTextarea);
      }, 0);
    }

    function createScheduleGridVersion(rowIndex) {
      if (activeMaintSheetKey !== "schedule_grid") return;
      const rows = collectMaintRows();
      const cols = scheduleGridColumnIndexes(rows);
      if (cols.code < 0 || cols.effective < 0) return;
      const selected = rows[rowIndex];
      if (!Array.isArray(selected)) return;
      const code = String(selected[cols.code] || "").trim();
      const oldEffective = String(selected[cols.effective] || "").trim();
      if (!code) return;
      const rawDate = window.prompt(`New effective date for ${code}`, "");
      if (rawDate == null) return;
      const newEffective = normaliseEffectiveDateInput(rawDate);
      if (!newEffective) {
        window.alert("Please enter a valid date, for example 2026-06-01.");
        return;
      }
      const copies = [];
      let insertAt = rowIndex + 1;
      rows.forEach((row, idx) => {
        if (idx === 0 || !Array.isArray(row)) return;
        const rowCode = String(row[cols.code] || "").trim();
        const rowEffective = String(row[cols.effective] || "").trim();
        if (rowCode !== code || rowEffective !== oldEffective) return;
        const next = [...row];
        next[cols.effective] = newEffective;
        copies.push(next);
        insertAt = Math.max(insertAt, idx + 1);
      });
      if (!copies.length) return;
      rows.splice(insertAt, 0, ...copies);
      currentMaintEffectiveFilter = newEffective;
      saveMaintFilterState("schedule_grid");
      setUnsavedChanges("餐單參數");
      setMaintRowsAndRender(rows, { preserveOrder: true });
    }

    function markScheduleGridNewShiftBatch(startIdx, count, batch = "", focusFirst = true) {
      if (!batch) batch = `new-shift-${Date.now()}-${Math.floor(Math.random() * 100000)}`;
      for (let i = startIdx; i < startIdx + count; i += 1) {
        const tr = document.querySelector(`#maint-editor tr[data-maint-row-index="${i}"]`);
        if (tr) tr.setAttribute("data-schedule-new-shift-batch", batch);
      }
      applyScheduleGridNewShiftFilter();
      if (!focusFirst) return;
      const first = scheduleGridInput(startIdx, scheduleGridColumnIndexes(collectMaintRows()).code);
      if (first) {
        focusMaintCell(first);
        beginMaintCellEdit(first);
      }
    }

    function addScheduleGridShiftCodeRows(rowIndex) {
      if (activeMaintSheetKey !== "schedule_grid") return;
      const rows = collectMaintRows();
      const cols = scheduleGridColumnIndexes(rows);
      if (cols.code < 0 || cols.content < 0) return;
      const count = 20;
      const insertAt = rows.length;
      const blanks = Array.from({ length: count }, () => emptyMaintRow(rows));
      const batch = `new-shift-${Date.now()}-${Math.floor(Math.random() * 100000)}`;
      scheduleGridNewShiftBatchId = batch;
      scheduleGridNewShiftStartIndex = insertAt;
      scheduleGridNewShiftCount = count;
      currentMaintFilter = SCHEDULE_GRID_NEW_SHIFT_FILTER;
      currentMaintEffectiveFilter = "";
      currentMaintYearFilter = "";
      rows.splice(insertAt, 0, ...blanks);
      setUnsavedChanges("餐單參數");
      setMaintRowsAndRender(rows, { preserveOrder: true });
      markScheduleGridNewShiftBatch(insertAt, count, batch);
    }

    function deleteScheduleGridVersion(rowIndex) {
      if (activeMaintSheetKey !== "schedule_grid") return;
      const rows = collectMaintRows();
      const cols = scheduleGridColumnIndexes(rows);
      if (cols.code < 0 || cols.effective < 0) return;
      const selected = rows[rowIndex];
      if (!Array.isArray(selected)) return;
      const code = String(selected[cols.code] || "").trim();
      const effective = String(selected[cols.effective] || "").trim();
      if (!code) return;
      const parsedEffective = parseYmd(effective);
      const effectiveLabel = parsedEffective ? dateDmyDow(parsedEffective.year, parsedEffective.month, parsedEffective.day) : effective;
      const label = effective ? `${code} ${effectiveLabel}` : `${code} 未填生效日期`;
      const ok = window.confirm(`Delete this version?\n${label}`);
      if (!ok) return;
      const next = rows.filter((row, idx) => {
        if (idx === 0 || !Array.isArray(row)) return true;
        return String(row[cols.code] || "").trim() !== code || String(row[cols.effective] || "").trim() !== effective;
      });
      if (next.length === rows.length) return;
      if (currentMaintEffectiveFilter === (effective || "__blank__")) currentMaintEffectiveFilter = "";
      saveMaintFilterState("schedule_grid");
      setUnsavedChanges("餐單參數");
      setMaintRowsAndRender(next, { preserveOrder: true });
    }

    function parseRosterMaintLine(text) {
      const s = String(text || "").trim().replace(/\u00a0/g, " ");
      const m = s.match(/^(\d{4})年(\d{1,2})月\s*(.*)$/);
      if (!m) return null;
      const tokens = m[3].trim().split(/\s+/).filter(Boolean);
      const days = [];
      const isDayToken = (token) => {
        if (!/^\d+$/.test(token)) return false;
        const n = Number(token);
        return Number.isInteger(n) && n >= 1 && n <= 31;
      };
      for (let i = 0; i < tokens.length;) {
        const day = Number(tokens[i]);
        if (!Number.isInteger(day) || day < 1 || day > 31) break;
        i += 1;
        const codeParts = [];
        while (i < tokens.length && !isDayToken(tokens[i])) {
          codeParts.push(tokens[i]);
          i += 1;
        }
        if (!codeParts.length) break;
        days.push({ day, code: codeParts.join(" ") });
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

    function dateDmyDow(year, month, day) {
      return `${dateDmy(year, month, day)} ${weekdayLabel(year, month, day)}`;
    }

    function weekdayLabel(year, month, day) {
      const d = new Date(year, month - 1, day);
      return ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][d.getDay()] || "";
    }

    // 30 小時制：凌晨 00:00–05:59 一律寫成 24:00–29:59（唔會有兩個寫法指同一個鐘點）。
    function normalTime(value) {
      const s = String(value || "").trim();
      const compact = s.match(/^(\d{1,2})(\d{2})$/);
      const m = compact || s.match(/(\d{1,2}):(\d{2})/);
      if (!m) return "";
      let hour = Number(m[1]);
      if (hour > 29) return "";
      if (hour < 6) hour += 24;
      return `${String(hour).padStart(2, "0")}:${m[2]}`;
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
      const p = String(pattern || "").trim().toLowerCase();
      const c = String(code || "").trim().toLowerCase();
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

    function wakeRowsByDate(rows) {
      const out = new Map();
      if (!Array.isArray(rows) || !rows.length) return out;
      const headers = new Map();
      (Array.isArray(rows[0]) ? rows[0] : []).forEach((cell, idx) => {
        const key = String(cell || "").trim();
        if (key) headers.set(key, idx);
      });
      const cDate = headers.has("日期") ? headers.get("日期") : 0;
      const cWake = headers.has("起身時間") ? headers.get("起身時間") : (headers.has("起身") ? headers.get("起身") : 1);
      (rows || []).slice(1).forEach((row) => {
        if (!Array.isArray(row)) return;
        const d = parseYmd(row[cDate]);
        const wake = normalTime(row[cWake]);
        if (!d || !wake) return;
        out.set(dateKey(d.year, d.month, d.day), wake);
      });
      return out;
    }

    // 起身表第三欄＝逐日手寫備註（同起身時間共用一行，兩者可以獨立存在）。
    function wakeNotesByDate(rows) {
      const out = new Map();
      if (!Array.isArray(rows) || !rows.length) return out;
      const headers = new Map();
      (Array.isArray(rows[0]) ? rows[0] : []).forEach((cell, idx) => {
        const key = String(cell || "").trim();
        if (key) headers.set(key, idx);
      });
      const cDate = headers.has("日期") ? headers.get("日期") : 0;
      const cNote = headers.has("備註") ? headers.get("備註") : 2;
      (rows || []).slice(1).forEach((row) => {
        if (!Array.isArray(row)) return;
        const d = parseYmd(row[cDate]);
        const note = String(row[cNote] || "").trim();
        if (!d || !note) return;
        out.set(dateKey(d.year, d.month, d.day), note);
      });
      return out;
    }

    function clockFromMinutes(minutes) {
      if (!Number.isFinite(minutes)) return "";
      const n = ((Math.round(minutes) % 1440) + 1440) % 1440;
      // 30 小時制顯示：凌晨嗰段屬前一日嘅 24:00–29:59。
      const hour = Math.floor(n / 60);
      return `${String(hour < 6 ? hour + 24 : hour).padStart(2, "0")}:${String(n % 60).padStart(2, "0")}`;
    }

    function wakeOffsetMinutes() {
      const hours = Number(googleCalendarSync && googleCalendarSync.wake_offset_hours);
      return Number.isFinite(hours) && hours > 0 ? Math.round(hours * 60) : 180;
    }

    function defaultWakeTimeForStart(start) {
      const minutes = timeMinutes(start);
      return minutes == null ? "" : clockFromMinutes(minutes - wakeOffsetMinutes());
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

    function renderRosterMaintReport(rows) {
      const overtimeByDate = overtimeRowsByDate(rosterReportSources.overtime);
      const wakeByDate = wakeRowsByDate(rosterReportSources.wake_alarms);
      const manualNoteByDate = wakeNotesByDate(rosterReportSources.wake_alarms);
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
          const defaultWake = start ? defaultWakeTimeForStart(start) : "";
          const wakeOverride = wakeByDate.get(key);
          const medical = medicalByDate.get(key) || [];
          const wake = wakeOverride || defaultWake;
          const duration = minutesBetween(start, end);
          const overtime = duration != null && duration > 615 ? duration - 600 : null;
          const overtimePay = overtime ? overtime : null;
          if (duration != null) totalDuration += duration;
          if (overtime != null) totalOvertime += overtime;
          if (overtimePay != null) totalPay += overtimePay;
          const holiday = holidaysByDate.get(key);
          // 假期名同日期／星期一樣要紅色；醫療行程同加班備註照舊黑色。
          const autoNoteParts = [];
          if (holiday) autoNoteParts.push(`<span class="report-red">${esc(holiday)}</span>`);
          medical.forEach((text) => autoNoteParts.push(esc(text)));
          if (ot.note) autoNoteParts.push(esc(ot.note));
          const weekday = weekdayLabel(parsed.year, parsed.month, item.day);
          const isToday = key === todayKey;
          const isSunday = weekday === "Sun";
          const dateClasses = ["report-date-cell", isToday ? "report-today-cell" : "", (isSunday || holiday) ? "report-red" : ""].filter(Boolean).join(" ");
          const weekdayClasses = ["report-weekday-cell", isToday ? "report-today-cell" : "", (isSunday || holiday) ? "report-red" : ""].filter(Boolean).join(" ");
          const noteClasses = ["report-note-cell", isToday && holiday ? "report-today-cell" : ""].filter(Boolean).join(" ");
          const autoNote = autoNoteParts.join(" / ");
          const manualNote = manualNoteByDate.get(key) || "";
          const wakeIsOverride = !!wake && wake !== defaultWake;
          const wakeCellClasses = ["roster-wake-cell", wakeIsOverride ? "roster-wake-override" : ""].filter(Boolean).join(" ");
          reportRows.push(`<tr class="${isToday ? "report-today-row" : ""}">
            <td class="${dateClasses}">${esc(dateDmy(parsed.year, parsed.month, item.day))}</td>
            <td class="${weekdayClasses}">${esc(weekday)}</td>
            <td class="${wakeCellClasses}" data-roster-field-cell="1" data-roster-field="wake" tabindex="0"><input class="roster-wake-input" type="text" inputmode="numeric" tabindex="-1" data-roster-field="wake" data-roster-field-date="${esc(key)}" data-roster-field-default="${esc(defaultWake)}" value="${esc(wake)}" /></td>
            <td>${esc(item.code)}</td>
            <td>${esc(start)}</td>
            <td>${esc(end)}</td>
            <td>${esc(minutesLabel(duration))}</td>
            <td>${esc(overtime ? minutesLabel(overtime) : "")}</td>
            <td>${esc(overtimePay ? overtimePay.toFixed(0) : "")}</td>
            <td class="${noteClasses}" data-roster-field-cell="1" data-roster-field="note" tabindex="0"><div class="roster-note-wrap"><span class="roster-note-auto">${autoNote}</span><span class="roster-note-sep"${autoNote && manualNote ? "" : " hidden"}>/</span><input class="roster-note-input" type="text" tabindex="-1" data-roster-note-empty="${manualNote ? "0" : "1"}" data-roster-field="note" data-roster-field-date="${esc(key)}" value="${esc(manualNote)}" /></div></td>
          </tr>`);
        });
      });
      return `<table class="maint-report-table" data-form-table>
        <colgroup>
          <col data-form-col-key="maint_roster_report_date" data-form-col-default="110" />
          <col data-form-col-key="maint_roster_report_weekday" data-form-col-default="70" />
          <col data-form-col-key="maint_roster_report_wake" data-form-col-default="80" />
          <col data-form-col-key="maint_roster_report_code" data-form-col-default="110" />
          <col data-form-col-key="maint_roster_report_start" data-form-col-default="80" />
          <col data-form-col-key="maint_roster_report_end" data-form-col-default="80" />
          <col data-form-col-key="maint_roster_report_duration" data-form-col-default="80" />
          <col data-form-col-key="maint_roster_report_overtime" data-form-col-default="80" />
          <col data-form-col-key="maint_roster_report_overtime_pay" data-form-col-default="90" />
          <col data-form-col-key="maint_roster_report_note" data-form-col-default="220" />
        </colgroup>
        <thead><tr><th data-form-col-key="maint_roster_report_date">日期</th><th data-form-col-key="maint_roster_report_weekday">星期</th><th data-form-col-key="maint_roster_report_wake">起身</th><th data-form-col-key="maint_roster_report_code">更碼</th><th data-form-col-key="maint_roster_report_start">開工</th><th data-form-col-key="maint_roster_report_end">收工</th><th data-form-col-key="maint_roster_report_duration">時長</th><th data-form-col-key="maint_roster_report_overtime">加班</th><th data-form-col-key="maint_roster_report_overtime_pay">加班費</th><th data-form-col-key="maint_roster_report_note">備註</th></tr></thead>
        <tbody>${reportRows.join("") || '<tr><td colspan="10" class="maint-empty">No roster data</td></tr>'}</tbody>
        <tfoot><tr><th colspan="6">Total</th><th>${esc(minutesLabel(totalDuration))}</th><th>${esc(minutesLabel(totalOvertime))}</th><th>${esc(totalPay ? totalPay.toFixed(0) : "")}</th><th></th></tr></tfoot>
      </table>`;
    }

    function isWorkRosterCode(code) {
      const s = String(code || "").trim();
      if (!s) return false;
      if (s === "SB") return false;
      return !["WL", "SH", "AL", "SL"].some((prefix) => s.startsWith(prefix));
    }

    function nonWorkRosterCategory(code) {
      const s = String(code || "").trim();
      if (s === "SB") return "SB";
      for (const prefix of ["AL", "SH", "SL", "WL"]) {
        if (s.startsWith(prefix)) return prefix;
      }
      return s || "非返工日";
    }

    function shiftAnalysisMonthKey(parsed) {
      return `${parsed.year}-${String(parsed.month).padStart(2, "0")}`;
    }

    function shiftAnalysisMonthLabel(monthKey) {
      const [year, month] = String(monthKey || "").split("-").map(Number);
      if (!Number.isInteger(year) || !Number.isInteger(month)) return monthKey;
      return `${MONTHS_EN[month - 1] || String(month).padStart(2, "0")} ${year}`;
    }

    function buildShiftCodeAnalysis(rows, collapseWorkdays = false) {
      const months = [];
      const monthSeen = new Set();
      const stats = new Map();
      (rows || []).forEach((row) => {
        const parsed = parseRosterMaintLine(Array.isArray(row) ? row[0] : "");
        if (!parsed) return;
        const monthKey = shiftAnalysisMonthKey(parsed);
        if (!monthSeen.has(monthKey)) {
          monthSeen.add(monthKey);
          months.push(monthKey);
        }
        parsed.days.forEach((item) => {
          const code = String(item.code || "").trim();
          if (!code) return;
          const isWork = isWorkRosterCode(code);
          const displayCode = isWork
            ? (collapseWorkdays ? "返工日" : code)
            : nonWorkRosterCategory(code);
          const key = isWork
            ? (collapseWorkdays ? "__workday__" : `work:${code}`)
            : `nonwork:${displayCode}`;
          const current = stats.get(key) || {
            key,
            code: displayCode,
            groupIndex: isWork ? 0 : 1,
            groupLabel: isWork ? "返工日" : "非返工日",
            count: 0,
            months: new Map(),
          };
          current.count += 1;
          current.months.set(monthKey, (current.months.get(monthKey) || 0) + 1);
          stats.set(key, current);
        });
      });
      months.sort((a, b) => a.localeCompare(b, "zh-Hant"));
      const records = Array.from(stats.values()).sort((a, b) => {
        if (a.groupIndex !== b.groupIndex) return a.groupIndex - b.groupIndex;
        return a.code.localeCompare(b.code, "zh-Hant");
      });
      return { months, records };
    }

    function shiftCodeAnalysisExpanded() {
      const saved = Number(formColumnWidths.shift_analysis_expanded);
      return !Number.isFinite(saved) || saved !== 0;
    }

    function setShiftCodeAnalysisExpanded(expanded) {
      formColumnWidths.shift_analysis_expanded = expanded ? 1 : 0;
    }

    function renderShiftCodeAnalysisTable(analysis, blockKey, expanded) {
      const months = analysis.months || [];
      const records = analysis.records || [];
      const span = Math.max(2, months.length + 2);
      const countText = (value) => value ? String(value) : "";
      const toggleLabel = expanded ? "▲" : "▼";
      const toggleTitle = expanded ? "收起返工日" : "展開返工更碼";
      const monthCols = months
        .map(() => `<col data-form-col-key="shift_analysis_number" data-form-col-default="64" />`)
        .join("");
      const monthHeads = months
        .map((month) => `<th class="shift-analysis-month-head" data-form-col-key="shift_analysis_number">${esc(shiftAnalysisMonthLabel(month))}</th>`)
        .join("");
      const monthTotals = new Map(months.map((month) => [month, 0]));
      let grandTotal = 0;
      const rowsHtml = records.map((item) => {
        const cells = months.map((month) => {
          const n = item.months.get(month) || 0;
          monthTotals.set(month, (monthTotals.get(month) || 0) + n);
          return `<td class="shift-analysis-number">${esc(countText(n))}</td>`;
        }).join("");
        grandTotal += item.count;
        return `<tr>
          <td>${esc(item.code)}</td>
          ${cells}
          <td class="shift-analysis-number">${esc(countText(item.count))}</td>
        </tr>`;
      });
      const totalCells = months
        .map((month) => `<th class="shift-analysis-number">${esc(countText(monthTotals.get(month) || 0))}</th>`)
        .join("");
      return `<table class="maint-report-table shift-code-analysis-table" data-form-table>
        <colgroup>
          <col data-form-col-key="shift_analysis_${blockKey}_code" data-form-col-default="110" />
          ${monthCols}
          <col data-form-col-key="shift_analysis_number" data-form-col-default="64" />
        </colgroup>
        <thead><tr><th class="shift-analysis-code-head" data-form-col-key="shift_analysis_${blockKey}_code"><button type="button" class="shift-analysis-toggle" title="${esc(toggleTitle)}" aria-label="${esc(toggleTitle)}">${toggleLabel}</button><span>更碼</span></th>${monthHeads}<th class="shift-analysis-total-head" data-form-col-key="shift_analysis_number">Total</th></tr></thead>
        <tbody>${rowsHtml.join("") || `<tr><td colspan="${span}" class="maint-empty">No roster data</td></tr>`}</tbody>
        <tfoot><tr><th>Total</th>${totalCells}<th class="shift-analysis-number">${esc(countText(grandTotal))}</th></tr></tfoot>
      </table>`;
    }

    function renderShiftCodeAnalysisReport(rows) {
      const expanded = shiftCodeAnalysisExpanded();
      const analysis = buildShiftCodeAnalysis(rows, !expanded);
      return `<div class="shift-code-analysis-layout">
        <div class="shift-code-analysis-sheet">
          ${renderShiftCodeAnalysisTable(analysis, "combined", expanded)}
        </div>
      </div>`;
    }

    function shiftCodeAnalysisOffsetPx() {
      const saved = Number(formColumnWidths.table_offset_shift_code_analysis);
      return Number.isFinite(saved) ? saved : 0;
    }

    function applyShiftCodeAnalysisSheetOffset(root = document) {
      const sheet = document.querySelector("#shift-code-analysis-out .shift-code-analysis-layout");
      if (!sheet) return;
      if (root !== document && !root.contains(sheet) && sheet !== root && !sheet.contains(root)) return;
      sheet.style.marginLeft = `${shiftCodeAnalysisOffsetPx()}px`;
    }

    function refreshShiftCodeAnalysisReport() {
      const out = document.getElementById("shift-code-analysis-out");
      if (!out) return;
      out.innerHTML = renderShiftCodeAnalysisReport(shiftCodeAnalysisRows);
      applyFormColumnWidths(out);
      attachFormColumnResizers(out);
      applyShiftCodeAnalysisSheetOffset(out);
      attachShiftCodeAnalysisSheetControls(out);
    }

    function attachShiftCodeAnalysisSheetControls(root = document) {
      const toggle = root.querySelector(".shift-analysis-toggle");
      if (toggle && toggle.dataset.shiftAnalysisToggleBound !== "1") {
        toggle.dataset.shiftAnalysisToggleBound = "1";
        toggle.addEventListener("click", (ev) => {
          ev.preventDefault();
          ev.stopPropagation();
          setShiftCodeAnalysisExpanded(!shiftCodeAnalysisExpanded());
          refreshShiftCodeAnalysisReport();
          persistColumnWidths();
        });
      }
      const handle = root.querySelector(".shift-analysis-code-head");
      if (handle && typeof attachHorizontalDragHandle === "function") {
        attachHorizontalDragHandle(handle, "table_offset_shift_code_analysis", () => applyShiftCodeAnalysisSheetOffset(root));
      }
    }

    function shiftAnalysisBlockOffsetPx(blockKey, axis, fallback) {
      const saved = Number(formColumnWidths[`shift_analysis_block_${blockKey}_${axis}`]);
      const value = Number.isFinite(saved) ? saved : fallback;
      return axis === "y" ? Math.max(0, value) : value;
    }

    function shiftAnalysisBlockWidth(block) {
      const table = block && block.querySelector ? block.querySelector("table[data-form-table]") : null;
      if (!table) return block ? block.getBoundingClientRect().width : 0;
      const colWidth = Array.from(table.querySelectorAll("col[data-form-col-key]")).reduce((total, col) => {
        const key = col.getAttribute("data-form-col-key");
        const fallback = Number(col.getAttribute("data-form-col-default")) || 120;
        return total + formColumnWidthPx(key, fallback);
      }, 0);
      const style = getComputedStyle(block);
      const borderX = parseFloat(style.borderLeftWidth || "0") + parseFloat(style.borderRightWidth || "0");
      return colWidth + borderX;
    }

    function applyShiftCodeAnalysisBlockLayout(root = document) {
      const container = document.querySelector(".shift-code-analysis-layout");
      if (!container) return;
      if (root !== document && !root.contains(container) && container !== root && !container.contains(root)) return;
      applyFormColumnWidths(container);
      const blocks = Array.from(container.querySelectorAll(".shift-analysis-block[data-shift-analysis-block]"));
      let defaultY = 0;
      let maxRight = 0;
      let maxBottom = 0;
      blocks.forEach((block) => {
        const blockKey = block.getAttribute("data-shift-analysis-block");
        const defaultX = 0;
        const x = shiftAnalysisBlockOffsetPx(blockKey, "x", defaultX);
        const y = shiftAnalysisBlockOffsetPx(blockKey, "y", defaultY);
        const width = shiftAnalysisBlockWidth(block);
        block.style.left = `${x}px`;
        block.style.top = `${y}px`;
        if (width > 0) block.style.width = `${width}px`;
        const height = block.getBoundingClientRect().height;
        maxRight = Math.max(maxRight, x + Math.max(width, block.getBoundingClientRect().width));
        maxBottom = Math.max(maxBottom, y + height);
        defaultY += height + 10;
      });
      container.style.width = `${Math.max(280, maxRight)}px`;
      container.style.height = `${Math.max(260, maxBottom)}px`;
    }

    async function openShiftCodeAnalysisReport() {
      if (!(await resolveUnsavedBeforeLeaving())) return;
      setActiveMenuPathForKey("shift_code_analysis");
      setReportsMenuTreeOpen(true);
      setActivePanel("reports");
      const status = document.getElementById("shift-code-analysis-status");
      const out = document.getElementById("shift-code-analysis-out");
      if (status) status.textContent = "Loading...";
      if (out) out.innerHTML = "";
      try {
        const [roster, payroll] = await Promise.all([
          loadMaintSheet("roster"),
          loadMaintSheet("payroll_times").catch(() => ({ rows: [] })),
        ]);
        rosterReportSources = {
          ...rosterReportSources,
          payroll_times: Array.isArray(payroll.rows) ? payroll.rows : [],
        };
        const rows = Array.isArray(roster.rows) ? roster.rows : [];
        shiftCodeAnalysisRows = rows;
        if (out) {
          refreshShiftCodeAnalysisReport();
        }
        if (status) status.textContent = "";
      } catch (e) {
        if (status) status.textContent = String(e && e.message ? e.message : e);
      }
    }

    function refreshRosterMaintReport() {
      const report = document.getElementById("maint-roster-report");
      if (!report) return;
      report.innerHTML = renderRosterMaintReport(collectMaintRows());
      applyFormColumnWidths(report);
      attachFormColumnResizers(report);
      attachRosterFieldInputs(report);
      applyRosterReportOffset();
      attachRosterReportDrag();
    }

    // 更表 report 可以 inline 打字嘅欄：起身時間同備註。兩欄共用同一套 cell 導航／編輯機制，
    // 分別淨係「點 format」同「寫返起身表邊個欄」——兩者都存喺起身表（日期／起身時間／備註）。
    const ROSTER_FIELD_DEFS = {
      wake: {
        format: (raw) => normalTime(String(raw || "").trim()) || "",
        strict: true,
        invalidMessage: (key, raw) => `起身時間格式錯誤：${key} ${raw}`,
        afterChange: (input) => updateRosterWakeOverrideClass(input),
        patch: (input, value) => ({ wake: rosterWakeValueForStorage(input, value) }),
      },
      note: {
        format: (raw) => String(raw || "").replace(/\s+/g, " ").trim(),
        strict: false,
        afterChange: (input) => updateRosterNoteLayout(input),
        patch: (input, value) => ({ note: value }),
      },
    };
    const ROSTER_FIELD_KEYS = Object.keys(ROSTER_FIELD_DEFS);

    function rosterFieldMeta(input) {
      const key = input && input.getAttribute ? String(input.getAttribute("data-roster-field") || "") : "";
      return ROSTER_FIELD_DEFS[key] ? { key, def: ROSTER_FIELD_DEFS[key] } : null;
    }

    function attachRosterFieldInputs(root = document) {
      const report = root.matches && root.matches("#maint-roster-report") ? root : root.querySelector("#maint-roster-report");
      if (!report) return;
      report.tabIndex = -1;
      report.__rosterFieldCells = {};
      report.__rosterFieldInputs = {};
      report.__rosterFieldActiveIndex = {};
      ROSTER_FIELD_KEYS.forEach((key) => {
        const cells = Array.from(report.querySelectorAll(`td[data-roster-field-cell][data-roster-field="${key}"]`))
          .filter((cell) => cell.tabIndex >= 0 && cell.querySelector("input[data-roster-field-date]"));
        const inputs = cells.map((cell) => cell.querySelector("input[data-roster-field-date]"));
        report.__rosterFieldCells[key] = cells;
        report.__rosterFieldInputs[key] = inputs;
        report.__rosterFieldActiveIndex[key] = 0;
        inputs.forEach((input, idx) => {
          input.dataset.rosterFieldIndex = String(idx);
          input.dataset.rosterFieldEditable = "1";
          input.dataset.rosterFieldLastSynced = ROSTER_FIELD_DEFS[key].format(input.value);
          input.dataset.rosterFieldEdited = "0";
          input.dataset.maintSavedValue = input.value;
          input.readOnly = true;
        });
      });
      if (!ROSTER_FIELD_DEFS[report.__rosterFieldActiveKey]) report.__rosterFieldActiveKey = ROSTER_FIELD_KEYS[0];
      if (report.dataset.rosterFieldDelegateBound === "1") return;
      report.dataset.rosterFieldDelegateBound = "1";
      report.addEventListener("keydown", handleRosterFieldKeydown);
      report.addEventListener("input", handleRosterFieldInput);
      report.addEventListener("focusin", handleRosterFieldFocusIn);
      report.addEventListener("focusout", handleRosterFieldFocusOut);
      report.addEventListener("mousedown", handleRosterFieldMouseDown);
    }

    function rosterFieldInputFromEvent(ev) {
      const input = ev && ev.target && ev.target.closest ? ev.target.closest("input[data-roster-field-date]") : null;
      if (!input || input.disabled || input.dataset.rosterFieldEditable !== "1") return null;
      return input.closest("#maint-roster-report") ? input : null;
    }

    function rosterFieldReportFromEvent(ev) {
      if (!ev || !ev.target || !ev.target.closest) return null;
      return ev.target.closest("#maint-roster-report");
    }

    function activeRosterFieldInput(report) {
      if (!report) return null;
      const key = ROSTER_FIELD_DEFS[report.__rosterFieldActiveKey] ? report.__rosterFieldActiveKey : ROSTER_FIELD_KEYS[0];
      const inputs = (report.__rosterFieldInputs || {})[key] || [];
      if (!inputs.length) return null;
      const idx = Number((report.__rosterFieldActiveIndex || {})[key]) || 0;
      return inputs[Math.max(0, Math.min(idx, inputs.length - 1))] || null;
    }

    function setRosterFieldActive(report, key, index, options = {}) {
      if (!report || !ROSTER_FIELD_DEFS[key]) return false;
      const inputs = (report.__rosterFieldInputs || {})[key] || [];
      const cells = (report.__rosterFieldCells || {})[key] || [];
      if (!inputs.length) return false;
      const idx = Math.max(0, Math.min(index, inputs.length - 1));
      ROSTER_FIELD_KEYS.forEach((other) => {
        ((report.__rosterFieldInputs || {})[other] || []).forEach((item) => delete item.dataset.rosterFieldActive);
        ((report.__rosterFieldCells || {})[other] || []).forEach((item) => delete item.dataset.rosterFieldActive);
      });
      const input = inputs[idx];
      const cell = cells[idx] || input.closest("td[data-roster-field-cell]");
      input.dataset.rosterFieldActive = "1";
      if (cell) cell.dataset.rosterFieldActive = "1";
      report.__rosterFieldActiveKey = key;
      if (!report.__rosterFieldActiveIndex) report.__rosterFieldActiveIndex = {};
      report.__rosterFieldActiveIndex[key] = idx;
      if (options.focus) focusRosterFieldInputElement(input);
      return true;
    }

    function markRosterFieldActive(report, input, options = {}) {
      const meta = rosterFieldMeta(input);
      if (!report || !meta) return false;
      const idx = Number(input.dataset.rosterFieldIndex);
      return setRosterFieldActive(report, meta.key, Number.isInteger(idx) ? idx : 0, options);
    }

    function handleRosterFieldKeydown(ev) {
      const report = rosterFieldReportFromEvent(ev);
      if (!report) return;
      const focusedInput = rosterFieldInputFromEvent(ev);
      const cell = ev.target && ev.target.closest ? ev.target.closest("td[data-roster-field-cell]") : null;
      const input = focusedInput
        || (cell ? cell.querySelector("input[data-roster-field-date]") : null)
        || activeRosterFieldInput(report);
      if (!input) return;
      const meta = rosterFieldMeta(input);
      if (!meta) return;
      const isEditing = focusedInput && input.dataset.rosterFieldEditing === "1";
      if (isEditing && ev.key === "Escape") {
        ev.preventDefault();
        cancelRosterFieldEdit(input);
        return;
      }
      if (!isEditing && ev.key === "F2") {
        ev.preventDefault();
        beginRosterFieldEdit(input, { select: true });
        return;
      }
      if (!isEditing && ev.key.length === 1 && !ev.ctrlKey && !ev.altKey && !ev.metaKey) {
        ev.preventDefault();
        beginRosterFieldEdit(input, { replaceValue: ev.key });
        input.dispatchEvent(new Event("input", { bubbles: true }));
        return;
      }
      if (!isEditing && (ev.key === "Delete" || ev.key === "Backspace")) {
        ev.preventDefault();
        input.value = "";
        input.dataset.rosterFieldEdited = "1";
        meta.def.afterChange(input);
        setUnsavedChanges("餐單參數");
        return;
      }
      // Tab／Shift-Tab 左右行（行到尾／頭就跳落一行／上一行），↑↓ 同 Enter 先係上下行。
      const isTab = ev.key === "Tab";
      const isVertBack = ev.key === "ArrowUp";
      const isVertForward = ev.key === "ArrowDown" || ev.key === "Enter";
      if (!isTab && !isVertBack && !isVertForward) return;
      ev.preventDefault();
      const idx = Number(input.dataset.rosterFieldIndex);
      if (!Number.isInteger(idx)) return;
      // 改咗就要 commit，唔理仲喺唔喺編輯 mode（Del 清空係唔會入編輯 mode 嘅）。
      if (input.dataset.rosterFieldEdited === "1") commitRosterFieldInput(input);
      if (isEditing) endRosterFieldEdit(input);
      const target = isTab
        ? rosterFieldNeighbour(report, meta.key, idx, ev.shiftKey ? -1 : 1)
        : ((report.__rosterFieldInputs || {})[meta.key] || [])[idx + (isVertForward ? 1 : -1)] || null;
      if (target) {
        focusRosterFieldInputElement(target);
      } else if (isVertBack || (isTab && ev.shiftKey)) {
        focusActiveRosterCell();
      } else {
        focusRosterFieldInputElement(input);
      }
    }

    // 由左至右數第 n 個可編輯格（ROSTER_FIELD_KEYS 順序＝表格欄次序）。
    function rosterFieldNeighbour(report, key, index, step) {
      const pos = ROSTER_FIELD_KEYS.indexOf(key);
      if (pos < 0) return null;
      const flat = pos + index * ROSTER_FIELD_KEYS.length + step;
      if (flat < 0) return null;
      const nextKey = ROSTER_FIELD_KEYS[flat % ROSTER_FIELD_KEYS.length];
      const inputs = (report.__rosterFieldInputs || {})[nextKey] || [];
      return inputs[Math.floor(flat / ROSTER_FIELD_KEYS.length)] || null;
    }

    function updateRosterWakeOverrideClass(input) {
      const cell = input && input.closest ? input.closest("td[data-roster-field-cell]") : null;
      if (!cell) return;
      const current = normalTime(input.value) || "";
      const def = normalTime(input.getAttribute("data-roster-field-default") || "") || "";
      cell.classList.toggle("roster-wake-override", !!current && current !== def);
    }

    // 備註格：左邊係公眾假期／醫療行程／加班表拼出嚟嘅唯讀文字，右邊先係手寫備註；
    // 兩邊都有嘢先顯示中間個「/」。冇手寫備註就唔佔位（否則 auto 文字後面會多咗一行空白），
    // 開始打字（input 攞到 focus）先至撐開。
    function updateRosterNoteLayout(input) {
      const cell = input && input.closest ? input.closest("td[data-roster-field-cell]") : null;
      if (!cell) return;
      const text = String(input.value || "").trim();
      input.dataset.rosterNoteEmpty = text ? "0" : "1";
      const auto = cell.querySelector(".roster-note-auto");
      const sep = cell.querySelector(".roster-note-sep");
      if (!sep) return;
      const hasAuto = !!(auto && String(auto.textContent || "").trim());
      sep.hidden = !(hasAuto && text);
    }

    function handleRosterFieldInput(ev) {
      const input = rosterFieldInputFromEvent(ev);
      if (!input) return;
      const meta = rosterFieldMeta(input);
      if (!meta) return;
      const wasEdited = input.dataset.rosterFieldEdited === "1";
      input.dataset.rosterFieldEdited = "1";
      meta.def.afterChange(input);
      if (!wasEdited) setUnsavedChanges("餐單參數");
    }

    function handleRosterFieldFocusIn(ev) {
      const cell = ev.target && ev.target.closest ? ev.target.closest("td[data-roster-field-cell]") : null;
      if (cell && ev.target === cell) {
        const input = cell.querySelector("input[data-roster-field-date]");
        if (input) markRosterFieldActive(cell.closest("#maint-roster-report"), input, { focus: false });
        return;
      }
      const input = rosterFieldInputFromEvent(ev);
      if (!input) return;
      const report = input.closest("#maint-roster-report");
      markRosterFieldActive(report, input, { focus: false });
      if (report && report.__rosterFieldProgramViewFocus === input) {
        report.__rosterFieldProgramViewFocus = null;
        return;
      }
      if (report && report.__rosterFieldProgramInputFocus === input) {
        report.__rosterFieldProgramInputFocus = null;
        return;
      }
      beginRosterFieldEdit(input, { select: true });
    }

    function handleRosterFieldFocusOut(ev) {
      const input = rosterFieldInputFromEvent(ev);
      if (!input) return;
      if (input.dataset.rosterFieldEdited === "1") commitRosterFieldInput(input);
      endRosterFieldEdit(input);
    }

    function handleRosterFieldMouseDown(ev) {
      const cell = ev.target && ev.target.closest ? ev.target.closest("td[data-roster-field-cell]") : null;
      if (!cell) return;
      const input = cell.querySelector("input[data-roster-field-date]");
      if (!input) return;
      ev.preventDefault();
      markRosterFieldActive(cell.closest("#maint-roster-report"), input, { focus: false });
      beginRosterFieldEdit(input, { select: true });
    }

    function focusRosterFieldInputElement(input) {
      if (!input) return false;
      const report = input.closest("#maint-roster-report");
      markRosterFieldActive(report, input, { focus: false });
      endRosterFieldEdit(input);
      input.readOnly = true;
      const cell = input.closest("td[data-roster-field-cell]");
      if (cell) cell.focus({ preventScroll: true });
      return true;
    }

    function beginRosterFieldEdit(input, options = {}) {
      if (!input) return false;
      if (input.dataset.rosterFieldEditing !== "1") {
        input.dataset.rosterFieldOriginalValue = input.value || "";
      }
      input.dataset.rosterFieldEditing = "1";
      input.readOnly = false;
      // 一入編輯 mode 就即刻撐開個位（唔靠 CSS :focus——window 冇 focus 嗰陣佢會唔中）。
      if (input.dataset.rosterNoteEmpty === "1") input.dataset.rosterNoteEmpty = "0";
      if (Object.prototype.hasOwnProperty.call(options, "replaceValue")) {
        input.value = options.replaceValue == null ? "" : String(options.replaceValue);
        input.dataset.rosterFieldEdited = "1";
        setUnsavedChanges("餐單參數");
      }
      focusRosterFieldInputForEdit(input);
      if (options.select) input.select();
      else setRosterFieldCaretToEnd(input);
      return true;
    }

    function endRosterFieldEdit(input) {
      if (!input) return;
      delete input.dataset.rosterFieldEditing;
      delete input.dataset.rosterFieldOriginalValue;
      input.readOnly = true;
      const meta = rosterFieldMeta(input);
      if (meta) meta.def.afterChange(input);
    }

    function cancelRosterFieldEdit(input) {
      if (!input) return false;
      if (input.dataset.rosterFieldEditing === "1") {
        input.value = input.dataset.rosterFieldOriginalValue || "";
        input.dataset.rosterFieldEdited = "0";
        const meta = rosterFieldMeta(input);
        if (meta) meta.def.afterChange(input);
        endRosterFieldEdit(input);
      }
      const report = input.closest("#maint-roster-report");
      markRosterFieldActive(report, input, { focus: true });
      return true;
    }

    function focusRosterFieldInputForEdit(input) {
      const report = input.closest("#maint-roster-report");
      if (report) report.__rosterFieldProgramInputFocus = input;
      input.focus({ preventScroll: true });
    }

    function setRosterFieldCaretToEnd(input) {
      if (!input || typeof input.setSelectionRange !== "function") return;
      const pos = String(input.value || "").length;
      input.setSelectionRange(pos, pos);
    }

    function rosterWakeValueForStorage(input, value) {
      const def = normalTime(input.getAttribute("data-roster-field-default") || "") || "";
      return value && (!def || value !== def) ? value : "";
    }

    function commitRosterFieldInput(input, options = {}) {
      if (!input) return false;
      const meta = rosterFieldMeta(input);
      if (!meta) return false;
      const raw = String(input.value || "").trim();
      const value = meta.def.format(raw);
      if (raw && !value && meta.def.strict) {
        if (options.allowInvalid) return false;
        throw new Error(meta.def.invalidMessage(String(input.getAttribute("data-roster-field-date") || ""), raw));
      }
      if (value) input.value = value;
      meta.def.afterChange(input);
      const last = input.dataset.rosterFieldLastSynced || "";
      if (input.dataset.rosterFieldEdited !== "1" && value === last) return true;
      const key = String(input.getAttribute("data-roster-field-date") || "").trim();
      if (!key) return false;
      writeRosterWakeAlarmRow(key, meta.def.patch(input, value));
      input.dataset.rosterFieldLastSynced = value;
      input.dataset.rosterFieldEdited = "0";
      return true;
    }

    function syncRosterFieldInputsToSources() {
      document.querySelectorAll("#maint-roster-report input[data-roster-field-date]").forEach((input) => {
        commitRosterFieldInput(input);
      });
    }

    // 起身表 = 逐日 overlay（起身時間／備註）：兩個欄位各自寫、唔會互相洗走；
    // 兩個都空嘅日子就唔留行。
    function writeRosterWakeAlarmRow(key, patch) {
      const existing = Array.isArray(rosterReportSources.wake_alarms) && rosterReportSources.wake_alarms.length
        ? rosterReportSources.wake_alarms
        : [["日期", "起身時間", "備註"]];
      const defaultHeader = ["日期", "起身時間", "備註"];
      const header = Array.isArray(existing[0]) ? [...existing[0]] : [...defaultHeader];
      while (header.length < defaultHeader.length) header.push(defaultHeader[header.length]);
      const entries = [];
      let found = false;
      existing.slice(1).forEach((row) => {
        if (!Array.isArray(row)) return;
        const d = parseYmd(row[0]);
        const rowKey = d ? dateKey(d.year, d.month, d.day) : "";
        if (!rowKey) return;
        const entry = { key: rowKey, wake: normalTime(row[1]) || "", note: String(row[2] || "").trim() };
        if (rowKey === key) {
          found = true;
          if (Object.prototype.hasOwnProperty.call(patch, "wake")) entry.wake = patch.wake || "";
          if (Object.prototype.hasOwnProperty.call(patch, "note")) entry.note = patch.note || "";
        }
        if (entry.wake || entry.note) entries.push(entry);
      });
      if (!found) {
        const entry = { key, wake: patch.wake || "", note: patch.note || "" };
        if (entry.wake || entry.note) entries.push(entry);
      }
      entries.sort((a, b) => String(a.key).localeCompare(String(b.key)));
      rosterReportSources.wake_alarms = [header, ...entries.map((e) => [e.key, e.wake, e.note])];
      return true;
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
        startWindowDrag({
          bodyClass: "is-horizontal-dragging",
          onMove: (mv) => {
            formColumnWidths.maint_roster_report_offset = startOffset + (mv.clientX - startX);
            applyRosterReportOffset();
          },
          onUp: () => {
            persistColumnWidths();
          },
        });
      };
      pane.querySelector(".maint-pane-title")?.addEventListener("mousedown", startDrag);
    }
