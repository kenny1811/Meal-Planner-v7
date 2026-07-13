    let dutyReportPlan = null;
    let dutyReportLoading = false;
    let dutyReportDate = "";
    let dutyBlockDragging = false;

    async function dutyShiftDate(deltaDays) {
      const base = dutyReportPlan ? dutyReportPlan.date_iso : "";
      if (!base || dutyReportLoading) return;
      const [y, m, d] = base.split("-").map(Number);
      const dt = new Date(Date.UTC(y, m - 1, d + deltaDays, 12, 0, 0));
      const iso = `${dt.getUTCFullYear()}-${String(dt.getUTCMonth() + 1).padStart(2, "0")}-${String(dt.getUTCDate()).padStart(2, "0")}`;
      const target = iso === dutyReportPlan.today_iso ? "" : iso;
      dutyReportLoading = true;
      try {
        const candidate = await loadDutyReportPlan(target);
        // 未有更碼嘅日子（更表未出）唔入去。
        if (candidate.source === "none") {
          dutyShowError(`${iso} 未有更碼，唔轉過去。`);
          return;
        }
        dutyReportDate = target;
        dutyReportPlan = candidate;
        dutyShowError("");
        renderDutyReport();
      } catch (e) {
        dutyShowError(e && e.message ? e.message : String(e));
      } finally {
        dutyReportLoading = false;
      }
    }

    function dutyEsc(text) {
      return String(text == null ? "" : text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }

    function dutyFmtDateTime(iso) {
      if (!iso) return "";
      const m = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})/);
      if (!m) return String(iso);
      return `${m[3]}/${m[2]} ${m[4]}:${m[5]}:${m[6]}`;
    }

    function dutyFmtTimeOnly(iso) {
      const m = String(iso || "").match(/[T ](\d{2}):(\d{2})/);
      return m ? `${m[1]}:${m[2]}` : "";
    }

    function dutySlotDateTimeMs(plan, slot) {
      const [y, mo, d] = plan.date_iso.split("-").map(Number);
      const [hh, mm] = slot.time.split(":").map(Number);
      const dayOffset = hh < 6 ? 1 : 0;
      return new Date(y, mo - 1, d + dayOffset, hh, mm, 0).getTime();
    }

    function dutyCountdownText(plan, slot) {
      const diffMs = dutySlotDateTimeMs(plan, slot) - Date.now();
      if (diffMs <= 0) return "now";
      const mins = Math.round(diffMs / 60000);
      if (mins < 60) return `in ${mins}m`;
      return `in ${Math.floor(mins / 60)}h ${mins % 60}m`;
    }

    function dutyStatusCell(plan, slot) {
      if (slot.status === "sent") {
        const manual = slot.manual ? " (manual)" : "";
        return `<span class="duty-status-sent">✓ sent ${dutyFmtTimeOnly(slot.sent_at)}${manual}</span>`;
      }
      if (slot.status === "failed") {
        return `<span class="duty-status-bad" title="${dutyEsc(slot.detail)}">✗ failed</span>`;
      }
      if (slot.status === "missed") {
        return `<span class="duty-status-bad">✗ missed</span>`;
      }
      if (slot.status === "skipped") return `<span class="duty-status-muted">skipped</span>`;
      if (slot.status === "stopped") return `<span class="duty-status-muted">stopped (唔報更)</span>`;
      if (slot.status === "no_record") return `<span class="duty-status-muted">—</span>`;
      if (slot.status === "due") {
        return plan.auto_send
          ? `<span class="duty-status-due">⏳ sending…</span>`
          : `<span class="duty-status-due">due (auto-send off)</span>`;
      }
      return `<span class="duty-status-muted">⏱ ${dutyCountdownText(plan, slot)}</span>`;
    }

    function dutySlotButtons(plan, slot) {
      const relation = plan.relation || "today";
      if (relation === "past") return "";
      const btn = (action, label, cls = "") =>
        `<button type="button" class="duty-btn ${cls}" data-duty-action="${action}" data-duty-slot="${dutyEsc(slot.id)}">${label}</button>`;
      if (slot.status === "sent") return relation === "today" ? btn("send", "Resend") : "";
      if (slot.status === "skipped") {
        const parts = [btn("unskip", "Unskip")];
        // skip 咗都可以手動即發（例如延遲收工，收工先報）——唔會取消 skip 狀態。
        if (relation === "today") parts.push(btn("send", "Send now", "duty-btn-primary"));
        return parts.join("");
      }
      if (slot.status === "stopped") return "";
      const parts = [];
      if (slot.status === "failed" || slot.status === "missed") {
        parts.push(btn("send", "Retry", "duty-btn-primary"));
        parts.push(btn("skip", "Skip"));
      } else {
        parts.push(btn("skip", "Skip"));
        if (relation === "today") parts.push(btn("send", "Send now", "duty-btn-primary"));
      }
      return parts.join("");
    }

    function dutySegmentsText(plan) {
      const segments = plan && plan.segments ? plan.segments : [];
      if (!segments.length) return "";
      return segments
        .map((seg) => (seg.from !== "00:00" ? `${seg.code}（由 ${seg.from}）` : seg.code))
        .join(" → ");
    }

    function dutyGroupCellEditable(plan, slot) {
      const relation = plan.relation || "today";
      return relation !== "past" && slot.status !== "sent" && slot.status !== "stopped";
    }

    function renderDutyReport() {
      const out = document.getElementById("duty-report-out");
      if (!out || !dutyReportPlan) return;
      const plan = dutyReportPlan;
      const health = plan.health || { cdp: false, whatsapp: false };
      const chip = (ok, label) =>
        `<span class="duty-chip ${ok ? "duty-chip-ok" : "duty-chip-bad"}">● ${label}</span>`;
      const lastSeg = plan.segments.length ? plan.segments[plan.segments.length - 1] : null;
      const currentGroup = lastSeg ? plan.mapping[lastSeg.code] || "" : "";
      const sourceLabel = plan.source === "override" ? "override" : plan.source === "roster" ? "roster sheet" : "—";
      const relation = plan.relation || "today";
      const relationLabel = relation === "today" ? "今日" : relation === "past" ? "過去" : "未來";
      const dayLabel = relation === "today" ? "今日" : "當日";

      const slotRows = plan.slots
        .map((slot) => {
          const rowClass = slot.status === "due" ? "duty-row-due" : slot.status === "skipped" || slot.status === "stopped" ? "duty-row-muted" : "";
          const timeMark = slot.time !== slot.original_time ? ` <span class="duty-status-muted" title="原定 ${dutyEsc(slot.original_time)}">*</span>` : "";
          const groupEditable = dutyGroupCellEditable(plan, slot);
          const groupHtml = dutyEsc(slot.group) || '<span class="duty-status-bad">未設定 group</span>';
          const groupCell = groupEditable
            ? `<td class="duty-group-cell" data-duty-group-slot="${dutyEsc(slot.id)}" title="Click to pick group">${groupHtml}<span class="duty-caret">▾</span></td>`
            : `<td>${groupHtml}</td>`;
          const timeEditable = groupEditable;
          const timeCell = timeEditable
            ? `<td class="duty-td-time"><input type="text" class="duty-time-input" data-duty-time-slot="${dutyEsc(slot.id)}" value="${dutyEsc(slot.time)}" title="09:16 / 0916 / 2416；留空還原原定 ${dutyEsc(slot.original_time)}" />${timeMark}</td>`
            : `<td class="duty-td-time">${dutyEsc(slot.time)}${timeMark}</td>`;
          return `<tr class="${rowClass}">
            ${timeCell}
            <td>${dutyEsc(slot.message)}</td>
            ${groupCell}
            <td>${dutyStatusCell(plan, slot)}</td>
            <td class="duty-td-actions">${dutySlotButtons(plan, slot)}</td>
          </tr>`;
        })
        .join("");

      const eventRows = (plan.events || [])
        .map(
          (ev) =>
            `<div class="duty-event"><span class="duty-status-muted">${dutyFmtDateTime(ev.at)}</span> ` +
            `${dutyEsc(ev.detail || ev.action)} <span class="duty-status-muted">· ${dutyEsc(ev.source)}</span></div>`
        )
        .join("");

      const mappingRows = Object.entries(plan.mapping)
        .map(
          ([code, group]) =>
            `<tr><td><input type="text" class="duty-map-code" value="${dutyEsc(code)}" /></td>` +
            `<td><input type="text" class="duty-map-group" value="${dutyEsc(group)}" /></td></tr>`
        )
        .join("");

      out.innerHTML = `
        <div class="duty-toolbar">
          <button type="button" class="duty-btn" data-duty-action="date-prev">◀</button>
          <span class="duty-date">${dutyEsc(plan.date_iso)}（${relationLabel}）· 30小時制</span>
          <button type="button" class="duty-btn" data-duty-action="date-next">▶</button>
          ${relation !== "today" ? '<button type="button" class="duty-btn" data-duty-action="date-today">返今日</button>' : ""}
          ${chip(health.cdp, "Chrome CDP")}
          ${chip(health.whatsapp, "WhatsApp")}
          <button type="button" class="duty-btn ${plan.auto_send ? "duty-btn-on" : ""}" data-duty-action="toggle-auto">Auto-send: ${plan.auto_send ? "on" : "off"}</button>
          <button type="button" class="duty-btn" data-duty-action="refresh">Refresh</button>
        </div>
        ${plan.data_error ? `<div class="err">${dutyEsc(plan.data_error)}</div>` : ""}
        <div class="duty-layout" id="duty-layout">
          <div class="duty-block duty-block-card" data-duty-block="stats">
            <div class="duty-block-title" title="Drag to move · double-click to reset">Summary</div>
            <div class="duty-stats">
              <div class="duty-stat-card"><div class="duty-stat-label">Today's code</div>
                <div class="duty-stat-value">${dutyEsc(dutySegmentsText(plan)) || "—"}</div>
                <div class="duty-stat-sub">source: ${dutyEsc(sourceLabel)}${plan.mode === "stop" ? " · 唔報更" : ""}</div></div>
              <div class="duty-stat-card"><div class="duty-stat-label">Target group</div>
                <div class="duty-stat-value duty-stat-group">${dutyEsc(currentGroup) || "—"}</div></div>
              <div class="duty-stat-card"><div class="duty-stat-label">Sent today</div>
                <div class="duty-stat-value">${plan.sent_count} / ${plan.total_count}</div>
                <div class="duty-stat-sub">${plan.next_time ? `next ${dutyEsc(plan.next_time)}` : "no more today"}</div></div>
            </div>
          </div>
          <div class="duty-block" data-duty-block="sheet">
            <div class="duty-block-title" title="Drag to move · double-click to reset">Schedule</div>
            <table class="duty-table" data-form-table>
              <colgroup>
                <col data-form-col-key="duty_col_time" data-form-col-default="56" />
                <col data-form-col-key="duty_col_message" data-form-col-default="206" />
                <col data-form-col-key="duty_col_group" data-form-col-default="172" />
                <col data-form-col-key="duty_col_status" data-form-col-default="128" />
                <col data-form-col-key="duty_col_actions" data-form-col-default="168" />
              </colgroup>
              <thead><tr>
                <th data-form-col-key="duty_col_time">Time</th>
                <th data-form-col-key="duty_col_message">Message</th>
                <th data-form-col-key="duty_col_group">Group</th>
                <th data-form-col-key="duty_col_status">Status</th>
                <th data-form-col-key="duty_col_actions" class="duty-td-actions">Action</th>
              </tr></thead>
              <tbody>${slotRows || '<tr><td colspan="5" class="duty-status-muted">當日冇報平安更</td></tr>'}</tbody>
            </table>
          </div>
          <div class="duty-block duty-block-card" data-duty-block="override">
            <div class="duty-block-title" title="Drag to move · double-click to reset">Override</div>
            <div class="duty-card-sub">${plan.mode === "stop" ? "唔報更（stopped）" : plan.source === "override" ? `Override：${dutyEsc(dutySegmentsText(plan))}` : "None — following roster sheet"}</div>
            ${relation === "past" ? '<div class="duty-status-muted">過去日只供回顧，唔可以改。</div>' : `
            <div class="duty-card-actions">
              <button type="button" class="duty-btn" data-duty-action="change-code">Change code…</button>
              <button type="button" class="duty-btn" data-duty-action="change-code-from">中途轉更碼…</button>
              ${plan.mode === "stop"
                ? `<button type="button" class="duty-btn duty-btn-primary" data-duty-action="resume">${dayLabel}要報更</button>`
                : `<button type="button" class="duty-btn" data-duty-action="stop">${dayLabel}唔報更</button>`}
              ${plan.source === "override" ? '<button type="button" class="duty-btn" data-duty-action="follow-roster">還原跟更表</button>' : ""}
            </div>`}
          </div>
          <div class="duty-block duty-block-card" data-duty-block="log">
            <div class="duty-block-title" title="Drag to move · double-click to reset">Control log</div>
            <div class="duty-events">${eventRows || '<span class="duty-status-muted">（未有記錄）</span>'}</div>
          </div>
          <div class="duty-block" data-duty-block="mapping">
            <div class="duty-block-title" title="Drag to move · double-click to reset">Code → group mapping</div>
            <table class="duty-map-table" data-form-table>
              <colgroup>
                <col data-form-col-key="duty_map_code" data-form-col-default="90" />
                <col data-form-col-key="duty_map_group" data-form-col-default="300" />
              </colgroup>
              <thead><tr><th data-form-col-key="duty_map_code">更碼</th><th data-form-col-key="duty_map_group">WhatsApp group</th></tr></thead>
              <tbody id="duty-map-body">${mappingRows}</tbody>
            </table>
            <div class="duty-card-actions">
              <button type="button" class="duty-btn" data-duty-action="map-add-row">+ Add</button>
              <button type="button" class="duty-btn duty-btn-primary" data-duty-action="map-save">Save mapping</button>
              <span class="duty-status-muted">Template:</span>
              <input type="text" id="duty-template-input" class="duty-template-input" value="${dutyEsc(plan.message_template)}" />
            </div>
          </div>
        </div>`;

      if (typeof applyFormColumnWidths === "function") applyFormColumnWidths(out);
      if (typeof attachFormColumnResizers === "function") attachFormColumnResizers(out);
      applyDutyBlockLayout();
      attachDutyBlockHandles(out);
    }

    function dutyBlockWidthPx(block, key) {
      const table = block.querySelector("table[data-form-table]");
      if (table) {
        // 有表嘅 block：闊度永遠貼實張表（columns 逐條校），忽略兼清走舊 saved 闊度。
        delete formColumnWidths[`duty_block_${key}_w`];
        let total = 0;
        table.querySelectorAll("col[data-form-col-key]").forEach((col) => {
          const colKey = col.getAttribute("data-form-col-key");
          const fallback = Number(col.getAttribute("data-form-col-default")) || 120;
          total += formColumnWidthPx(colKey, fallback);
        });
        return total + 4;
      }
      const saved = Number(formColumnWidths[`duty_block_${key}_w`]);
      if (Number.isFinite(saved) && saved >= 120) return saved;
      return 400;
    }

    function applyDutyBlockLayout() {
      const container = document.getElementById("duty-layout");
      if (!container) return;
      const blocks = Array.from(container.querySelectorAll("[data-duty-block]"));
      let defaultY = 0;
      let maxRight = 0;
      let maxBottom = 0;
      blocks.forEach((block) => {
        const key = block.getAttribute("data-duty-block");
        const savedX = Number(formColumnWidths[`duty_block_${key}_x`]);
        const savedY = Number(formColumnWidths[`duty_block_${key}_y`]);
        const savedH = Number(formColumnWidths[`duty_block_${key}_h`]);
        const x = Number.isFinite(savedX) ? savedX : 0;
        const y = Number.isFinite(savedY) ? Math.max(0, savedY) : defaultY;
        const width = dutyBlockWidthPx(block, key);
        block.style.left = `${x}px`;
        block.style.top = `${y}px`;
        block.style.width = `${width}px`;
        const fixedH = Number.isFinite(savedH) && savedH >= 60;
        block.style.height = fixedH ? `${savedH}px` : "";
        block.classList.toggle("duty-block-scroll", fixedH);
        const height = block.getBoundingClientRect().height;
        maxRight = Math.max(maxRight, x + width);
        maxBottom = Math.max(maxBottom, y + height);
        // 預設疊位只按 DOM 次序累加，唔理有冇被拖走——每個 block 位置互相獨立。
        defaultY += height + 8;
      });
      container.style.width = `${Math.max(320, maxRight)}px`;
      container.style.height = `${Math.max(120, maxBottom)}px`;
    }

    function dutyEnsurePosition(block, key) {
      if (!Number.isFinite(Number(formColumnWidths[`duty_block_${key}_x`]))) {
        formColumnWidths[`duty_block_${key}_x`] = block.offsetLeft;
      }
      if (!Number.isFinite(Number(formColumnWidths[`duty_block_${key}_y`]))) {
        formColumnWidths[`duty_block_${key}_y`] = block.offsetTop;
      }
    }

    function attachDutyBlockHandles(root) {
      root.querySelectorAll(".duty-block[data-duty-block]").forEach((block) => {
        const key = block.getAttribute("data-duty-block");
        if (!key || block.dataset.dutyHandlesBound === "1") return;
        block.dataset.dutyHandlesBound = "1";

        const title = block.querySelector(".duty-block-title");
        if (title) {
          title.addEventListener("mousedown", (ev) => {
            if (ev.button != null && ev.button !== 0) return;
            ev.preventDefault();
            dutyEnsurePosition(block, key);
            const startX = ev.clientX;
            const startY = ev.clientY;
            const start = { x: block.offsetLeft, y: block.offsetTop };
            dutyBlockDragging = true;
            document.body.classList.add("is-dnd-dragging");
            const onMove = (mv) => {
              formColumnWidths[`duty_block_${key}_x`] = start.x + (mv.clientX - startX);
              formColumnWidths[`duty_block_${key}_y`] = Math.max(0, start.y + (mv.clientY - startY));
              applyDutyBlockLayout();
            };
            const onUp = () => {
              window.removeEventListener("mousemove", onMove);
              window.removeEventListener("mouseup", onUp);
              document.body.classList.remove("is-dnd-dragging");
              dutyBlockDragging = false;
              persistColumnWidths();
            };
            window.addEventListener("mousemove", onMove);
            window.addEventListener("mouseup", onUp);
          });
          title.addEventListener("dblclick", () => {
            ["x", "y", "w", "h"].forEach((axis) => delete formColumnWidths[`duty_block_${key}_${axis}`]);
            applyDutyBlockLayout();
            persistColumnWidths();
          });
        }

        // resize handles：有表嘅 block 闊度跟表，只俾上下改高度；冇表先有四邊。
        const edges = block.querySelector("table[data-form-table]") ? ["n", "s"] : ["n", "s", "e", "w"];
        edges.forEach((edge) => {
          const grip = document.createElement("span");
          grip.className = `duty-rs duty-rs-${edge}`;
          grip.title = "Drag to resize";
          grip.addEventListener("mousedown", (ev) => {
            ev.preventDefault();
            ev.stopPropagation();
            dutyEnsurePosition(block, key);
            const startX = ev.clientX;
            const startY = ev.clientY;
            const rect = block.getBoundingClientRect();
            const start = {
              x: block.offsetLeft,
              y: block.offsetTop,
              w: rect.width,
              h: rect.height,
            };
            dutyBlockDragging = true;
            const onMove = (mv) => {
              const dx = mv.clientX - startX;
              const dy = mv.clientY - startY;
              if (edge === "e") {
                formColumnWidths[`duty_block_${key}_w`] = Math.max(120, start.w + dx);
              } else if (edge === "w") {
                const width = Math.max(120, start.w - dx);
                formColumnWidths[`duty_block_${key}_w`] = width;
                formColumnWidths[`duty_block_${key}_x`] = start.x + (start.w - width);
              } else if (edge === "s") {
                formColumnWidths[`duty_block_${key}_h`] = Math.max(60, start.h + dy);
              } else if (edge === "n") {
                const height = Math.max(60, start.h - dy);
                formColumnWidths[`duty_block_${key}_h`] = height;
                formColumnWidths[`duty_block_${key}_y`] = Math.max(0, start.y + (start.h - height));
              }
              applyDutyBlockLayout();
            };
            const onUp = () => {
              window.removeEventListener("mousemove", onMove);
              window.removeEventListener("mouseup", onUp);
              dutyBlockDragging = false;
              persistColumnWidths();
            };
            window.addEventListener("mousemove", onMove);
            window.addEventListener("mouseup", onUp);
          });
          block.appendChild(grip);
        });
      });
    }

    function dutyShowError(message) {
      const err = document.getElementById("duty-report-err");
      if (err) err.textContent = message || "";
    }

    async function refreshDutyReport(showBusy = true) {
      if (dutyReportLoading) return;
      dutyReportLoading = true;
      if (showBusy) dutyShowError("");
      try {
        dutyReportPlan = await loadDutyReportPlan(dutyReportDate);
        dutyShowError("");
        renderDutyReport();
      } catch (e) {
        dutyShowError(e && e.message ? e.message : String(e));
      } finally {
        dutyReportLoading = false;
      }
    }

    async function openDutyReportPanel() {
      setActiveMenuPathForKey("duty_report");
      setActivePanel("duty_report");
      await refreshDutyReport();
    }

    function dutyCloseGroupPicker() {
      const menu = document.getElementById("duty-group-picker");
      if (menu) menu.remove();
    }

    function dutyShowGroupPicker(slotId, anchor) {
      dutyCloseGroupPicker();
      if (!dutyReportPlan) return;
      const slot = (dutyReportPlan.slots || []).find((s) => s.id === slotId);
      const groups = [];
      Object.values(dutyReportPlan.mapping || {}).forEach((g) => {
        if (g && !groups.includes(g)) groups.push(g);
      });
      if (slot && slot.group && !groups.includes(slot.group)) groups.push(slot.group);
      const menu = document.createElement("div");
      menu.id = "duty-group-picker";
      menu.className = "duty-pop-menu";
      const addItem = (label, handler, muted) => {
        const item = document.createElement("button");
        item.type = "button";
        item.textContent = label;
        if (muted) item.classList.add("duty-pop-muted");
        item.addEventListener("click", () => {
          dutyCloseGroupPicker();
          handler();
        });
        menu.appendChild(item);
      };
      groups.forEach((g) => addItem(g, () => dutyApply({ slot: { id: slotId, group: g } })));
      addItem("（預設：跟對照表）", () => dutyApply({ slot: { id: slotId, group: "" } }), true);
      addItem("自訂…", () => {
        const next = window.prompt("輸入 WhatsApp group 名", slot ? slot.group : "");
        if (next && next.trim()) dutyApply({ slot: { id: slotId, group: next.trim() } });
      }, true);
      document.body.appendChild(menu);
      const rect = anchor.getBoundingClientRect();
      menu.style.left = `${Math.max(6, Math.min(window.innerWidth - 300, rect.left))}px`;
      menu.style.top = `${rect.bottom + 4}px`;
      setTimeout(() => {
        const onDocClick = (ev) => {
          if (!menu.contains(ev.target)) {
            dutyCloseGroupPicker();
            document.removeEventListener("click", onDocClick);
          }
        };
        document.addEventListener("click", onDocClick);
      }, 0);
    }

    async function dutyApply(payload) {
      try {
        if (dutyReportDate) payload.date_iso = dutyReportDate;
        dutyReportPlan = await postDutyReportOverride(payload);
        dutyShowError("");
        renderDutyReport();
      } catch (e) {
        dutyShowError(e && e.message ? e.message : String(e));
      }
    }

    async function dutyHandleAction(action, slotId, target) {
      if (action === "refresh") return refreshDutyReport();
      if (action === "date-prev") return dutyShiftDate(-1);
      if (action === "date-next") return dutyShiftDate(1);
      if (action === "date-today") {
        dutyReportDate = "";
        return refreshDutyReport();
      }
      if (action === "toggle-auto") {
        try {
          dutyReportPlan = await postDutyReportConfig({ auto_send: !(dutyReportPlan && dutyReportPlan.auto_send) });
          dutyShowError("");
          renderDutyReport();
        } catch (e) {
          dutyShowError(e.message || String(e));
        }
        return;
      }
      if (action === "stop") return dutyApply({ mode: "stop" });
      if (action === "resume") return dutyApply({ mode: "auto" });
      if (action === "follow-roster") return dutyApply({ segments: [] });
      if (action === "change-code") {
        const code = window.prompt("改用邊個更碼？（成日重排）");
        if (!code || !code.trim()) return;
        return dutyApply({ mode: "auto", segments: [{ from: "00:00", code: code.trim() }] });
      }
      if (action === "change-code-from") {
        const code = window.prompt("由某時間起轉用邊個更碼？");
        if (!code || !code.trim()) return;
        const from = window.prompt("由幾點起？（09:16 / 0916）", "");
        if (!from || !/^(\d{1,2}:\d{2}|\d{3,4})$/.test(from.trim())) return dutyShowError("時間格式要 HH:MM 或 HHMM");
        let fromText = from.trim();
        if (/^\d{3,4}$/.test(fromText)) fromText = `${fromText.slice(0, -2).padStart(2, "0")}:${fromText.slice(-2)}`;
        const base = (dutyReportPlan && dutyReportPlan.segments ? dutyReportPlan.segments : []).filter(
          (seg) => seg.from < fromText
        );
        base.push({ from: fromText, code: code.trim() });
        return dutyApply({ mode: "auto", segments: base });
      }
      if (action === "map-add-row") {
        const body = document.getElementById("duty-map-body");
        if (body) {
          const tr = document.createElement("tr");
          tr.innerHTML = '<td><input type="text" class="duty-map-code" value="" /></td><td><input type="text" class="duty-map-group" value="" /></td>';
          body.appendChild(tr);
        }
        return;
      }
      if (action === "map-save") {
        const mapping = {};
        document.querySelectorAll("#duty-map-body tr").forEach((tr) => {
          const code = (tr.querySelector(".duty-map-code") || {}).value || "";
          const group = (tr.querySelector(".duty-map-group") || {}).value || "";
          if (code.trim()) mapping[code.trim()] = group.trim();
        });
        const templateInput = document.getElementById("duty-template-input");
        const payload = { mapping };
        if (templateInput && templateInput.value.includes("{code}")) payload.message_template = templateInput.value;
        try {
          dutyReportPlan = await postDutyReportConfig(payload);
          dutyShowError("");
          renderDutyReport();
        } catch (e) {
          dutyShowError(e.message || String(e));
        }
        return;
      }
      if (!slotId) return;
      if (action === "skip") return dutyApply({ slot: { id: slotId, skip: true } });
      if (action === "unskip") return dutyApply({ slot: { id: slotId, skip: false } });
      if (action === "send") {
        if (target) target.disabled = true;
        try {
          dutyReportPlan = await postDutyReportSend(slotId, dutyReportDate);
          dutyShowError("");
          renderDutyReport();
        } catch (e) {
          dutyShowError(e.message || String(e));
          if (target) target.disabled = false;
        }
      }
    }

    document.addEventListener("DOMContentLoaded", () => {
      const out = document.getElementById("duty-report-out");
      if (out) {
        out.addEventListener("click", (ev) => {
          const groupCell = ev.target.closest("[data-duty-group-slot]");
          if (groupCell) {
            ev.stopPropagation();
            dutyShowGroupPicker(groupCell.getAttribute("data-duty-group-slot"), groupCell);
            return;
          }
          const button = ev.target.closest("[data-duty-action]");
          if (!button) return;
          dutyHandleAction(button.dataset.dutyAction, button.dataset.dutySlot || "", button);
        });
        out.addEventListener("change", (ev) => {
          const input = ev.target.closest("input[data-duty-time-slot]");
          if (!input) return;
          const slotId = input.getAttribute("data-duty-time-slot");
          const slot = dutyReportPlan && (dutyReportPlan.slots || []).find((s) => s.id === slotId);
          const value = input.value.trim();
          if (slot && value === slot.time) return;
          dutyApply({ slot: { id: slotId, time: value } });
        });
        out.addEventListener("keydown", (ev) => {
          if (ev.key === "Enter" && ev.target.closest("input[data-duty-time-slot]")) {
            ev.preventDefault();
            ev.target.blur();
          }
        });
        // 時間格：第一下 click 即全選（mousedown 截住，防止 mouseup 收起全選），
        // 已 focus 之後再 click 先係正常擺游標。
        out.addEventListener("mousedown", (ev) => {
          const input = ev.target.closest("input[data-duty-time-slot]");
          if (input && document.activeElement !== input) {
            ev.preventDefault();
            input.focus();
            input.select();
          }
        });
        // 鍵盤 Tab 入嚟都全選。
        out.addEventListener("focusin", (ev) => {
          const input = ev.target.closest("input[data-duty-time-slot]");
          if (input) setTimeout(() => {
            if (document.activeElement === input && input.selectionStart === input.selectionEnd) input.select();
          }, 0);
        });
      }
      setInterval(() => {
        if (activePanel !== "duty_report" || dutyReportDate || dutyBlockDragging) return;
        if (document.getElementById("duty-group-picker")) return;
        const focused = document.activeElement;
        if (focused && out && out.contains(focused) && focused.tagName === "INPUT") return;
        refreshDutyReport(false);
      }, 10000);
    });
