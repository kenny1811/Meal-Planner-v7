
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

    function beginRosterCellEdit(input, replaceValue = false) {
      if (!input) return;
      input.dataset.maintOriginalValue = input.value;
      input.readOnly = false;
      input.dataset.maintEditing = "1";
      input.dataset.maintReplaceOnComposition = replaceValue ? "1" : "";
      input.focus();
      if (replaceValue) input.value = "";
      const pos = replaceValue ? 0 : String(input.value || "").length;
      input.setSelectionRange(pos, pos);
    }

    function syncMaintSavedBaselines(root = document) {
      root.querySelectorAll("#maint-editor textarea[data-maint-roster-row]").forEach((input) => {
        input.dataset.maintSavedValue = input.value;
        if (input.dataset.maintEditing === "1") {
          input.dataset.maintOriginalValue = input.value;
        }
      });
      // report 嘅起身／備註格同 textarea 一樣要記低 baseline：text input 係失焦先 fire change，
      // 冇 baseline 嘅話儲存完離開個格會又一次標「未儲存」。
      root.querySelectorAll("#maint-roster-report input[data-roster-field-date]").forEach((input) => {
        input.dataset.maintSavedValue = input.value;
      });
    }

    function rosterCodeIssuesText(issues) {
      const parts = issues.map((issue) => {
        const code = String((issue && issue.roster_code) || "").trim() || "(空白)";
        const dates = Array.isArray(issue && issue.dates) ? issue.dates : [];
        const shown = dates.slice(0, 4).join("、");
        const more = dates.length > 4 ? ` 等 ${dates.length} 日` : "";
        const reason = issue && issue.reason;
        const why = reason === "unknown_code"
          ? "行位表冇呢個更碼"
          : reason === "missing_report_rows"
            ? "當日版本冇齊「報開工／報收工」兩行"
            : "當日冇已生效嘅行位表版本";
        return `${code}：${why}（${shown}${more}）`;
      });
      return `有更碼攞唔到行位表 ——\n${parts.join("\n")}`;
    }

    let rosterCodeCheckBusy = false;

    /** 離開一行更表時查嗰行嘅更碼；有問題就問要唔要留低更正。 */
    async function checkRosterLineOnLeave(input) {
      if (!input || rosterCodeCheckBusy) return;
      const text = String(input.value || "");
      rosterCodeCheckBusy = true;
      let issues = [];
      try {
        const result = await checkRosterLine(text);
        issues = Array.isArray(result && result.issues) ? result.issues : [];
      } catch (_) {
        issues = [];
      } finally {
        rosterCodeCheckBusy = false;
      }
      if (!issues.length) return false;
      if (!window.confirm(`${rosterCodeIssuesText(issues)}\n\n要唔要返去更正？`)) return false;
      const rowIdx = Number(input.getAttribute("data-maint-roster-row"));
      if (Number.isInteger(rowIdx)) setActiveRosterMonthIndex(rowIdx);
      beginRosterCellEdit(input);
      return true;
    }

    /**
     * Ctrl+S／Save 掣：每次都查成張更表（唔止編輯緊嗰行，亦唔壓抑重覆提問），
     * 確保冇問題更碼可以靜靜雞寫入。回傳 false = 用戶要留低更正，唔好儲存。
     */
    async function checkRosterCodesBeforeSave(rows) {
      if (activeMaintSheetKey !== "roster") return true;
      let issues = [];
      try {
        const result = await checkRosterRows(rows);
        issues = Array.isArray(result && result.issues) ? result.issues : [];
      } catch (_) {
        issues = [];
      }
      if (!issues.length) return true;
      if (!window.confirm(`${rosterCodeIssuesText(issues)}\n\n要唔要返去更正？（撳「取消」= 照樣儲存）`)) return true;
      focusRosterRowForIssue(issues[0]);
      return false;
    }

    /** 跳返去出事嗰行：先按日期嘅年月配對，配唔到就搵含住嗰個更碼嘅行。 */
    function focusRosterRowForIssue(issue) {
      const inputs = Array.from(document.querySelectorAll("#maint-editor textarea[data-maint-roster-row]"));
      if (!inputs.length) return;
      const firstDate = Array.isArray(issue && issue.dates) ? String(issue.dates[0] || "") : "";
      const label = firstDate.slice(0, 7);
      const code = String((issue && issue.roster_code) || "").trim();
      const target = inputs.find((input) => {
        const parsed = parseRosterMaintLine(input.value);
        return parsed && label && parsed.label === label;
      }) || inputs.find((input) => code && String(input.value || "").includes(code));
      if (!target) return;
      const rowIdx = Number(target.getAttribute("data-maint-roster-row"));
      if (Number.isInteger(rowIdx)) setActiveRosterMonthIndex(rowIdx);
      target.scrollIntoView({ block: "nearest", inline: "nearest" });
      beginRosterCellEdit(target);
    }

    function endRosterCellEdit(input, options = {}) {
      if (!input) return;
      if (options.cancel) {
        input.value = input.dataset.maintOriginalValue || "";
      }
      const editedValue = input.dataset.maintEditing === "1" && !options.cancel
        ? String(input.value || "")
        : null;
      const beforeEdit = String(input.dataset.maintOriginalValue || "");
      input.readOnly = true;
      delete input.dataset.maintEditing;
      delete input.dataset.maintOriginalValue;
      delete input.dataset.maintReplaceOnComposition;
      delete input.dataset.maintPendingDirectKey;
      const timer = rosterDirectKeyTimers.get(input);
      if (timer) clearTimeout(timer);
      rosterDirectKeyTimers.delete(input);
      autoResizeTextarea(input);
      // 郁過就查（連加個 space 都算），有錯就即刻彈。
      if (editedValue !== null && editedValue !== beforeEdit) {
        checkRosterLineOnLeave(input);
      }
    }

    function focusRosterCell(rowIdx) {
      const input = document.querySelector(`#maint-editor textarea[data-maint-roster-row="${rowIdx}"]`);
      if (!input) return false;
      input.focus();
      input.scrollIntoView({ block: "nearest", inline: "nearest" });
      return true;
    }

    function lastRosterCellIndex() {
      const indexes = Array.from(document.querySelectorAll("#maint-editor textarea[data-maint-roster-row]"))
        .map((input) => Number(input.getAttribute("data-maint-roster-row")))
        .filter((idx) => Number.isInteger(idx) && idx >= 0);
      return indexes.length ? Math.max(...indexes) : -1;
    }

    function focusLastRosterCell() {
      const idx = lastRosterCellIndex();
      return idx >= 0 && focusRosterCell(idx);
    }

    function focusActiveRosterCell() {
      return focusRosterCell(activeRosterMonthIndex) || focusLastRosterCell();
    }

    function rosterWakeInputs() {
      return Array.from(document.querySelectorAll("#maint-roster-report input[data-roster-field=\"wake\"]"))
        .filter((input) => input.dataset.rosterFieldEditable === "1" && !input.disabled);
    }

    function focusRosterWakeInput(index) {
      const inputs = rosterWakeInputs();
      if (!inputs.length) return false;
      const idx = Math.max(0, Math.min(index, inputs.length - 1));
      const input = inputs[idx];
      if (typeof focusRosterFieldInputElement === "function") return focusRosterFieldInputElement(input);
      input.focus({ preventScroll: true });
      input.select();
      return true;
    }

    function focusFirstRosterWakeInput() {
      return focusRosterWakeInput(0);
    }
    const rosterDirectKeyTimers = new WeakMap();

    function handleRosterCellKeydown(ev) {
      const input = ev.currentTarget;
      const rowIdx = Number(input.getAttribute("data-maint-roster-row"));
      const isLastRosterCell = rowIdx === lastRosterCellIndex();
      if (input.dataset.maintEditing === "1") {
        if (ev.key === "ArrowUp" || ev.key === "ArrowDown") {
          if (textareaShouldKeepArrow(input, ev.key)) return;
        }
        if (ev.key === "Enter" || ev.key === "Escape" || ev.key === "ArrowUp" || ev.key === "ArrowDown" || ev.key === "Tab") {
          ev.preventDefault();
          endRosterCellEdit(input, { cancel: ev.key === "Escape" });
          if ((ev.key === "Enter" || ev.key === "ArrowDown" || (ev.key === "Tab" && !ev.shiftKey)) && isLastRosterCell && focusFirstRosterWakeInput()) {
            return;
          }
          if (ev.key === "Enter" || ev.key === "ArrowUp" || ev.key === "ArrowDown" || ev.key === "Tab") {
            const delta = ev.key === "ArrowUp" ? -1 : 1;
            if (ev.key === "Tab" && ev.shiftKey) focusRosterCell(rowIdx - 1) || input.focus();
            else if (ev.key === "Tab") focusRosterCell(rowIdx + 1) || input.focus();
            else focusRosterCell(rowIdx + delta) || input.focus();
          } else {
            input.focus();
          }
        }
        return;
      }
      if ((ev.key === "ArrowDown" || ev.key === "Enter" || (ev.key === "Tab" && !ev.shiftKey)) && isLastRosterCell && focusFirstRosterWakeInput()) {
        ev.preventDefault();
        return;
      }
      if (ev.key === "ArrowUp" || ev.key === "ArrowDown" || ev.key === "Enter" || ev.key === "Tab") {
        ev.preventDefault();
        const delta = ev.key === "ArrowUp" || (ev.key === "Tab" && ev.shiftKey) ? -1 : 1;
        focusRosterCell(rowIdx + delta);
        return;
      }
      if (ev.key === "F2") {
        ev.preventDefault();
        beginRosterCellEdit(input);
        return;
      }
      if (ev.key === "Process" && !ev.ctrlKey && !ev.altKey && !ev.metaKey) {
        beginRosterCellEdit(input, true);
        return;
      }
      if (ev.key.length === 1 && !ev.ctrlKey && !ev.altKey && !ev.metaKey) {
        beginRosterCellEdit(input, true);
      }
    }

    function attachRosterSplitResizer(editor) {
      const grip = editor.querySelector("#maint-roster-report-resizer");
      const split = editor.querySelector(".maint-roster-split");
      if (!grip || !split || grip.dataset.bound === "1") return;
      grip.dataset.bound = "1";
      grip.addEventListener("mousedown", (ev) => {
        ev.preventDefault();
        const rect = split.getBoundingClientRect();
        startWindowDrag({
          onMove: (mv) => {
            const topHeight = Math.max(0, Math.min(rect.height - 6, mv.clientY - rect.top));
            formColumnWidths.maint_roster_top_height = topHeight;
            split.style.gridTemplateRows = `${topHeight}px 6px 1fr`;
          },
          onUp: () => {
            persistColumnWidths();
          },
        });
      });
    }

    function renderRosterGcSyncToggle() {
      const authenticated = !!(googleCalendarAuth && googleCalendarAuth.authenticated);
      const active = authenticated && !!(googleCalendarSync && googleCalendarSync.enabled && googleCalendarSync.write);
      return `<div class="gc-sync-controls">
        <label class="gc-sync-toggle" title="開啟後，儲存更表會同步寫入 Google Calendar">
          <input type="checkbox" id="roster-gc-sync-toggle" ${active ? "checked" : ""} ${authenticated ? "" : "disabled"} />
          <span class="gc-sync-slider" aria-hidden="true"></span>
          <span class="gc-sync-label">儲存時同時更新到GC</span>
        </label>
        <button class="gc-sync-login" id="roster-gc-login" type="button" title="登入並授權 Google Calendar">${authenticated ? "已登入" : "請登入"}</button>
        <span class="gc-sync-status" id="roster-gc-status"></span>
      </div>`;
    }

    function attachRosterGcSyncToggle(editor) {
      const toggle = editor.querySelector("#roster-gc-sync-toggle");
      const login = editor.querySelector("#roster-gc-login");
      const status = editor.querySelector("#roster-gc-status");
      const applyAuthState = async (auth, options = {}) => {
        googleCalendarAuth = {
          ...(googleCalendarAuth || {}),
          ...(auth || {}),
          authenticated: !!(auth && auth.authenticated),
        };
        if (toggle) {
          toggle.disabled = !googleCalendarAuth.authenticated;
          toggle.checked = googleCalendarAuth.authenticated && !!(googleCalendarSync && googleCalendarSync.enabled && googleCalendarSync.write);
        }
        if (login) {
          login.disabled = !!googleCalendarAuth.authenticated;
          login.textContent = googleCalendarAuth.authenticated ? "已登入" : "請登入";
          login.title = googleCalendarAuth.authenticated ? "Google Calendar 已登入" : "登入並授權 Google Calendar";
        }
        if (!googleCalendarAuth.authenticated) {
          if (googleCalendarSync && (googleCalendarSync.enabled || googleCalendarSync.write)) {
            googleCalendarSync = { ...(googleCalendarSync || {}), enabled: false, write: false };
            await persistGoogleCalendarSync();
          }
          if (status) status.textContent = "";
        } else if (status && (options.showConnected || !status.textContent)) {
          status.textContent = "";
        }
      };
      const refreshAuthState = async () => {
        try {
          await applyAuthState(await loadGoogleCalendarAuthStatus());
        } catch (_) {
          await applyAuthState({ authenticated: false, status: "unknown" });
        }
      };
      const persist = async () => {
        if (!googleCalendarAuth || !googleCalendarAuth.authenticated) {
          if (toggle) toggle.checked = false;
          googleCalendarSync = { ...(googleCalendarSync || {}), enabled: false, write: false };
          await persistGoogleCalendarSync();
          if (status) status.textContent = "";
          return;
        }
        const current = googleCalendarSync || {};
        googleCalendarSync = {
          ...current,
          enabled: !!(toggle && toggle.checked),
          write: !!(toggle && toggle.checked),
        };
        await persistGoogleCalendarSync();
      };
      [toggle, login].forEach((el) => {
        if (!el) return;
        el.addEventListener("input", (ev) => ev.stopPropagation());
        el.addEventListener("change", (ev) => ev.stopPropagation());
        el.addEventListener("keydown", (ev) => ev.stopPropagation());
        el.addEventListener("mousedown", (ev) => ev.stopPropagation());
      });
      if (toggle) toggle.addEventListener("change", persist);
      if (login) login.addEventListener("click", async () => {
        if (googleCalendarAuth && googleCalendarAuth.authenticated) return;
        if (status) status.textContent = "登入中...";
        login.disabled = true;
        try {
          const result = await connectGoogleCalendar();
          if (result && result.token_file) {
            googleCalendarSync = { ...(googleCalendarSync || {}), token_file: result.token_file };
            await persist();
          }
          await applyAuthState({ ...result, authenticated: true }, { showConnected: true });
        } catch (err) {
          if (status) status.textContent = String(err && err.message ? err.message : err);
        } finally {
          login.disabled = !!(googleCalendarAuth && googleCalendarAuth.authenticated);
        }
      });
      refreshAuthState();
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
          <td data-form-col-key="maint_roster_text"><textarea data-auto-row-height data-maint-roster-row="${rIdx}" data-maint-saved-value="${esc(text ?? "")}" aria-label="${esc(label)}" spellcheck="false" readonly>${esc(text ?? "")}</textarea></td>
        </tr>`;
      }).join("");
      const topHeight = Number(formColumnWidths.maint_roster_top_height);
      const splitStyle = Number.isFinite(topHeight) ? ` style="grid-template-rows:${Math.max(0, topHeight)}px 6px 1fr"` : "";
      editor.innerHTML = `<div class="maint-sheet-title maint-roster-title">
          <div class="maint-roster-title-left">${renderRosterGcSyncToggle()}</div>
        </div>
        <div class="maint-roster-split"${splitStyle}>
          <section class="maint-roster-pane">
            <div class="maint-pane-title">${esc(menuLabel("roster"))}</div>
            <table class="maint-roster-table" data-form-table>
              <colgroup>
                <col data-form-col-key="maint_roster_text" data-form-col-default="760" />
              </colgroup>
              <tbody>${monthRows || '<tr><td class="maint-empty">No roster months</td></tr>'}</tbody>
            </table>
          </section>
          <div id="maint-roster-report-resizer" class="maint-roster-report-resizer" title="Drag to resize report height"></div>
          <section class="maint-roster-pane" id="maint-roster-report-pane">
            <div class="maint-pane-title" title="Drag left or right to move report">${esc(menuLabel("roster"))}報表</div>
            <div id="maint-roster-report">${renderRosterMaintReport(rows)}</div>
          </section>
        </div>`;
      editor.querySelectorAll("textarea[data-maint-roster-row]").forEach((input) => {
        input.readOnly = true;
        input.addEventListener("focus", () => setActiveRosterMonthIndex(Number(input.getAttribute("data-maint-roster-row"))));
        input.addEventListener("mousedown", () => setActiveRosterMonthIndex(Number(input.getAttribute("data-maint-roster-row"))));
        input.addEventListener("input", () => {
          activeRosterMonthIndex = Number(input.getAttribute("data-maint-roster-row"));
          setUnsavedChanges("餐單參數");
          refreshRosterMaintReport();
        });
        input.addEventListener("blur", () => endRosterCellEdit(input));
        input.addEventListener("dblclick", () => beginRosterCellEdit(input));
        input.addEventListener("compositionstart", () => {
          if (input.readOnly) {
            beginRosterCellEdit(input, true);
          }
          const timer = rosterDirectKeyTimers.get(input);
          if (timer) {
            clearTimeout(timer);
            rosterDirectKeyTimers.delete(input);
          }
          delete input.dataset.maintPendingDirectKey;
          delete input.dataset.maintReplaceOnComposition;
        });
        input.addEventListener("keydown", handleRosterCellKeydown);
      });
      editor.querySelectorAll(".maint-roster-table tr[data-maint-row-index]").forEach((row) => {
        row.addEventListener("mousedown", () => setActiveRosterMonthIndex(Number(row.getAttribute("data-maint-row-index"))));
      });
      bindMaintContextMenu(editor);
      attachRosterGcSyncToggle(editor);
      attachRosterFieldInputs(editor);
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

    function isScheduleGridEffectiveCol(colIndex) {
      if (activeMaintSheetKey !== "schedule_grid" && maintSheetPayload.sheet_key !== "schedule_grid") return false;
      const header = Array.isArray(maintSheetPayload.rows && maintSheetPayload.rows[0]) ? maintSheetPayload.rows[0] : [];
      const text = String(header[colIndex] || "").trim();
      return text === "生效日期" || text === "生效" || text === "Effective From";
    }

    function isMaintDateDisplayCol(colIndex) {
      const header = Array.isArray(maintSheetPayload.rows && maintSheetPayload.rows[0]) ? maintSheetPayload.rows[0] : [];
      const text = String(header[colIndex] || "").trim();
      return text === "日期" || text === "生效日期" || text === "生效" || text === "Effective From";
    }

    function isScheduleGridTimeCol(colIndex) {
      if (activeMaintSheetKey !== "schedule_grid" && maintSheetPayload.sheet_key !== "schedule_grid") return false;
      const header = Array.isArray(maintSheetPayload.rows && maintSheetPayload.rows[0]) ? maintSheetPayload.rows[0] : [];
      return String(header[colIndex] || "").trim() === "時間";
    }

    function formatMaintTimeValue(sheetKey, rowIndex, colIndex, value, isInputEvent = false) {
      if (rowIndex === 0) return value;
      const s = String(value ?? "").trim();
      if (!s) return "";

      if (isMaintDateDisplayCol(colIndex)) {
        if (isInputEvent) return value;
        const d = parseYmd(s);
        if (d) return dateDmyDow(d.year, d.month, d.day);
      }

      if (sheetKey === "schedule_grid" && isScheduleGridTimeCol(colIndex)) {
        if (isInputEvent) return value;
        return normalTime(s) || s;
      }

      if (sheetKey === "payroll_times") {
        const header = Array.isArray(maintSheetPayload.rows && maintSheetPayload.rows[0]) ? maintSheetPayload.rows[0] : [];
        const name = String(header[colIndex] || "").trim();
        if (name === "開始時間" || name === "結束時間") {
          if (isInputEvent) return value;
          return normalTime(s) || s;
        }
      }

      if (sheetKey === "overtime") {
        if (colIndex === 0) {
          if (isInputEvent) return value;
          const d = parseYmd(s);
          if (d) return dateDmy(d.year, d.month, d.day);
        } else if (colIndex === 1 || colIndex === 2) {
          if (isInputEvent) return value;
          // 30 小時制：00:00–05:59 一律存做 24:00–29:59（加班表用 HHMM 冇冒號）。
          const t = normalTime(s);
          if (t) return t.replace(":", "");
        }
        return isInputEvent ? value : s;
      }

      if (sheetKey === "medical_appointments" && colIndex === 2) {
        if (isInputEvent) return value;
        const t = normalTime(s);
        if (t) return t;
      }

      return value;
    }

    function isMaintMoneyColumn(sheetKey, rowIndex, colIndex) {
      return sheetKey === "medical_appointments" && rowIndex > 0 && (colIndex === 4 || colIndex === 5);
    }

    function isMaintDurationColumn(sheetKey, rowIndex, colIndex) {
      return sheetKey === "schedule_grid" && rowIndex > 0 && colIndex === 3;
    }

    function isPlainMoneyValue(value) {
      return /^\s*\d+(?:,\d{3})*(?:\.\d+)?\s*$/.test(String(value ?? ""));
    }

    function maintCellClass(sheetKey, rowIndex, colIndex, value) {
      const classes = [];
      if (isMaintDurationColumn(sheetKey, rowIndex, colIndex)) {
        classes.push("maint-duration-cell");
      }
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
      writeMaintInputToMemory(input, isInputEvent);
      const cell = input.closest("td");
      if (cell) {
        cell.classList.toggle("maint-duration-cell", isMaintDurationColumn(activeMaintSheetKey, rowIndex, colIndex));
        cell.classList.toggle("maint-money-cell", isMaintMoneyColumn(activeMaintSheetKey, rowIndex, colIndex) && isPlainMoneyValue(input.value));
      }
    }

    let currentMaintFilter = "";
    let currentMaintEffectiveFilter = "";
    let currentMaintYearFilter = "";
    let scheduleGridPickerRefreshBusy = false;

    function maintFilterStore() {
      try {
        return JSON.parse(window.localStorage.getItem("mealplanner_maint_filters") || "{}") || {};
      } catch (_) {
        return {};
      }
    }

    function loadMaintFilterState(sheetKey) {
      const state = maintFilterStore()[sheetKey] || {};
      currentMaintFilter = String(state.code || "");
      currentMaintEffectiveFilter = String(state.effective || "");
      currentMaintYearFilter = String(state.year || "");
    }

    function saveMaintFilterState(sheetKey) {
      try {
        const store = maintFilterStore();
        store[sheetKey] = {
          code: currentMaintFilter === SCHEDULE_GRID_NEW_SHIFT_FILTER ? "" : (currentMaintFilter || ""),
          effective: currentMaintEffectiveFilter || "",
          year: currentMaintYearFilter || "",
        };
        window.localStorage.setItem("mealplanner_maint_filters", JSON.stringify(store));
      } catch (_) {}
    }

    /** 撳停用／啟用：改「停用」欄，跟住成張表重算時長，再 render。 */
    function bindMaintDisableToggles(root) {
      root.querySelectorAll("[data-maint-disable-row]").forEach((btn) => {
        btn.addEventListener("click", (ev) => {
          ev.preventDefault();
          ev.stopPropagation();
          const rIdx = Number(btn.getAttribute("data-maint-disable-row"));
          if (!Number.isInteger(rIdx) || rIdx <= 0) return;
          const rows = collectMaintRows();
          const header = Array.isArray(rows[0]) ? rows[0] : [];
          let offIdx = header.findIndex((cell) => String(cell || "").trim() === "停用");
          if (offIdx < 0) {
            offIdx = header.length;
            rows[0] = [...header, "停用"];
          }
          const row = Array.isArray(rows[rIdx]) ? [...rows[rIdx]] : [];
          while (row.length <= offIdx) row.push("");
          const nowDisabled = !String(row[offIdx] || "").trim();
          row[offIdx] = nowDisabled ? "1" : "";
          rows[rIdx] = row;
          maintSheetPayload.rows = recomputeScheduleGridDurations(rows);
          setUnsavedChanges("餐單參數");
          // 唔叫 renderMaintEditor()——重砌 639 行又慢又會令捲軸彈返上頂。
          // 撳停用實際只郁三樣嘢：嗰行 dim、粒掣個字、受影響嗰幾格時長／內容。
          applyScheduleGridDisableInPlace(rIdx, nowDisabled, btn);
        });
      });
    }

    /** 撳完停用／啟用，直接改 DOM：唔重砌，所以捲軸唔會郁。 */
    function applyScheduleGridDisableInPlace(rIdx, nowDisabled, btn) {
      const rows = Array.isArray(maintSheetPayload.rows) ? maintSheetPayload.rows : [];
      const header = Array.isArray(rows[0]) ? rows[0].map((c) => String(c || "").trim()) : [];
      const cContent = header.indexOf("內容");
      const cDur = header.indexOf("時長");
      const tr = document.querySelector(`#maint-editor tr[data-maint-row-index="${rIdx}"]`);
      if (tr) tr.classList.toggle("maint-row-off", nowDisabled);
      if (btn) btn.textContent = nowDisabled ? "Enable" : "Disable";
      // 停用一格會令前後幾格時長重算，所以內容／時長兩欄全部同步返（只寫有變嘅格）。
      [cContent, cDur].forEach((cIdx) => {
        if (cIdx < 0) return;
        document.querySelectorAll(`#maint-editor [data-maint-row][data-maint-col="${cIdx}"]`).forEach((input) => {
          const r = Number(input.getAttribute("data-maint-row"));
          if (!Number.isInteger(r) || r <= 0 || !Array.isArray(rows[r])) return;
          const value = String(rows[r][cIdx] ?? "");
          if (input.value === value) return;
          input.value = value;
          if (input.tagName.toLowerCase() === "textarea") autoResizeTextarea(input);
        });
      });
    }

    /** 內容尾巴嗰個數字同時長欄一致：先剝走舊數字，再貼返新嘅（同電腦出 label 一樣做法）。 */
    function contentWithDuration(content, duration) {
      const base = String(content ?? "").replace(/\s+\d{1,3}$/, "").trim();
      if (!base) return String(content ?? "").trim();
      return duration ? `${base} ${duration}` : base;
    }

    /**
     * 重算時長：一格嘅時長 ＝ 去下一個「佔時間」行嘅距離。
     * `-` 開頭嘅 marker 行同停用行都唔佔時間，前一格跨過佢哋；最後一格留空。
     * 逐個（更碼 + 生效日期）版本各自計。
     */
    function recomputeScheduleGridDurations(rows) {
      if (maintSheetPayload.sheet_key !== "schedule_grid" || !Array.isArray(rows[0])) return rows;
      const header = rows[0].map((cell) => String(cell || "").trim());
      const cCode = header.indexOf("更碼");
      const cTime = header.indexOf("時間");
      const cContent = header.indexOf("內容");
      const cDur = header.indexOf("時長");
      const cEff = header.findIndex((h) => h === "生效日期" || h === "生效" || h === "Effective From");
      const cOff = header.indexOf("停用");
      if (cCode < 0 || cTime < 0 || cContent < 0 || cDur < 0) return rows;

      const minutesOf = (text) => {
        const m = String(text || "").trim().match(/^(\d{1,2}):(\d{2})$/);
        return m ? Number(m[1]) * 60 + Number(m[2]) : null;
      };
      const groups = new Map();
      rows.forEach((row, rIdx) => {
        if (rIdx === 0 || !Array.isArray(row)) return;
        const key = `${String(row[cCode] || "").trim()}@@${cEff >= 0 ? String(row[cEff] || "").trim() : ""}`;
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(rIdx);
      });
      groups.forEach((indexes) => {
        const live = indexes.filter((rIdx) => {
          const row = rows[rIdx];
          const off = cOff >= 0 && String(row[cOff] || "").trim();
          const marker = String(row[cContent] || "").trim().startsWith("-");
          return !off && !marker && minutesOf(row[cTime]) !== null;
        }).sort((a, b) => minutesOf(rows[a][cTime]) - minutesOf(rows[b][cTime]));
        indexes.forEach((rIdx) => {
          if (!live.includes(rIdx)) {
            const row = [...rows[rIdx]];
            while (row.length <= cDur) row.push("");
            row[cDur] = "";
            row[cContent] = contentWithDuration(row[cContent], "");
            rows[rIdx] = row;
          }
        });
        live.forEach((rIdx, i) => {
          const row = [...rows[rIdx]];
          while (row.length <= cDur) row.push("");
          row[cDur] = i + 1 < live.length
            ? String(minutesOf(rows[live[i + 1]][cTime]) - minutesOf(rows[rIdx][cTime]))
            : "";
          row[cContent] = contentWithDuration(row[cContent], row[cDur]);
          rows[rIdx] = row;
        });
      });
      return rows;
    }

    function renderMaintEditor() {
      const editor = document.getElementById("maint-editor");
      if (!editor) return;
      editor.classList.toggle("maint-editor--roster", maintSheetPayload.sheet_key === "roster");
      if (maintSheetPayload.sheet_key === "roster") {
        currentMaintFilter = "";
        currentMaintEffectiveFilter = "";
        currentMaintYearFilter = "";
        renderRosterMaintEditor();
        return;
      }
      let rows = Array.isArray(maintSheetPayload.rows) ? maintSheetPayload.rows : [];
      if (maintSheetPayload.sheet_key === "schedule_grid" && Array.isArray(rows[0])) {
        const hasEffectiveCol = rows[0].some((cell) => {
          const text = String(cell || "").trim();
          return text === "生效日期" || text === "生效" || text === "Effective From";
        });
        if (!hasEffectiveCol) {
          rows = rows.map((row, idx) => {
            const next = Array.isArray(row) ? [...row] : [];
            next[4] = idx === 0 ? "生效日期" : (next[4] || "");
            return next;
          });
          maintSheetPayload.rows = rows;
        }
        // 「停用」欄係後加嘅 logical field：舊資料冇就即刻補上（同上面生效日期一樣做法）。
        const offColName = "停用";
        if (!rows[0].some((cell) => String(cell || "").trim() === offColName)) {
          const offIdx = rows[0].length;
          rows = rows.map((row, idx) => {
            const next = Array.isArray(row) ? [...row] : [];
            while (next.length < offIdx) next.push("");
            next[offIdx] = idx === 0 ? offColName : (next[offIdx] || "");
            return next;
          });
          maintSheetPayload.rows = rows;
        }
        if (!scheduleGridNewShiftBatchId && !scheduleGridSkipNextRenderSort) {
          rows = sortedScheduleGridRows(rows);
          maintSheetPayload.rows = rows;
        }
        scheduleGridSkipNextRenderSort = false;
      }
      loadMaintFilterState(maintSheetPayload.sheet_key || "");
      const cols = maintColumnCount(rows);
      const title = menuLabel(maintSheetPayload.sheet_key) || maintSheetPayload.display_name || "Sheet";
      const formKey = `maint_${maintSheetPayload.sheet_key || "sheet"}`;
      // 「停用」欄唔出，改為最前面一條窄欄放 toggle。
      const offColIdx = maintSheetPayload.sheet_key === "schedule_grid" && Array.isArray(rows[0])
        ? rows[0].findIndex((cell) => String(cell || "").trim() === "停用")
        : -1;
      const colGroup = (offColIdx >= 0 ? `<col data-form-col-key="${formKey}_col_off" data-form-col-default="56" />` : "")
        + Array.from({ length: cols }, (_, i) => (
          i === offColIdx ? "" : `<col data-form-col-key="${formKey}_col_${i}" data-form-col-default="160" />`
        )).join("");
      const isShiftCodeCol = (cIdx) => {
        return rows.length > 0 && Array.isArray(rows[0]) && String(rows[0][cIdx]).trim() === "更碼";
      };

      let shiftCodeColIdx = undefined;
      let effectiveColIdx = undefined;
      let dateColIdx = undefined;
      for (let i = 0; i < cols; i++) {
        if (isShiftCodeCol(i)) {
          shiftCodeColIdx = i;
          break;
        }
      }
      if (Array.isArray(rows[0])) {
        dateColIdx = rows[0].findIndex((cell) => String(cell || "").trim() === "日期");
        if (dateColIdx < 0) dateColIdx = undefined;
      }
      if (maintSheetPayload.sheet_key === "schedule_grid" && Array.isArray(rows[0])) {
        effectiveColIdx = rows[0].findIndex((cell) => {
          const text = String(cell || "").trim();
          return text === "生效日期" || text === "生效" || text === "Effective From";
        });
        if (effectiveColIdx < 0) effectiveColIdx = undefined;
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
        const newShiftOption = maintSheetPayload.sheet_key === "schedule_grid" && scheduleGridNewShiftBatchId
          ? `<option value="${SCHEDULE_GRID_NEW_SHIFT_FILTER}" ${currentMaintFilter === SCHEDULE_GRID_NEW_SHIFT_FILTER ? "selected" : ""}>&lt;new shift code&gt;</option>`
          : "";
        filterHtml = `<select id="maint-table-filter" class="maint-filter-select" style="margin-left: 16px; padding: 4px 8px; font-size: 0.9em; border-radius: 4px; border: 1px solid var(--border);">
          <option value="">全部更碼</option>
          ${newShiftOption}
          ${codes.map(c => `<option value="${esc(c)}" ${c === currentMaintFilter ? "selected" : ""}>${esc(c)}</option>`).join("")}
        </select>`;
      } else {
        currentMaintFilter = "";
      }
      if (effectiveColIdx !== undefined) {
        const uniqueVersions = new Set();
        for (let i = 1; i < rows.length; i++) {
          if (!Array.isArray(rows[i])) continue;
          const version = String(rows[i][effectiveColIdx] || "").trim();
          uniqueVersions.add(version || "__blank__");
        }
        const versions = Array.from(uniqueVersions).sort((a, b) => {
          if (a === "__blank__") return -1;
          if (b === "__blank__") return 1;
          return a.localeCompare(b);
        });
        if (!versions.includes(currentMaintEffectiveFilter)) currentMaintEffectiveFilter = "";
        filterHtml += `<select id="maint-effective-filter" class="maint-filter-select" style="margin-left: 8px; padding: 4px 8px; font-size: 0.9em; border-radius: 4px; border: 1px solid var(--border);">
          <option value="">全部生效日期</option>
          ${versions.map(v => `<option value="${esc(v)}" ${v === currentMaintEffectiveFilter ? "selected" : ""}>${esc(v === "__blank__" ? "未填生效日期" : v)}</option>`).join("")}
        </select>`;
      } else {
        currentMaintEffectiveFilter = "";
      }
      if (dateColIdx !== undefined) {
        const years = new Set();
        for (let i = 1; i < rows.length; i++) {
          if (!Array.isArray(rows[i])) continue;
          const d = parseYmd(rows[i][dateColIdx]);
          if (d && Number.isInteger(d.year)) years.add(String(d.year));
        }
        const yearOptions = Array.from(years).sort();
        if (!yearOptions.includes(currentMaintYearFilter)) currentMaintYearFilter = "";
        filterHtml += `<select id="maint-year-filter" class="maint-filter-select" style="margin-left: 8px; padding: 4px 8px; font-size: 0.9em; border-radius: 4px; border: 1px solid var(--border);">
          <option value="">全部年份</option>
          ${yearOptions.map(y => `<option value="${esc(y)}" ${y === currentMaintYearFilter ? "selected" : ""}>${esc(y)}</option>`).join("")}
        </select>`;
      } else {
        currentMaintYearFilter = "";
      }

      const visibleRows = rows.map((row, rIdx) => ({ row, rIdx })).filter(({ row, rIdx }) => {
        if (maintSheetPayload.sheet_key !== "schedule_grid" || rIdx === 0) return true;
        if (currentMaintFilter === SCHEDULE_GRID_NEW_SHIFT_FILTER) {
          return scheduleGridNewShiftBatchId
            && rIdx >= scheduleGridNewShiftStartIndex
            && rIdx < scheduleGridNewShiftStartIndex + scheduleGridNewShiftCount;
        }
        const codeVal = shiftCodeColIdx !== undefined && Array.isArray(row) ? String(row[shiftCodeColIdx] || "").trim() : "";
        const versionVal = effectiveColIdx !== undefined && Array.isArray(row)
          ? (normaliseEffectiveDateInput(row[effectiveColIdx]) || String(row[effectiveColIdx] || "").trim())
          : "";
        const versionKey = versionVal || "__blank__";
        const parsedDate = dateColIdx !== undefined && Array.isArray(row) ? parseYmd(row[dateColIdx]) : null;
        const rowYear = parsedDate ? String(parsedDate.year) : "";
        const codeMatches = !currentMaintFilter || codeVal === currentMaintFilter || codeVal === "";
        const versionMatches = !currentMaintEffectiveFilter || versionKey === currentMaintEffectiveFilter;
        const yearMatches = !currentMaintYearFilter || rowYear === currentMaintYearFilter || rowYear === "";
        return codeMatches && versionMatches && yearMatches;
      });

      const body = visibleRows.map(({ row, rIdx }) => {
        const batchAttr = maintSheetPayload.sheet_key === "schedule_grid"
          && scheduleGridNewShiftBatchId
          && rIdx >= scheduleGridNewShiftStartIndex
          && rIdx < scheduleGridNewShiftStartIndex + scheduleGridNewShiftCount
          ? ` data-schedule-new-shift-batch="${esc(scheduleGridNewShiftBatchId)}"`
          : "";
        // 除咗更表（roster 第 0 行係一月資料，唔係標題），其餘 sheet 第 0 行都係標題列：
        // 跟餐單 hdr-labels 一樣藍底 + 釘喺頂，scroll 嘅只係資料。
        const headerRowClass = rIdx === 0 && maintSheetPayload.sheet_key !== "roster"
          ? ' class="maint-blue-header maint-sticky-header"'
          : "";
        const offClass = rIdx > 0 && isScheduleGridRowDisabled(row) ? " maint-row-off" : "";
        const rowClass = headerRowClass
          ? headerRowClass.replace('"', `"${offClass ? offClass.trim() + " " : ""}`)
          : (offClass ? ` class="${offClass.trim()}"` : "");
        return `<tr data-maint-row-index="${rIdx}"${rowClass}${batchAttr}>${maintRowHtml(row, rIdx, cols, formKey, isShiftCodeCol)}</tr>`;
      }).join("");
      editor.innerHTML = `<div class="maint-sheet-title" style="display:flex;align-items:center;"><span>${esc(title)}</span>${filterHtml}</div>
        <div class="maint-sheet-body"><table class="maint-table" data-form-table>
          <colgroup>${colGroup}</colgroup>
          <tbody>${body}</tbody>
        </table></div>`;
      bindMaintDisableToggles(editor);
      bindMaintContextMenu(editor);
      applyFormColumnWidths(editor);
      attachFormColumnResizers(editor);
      bindMaintRowInputs(editor);

      const filterSelect = editor.querySelector("#maint-table-filter");
      const effectiveSelect = editor.querySelector("#maint-effective-filter");
      const yearSelect = editor.querySelector("#maint-year-filter");
      if ((filterSelect && shiftCodeColIdx !== undefined) || effectiveSelect || yearSelect) {
        const sortScheduleGridForFilterChange = () => {
          if (maintSheetPayload.sheet_key !== "schedule_grid") return false;
          if (currentMaintFilter === SCHEDULE_GRID_NEW_SHIFT_FILTER) return false;
          maintSheetPayload.rows = sortedScheduleGridRows(collectMaintRows());
          renderMaintEditor();
          return true;
        };
        const applyFilter = () => {
          const codeValFilter = filterSelect ? filterSelect.value : "";
          const effectiveValFilter = effectiveSelect ? effectiveSelect.value : "";
          const yearValFilter = yearSelect ? yearSelect.value : "";
          currentMaintFilter = codeValFilter;
          currentMaintEffectiveFilter = effectiveValFilter;
          currentMaintYearFilter = yearValFilter;
          saveMaintFilterState(maintSheetPayload.sheet_key || "");
          editor.querySelectorAll("tr[data-maint-row-index]").forEach(tr => {
            const idx = Number(tr.getAttribute("data-maint-row-index"));
            if (idx === 0) return;
            const codeInput = shiftCodeColIdx !== undefined
              ? tr.querySelector(`[data-maint-row="${idx}"][data-maint-col="${shiftCodeColIdx}"]`)
              : null;
            const codeVal = codeInput ? String(codeInput.value).trim() : "";
            const versionInput = effectiveColIdx !== undefined
              ? tr.querySelector(`[data-maint-row="${idx}"][data-maint-col="${effectiveColIdx}"]`)
              : null;
            const versionVal = versionInput ? (normaliseEffectiveDateInput(versionInput.value) || String(versionInput.value).trim()) : "";
            const versionKey = versionVal || "__blank__";
            const dateInput = dateColIdx !== undefined
              ? tr.querySelector(`[data-maint-row="${idx}"][data-maint-col="${dateColIdx}"]`)
              : null;
            const parsedDate = dateInput ? parseYmd(dateInput.value) : null;
            const rowYear = parsedDate ? String(parsedDate.year) : "";
            const isNewShiftRow = codeValFilter === SCHEDULE_GRID_NEW_SHIFT_FILTER
              && tr.getAttribute("data-schedule-new-shift-batch") === scheduleGridNewShiftBatchId;
            const codeMatches = codeValFilter === SCHEDULE_GRID_NEW_SHIFT_FILTER
              ? isNewShiftRow
              : (!codeValFilter || codeVal === codeValFilter || codeVal === "");
            const versionMatches = !effectiveValFilter || versionKey === effectiveValFilter;
            const yearMatches = !yearValFilter || rowYear === yearValFilter || rowYear === "";
            if (codeMatches && versionMatches && yearMatches) {
              tr.style.display = "";
              setTimeout(() => {
                tr.querySelectorAll("textarea[data-auto-row-height]").forEach(autoResizeTextarea);
              }, 0);
            } else {
              tr.style.display = "none";
            }
          });
        };
        const restorePickerValues = () => {
          if (filterSelect) filterSelect.value = currentMaintFilter;
          if (effectiveSelect) effectiveSelect.value = currentMaintEffectiveFilter;
          if (yearSelect) yearSelect.value = currentMaintYearFilter;
        };
        const pickerFilters = () => ({
          code: filterSelect ? filterSelect.value : "",
          effective: effectiveSelect ? effectiveSelect.value : "",
          year: yearSelect ? yearSelect.value : "",
        });
        const reloadScheduleGridAfterPickerChange = async (nextFilters) => {
          if (maintSheetPayload.sheet_key !== "schedule_grid") return false;
          if (unsavedChanges) {
            restorePickerValues();
            const ok = await resolveUnsavedBeforeLeaving();
            if (!ok) return true;
          }
          const reloaded = await refreshScheduleGridForPicker(nextFilters);
          if (!reloaded) restorePickerValues();
          return true;
        };
        let lastPickerChangeAt = 0;
        let lastPickerOpenAt = 0;
        const scheduleSameValuePickerReload = () => {
          if (maintSheetPayload.sheet_key !== "schedule_grid") return;
          const clickAt = Date.now();
          if (clickAt - lastPickerOpenAt < 250) return;
          window.setTimeout(async () => {
            if (lastPickerChangeAt >= clickAt) return;
            await reloadScheduleGridAfterPickerChange(pickerFilters());
          }, 350);
        };
        [filterSelect, effectiveSelect, yearSelect].filter(Boolean).forEach((select) => {
          select.addEventListener("pointerdown", () => {
            lastPickerOpenAt = Date.now();
          });
          select.addEventListener("click", scheduleSameValuePickerReload);
        });
        if (filterSelect) filterSelect.addEventListener("change", async () => {
          lastPickerChangeAt = Date.now();
          const nextFilter = filterSelect.value;
          if (await reloadScheduleGridAfterPickerChange({
            code: nextFilter,
            effective: effectiveSelect ? effectiveSelect.value : "",
            year: yearSelect ? yearSelect.value : "",
          })) return;
          currentMaintFilter = nextFilter;
          currentMaintEffectiveFilter = effectiveSelect ? effectiveSelect.value : "";
          currentMaintYearFilter = yearSelect ? yearSelect.value : "";
          saveMaintFilterState(maintSheetPayload.sheet_key || "");
          if (!sortScheduleGridForFilterChange()) applyFilter();
        });
        if (effectiveSelect) effectiveSelect.addEventListener("change", async () => {
          lastPickerChangeAt = Date.now();
          if (await reloadScheduleGridAfterPickerChange(pickerFilters())) return;
          currentMaintFilter = filterSelect ? filterSelect.value : "";
          currentMaintEffectiveFilter = effectiveSelect.value;
          currentMaintYearFilter = yearSelect ? yearSelect.value : "";
          saveMaintFilterState(maintSheetPayload.sheet_key || "");
          if (!sortScheduleGridForFilterChange()) applyFilter();
        });
        if (yearSelect) yearSelect.addEventListener("change", async () => {
          lastPickerChangeAt = Date.now();
          if (await reloadScheduleGridAfterPickerChange(pickerFilters())) return;
          currentMaintFilter = filterSelect ? filterSelect.value : "";
          currentMaintEffectiveFilter = effectiveSelect ? effectiveSelect.value : "";
          currentMaintYearFilter = yearSelect.value;
          saveMaintFilterState(maintSheetPayload.sheet_key || "");
          if (!sortScheduleGridForFilterChange()) applyFilter();
        });
        if (maintSheetPayload.sheet_key !== "schedule_grid" && (currentMaintFilter || currentMaintEffectiveFilter || currentMaintYearFilter)) applyFilter();
      }

      applyTableOffsets(editor);
      attachTableDragHandles(editor);
    }

    function bindMaintContextMenu(editor) {
      if (!editor || editor.dataset.maintContextBound === "1") return;
      editor.dataset.maintContextBound = "1";
      editor.addEventListener("contextmenu", (ev) => {
        ev.preventDefault();
        const row = ev.target && ev.target.closest ? ev.target.closest("tr[data-maint-row-index]") : null;
        const idx = row ? Number(row.getAttribute("data-maint-row-index")) : -1;
        showMaintRowMenu(ev, Number.isInteger(idx) ? idx : -1);
      });
    }
    function scheduleGridRowsFromMemory() {
      return Array.isArray(maintSheetPayload.rows)
        ? maintSheetPayload.rows.map((row) => Array.isArray(row) ? [...row] : [])
        : [];
    }

    function writeMaintInputToMemory(input, isInputEvent = false) {
      if (maintSheetPayload.sheet_key !== "schedule_grid" || !input) return false;
      const r = Number(input.getAttribute("data-maint-row"));
      const c = Number(input.getAttribute("data-maint-col"));
      if (!Number.isInteger(r) || !Number.isInteger(c) || r < 0 || c < 0) return false;
      const rows = Array.isArray(maintSheetPayload.rows) ? maintSheetPayload.rows : [];
      while (rows.length <= r) rows.push([]);
      if (!Array.isArray(rows[r])) rows[r] = [];
      rows[r][c] = isMaintDateDisplayCol(c) && !isInputEvent
        ? (normaliseEffectiveDateInput(input.value) || String(input.value || "").trim())
        : formatMaintTimeValue(activeMaintSheetKey, r, c, input.value, isInputEvent);
      maintSheetPayload.rows = rows;
      return true;
    }

    function collectMaintRows() {
      if (maintSheetPayload.sheet_key === "schedule_grid") return scheduleGridRowsFromMemory();
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
        if (isMaintDateDisplayCol(c)) {
          rows[r][c] = normaliseEffectiveDateInput(input.value) || String(input.value || "").trim();
        } else {
          rows[r][c] = formatMaintTimeValue(activeMaintSheetKey, r, c, input.value);
        }
      });
      for (const row of rows) {
        while (row.length && (row[row.length - 1] == null || String(row[row.length - 1]).trim() === "")) row.pop();
      }
      while (rows.length && !rows[rows.length - 1].some((cell) => cell != null && String(cell).trim() !== "")) rows.pop();
      return rows;
    }

    function collectWakeAlarmRowsForRosterSave() {
      syncRosterFieldInputsToSources();
      const existing = Array.isArray(rosterReportSources.wake_alarms) ? rosterReportSources.wake_alarms : [];
      const rows = [["日期", "起身時間", "備註"]];
      (existing || []).slice(1).forEach((row) => {
        if (!Array.isArray(row)) return;
        const d = parseYmd(row[0]);
        const key = d ? dateKey(d.year, d.month, d.day) : "";
        const wake = normalTime(row[1]) || "";
        const note = String(row[2] || "").trim();
        // 淨係有備註、冇改起身時間嘅日子一樣要留低。
        if (key && (wake || note)) rows.push([key, wake, note]);
      });
      rows.splice(1, rows.length - 1, ...rows.slice(1).sort((a, b) => String(a[0]).localeCompare(String(b[0]))));
      return rows;
    }

    function prepareScheduleGridRowsForDisplay(rows) {
      if (!Array.isArray(rows)) return [];
      return recalculateScheduleGridDurations(rows);
    }

    function rowsForMaintSave(rows) {
      if (activeMaintSheetKey !== "schedule_grid") return rows;
      return sortedScheduleGridRows(rows).filter((row, idx) => {
        if (idx === 0) return true;
        if (!Array.isArray(row)) return false;
        const cols = scheduleGridColumnIndexes(rows);
        return cols.content < 0 || String(row[cols.content] || "").trim() !== "";
      });
    }

    function sortedScheduleGridRows(rows) {
      if (!Array.isArray(rows) || !rows.length) return rows;
      const cols = scheduleGridColumnIndexes(rows);
      const header = rows[0];
      const body = rows.slice(1).map((row, idx) => ({ row, idx }));
      const effectiveKey = (row) => {
        if (cols.effective < 0) return "";
        const parsed = parseYmd(row[cols.effective]);
        if (parsed) return dateKey(parsed.year, parsed.month, parsed.day);
        const raw = String(row[cols.effective] || "").trim();
        return raw;
      };
      body.sort((a, b) => {
        const codeA = cols.code >= 0 ? String(a.row[cols.code] || "").trim() : "";
        const codeB = cols.code >= 0 ? String(b.row[cols.code] || "").trim() : "";
        const codeCmp = codeA.localeCompare(codeB);
        if (codeCmp) return codeCmp;
        const effectiveCmp = effectiveKey(a.row).localeCompare(effectiveKey(b.row));
        if (effectiveCmp) return effectiveCmp;
        const timeA = cols.time >= 0 ? timeMinutes(a.row[cols.time]) : null;
        const timeB = cols.time >= 0 ? timeMinutes(b.row[cols.time]) : null;
        const timeCmp = (timeA == null ? Number.MAX_SAFE_INTEGER : timeA) - (timeB == null ? Number.MAX_SAFE_INTEGER : timeB);
        if (timeCmp) return timeCmp;
        return a.idx - b.idx;
      });
      return [header, ...body.map((item) => item.row)];
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

    function sortMtrDoorsRows(rows) {
      if (!Array.isArray(rows) || rows.length < 2 || !Array.isArray(rows[0])) return rows;
      const header = rows[0];
      let codeIdx = header.findIndex((cell) => String(cell || "").trim() === "更碼");
      if (codeIdx < 0) codeIdx = 0;
      const body = rows.slice(1).filter((row) => Array.isArray(row));
      body.sort((a, b) =>
        String(a[codeIdx] ?? "").trim().toLowerCase().localeCompare(String(b[codeIdx] ?? "").trim().toLowerCase())
      );
      return [header, ...body];
    }

    async function openMaintSheet(sheetKey, openTree = true) {
      if (!sheetKey) return;
      if (sheetKey !== activeMaintSheetKey && !(await resolveUnsavedBeforeLeaving())) return;
      setActivePanel("maint");
      setActiveMenuPathForKey(sheetKey);
      if (openTree) openMenuTreeForGroup(menuGroupForKey(sheetKey));
      activeMaintSheetKey = sheetKey;
      try {
        window.localStorage.setItem("mealplanner_active_maint_sheet", sheetKey);
      } catch (_) {}
      showMaintError("");
      setMaintStatus("Loading...");
      try {
        maintSheetPayload = await loadMaintSheet(sheetKey);
        if (!Array.isArray(maintSheetPayload.rows)) maintSheetPayload.rows = [];
        if (sheetKey === "schedule_grid") {
          maintSheetPayload.rows = prepareScheduleGridRowsForDisplay(maintSheetPayload.rows);
        }
        if (sheetKey === "mtr_doors") {
          maintSheetPayload.rows = sortMtrDoorsRows(maintSheetPayload.rows);
        }
        if (sheetKey === "roster") {
          const [payroll, overtime, wakeAlarms, holidays, medical] = await Promise.all([
            loadMaintSheet("payroll_times").catch(() => ({ rows: [] })),
            loadMaintSheet("overtime").catch(() => ({ rows: [] })),
            loadMaintSheet("wake_alarms").catch(() => ({ rows: [["日期", "起身時間", "備註"]] })),
            loadMaintSheet("public_holidays").catch(() => ({ rows: [] })),
            loadMaintSheet("medical_appointments").catch(() => ({ rows: [] })),
          ]);
          rosterReportSources = {
            payroll_times: Array.isArray(payroll.rows) ? payroll.rows : [],
            overtime: Array.isArray(overtime.rows) ? overtime.rows : [],
            wake_alarms: Array.isArray(wakeAlarms.rows) ? wakeAlarms.rows : [["日期", "起身時間", "備註"]],
            public_holidays: Array.isArray(holidays.rows) ? holidays.rows : [],
            medical_appointments: Array.isArray(medical.rows) ? medical.rows : [],
          };
        }
        renderMaintEditor();
        clearUnsavedChanges("餐單參數");
        setMaintStatus("");
      } catch (e) {
        showMaintError(String(e.message || e));
        setMaintStatus("");
      }
      setActivePanel("maint", false);
    }

    async function refreshScheduleGridForPicker(nextFilters = null) {
      if (scheduleGridPickerRefreshBusy) return false;
      if (activePanel !== "maint" || activeMaintSheetKey !== "schedule_grid") return false;
      if (unsavedChanges) {
        setMaintStatus("有未儲存修改，儲存或放棄後再揀更碼會重新載入");
        return false;
      }
      scheduleGridPickerRefreshBusy = true;
      try {
        const codeFilter = nextFilters && Object.prototype.hasOwnProperty.call(nextFilters, "code")
          ? nextFilters.code
          : currentMaintFilter;
        const effectiveFilter = nextFilters && Object.prototype.hasOwnProperty.call(nextFilters, "effective")
          ? nextFilters.effective
          : currentMaintEffectiveFilter;
        const yearFilter = nextFilters && Object.prototype.hasOwnProperty.call(nextFilters, "year")
          ? nextFilters.year
          : currentMaintYearFilter;
        maintSheetPayload = await loadMaintSheet("schedule_grid");
        if (!Array.isArray(maintSheetPayload.rows)) maintSheetPayload.rows = [];
        maintSheetPayload.rows = prepareScheduleGridRowsForDisplay(maintSheetPayload.rows);
        currentMaintFilter = codeFilter;
        currentMaintEffectiveFilter = effectiveFilter;
        currentMaintYearFilter = yearFilter;
        saveMaintFilterState("schedule_grid");
        renderMaintEditor();
        clearUnsavedChanges("餐單參數");
        setMaintStatus("");
        return true;
      } catch (e) {
        showMaintError(String(e.message || e));
        return false;
      } finally {
        scheduleGridPickerRefreshBusy = false;
      }
    }

    function googleCalendarSyncSummary(result) {
      if (!result || typeof result !== "object") return "";
      const part = (key, label) => {
        const item = result[key];
        if (!item || typeof item !== "object") return "";
        const created = Number(item.created || 0);
        const updated = Number(item.updated || 0);
        const deleted = Number(item.deleted || 0);
        const skipped = Number(item.skipped_unmanaged || 0) + Number(item.skipped_ambiguous || 0);
        if (!created && !updated && !deleted && !skipped) return "";
        return `${label} +${created} / ~${updated} / -${deleted}${skipped ? ` / skip ${skipped}` : ""}`;
      };
      return [part("work", "更表"), part("alarm", "起身"), part("leave", "大假")].filter(Boolean).join("; ");
    }

    function payrollCheckStatus(saveResult) {
      const pc = saveResult && saveResult.payroll_check;
      if (!pc || typeof pc !== "object") return "";
      if (pc.status === "error") return `更時表檢查失敗: ${pc.detail || "unknown"}`;
      const issues = Array.isArray(pc.issues) ? pc.issues : [];
      if (!issues.length) return "";
      const parts = issues.map((it) => `${it.code} 冇${it.uncovered_days}`);
      return `更時表有日子 match 唔到: ${parts.join("; ")}`;
    }

    function googleCalendarSyncStatus(saveResult) {
      const gc = saveResult && saveResult.google_calendar_sync;
      if (!gc || typeof gc !== "object") return "";
      if (gc.status === "disabled") return "GC disabled";
      if (gc.status === "not_authenticated") return "GC 未登入，已只儲存本地更表";
      if (gc.status === "dry_run") return "GC dry run";
      if (gc.status === "empty") return "GC no roster events";
      if (gc.status === "error") return `GC error: ${gc.detail || "unknown"}`;
      return googleCalendarSyncSummary(gc) || "GC no changes";
    }

    async function saveMaintEditor() {
      if (!activeMaintSheetKey) return;
      showMaintError("");
      setMaintStatus("Saving...");
      try {
        const rows = rowsForMaintSave(collectMaintRows());
        if (!(await checkRosterCodesBeforeSave(rows))) {
          setMaintStatus("");
          return;
        }
        if (activeMaintSheetKey === "roster") {
          const wakeRows = collectWakeAlarmRowsForRosterSave();
          await persistMaintSheet("wake_alarms", wakeRows);
          rosterReportSources.wake_alarms = wakeRows;
        }
        const result = await persistMaintSheet(activeMaintSheetKey, rows);
        maintSheetPayload.rows = rows;
        if (activeMaintSheetKey === "schedule_grid" && scheduleGridNewShiftBatchId) {
          scheduleGridNewShiftBatchId = "";
          scheduleGridNewShiftStartIndex = -1;
          scheduleGridNewShiftCount = 0;
          currentMaintFilter = "";
          renderMaintEditor();
        } else if (activeMaintSheetKey === "schedule_grid") {
          renderMaintEditor();
        }
        syncMaintSavedBaselines();
        clearUnsavedChanges("餐單參數");
        let gcStatus = "";
        if (activeMaintSheetKey === "roster") {
          gcStatus = googleCalendarSyncStatus(result);
        } else if (activeMaintSheetKey === "payroll_times") {
          gcStatus = payrollCheckStatus(result);
        }
        setMaintStatus(`Save ${menuLabel(activeMaintSheetKey)} ${new Date().toLocaleTimeString("en-GB")}${gcStatus ? `; ${gcStatus}` : ""}`);
        await refreshMaintSheets();
      } catch (e) {
        showMaintError(String(e.message || e));
        setMaintStatus("");
      }
    }

