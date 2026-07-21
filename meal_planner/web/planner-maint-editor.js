    let rosterGcConsistencyTimer = null;
    let rosterGcConsistencySeq = 0;

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
      scheduleRosterGcConsistencyCheck();
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
    }

    function rosterCodeIssuesText(issues) {
      const parts = issues.map((issue) => {
        const code = String((issue && issue.roster_code) || "").trim() || "(空白)";
        const dates = Array.isArray(issue && issue.dates) ? issue.dates : [];
        const shown = dates.slice(0, 4).join("、");
        const more = dates.length > 4 ? ` 等 ${dates.length} 日` : "";
        const why = issue && issue.reason === "unknown_code"
          ? "行位表冇呢個更碼"
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
      return Array.from(document.querySelectorAll("#maint-roster-report input[data-roster-wake-date]"))
        .filter((input) => input.dataset.rosterWakeEditable === "1" && !input.disabled);
    }

    function focusRosterWakeInput(index) {
      const inputs = rosterWakeInputs();
      if (!inputs.length) return false;
      const idx = Math.max(0, Math.min(index, inputs.length - 1));
      const input = inputs[idx];
      if (typeof focusRosterWakeInputElement === "function") return focusRosterWakeInputElement(input);
      input.focus({ preventScroll: true });
      input.select();
      return true;
    }

    function focusFirstRosterWakeInput() {
      return focusRosterWakeInput(0);
    }
    const rosterDirectKeyTimers = new WeakMap();

    function queueRosterDirectKey(input, key) {
      if (!input || !key) return;
      const oldTimer = rosterDirectKeyTimers.get(input);
      if (oldTimer) clearTimeout(oldTimer);
      input.dataset.maintPendingDirectKey = key;
      const timer = setTimeout(() => {
        rosterDirectKeyTimers.delete(input);
        if (input.dataset.maintEditing !== "1" || input.dataset.maintPendingDirectKey !== key) return;
        input.value = `${key}${input.value || ""}`;
        delete input.dataset.maintPendingDirectKey;
        delete input.dataset.maintReplaceOnComposition;
        const pos = String(input.value || "").length;
        input.setSelectionRange(pos, pos);
        input.dispatchEvent(new Event("input", { bubbles: true }));
      }, 40);
      rosterDirectKeyTimers.set(input, timer);
    }

    function rosterTextareaCaretTop(input, position) {
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

    function rosterTextareaShouldKeepArrow(input, key) {
      if (!input || !input.tagName || input.tagName.toLowerCase() !== "textarea") return false;
      if (input.selectionStart !== input.selectionEnd) return true;
      const pos = Number.isInteger(input.selectionStart) ? input.selectionStart : 0;
      const firstTop = rosterTextareaCaretTop(input, 0);
      const caretTop = rosterTextareaCaretTop(input, pos);
      const lastTop = rosterTextareaCaretTop(input, String(input.value || "").length);
      const style = window.getComputedStyle(input);
      const fontSize = parseFloat(style.fontSize) || 16;
      const lineHeight = parseFloat(style.lineHeight) || fontSize * 1.2;
      const tolerance = Math.max(2, lineHeight * 0.25);
      if (key === "ArrowUp") return caretTop > firstTop + tolerance;
      if (key === "ArrowDown") return caretTop < lastTop - tolerance;
      return false;
    }

    function handleRosterCellKeydown(ev) {
      const input = ev.currentTarget;
      const rowIdx = Number(input.getAttribute("data-maint-roster-row"));
      const isLastRosterCell = rowIdx === lastRosterCellIndex();
      if (input.dataset.maintEditing === "1") {
        if (ev.key === "ArrowUp" || ev.key === "ArrowDown") {
          if (rosterTextareaShouldKeepArrow(input, ev.key)) return;
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

    function activeRosterTextForConsistency() {
      const input = document.querySelector(`#maint-editor textarea[data-maint-roster-row="${activeRosterMonthIndex}"]`);
      if (input) return String(input.value || "");
      const rows = Array.isArray(maintSheetPayload.rows) ? maintSheetPayload.rows : [];
      const row = rows[activeRosterMonthIndex];
      return String((Array.isArray(row) ? row[0] : row) || "");
    }

    function setRosterGcConsistencyWarnings(warnings) {
      const box = document.getElementById("roster-gc-consistency-warning");
      if (!box) return;
      const items = Array.isArray(warnings) ? warnings.filter(Boolean) : [];
      box.textContent = items.join("；");
      box.hidden = !items.length;
    }

    function scheduleRosterGcConsistencyCheck(delay = 600) {
      if (activeMaintSheetKey !== "roster") return;
      if (rosterGcConsistencyTimer) clearTimeout(rosterGcConsistencyTimer);
      rosterGcConsistencyTimer = window.setTimeout(refreshRosterGcConsistencyCheck, delay);
    }

    async function refreshRosterGcConsistencyCheck() {
      rosterGcConsistencyTimer = null;
      const seq = ++rosterGcConsistencySeq;
      const text = activeRosterTextForConsistency();
      if (!text.trim() || typeof checkGoogleCalendarNonworkConsistency !== "function") {
        setRosterGcConsistencyWarnings([]);
        return;
      }
      try {
        const result = await checkGoogleCalendarNonworkConsistency(text);
        if (seq !== rosterGcConsistencySeq) return;
        if (result && result.complete && Array.isArray(result.warnings)) {
          setRosterGcConsistencyWarnings(result.warnings);
        } else {
          setRosterGcConsistencyWarnings([]);
        }
      } catch (err) {
        if (seq !== rosterGcConsistencySeq) return;
        setRosterGcConsistencyWarnings([String(err && err.message ? err.message : err)]);
      }
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
          <div class="roster-gc-consistency-warning" id="roster-gc-consistency-warning" hidden></div>
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
          scheduleRosterGcConsistencyCheck();
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
      attachRosterWakeInputs(editor);
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
      scheduleRosterGcConsistencyCheck(50);
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
        return isInputEvent ? value : s;
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
      const colGroup = Array.from(
        { length: cols },
        (_, i) => `<col data-form-col-key="${formKey}_col_${i}" data-form-col-default="160" />`
      ).join("");
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
        filterHtml = `<select id="maint-table-filter" class="maint-filter-select" style="margin-left: 16px; padding: 4px 8px; font-size: 0.9em; border-radius: 4px; border: 1px solid var(--border); background: var(--bg); color: inherit; cursor: pointer;">
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
        filterHtml += `<select id="maint-effective-filter" class="maint-filter-select" style="margin-left: 8px; padding: 4px 8px; font-size: 0.9em; border-radius: 4px; border: 1px solid var(--border); background: var(--bg); color: inherit; cursor: pointer;">
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
        filterHtml += `<select id="maint-year-filter" class="maint-filter-select" style="margin-left: 8px; padding: 4px 8px; font-size: 0.9em; border-radius: 4px; border: 1px solid var(--border); background: var(--bg); color: inherit; cursor: pointer;">
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
        const headerRowClass = maintSheetPayload.sheet_key === "mtr_doors" && rIdx === 0
          ? ' class="maint-blue-header"'
          : "";
        return `<tr data-maint-row-index="${rIdx}"${headerRowClass}${batchAttr}>${maintRowHtml(row, rIdx, cols, formKey, isShiftCodeCol)}</tr>`;
      }).join("");
      editor.innerHTML = `<div class="maint-sheet-title" style="display:flex;align-items:center;"><span>${esc(title)}</span>${filterHtml}</div>
        <table class="maint-table" data-form-table>
          <colgroup>${colGroup}</colgroup>
          <tbody>${body}</tbody>
        </table>`;
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
      document.querySelectorAll("#maint-roster-report input[data-roster-wake-date]").forEach((input) => {
        syncRosterWakeInputToSources(input);
      });
      const existing = Array.isArray(rosterReportSources.wake_alarms) ? rosterReportSources.wake_alarms : [];
      const rows = [["日期", "起身時間", "備註"]];
      (existing || []).slice(1).forEach((row) => {
        if (!Array.isArray(row)) return;
        const d = parseYmd(row[0]);
        const key = d ? dateKey(d.year, d.month, d.day) : "";
        const wake = normalTime(row[1]);
        if (key && wake) rows.push([key, wake, String(row[2] || "").trim()]);
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

    async function importActiveMaintSheet() {
      if (!activeMaintSheetKey) return;
      showMaintError("");
      setMaintStatus("Importing...");
      try {
        if (activeMaintSheetKey === "schedule_grid") {
          const preview = await importScheduleGridFromAdbPhone();
          const result = await confirmScheduleGridFromPhoneIp();
          maintSheetPayload = await loadMaintSheet(activeMaintSheetKey);
          const importedRows = Number.isFinite(Number(result.imported_row_count)) ? Number(result.imported_row_count) : null;
          const replacedRows = Number.isFinite(Number(result.replaced_row_count)) ? Number(result.replaced_row_count) : null;
          const phoneUrl = String((preview && preview.phone_url) || result.phone_url || "").trim();
          if (!Array.isArray(maintSheetPayload.rows)) maintSheetPayload.rows = [];
          renderMaintEditor();
          clearUnsavedChanges("餐單參數");
          setMaintStatus(
            importedRows === null || replacedRows === null
              ? `已匯入電話行位表${phoneUrl ? `；來源 ${phoneUrl}` : ""}`
              : `已匯入電話行位表：${importedRows} 行；取代 ${replacedRows} 行${phoneUrl ? `；來源 ${phoneUrl}` : ""}`
          );
          await refreshMaintSheets();
          return;
        }
        maintSheetPayload = await importMaintSheet(activeMaintSheetKey);
        if (!Array.isArray(maintSheetPayload.rows)) maintSheetPayload.rows = [];
        renderMaintEditor();
        clearUnsavedChanges("餐單參數");
        setMaintStatus(`已匯入 ${menuLabel(activeMaintSheetKey)}：${maintSheetPayload.rows.length} 行`);
        await refreshMaintSheets();
      } catch (e) {
        showMaintError(String(e.message || e));
        setMaintStatus("");
      }
    }
