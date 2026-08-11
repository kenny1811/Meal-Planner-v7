    // OnOffDuty panel: 每日 On Duty / Off Duty Google Form 打卡預填連結。
    // 時間來源 = 更時表（睇適用日）+ 加班表 override，同 Report Normal（報平安更）分開。
    // 兩張卡都有 Hold / Resume / Send now：未定幾點開工（打風）或未走得（遲收工）就 hold，
    // 真發生嗰陣撳 Send now —— form + WhatsApp 齊發。
    // 冇半自動模式：夠鐘一定自動交，Open form 淨係方便自己開嚟睇（只留 history 記錄）。
    let onoffPlan = null;
    let onoffLoading = false;
    let onoffDate = "";

    function onoffEsc(text) {
      return String(text == null ? "" : text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }

    function onoffShowError(message) {
      const err = document.getElementById("onoffduty-err");
      if (err) err.textContent = message || "";
    }

    async function refreshOnOffDuty(showBusy = true) {
      if (onoffLoading) return;
      onoffLoading = true;
      if (showBusy) onoffShowError("");
      try {
        onoffPlan = await loadOnOffDutyPlan(onoffDate);
        onoffShowError("");
        renderOnOffDuty();
      } catch (e) {
        onoffShowError(e && e.message ? e.message : String(e));
      } finally {
        onoffLoading = false;
      }
    }

    async function openOnOffDutyPanel() {
      if (typeof setActiveMenuPathForKey === "function") setActiveMenuPathForKey("onoffduty");
      setActivePanel("onoffduty");
      await refreshOnOffDuty();
    }

    async function onoffShiftDate(deltaDays) {
      const base = onoffPlan ? onoffPlan.date_iso : "";
      if (!base || onoffLoading) return;
      const [y, m, d] = base.split("-").map(Number);
      const dt = new Date(Date.UTC(y, m - 1, d + deltaDays, 12, 0, 0));
      const iso = `${dt.getUTCFullYear()}-${String(dt.getUTCMonth() + 1).padStart(2, "0")}-${String(dt.getUTCDate()).padStart(2, "0")}`;
      onoffDate = iso === onoffPlan.today_iso ? "" : iso;
      await refreshOnOffDuty();
    }

    function onoffFmtLoggedAt(iso) {
      const m = String(iso || "").match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
      return m ? `${m[3]}/${m[2]} ${m[4]}:${m[5]}` : "";
    }

    function onoffStatusLine(action) {
      if (action.status === "sent") {
        return `<div class="duty-status-sent">✓ sent ${onoffFmtLoggedAt(action.logged_at)} · ${onoffEsc(action.log_source)}</div>`;
      }
      if (action.status === "failed") {
        return `<div class="duty-status-bad" title="${onoffEsc(action.detail || "")}">✗ failed ${onoffFmtLoggedAt(action.logged_at)} · retrying</div>`;
      }
      if (action.status === "missed") {
        return `<div class="duty-status-bad" title="${onoffEsc(action.detail || "")}">✗ missed — open the form yourself</div>`;
      }
      if (action.status === "hold") {
        const what = action.kind === "start" ? "start" : "finish";
        return `<div class="duty-status-due">⏸ holding — press Send now when you really ${what}</div>`;
      }
      return `<div class="duty-status-muted">not reported yet</div>`;
    }

    // 完整經過（append-only）：交過就永遠留低，改時間唔會抹走。
    const ONOFF_HISTORY_ICON = {
      sent: "✓", opened: "↗", failed: "✗", missed: "✗",
      hold: "⏸", resumed: "▶", rearmed: "↻", cleared: "·",
    };

    function onoffHistoryLines(action) {
      const rows = Array.isArray(action.history) ? action.history : [];
      if (!rows.length) return "";  // 開過 form（唔入狀態）都要見到，所以一行都show
      // 一行 = 幾時 + 符號 + 當時嗰個時間。狀態字、source、detail 都係符號已經講咗嘅嘢。
      const items = rows.map((h) => {
        const icon = ONOFF_HISTORY_ICON[h.status] || "·";
        return `<li>${onoffEsc(onoffFmtLoggedAt(h.recorded_at))} ${icon} ${onoffEsc(h.time_text || "")}</li>`;
      });
      return `<details class="onoff-history"><summary>經過（${rows.length}）</summary><ul>${items.join("")}</ul></details>`;
    }

    function onoffActionCard(action) {
      const hasUrl = !!action.url;
      const overridden = onoffPlan && (action.kind === "start" ? onoffPlan.start_override : onoffPlan.end_override);
      const timeText = (action.time || "—") + (overridden ? " *" : "");
      const openBtn = hasUrl
        ? `<a class="duty-btn duty-btn-primary onoff-open" href="${onoffEsc(action.url)}" target="_blank" rel="noopener" data-onoff-kind="${onoffEsc(action.kind)}">Open form ↗</a>`
        : "";
      const copyBtn = hasUrl
        ? `<button type="button" class="duty-btn onoff-copy" data-onoff-copy="${onoffEsc(action.url)}">Copy link</button>`
        : "";
      // 今日兩張卡都有：Hold（form + 報平安更 slot 一齊 hold）＋ Send now（form + WhatsApp 齊發）。
      let lateBtns = "";
      if (onoffPlan && (onoffPlan.relation || "today") === "today" && action.status !== "sent") {
        const kind = onoffEsc(action.kind);
        const holding = action.status === "hold";
        const holdTitle = action.kind === "start"
          ? "Hold both sides: the WhatsApp 報開工 slot and the On Duty form stop auto-firing"
          : "Hold both sides: the WhatsApp 報收工 slot and the Off Duty form stop auto-firing";
        const sendTitle = action.kind === "start"
          ? "Fire now at the current time: submit the form + send WhatsApp; the real start time is written to 加班表 when it differs from the planned one"
          : "Fire now at the current time: submit the form + send WhatsApp; 加班表 is written only outside the payroll window and over 10.25 h total";
        lateBtns = `${holding
            ? `<button type="button" class="duty-btn" data-onoff-action="duty-release" data-onoff-for="${kind}">Resume</button>`
            : `<button type="button" class="duty-btn" data-onoff-action="duty-hold" data-onoff-for="${kind}" title="${onoffEsc(holdTitle)}">Hold</button>`}
           <button type="button" class="duty-btn${holding ? " duty-btn-primary" : ""}" data-onoff-action="duty-send" data-onoff-for="${kind}" title="${onoffEsc(sendTitle)}">Send now</button>`;
      }
      return `<div class="duty-stat-card onoff-card">
        <div class="duty-stat-label">${onoffEsc(action.label)}</div>
        <div class="duty-stat-value" ${overridden ? 'title="加班表 override"' : ""}>${onoffEsc(timeText)}</div>
        ${onoffStatusLine(action)}
        ${onoffHistoryLines(action)}
        <div class="duty-card-actions">${openBtn}${copyBtn}</div>
        ${lateBtns ? `<div class="duty-card-actions">${lateBtns}</div>` : ""}
      </div>`;
    }

    function renderOnOffDuty() {
      const out = document.getElementById("onoffduty-out");
      if (!out || !onoffPlan) return;
      const plan = onoffPlan;
      const relation = plan.relation || "today";
      const relationLabel = relation === "today" ? "今日" : relation === "past" ? "過去" : "未來";
      const formLabel = plan.form === "vca" ? "VCA form" : plan.form === "other" ? "其他 form" : "—";

      const cards = (plan.actions || []).map(onoffActionCard).join("");
      const body = plan.actions && plan.actions.length
        ? `<div class="duty-stats onoff-stats">${cards}</div>`
        : `<div class="duty-status-muted onoff-note">${onoffEsc(plan.note || "當日冇嘢報")}</div>`;

      const metaParts = [
        `Code ${onoffEsc(plan.roster_code) || "—"}`,
        onoffEsc(formLabel),
        onoffEsc(plan.post || ""),
        plan.staff_number ? `Staff ${onoffEsc(plan.staff_number)}` : "",
      ].filter(Boolean);
      // 所有嘢一個 block：title 拖得郁（同 ReportNormal blocks 共用位置記憶）。
      out.innerHTML = `
        <div class="duty-layout" id="onoff-layout">
          <div class="duty-block duty-block-card" data-duty-block="onoff">
            <div class="duty-block-title" title="Drag to move · double-click to reset">OnOffDuty</div>
            <div class="duty-toolbar onoff-toolbar">
              <button type="button" class="duty-btn" data-onoff-action="date-prev">◀</button>
              <span class="duty-date">${onoffEsc(plan.date_iso)}（${relationLabel}）· 30小時制</span>
              <button type="button" class="duty-btn" data-onoff-action="date-next">▶</button>
              ${relation !== "today" ? '<button type="button" class="duty-btn" data-onoff-action="date-today">返今日</button>' : ""}
              <button type="button" class="duty-btn" data-onoff-action="refresh">Refresh</button>
            </div>
            <div class="onoff-meta">${metaParts.join(" · ")}</div>
            ${body}
          </div>
        </div>`;
      applyDutyBlockLayout();
      attachDutyBlockHandles(out);
    }

    document.addEventListener("DOMContentLoaded", () => {
      const out = document.getElementById("onoffduty-out");
      if (!out) return;
      out.addEventListener("click", (ev) => {
        const open = ev.target.closest("a.onoff-open[data-onoff-kind]");
        if (open) {
          // 唔攔 navigation（新 tab 開 form），背後記 log 再刷新狀態。
          const kind = open.getAttribute("data-onoff-kind");
          postOnOffDutyLog(kind, onoffDate, "opened")
            .then((plan) => { onoffPlan = plan; renderOnOffDuty(); })
            .catch(() => {});
          return;
        }
        const copy = ev.target.closest("[data-onoff-copy]");
        if (copy) {
          const url = copy.getAttribute("data-onoff-copy");
          if (navigator.clipboard && url) {
            navigator.clipboard.writeText(url).then(
              () => { copy.textContent = "Copied ✓"; setTimeout(() => (copy.textContent = "Copy link"), 1500); },
              () => onoffShowError("Copy failed")
            );
          }
          return;
        }
        const btn = ev.target.closest("[data-onoff-action]");
        if (!btn) return;
        const action = btn.dataset.onoffAction;
        if (action === "refresh") return refreshOnOffDuty();
        if (action === "date-prev") return onoffShiftDate(-1);
        if (action === "date-next") return onoffShiftDate(1);
        if (action === "date-today") { onoffDate = ""; return refreshOnOffDuty(); }
        const forKind = btn.getAttribute("data-onoff-for") || "end";
        if (action === "duty-hold" || action === "duty-release") {
          postOnOffDutyHoldSend(action === "duty-hold" ? "hold" : "release", forKind)
            .then((plan) => { onoffPlan = plan; onoffShowError(""); renderOnOffDuty(); })
            .catch((e) => onoffShowError(e.message || String(e)));
          return;
        }
        if (action === "duty-send") {
          const isStart = forKind === "start";
          const lines = isStart
            ? "· 交 On Duty form（而家時間）\n· 出 WhatsApp 報開工\n· 實際開工同預設唔同就寫入加班表（報平安更／餐單／日曆跟住郁）"
            : "· 交 Off Duty form（而家時間）\n· 出 WhatsApp 報收工\n· 超出更時表窗口（早開工/遲收工）兼 總工時>10.25h 先寫加班表";
          if (!window.confirm((isStart ? "以而家時間報開工？\n" : "以而家時間報收工？\n") + lines)) return;
          btn.disabled = true;
          postOnOffDutyHoldSend("send_now", forKind)
            .then((plan) => {
              onoffPlan = plan;
              const r = plan.sendnow_result || {};
              onoffShowError("");
              renderOnOffDuty();
              window.alert(`齊發完成 ${r.actual || ""}\nForm: sent\nWhatsApp: ${r.whatsapp || "?"}\n加班表: ${r.overtime_written ? "已寫入" : "冇寫"}`);
            })
            .catch((e) => { onoffShowError(e.message || String(e)); btn.disabled = false; });
          return;
        }
      });
    });
