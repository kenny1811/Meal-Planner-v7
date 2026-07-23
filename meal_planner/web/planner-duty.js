    let dutyReportPlan = null;
    let dutyReportLoading = false;
    let dutyReportDate = "";
    let dutyBlockDragging = false;
    let dutyMapPendingFocus = null;

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
      if (slot.status === "stopped") return "";
      const parts = [];
      if (slot.status === "failed" || slot.status === "missed") {
        parts.push(btn("skip", "Skip"));
        parts.push(btn("send", "Retry", "duty-btn-primary"));
      } else if (slot.status === "skipped") {
        // skipped：Skip 掣變 Skipped（dim，撳一下取消 skip）；Send 照常可用（收工先報）。
        parts.push(btn("unskip", "Skipped", "duty-btn-dim"));
        if (relation === "today") parts.push(btn("send", "Send now", "duty-btn-primary"));
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
        .map((slot, index) => {
          const rowClass = slot.status === "due" ? "duty-row-due" : slot.status === "skipped" || slot.status === "stopped" ? "duty-row-muted" : "";
          const timeMark = slot.time !== slot.original_time ? ` <span class="duty-status-muted" title="原定 ${dutyEsc(slot.original_time)}">*</span>` : "";
          const groupEditable = dutyGroupCellEditable(plan, slot);
          const groupHtml = dutyEsc(slot.group) || '<span class="duty-status-bad">未設定 group</span>';
          const groupCell = groupEditable
            ? `<td class="duty-plain duty-group-cell" tabindex="0" data-duty-group-slot="${dutyEsc(slot.id)}" title="Click / Enter to pick group">${groupHtml}<span class="duty-caret">▾</span></td>`
            : `<td class="duty-plain">${groupHtml}</td>`;
          const timeEditable = groupEditable;
          const timeCell = timeEditable
            ? `<td class="duty-td-time"><input type="text" readonly class="duty-time-input" data-duty-time-slot="${dutyEsc(slot.id)}" value="${dutyEsc(slot.time)}" title="F2 / 雙擊改：09:16 / 0916 / 2416；留空還原原定 ${dutyEsc(slot.original_time)}" />${timeMark}</td>`
            : `<td class="duty-td-time duty-plain">${dutyEsc(slot.time)}${timeMark}</td>`;
          const messageCell = timeEditable
            ? `<td><input type="text" readonly class="duty-msg-input" data-duty-msg-slot="${dutyEsc(slot.id)}" value="${dutyEsc(slot.message)}" title="F2 / 雙擊改；留空還原預設：${dutyEsc(slot.default_message || "")}" /></td>`
            : `<td class="duty-plain">${dutyEsc(slot.message)}</td>`;
          return `<tr class="${rowClass}">
            ${timeCell}
            ${messageCell}
            ${groupCell}
            <td class="duty-plain">${dutyStatusCell(plan, slot)}</td>
            <td class="duty-plain duty-td-actions">${dutySlotButtons(plan, slot)}</td>
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
            `<tr><td><input type="text" readonly class="duty-map-cell duty-map-code" data-duty-map-orig="${dutyEsc(code)}" value="${dutyEsc(code)}" /></td>` +
            `<td><input type="text" readonly class="duty-map-cell duty-map-group" data-duty-map-orig="${dutyEsc(code)}" value="${dutyEsc(group)}" /></td></tr>`
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
            <table class="maint-table duty-table" data-form-table>
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
                <th data-form-col-key="duty_col_actions">Action</th>
              </tr></thead>
              <tbody>${slotRows || '<tr><td colspan="5" class="duty-plain duty-status-muted">當日冇報平安更</td></tr>'}</tbody>
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
            <table class="maint-table duty-map-table" data-form-table>
              <colgroup>
                <col data-form-col-key="duty_map_code" data-form-col-default="90" />
                <col data-form-col-key="duty_map_group" data-form-col-default="300" />
              </colgroup>
              <thead><tr><th data-form-col-key="duty_map_code">更碼</th><th data-form-col-key="duty_map_group">WhatsApp group</th></tr></thead>
              <tbody id="duty-map-body">${mappingRows}</tbody>
            </table>
            <div class="duty-card-actions">
              <button type="button" class="duty-btn" data-duty-action="map-add-row">+ Add row</button>
              <span class="duty-status-muted">改一格即存 · 更碼清空＝刪行</span>
            </div>
            <div class="duty-card-actions">
              <span class="duty-status-muted">Template:</span>
              <input type="text" id="duty-template-input" class="duty-template-input" value="${dutyEsc(plan.message_template)}" title="改完 Enter / 點走即存；必須含 {code}" />
            </div>
          </div>
        </div>`;

      if (typeof applyFormColumnWidths === "function") applyFormColumnWidths(out);
      if (typeof attachFormColumnResizers === "function") attachFormColumnResizers(out);
      applyDutyBlockLayout();
      attachDutyBlockHandles(out);
      dutyRestorePendingFocus();
      dutyRestoreMapFocus();
    }

    function dutyMapCells() {
      const body = document.getElementById("duty-map-body");
      if (!body) return [];
      return Array.from(body.querySelectorAll("tr")).map((tr) => ({
        code: tr.querySelector(".duty-map-code"),
        group: tr.querySelector(".duty-map-group"),
      }));
    }

    function dutyRestoreMapFocus() {
      if (!dutyMapPendingFocus) return;
      const pf = dutyMapPendingFocus;
      dutyMapPendingFocus = null;
      const rows = dutyMapCells();
      const row = rows[Math.max(0, Math.min(rows.length - 1, pf.row))];
      const el = row && row[pf.col];
      if (el) el.focus();
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
      return key === "onoff" ? 600 : 400; // onoff：要放得落兩張 action 卡
    }

    function applyDutyBlockLayout() {
      // duty_report 同 onoffduty 兩個 panel 共用同一套 block 拖放／位置記憶。
      ["duty-layout", "onoff-layout"].forEach((id) => applyDutyBlockLayoutFor(id));
    }

    function applyDutyBlockLayoutFor(containerId) {
      const container = document.getElementById(containerId);
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
            startWindowDrag({
              bodyClass: "is-dnd-dragging",
              onMove: (mv) => {
                formColumnWidths[`duty_block_${key}_x`] = start.x + (mv.clientX - startX);
                formColumnWidths[`duty_block_${key}_y`] = Math.max(0, start.y + (mv.clientY - startY));
                applyDutyBlockLayout();
              },
              onUp: () => {
                dutyBlockDragging = false;
                persistColumnWidths();
              },
            });
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
            startWindowDrag({
              onMove: (mv) => {
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
              },
              onUp: () => {
                dutyBlockDragging = false;
                persistColumnWidths();
              },
            });
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
      const rowIndex = dutyGridRows().findIndex(
        (r) => r.group && r.group.getAttribute("data-duty-group-slot") === slotId
      );
      const applyGroup = (value) => {
        if (rowIndex >= 0) dutyPendingFocus = { row: rowIndex, col: "group" };
        dutyApply({ slot: { id: slotId, group: value } });
      };
      groups.forEach((g) => addItem(g, () => applyGroup(g)));
      addItem("（預設：跟對照表）", () => applyGroup(""), true);
      addItem("自訂…", () => {
        const next = window.prompt("輸入 WhatsApp group 名", slot ? slot.group : "");
        if (next && next.trim()) applyGroup(next.trim());
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

    // 由 mapping 表 DOM 砌返成個 mapping，即打即存。
    let dutyMapSaving = false;
    async function dutySaveMappingFromDom(focusHint) {
      if (dutyMapSaving) return;
      dutyMapSaving = true;
      const mapping = {};
      document.querySelectorAll("#duty-map-body tr").forEach((tr) => {
        const code = ((tr.querySelector(".duty-map-code") || {}).value || "").trim();
        const group = ((tr.querySelector(".duty-map-group") || {}).value || "").trim();
        if (code) mapping[code] = group;
      });
      if (focusHint) dutyMapPendingFocus = focusHint;
      try {
        dutyReportPlan = await postDutyReportConfig({ mapping });
        dutyShowError("");
        renderDutyReport();
      } catch (e) {
        dutyShowError(e.message || String(e));
      } finally {
        dutyMapSaving = false;
      }
    }

    async function dutySaveTemplateFromDom() {
      const input = document.getElementById("duty-template-input");
      if (!input) return;
      const value = input.value;
      if (!value.includes("{code}")) {
        dutyShowError("Template 必須包含 {code}");
        return;
      }
      if (dutyReportPlan && value === dutyReportPlan.message_template) return;
      try {
        dutyReportPlan = await postDutyReportConfig({ message_template: value });
        dutyShowError("");
        renderDutyReport();
      } catch (e) {
        dutyShowError(e.message || String(e));
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
          tr.innerHTML = `<td><input type="text" readonly class="duty-map-cell duty-map-code" data-duty-map-orig="" value="" /></td><td><input type="text" readonly class="duty-map-cell duty-map-group" data-duty-map-orig="" value="" /></td>`;
          body.appendChild(tr);
          const codeInput = tr.querySelector(".duty-map-code");
          if (codeInput) beginCatalogCellEdit(codeInput);
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

    let dutyPendingFocus = null;

    // 報更 sheet 直接用返營養清單（catalog）嘅 cell edit 引擎：
    //   beginCatalogCellEdit / endCatalogCellEdit / catalogCellInputFrom / focusCatalogCell
    // （見 planner-config.js）。呢度淨係保留報更獨有嘅嘢：group picker 格、
    // 即打即存 commit、re-render 之後還原 focus。

    function dutyGridRows() {
      const out = document.getElementById("duty-report-out");
      if (!out) return [];
      return Array.from(out.querySelectorAll("table.duty-table tbody tr")).map((tr) => ({
        time: tr.querySelector("input[data-duty-time-slot]"),
        msg: tr.querySelector("input[data-duty-msg-slot]"),
        group: tr.querySelector("[data-duty-group-slot]"),
      }));
    }

    function dutyFocusCell(rowIndex, col) {
      const rows = dutyGridRows();
      for (let r = Math.max(0, rowIndex); r < rows.length; r += 1) {
        const el = rows[r][col];
        if (el) {
          el.focus();
          return true;
        }
      }
      return false;
    }

    function dutyRestorePendingFocus() {
      if (!dutyPendingFocus) return;
      const pf = dutyPendingFocus;
      dutyPendingFocus = null;
      dutyFocusCell(pf.row, pf.col);
    }

    // 由某格（input 或 group td）按方向鍵移 focus；跨越 group picker 欄。用 catalog 嘅 focusCatalogCell。
    function dutyMoveFocus(el, key) {
      const dr = key === "ArrowUp" ? -1 : (key === "ArrowDown" || key === "Enter") ? 1 : 0;
      const dc = key === "ArrowLeft" ? -1 : key === "ArrowRight" ? 1 : 0;
      const cell = el.closest("td, th");
      const row = el.closest("tr");
      const body = row && row.parentElement;
      if (!cell || !row || !body) return;
      const rows = Array.from(body.rows);
      const pos = rows.indexOf(row);
      const targetRow = rows[pos + dr] || row;
      const targetCell = targetRow.cells[cell.cellIndex + dc];
      if (!targetCell) return;
      const focusable = targetCell.querySelector("input")
        || (targetCell.matches && targetCell.matches("[data-duty-group-slot]") ? targetCell : null);
      if (focusable) focusCatalogCell(focusable);
    }

    // 即打即存一個 cell；moveKey 有值就記低下一格位置，re-render 後還原 focus。
    function dutyCommitCell(el, moveKey) {
      const dr = moveKey === "ArrowUp" ? -1 : moveKey ? 1 : 0;
      if (el.matches("input[data-duty-time-slot]")) {
        const slotId = el.getAttribute("data-duty-time-slot");
        if (moveKey) {
          const rows = dutyGridRows();
          dutyPendingFocus = { row: rows.findIndex((r) => r.time === el) + dr, col: "time" };
        }
        dutyApply({ slot: { id: slotId, time: el.value.trim() } });
      } else if (el.matches("input[data-duty-msg-slot]")) {
        const slotId = el.getAttribute("data-duty-msg-slot");
        if (moveKey) {
          const rows = dutyGridRows();
          dutyPendingFocus = { row: rows.findIndex((r) => r.msg === el) + dr, col: "msg" };
        }
        dutyApply({ slot: { id: slotId, message: el.value.trim() } });
      } else if (el.classList.contains("duty-map-cell")) {
        const cells = dutyMapCells();
        const col = el.classList.contains("duty-map-code") ? "code" : "group";
        dutyMapPendingFocus = { row: cells.findIndex((r) => r.code === el || r.group === el) + dr, col };
        dutySaveMappingFromDom();
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
        // Cell 嘅即存由 keydown(Enter/↑↓) 同 focusout 統一做（dutyCommitCell）；
        // change 淨係處理 Template 輸入框。
        out.addEventListener("change", (ev) => {
          if (ev.target.id === "duty-template-input") dutySaveTemplateFromDom();
        });
        // Sheet 鍵盤：全部用返 catalog 引擎（beginCatalogCellEdit / endCatalogCellEdit /
        // focusCatalogCell）。Group 格係 picker，Enter/F2/打字開 pickup、箭咀導航。
        out.addEventListener("keydown", (ev) => {
          const el = ev.target;
          const isGroup = el.matches && el.matches("[data-duty-group-slot]");
          const isCell = el.matches && el.matches(
            "input[data-duty-time-slot], input[data-duty-msg-slot], .duty-map-cell"
          );
          if (!isGroup && !isCell) return;

          if (isGroup) {
            if (["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(ev.key)) {
              ev.preventDefault();
              dutyMoveFocus(el, ev.key);
            } else if (ev.key === "Enter" || ev.key === "F2" || ev.key === " "
                || (ev.key.length === 1 && !ev.ctrlKey && !ev.altKey && !ev.metaKey)) {
              ev.preventDefault();
              dutyShowGroupPicker(el.getAttribute("data-duty-group-slot"), el);
            }
            return;
          }

          if (el.dataset.catalogEditing === "1") {
            if (["Escape", "Enter", "ArrowUp", "ArrowDown"].includes(ev.key)) {
              ev.preventDefault();
              if (ev.key === "Escape") { endCatalogCellEdit(el, { cancel: true }); return; }
              const moveKey = ev.key === "ArrowUp" ? "ArrowUp" : "ArrowDown"; // Enter＝落下一行
              const changed = el.value !== el.dataset.catalogOriginalValue;
              endCatalogCellEdit(el);
              if (changed) {
                dutyCommitCell(el, moveKey);      // 即存 → re-render → 還原 focus
              } else {
                dutyMoveFocus(el, moveKey);
              }
            }
            return;
          }

          // view mode
          if (["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Enter"].includes(ev.key)) {
            ev.preventDefault();
            dutyMoveFocus(el, ev.key === "Enter" ? "ArrowDown" : ev.key);
            return;
          }
          if (ev.key === "F2") { ev.preventDefault(); beginCatalogCellEdit(el); return; }
          if (ev.key === "Process") { beginCatalogCellEdit(el, true); return; }
          if (ev.key.length === 1 && !ev.ctrlKey && !ev.altKey && !ev.metaKey) {
            beginCatalogCellEdit(el, true); // 打字即入 edit + 取代（唔 preventDefault）
          }
        });
        out.addEventListener("dblclick", (ev) => {
          const input = ev.target.closest("input[data-duty-time-slot], input[data-duty-msg-slot], .duty-map-cell");
          if (input) { ev.preventDefault(); beginCatalogCellEdit(input); }
        });
        out.addEventListener("compositionstart", (ev) => {
          const input = ev.target.closest("input[data-duty-time-slot], input[data-duty-msg-slot], .duty-map-cell");
          if (input && input.readOnly) beginCatalogCellEdit(input, true);
        });
        // 離開個格：endCatalogCellEdit 還原 readonly；若值有改就即存。
        out.addEventListener("focusout", (ev) => {
          const input = ev.target.closest("input[data-duty-time-slot], input[data-duty-msg-slot], .duty-map-cell");
          if (!input || input.dataset.catalogEditing !== "1") return;
          const changed = input.value !== input.dataset.catalogOriginalValue;
          endCatalogCellEdit(input);
          if (changed) dutyCommitCell(input, null);
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
