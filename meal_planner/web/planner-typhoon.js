    // Typhoon panel: 打風落波 what-if —— 一次過睇齊行位表／餐單／報平安／報開工收工點反應。
    // 實際開工 = max(落波 + 品牌 offset, 原定開工)，收工唔郁。
    // 「確實」＝天文台已公布嘅落波時間；剔咗先開得 Apply（寫加班表開工 + 重排報平安更）。
    let typhoonPlan = null;
    let typhoonLoading = false;
    let typhoonDate = "";
    let typhoonSignal = "";
    let typhoonCode = "";
    let typhoonConfirmed = false;
    let typhoonDayOff = false;
    let typhoonName = "";
    let typhoonNameNote = "";
    let typhoonRefocusSignal = false;  // 重畫成個 panel 會失去 focus，打字期間要留返喺個格度
    let typhoonSignalCaret = null;
    let typhoonSignalTyping = false;
    let typhoonRefocusName = false;
    // 重新計出嚟嘅當日餐單（要行 LP，撳 Recalculate 先計）——連住邊個日期／開工時間計出嚟。
    let typhoonMeal = null;
    let typhoonMealBusy = false;

    // Ctrl+A 揀晒 / Ctrl+左 click 逐個加減；揀咗 2 個或以上，拖任何一個 title 就成組一齊郁。
    // Esc 或者撳空白位取消。
    let typhoonSelected = new Set();

    function typhoonBlockEls() {
      const layout = document.getElementById("typhoon-layout");
      return layout ? Array.from(layout.querySelectorAll("[data-duty-block]")) : [];
    }

    function typhoonMarkSelection() {
      typhoonBlockEls().forEach((block) => {
        const key = block.getAttribute("data-duty-block");
        block.classList.toggle("typhoon-block-selected", typhoonSelected.has(key));
      });
    }

    function typhoonSelectAllBlocks() {
      typhoonSelected = new Set(typhoonBlockEls().map((b) => b.getAttribute("data-duty-block")));
      typhoonMarkSelection();
    }

    function typhoonClearSelection() {
      if (!typhoonSelected.size) return;
      typhoonSelected = new Set();
      typhoonMarkSelection();
    }

    // Capture 階段行先，攔住 attachDutyBlockHandles 嗰個「淨係郁自己」嘅 handler。
    function typhoonBindGroupDrag(out) {
      if (out.dataset.typhoonGroupBound === "1") return;
      out.dataset.typhoonGroupBound = "1";
      out.addEventListener(
        "mousedown",
        (ev) => {
          if (ev.button != null && ev.button !== 0) return;
          if (!ev.target.closest) return;
          // Ctrl + 左 click ＝ 逐個加減揀選（撳邊度都得，除咗真係要撳嗰啲嘢）。
          if (ev.ctrlKey || ev.metaKey) {
            const picked = ev.target.closest("[data-duty-block]");
            if (!picked) return;
            if (ev.target.closest("input,textarea,select,button,a,.form-col-resizer,.duty-rs")) return;
            ev.preventDefault();
            ev.stopPropagation();
            const pickedKey = picked.getAttribute("data-duty-block");
            if (typhoonSelected.has(pickedKey)) typhoonSelected.delete(pickedKey);
            else typhoonSelected.add(pickedKey);
            typhoonMarkSelection();
            return;
          }
          const title = ev.target.closest(".duty-block-title");
          if (!title) return;
          const block = title.closest("[data-duty-block]");
          const key = block && block.getAttribute("data-duty-block");
          if (!key || typhoonSelected.size < 2 || !typhoonSelected.has(key)) return;
          ev.preventDefault();
          ev.stopPropagation();
          const startX = ev.clientX;
          const startY = ev.clientY;
          const starts = typhoonBlockEls()
            .filter((b) => typhoonSelected.has(b.getAttribute("data-duty-block")))
            .map((b) => ({ key: b.getAttribute("data-duty-block"), x: b.offsetLeft, y: b.offsetTop }));
          startWindowDrag({
            bodyClass: "is-dnd-dragging",
            onMove: (mv) => {
              const dx = mv.clientX - startX;
              const dy = mv.clientY - startY;
              // 同單個 block 一樣落 10px 格（成組一齊郁都要對齊）。
              starts.forEach((item) => {
                formColumnWidths[`duty_block_${item.key}_x`] = dutyBlockSnap(item.x + dx);
                formColumnWidths[`duty_block_${item.key}_y`] = Math.max(0, dutyBlockSnap(item.y + dy));
              });
              applyDutyBlockLayout();
            },
            onUp: () => persistColumnWidths(),
          });
        },
        true
      );
    }

    function typhoonEsc(text) {
      return String(text == null ? "" : text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }

    function typhoonShowError(message) {
      const err = document.getElementById("typhoon-err");
      if (err) err.textContent = message || "";
    }

    let typhoonRefreshPending = false;

    // 攞緊嘢期間再叫一次唔可以就咁掉咗——排隊等佢完再行一次，
    // 否則（例如天文台個名遲少少先返到）個 plan 會停喺舊值。
    async function refreshTyphoon() {
      if (typhoonLoading) {
        typhoonRefreshPending = true;
        return;
      }
      typhoonLoading = true;
      try {
        typhoonPlan = await loadTyphoonPlan({
          dateIso: typhoonDate,
          signalTime: typhoonSignal,
          code: typhoonCode,
          confirmed: typhoonConfirmed,
          dayOff: typhoonDayOff,
          name: typhoonName,
        });
        typhoonShowError("");
        // 後端會將落波時間讀成 30 小時制（02:56 → 26:56）——個格跟返佢，
        // 唔好留住你打嗰個 24 小時寫法，否則睇落同下面啲時間對唔上。
        if (typhoonPlan && typhoonPlan.signal_time) typhoonSignal = typhoonPlan.signal_time;
        renderTyphoon();
        persistTyphoonState();
      } catch (e) {
        typhoonShowError(e && e.message ? e.message : String(e));
      } finally {
        typhoonLoading = false;
        if (typhoonRefreshPending) {
          typhoonRefreshPending = false;
          refreshTyphoon();
        }
      }
    }

    // 30 小時制：凌晨 00:00–05:59 寫成 24:00–29:59（落波時間唔收 00:xx 嗰個寫法）。
    function typhoonNowHHMM() {
      const now = new Intl.DateTimeFormat("en-GB", {
        timeZone: HK_TZ, hour: "2-digit", minute: "2-digit", hour12: false,
      }).format(new Date());
      const hour = parseInt(now.slice(0, 2), 10);
      return hour < 6 ? `${hour + 24}:${now.slice(3)}` : now;
    }

    // 記住上次嘅輸入（日期／落波／個名／確實／更碼），存喺 ui-state。
    function persistTyphoonState() {
      typhoonSavedState = {
        date_iso: typhoonDate,
        signal_time: typhoonSignal,
        name: typhoonName,
        confirmed: typhoonConfirmed,
        day_off: typhoonDayOff,
        code: typhoonCode,
      };
      persistUiState({ typhoon_state: typhoonSavedState }).catch(() => {});
    }

    // 離開 Typhoon 畫面（撳去第二個 menu）就即刻存一次——
    // 唔靠「下次成功重算先存」，打完字直接走人都唔會漏。
    function leaveTyphoonPanel() {
      if (typeof activePanel !== "undefined" && activePanel !== "typhoon") return;
      const box = document.getElementById("typhoon-signal");
      if (box) typhoonSignal = box.value;
      const nameBox = document.getElementById("typhoon-name");
      if (nameBox) typhoonName = nameBox.value;
      persistTyphoonState();
    }

    // 開返上次個畫面；第一次用（冇存過）就今日 + 而家。cursor 一律落喺落波時間度。
    async function openTyphoonPanel() {
      if (typeof setActiveMenuPathForKey === "function") setActiveMenuPathForKey("typhoon");
      setActivePanel("typhoon");
      const saved = typhoonSavedState || {};
      typhoonDate = String(saved.date_iso || "");
      typhoonCode = String(saved.code || "");
      typhoonName = String(saved.name || "");
      typhoonConfirmed = !!saved.confirmed;
      typhoonDayOff = !!saved.day_off;
      typhoonSignal = String(saved.signal_time || "") || typhoonNowHHMM();
      typhoonSignalTyping = false;
      typhoonRefocusSignal = true;
      typhoonSignalCaret = null;
      // 上次計好嗰份餐單留喺 memory：日期／開工時間一樣就即刻見返，唔使等 LP 再跑。
      await refreshTyphoon();
      fillTyphoonNameFromObservatory();
    }

    // 個名由天文台正追蹤緊嘅熱帶氣旋帶出嚟（10 分鐘 cache），每次開面板都覆蓋返最新嗰個。
    // 攞唔到就唔郁（留返上次嗰個 + 講明點解）。直接改個格嘅 value，唔重畫，唔會搶走 cursor。
    function fillTyphoonNameFromObservatory() {
      loadTyphoonCurrentName()
        .then((data) => {
          typhoonNameNote = String((data && data.note) || "");
          const box = document.getElementById("typhoon-name");
          if (!box) return;
          box.title = typhoonNameNote || `天文台：${(data.names || []).map((n) => n.zh || n.en).join("、")}`;
          // 每次入嚟都跟返而家真係吹緊嗰個——上次存低嘅舊名唔應該賴死唔走。
          if (!data.name || data.name === typhoonName) return;
          typhoonName = data.name;
          box.value = data.name;
          // 加班表個備註由後端砌（同 Apply 寫落去嗰個係同一段 code），所以要重算一次。
          typhoonRefocusSignal = true;  // cursor 留返喺落波時間度
          refreshTyphoon();
        })
        .catch(() => {});
    }

    // ◀ ▶ 郁嘅係「落波日期」（同落波時間一 pair），唔係模擬邊日。
    async function typhoonShiftDate(deltaDays) {
      const base = typhoonPlan ? (typhoonPlan.signal_date_iso || typhoonPlan.date_iso) : "";
      if (!base || typhoonLoading) return;
      const [y, m, d] = base.split("-").map(Number);
      const dt = new Date(Date.UTC(y, m - 1, d + deltaDays, 12, 0, 0));
      const iso = `${dt.getUTCFullYear()}-${String(dt.getUTCMonth() + 1).padStart(2, "0")}-${String(dt.getUTCDate()).padStart(2, "0")}`;
      typhoonDate = iso === typhoonPlan.today_iso ? "" : iso;
      typhoonCode = "";  // 換日 = 換更碼，手動揀嗰個唔再作準
      await refreshTyphoon();
    }

    // 30 小時制顯示：凌晨 00:00–05:59 屬前一日嘅 24:00–29:59。
    // sheet 入面照樣存 00:xx（其他頁、電話、日曆都係咁讀），呢度淨係顯示層轉。
    // 唔似時間嘅字（例如備註「颱風Kajiki」）原封不動。
    function typhoon30(text) {
      const m = /^(\d{1,2}):(\d{2})$/.exec(String(text == null ? "" : text).trim());
      if (!m) return text;
      const hour = parseInt(m[1], 10);
      return hour < 6 ? `${hour + 24}:${m[2]}` : text;
    }

    // 同一張表入面會撈埋唔同日嘅時間（開工過咗 30:00 就冚落第二日朝早），
    // 所以每個時間都要連日期出——淨睇 HH:MM 分唔到邊日。
    function typhoonDateFor(minutes) {
      const base = (typhoonPlan && typhoonPlan.date_iso) || "";
      const [y, mo, d] = base.split("-").map(Number);
      if (!y) return { iso: "", dm: "" };
      // 一日由 06:00 起計：06:00–29:59 都算當日，夠 30:00 先過下一日。
      const offset = Math.floor(((minutes || 0) - 360) / 1440);
      const dt = new Date(Date.UTC(y, mo - 1, d + offset, 12, 0, 0));
      const dd = String(dt.getUTCDate()).padStart(2, "0");
      const mm = String(dt.getUTCMonth() + 1).padStart(2, "0");
      return { iso: `${dt.getUTCFullYear()}-${mm}-${dd}`, dm: `${dd}/${mm}` };
    }

    // minutes 有就用（最準）；冇就由 HH:MM 反推 30 小時制分鐘。
    // 報開工同 plan.start 個 string 一樣，所以撞正就借返佢個分鐘數。
    // bareOn：呢個 block 本身已經寫住嗰日（例如加班表有「日期」一行）——
    // 同嗰日一樣就唔使再喺時間前面插多次日期，唔同日先插。
    function typhoonWhen(text, minutes, bareOn) {
      const raw = String(text == null ? "" : text).trim();
      const m = /^(\d{1,2}):(\d{2})$/.exec(raw);
      if (!m) return text;
      let mins = minutes;
      if (mins == null) {
        const plan = typhoonPlan || {};
        if (plan.start && raw === plan.start && plan.start_minutes != null) mins = plan.start_minutes;
        else {
          const hour = parseInt(m[1], 10);
          mins = (hour < 6 ? hour + 24 : hour) * 60 + parseInt(m[2], 10);
        }
      }
      const when = typhoonDateFor(mins);
      const clock = typhoon30(_hhmmFrom(mins));
      return bareOn && when.iso === bareOn ? clock : `${when.dm} ${clock}`;
    }

    function _hhmmFrom(minutes) {
      const within = ((minutes % 1440) + 1440) % 1440;
      const hour = minutes >= 1440 && minutes < 1800 ? Math.floor(minutes / 60) : Math.floor(within / 60);
      return `${String(hour).padStart(2, "0")}:${String(within % 60).padStart(2, "0")}`;
    }

    function typhoonArrow(before, after, bareOn) {
      const a = typhoonEsc(typhoonWhen(before, null, bareOn) || "—");
      const b = typhoonEsc(typhoonWhen(after, null, bareOn) || "—");
      if (!before || before === after) return `<span class="typhoon-same">${b}</span>`;
      return `<span class="typhoon-was">${a}</span> → <span class="typhoon-now">${b}</span>`;
    }

    // 模擬邊一日：落波之後最近嗰個返到工嘅工作日，唔一定係落波嗰日。
    function typhoonTargetLabel(plan) {
      if (!plan.date_iso) return "";
      const [y, m, d] = plan.date_iso.split("-").map(Number);
      const dow = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][
        new Date(Date.UTC(y, m - 1, d, 12, 0, 0)).getUTCDay()
      ];
      const days = plan.days_after_signal || 0;
      const same = days === 0 ? "" : ` · ${days}d after the signal`;
      return `<span class="duty-chip typhoon-target" title="落波之後最近嗰個返到工嘅工作日">Work day ${String(d).padStart(2, "0")}/${String(m).padStart(2, "0")} ${dow}${same}</span>`;
    }

    function typhoonSummary(plan, applyBtn = "") {
      const delay = plan.delay_minutes
        ? `${Math.floor(plan.delay_minutes / 60)}h${String(plan.delay_minutes % 60).padStart(2, "0")} late`
        : "on time";
      const offsetText = plan.offset_minutes ? `+${plan.offset_minutes} min` : "start at once";
      if (plan.day_off_possible && !plan.day_off) {
        // 有可能唔使返但未宣佈：照出正常模擬，提示併入下面 Apply 嗰行，唔另佔一行。
        return typhoonSummaryCards(plan, applyBtn);
      }
      if (plan.day_off) {
        // 全日唔使返：唔好再出一堆「幾點開工／遲咗幾多」——嗰啲全部唔適用。
        return `<div class="duty-stats typhoon-stats">
          <div class="duty-stat-card typhoon-dayoff">
            <div class="duty-stat-label">Signal down</div>
            <div class="duty-stat-value">${typhoonEsc(plan.signal_time)}</div>
            <div class="duty-stat-sub">${plan.confirmed ? "confirmed" : "estimated"}</div>
          </div>
          <div class="duty-stat-card typhoon-dayoff">
            <div class="duty-stat-label">Off duty</div>
            <div class="duty-stat-value">${typhoonEsc(typhoonWhen(plan.end, plan.end_minutes) || "—")}</div>
            <div class="duty-stat-sub">less than 4h away</div>
          </div>
          <div class="duty-stat-card typhoon-dayoff">
            <div class="duty-stat-label">Day off</div>
            <div class="duty-stat-value">${typhoonEsc(plan.day_off_code || "—")}</div>
            <div class="duty-stat-sub">全日唔使返</div>
          </div>
          ${applyBtn ? `<div class="typhoon-apply-slot">${applyBtn}</div>` : ""}
        </div>`;
      }
      return typhoonSummaryCards(plan, applyBtn);
    }

    function typhoonSummaryCards(plan, applyBtn = "") {
      const delay = plan.delay_minutes
        ? `${Math.floor(plan.delay_minutes / 60)}h${String(plan.delay_minutes % 60).padStart(2, "0")} late`
        : "on time";
      const offsetText = plan.offset_minutes ? `+${plan.offset_minutes} min` : "start at once";
      const cards = [
        { label: "Signal down", value: typhoonWhen(plan.signal_time, plan.signal_minutes), sub: plan.confirmed ? "confirmed" : "estimated" },
        { label: `${plan.brand} rule`, value: offsetText, sub: `earliest ${typhoonWhen(plan.earliest_start, plan.earliest_minutes)}` },
        { label: "Planned on duty", value: typhoonWhen(plan.planned_start, plan.planned_minutes), sub: plan.overtime_start ? "Overtime override" : "Schedule Grid" },
        { label: "On duty", value: typhoonWhen(plan.start, plan.start_minutes), sub: delay },
        { label: "Off duty", value: typhoonWhen(plan.end, plan.end_minutes) || "—", sub: "unchanged by typhoon" },
      ];
      return `<div class="duty-stats typhoon-stats">${cards
        .map(
          (c) => `<div class="duty-stat-card">
            <div class="duty-stat-label">${typhoonEsc(c.label)}</div>
            <div class="duty-stat-value">${typhoonEsc(c.value || "—")}</div>
            <div class="duty-stat-sub">${typhoonEsc(c.sub)}</div>
          </div>`
        )
        .join("")}${applyBtn ? `<div class="typhoon-apply-slot">${applyBtn}</div>` : ""}</div>`;
    }

    // 用返系統標準嗰套 sheet：colgroup + data-form-col-key，欄闊拖得住兼記得住，
    // applyFormColumnWidths 會順手將 table 闊度設成各欄總和（唔會撐到成行咁闊）。
    function typhoonTable(prefix, columns, body) {
      const cols = columns
        .map((c) => `<col data-form-col-key="typhoon_${prefix}_${c.key}" data-form-col-default="${c.width}" />`)
        .join("");
      const heads = columns
        .map((c) => `<th data-form-col-key="typhoon_${prefix}_${c.key}">${typhoonEsc(c.label)}</th>`)
        .join("");
      return `<table class="typhoon-table" data-form-table>
        <colgroup>${cols}</colgroup>
        <thead><tr>${heads}</tr></thead>
        <tbody>${body}</tbody></table>`;
    }

    function typhoonSectionNote(note) {
      return note ? `<div class="duty-status-muted typhoon-note">${typhoonEsc(note)}</div>` : "";
    }

    function typhoonGridTable(section) {
      if (!section.rows.length) return typhoonSectionNote(section.note || "No data.");
      const body = section.rows
        .map((row) => {
          const cls = row.inserted ? "typhoon-row-new" : row.unreachable ? "duty-row-muted" : "";
          const timeCell = row.inserted
            ? `<span class="typhoon-now">${typhoonEsc(typhoonWhen(row.time, row.minutes))}</span>`
            : typhoonEsc(typhoonWhen(row.time, row.minutes));
          const state = row.inserted
            ? (row.is_start ? "on duty (typhoon)" : "typhoon report")
            : row.unreachable
              ? "missed (before start)"
              : "";
          return `<tr class="${cls}">
            <td class="duty-td-time">${timeCell}</td>
            <td>${typhoonEsc(row.content)}</td>
            <td class="typhoon-td-len">${row.duration_min == null ? "" : typhoonEsc(row.duration_min)}</td>
            <td class="typhoon-state">${typhoonEsc(state)}</td>
          </tr>`;
        })
        .join("");
      return typhoonSectionNote(section.note) + typhoonTable("grid", [
        { key: "time", label: "Time", width: 116 },
        { key: "item", label: "Item", width: 320 },
        { key: "length", label: "Length", width: 70 },
        { key: "status", label: "Status", width: 210 },
      ], body);
    }

    // 打風日報更係一條全新時間表（開工起計每 4 個鐘），唔係逐個 slot 移，
    // 所以出一張新表；原定嗰堆鐘點喺表上面列返出嚟對照。
    function typhoonReportTable(section) {
      if (!section.rows.length) return typhoonSectionNote(section.note || "No data.");
      const body = section.rows
        .map(
          // Item 出返真正會 send 出去嗰句（唔係行位表個標籤）——所見即所發。
          (row) => `<tr class="${row.skipped ? "duty-row-muted" : ""}" title="${typhoonEsc(row.content)}">
            <td class="duty-td-time">${typhoonEsc(typhoonWhen(row.time, row.minutes))}</td>
            <td>${typhoonEsc(row.message)}</td>
            <td>${typhoonEsc(row.group || "—")}</td>
            <td class="typhoon-state">${row.skipped ? "skipped" : ""}</td>
          </tr>`
        )
        .join("");
      // 「打風前」嗰串鐘點：同下面張表一樣就唔使出（純重複），唔同先列出嚟對照。
      const plannedTimes = section.planned_times || [];
      const rowTimes = section.rows.map((r) => r.time);
      const samePlan =
        plannedTimes.length === rowTimes.length && plannedTimes.every((t, i) => t === rowTimes[i]);
      const planned = samePlan ? "" : plannedTimes.map((t) => typhoonWhen(t)).join(" · ");
      const h = section.interval_hours;
      const cadence =
        section.mode === "typhoon"
          ? `<div class="duty-status-muted typhoon-note">Every ${h}h from the on-duty time; the last one uses the finish time when it lands under ${h}h.${planned ? ` · Before the typhoon: ${typhoonEsc(planned)}` : ""}</div>`
          : "";
      return typhoonSectionNote(section.note) + cadence + typhoonTable("report", [
        { key: "time", label: "Time", width: 116 },
        { key: "message", label: "Message", width: 230 },
        { key: "group", label: "Group", width: 230 },
        { key: "status", label: "Status", width: 120 },
      ], body);
    }

    // 手上嗰份餐單係咪已經對唔上而家個模擬（換咗日／開工時間／全日唔使返）。
    function typhoonMealStale(plan) {
      return !typhoonMeal
        || typhoonMeal.forDate !== plan.date_iso
        || typhoonMeal.forStart !== plan.start
        || typhoonMeal.forDayOff !== !!plan.day_off;
    }

    // 模擬一有結果就自己計埋餐單，唔使撳掣（LP 大概三幾秒）。
    // 慢半拍先開始：打字期間 plan 會連環更新，唔想每次都開一個 LP。
    let typhoonAutoMealTimer = null;
    // 計失敗嗰組輸入（日期＋開工＋day off）；換咗任何一樣先再自動計。
    let typhoonMealFailedKey = "";
    let typhoonMealError = "";

    function typhoonMealKey(plan) {
      return `${plan.date_iso}|${plan.start}|${plan.day_off ? 1 : 0}`;
    }

    function typhoonAutoRecalcMeals(plan) {
      if (!plan || !plan.ok || typhoonMealBusy || !typhoonMealStale(plan)) return;
      // 同一組輸入計失敗過就唔好再自動試——唔係嘅話會一路重試一路重畫（成個 block 閃）。
      if (typhoonMealFailedKey === typhoonMealKey(plan)) return;
      if (typhoonAutoMealTimer) clearTimeout(typhoonAutoMealTimer);
      typhoonAutoMealTimer = setTimeout(() => typhoonRecalcMeals(), 300);
    }

    // 全份餐單：直接叫餐單頁個 renderPeriodTable，食材／10 個營養值／次序完全一樣。
    // 兩粒掣擺喺張表右邊（同 Target 幾行平排），唔會霸多一行高度。
    function typhoonFullMealPlan(plan) {
      const stale = typhoonMealStale(plan);
      const busy = typhoonMealBusy;
      const actions = `<div class="typhoon-meal-actions">
        <button type="button" class="duty-btn duty-btn-primary" data-typhoon-action="meal-generate" ${busy ? "disabled" : ""}>
          ${busy ? "…" : "Generate"}</button>
        <button type="button" class="duty-btn" data-typhoon-action="recalc" ${busy ? "disabled" : ""}>
          ${busy ? "…" : "Recalculate"}</button>
        <div class="duty-status-muted typhoon-meal-hint">${typhoonEsc(
          busy
            ? "running the solver…"
            : stale
              ? (typhoonMealFailedKey === typhoonMealKey(plan)
                  ? `Could not work out the meals: ${typhoonMealError}`
                  : "working out the day's meals…")
              : typhoonMeal.snack_note || "Generate = another draw · Recalculate = same draw"
        )}</div>
      </div>`;
      const payload = (!stale && !busy && typhoonMeal.payload) || null;
      const sheet = payload
        ? renderPeriodTable(payload.days || [], payload.headers || null, payload.nutrient_keys, payload.indicator_rows)
        : "";
      return `<div class="typhoon-meal-wrap">${sheet}${actions}</div>`;
    }

    function typhoonOvertimeTable(section) {
      // 冇行 ＝ 開工冇郁，唔使寫加班表；出返句解釋就得，唔好出張空表。
      if (!section.rows.length) return typhoonSectionNote(section.note || "No change.");
      // 加班表本身第一行就係「日期」——同嗰日嘅時間唔使再帶日期。
      const dateRow = section.rows.find((r) => r.field === "日期") || {};
      const bareOn = String(dateRow.after || dateRow.before || "");
      const body = section.rows
        .map(
          (row) => `<tr>
            <td>${typhoonEsc(row.field)}</td>
            <td class="duty-td-time">${typhoonArrow(row.before, row.after, bareOn)}</td>
          </tr>`
        )
        .join("");
      return typhoonSectionNote(section.note) + typhoonTable("overtime", [
        { key: "field", label: "Field", width: 70 },
        { key: "value", label: "Now → After apply", width: 210 },
      ], body);
    }

    function typhoonGcTable(section) {
      if (!section.rows.length) return typhoonSectionNote(section.note || "No data.");
      const body = section.rows
        .map(
          (row) => `<tr>
            <td title="${typhoonEsc(row.calendar_id || "")}">${typhoonEsc(row.calendar)}</td>
            <td>${typhoonEsc(row.event)}</td>
            <td class="duty-td-time">${typhoonArrow(row.before, row.after)}</td>
          </tr>`
        )
        .join("");
      const sub = section.wake_offset_hours
        ? `<div class="duty-status-muted typhoon-note">起身 = ${section.wake_offset_hours}h before on duty · calendar times come from 更時表, not the Schedule Grid</div>`
        : "";
      return typhoonSectionNote(section.note) + sub + typhoonTable("gc", [
        { key: "calendar", label: "Calendar", width: 80 },
        { key: "event", label: "Event", width: 110 },
        { key: "time", label: "Planned → Typhoon", width: 170 },
      ], body);
    }

    function typhoonOnOffCards(section, applied) {
      const cards = section.rows
        .map((row) => {
          const held = row.kind === "start" ? applied.hold_start : applied.hold_end;
          return `<div class="duty-stat-card onoff-card">
            <div class="duty-stat-label">${typhoonEsc(row.label)}</div>
            <div class="duty-stat-value">${typhoonArrow(row.before, row.after)}</div>
            <div class="duty-stat-sub">${held ? "⏸ holding — press Send now when it really happens" : "auto-submits at this time"}</div>
          </div>`;
        })
        .join("");
      const meta = [section.form_label, section.post].filter(Boolean).join(" · ");
      return `${typhoonSectionNote(section.note)}<div class="onoff-meta">${typhoonEsc(meta)}</div>
        <div class="duty-stats onoff-stats">${cards}</div>`;
    }

    // 用返 ReportNormal／OnOffDuty 嗰套 block：title 拖得郁、位置記得住、
    // 有表嘅 block 闊度自動 = 各欄總和（見 dutyBlockWidthPx）。
    function typhoonBlock(key, title, inner) {
      const hasTable = inner.includes("<table");
      const cls = hasTable ? "duty-block duty-block-card typhoon-block-table" : "duty-block duty-block-card";
      return `<div class="${cls}" data-duty-block="typhoon_${key}">
        <div class="duty-block-title" title="Drag to move · double-click to reset · Ctrl+A select all · Ctrl+click to pick blocks, then drag any one to move them together">${typhoonEsc(title)}</div>
        <div class="typhoon-block-body">${inner}</div>
      </div>`;
    }

    function renderTyphoon() {
      const out = document.getElementById("typhoon-out");
      if (!out || !typhoonPlan) return;
      const plan = typhoonPlan;
      const relationLabel = plan.relation === "today" ? "today" : plan.relation === "past" ? "past" : "future";
      // 更碼直接揀住當日嗰個（跟更表），揀第二個就當手動 override。
      const codes = Array.isArray(plan.known_codes) ? plan.known_codes : [];
      const current = plan.roster_code || "";
      const list = !current || codes.includes(current) ? codes : [current].concat(codes);
      const options =
        (current ? "" : '<option value="" selected>(no code)</option>') +
        list
          .map(
            (code) =>
              `<option value="${typhoonEsc(code)}"${code === current ? " selected" : ""}>${typhoonEsc(code)}</option>`
          )
          .join("");

      const applied = (plan.applied || {});
      const appliedChip = applied.overtime_matches
        ? `<span class="duty-chip duty-chip-ok">Applied · Overtime start ${typhoonEsc(applied.overtime_start)}</span>`
        : applied.overtime_start
          ? `<span class="duty-chip">Overtime already has start ${typhoonEsc(applied.overtime_start)}</span>`
          : "";

      // 撳走／撳 Enter 之後先重畫，所以呢度一律出後端讀到嗰個 HH:MM。
      const signalValue = plan.signal_time || typhoonSignal;
      const toolbar = `<div class="duty-toolbar typhoon-toolbar">
        <button type="button" class="duty-btn" data-typhoon-action="date-prev">◀</button>
        <input type="date" id="typhoon-date" class="typhoon-date-input" value="${typhoonEsc(plan.signal_date_iso || plan.date_iso)}" title="落波日期（同落波時間一 pair）" />
        <button type="button" class="duty-btn" data-typhoon-action="date-next">▶</button>
        <span class="duty-date">${relationLabel}</span>
        ${plan.relation !== "today" ? '<button type="button" class="duty-btn" data-typhoon-action="date-today">Today</button>' : ""}
        <label class="typhoon-field">Signal down
          <input type="text" id="typhoon-signal" class="typhoon-time" value="${typhoonEsc(signalValue)}" maxlength="5" placeholder="11:40" title="11:40 / 1140 / 2416 all accepted" />
        </label>
        <label class="typhoon-field"><input type="checkbox" id="typhoon-confirmed" ${typhoonConfirmed ? "checked" : ""} />Confirmed</label>
        <label class="typhoon-field">Name
          <input type="text" id="typhoon-name" class="typhoon-name" value="${typhoonEsc(typhoonName)}" placeholder="韋帕" title="${typhoonEsc(typhoonNameNote || "加班表備註會寫「颱風」+ 呢個名（預設由天文台帶出）")}" />
        </label>
        <label class="typhoon-field ${plan.day_off_possible ? "typhoon-dayoff-live" : "typhoon-field-off"}" title="${typhoonEsc(
          plan.day_off_possible
            ? "舖頭宣佈全日唔使返先剔——唔夠 4 個鐘唔代表自動放假"
            : "落波距離收工夠 4 個鐘，唔會全日唔使返"
        )}"><input type="checkbox" id="typhoon-dayoff" ${typhoonDayOff ? "checked" : ""} ${plan.day_off_possible ? "" : "disabled"} />Day off</label>
        <label class="typhoon-field">Code
          <select id="typhoon-code">${options}</select>
        </label>
        <button type="button" class="duty-btn" data-typhoon-action="refresh">Simulate</button>
        ${typhoonTargetLabel(plan)}
      </div>`;

      if (!plan.ok) {
        out.innerHTML = `<div class="duty-layout" id="typhoon-layout">${typhoonBlock(
          "main",
          "Typhoon",
          `${toolbar}<div class="duty-status-muted typhoon-note">${typhoonEsc(plan.note || "Fill in the form above.")}</div>`
        )}</div>`;
        attachTyphoonInputs();
        return;
      }

      // 提示唔再霸一行——併埋做 Apply 個 tooltip；已套用嗰粒 chip 一齊跟埋。
      const applyHint = [plan.day_off_note, plan.apply_blocked].filter(Boolean).join("　")
        || "Writes the on-duty time into Overtime and reshapes ReportNormal — the Schedule Grid is never touched";
      const applyBtn = `<button type="button" class="duty-btn duty-btn-primary typhoon-apply-btn"
        data-typhoon-action="apply" ${plan.can_apply ? "" : "disabled"}
        title="${typhoonEsc(applyHint)}">Apply</button>${appliedChip}`;

      out.innerHTML = `<div class="duty-layout" id="typhoon-layout">
        ${typhoonBlock("main", "Typhoon", `${toolbar}${typhoonSummary(plan, applyBtn)}`)}
        ${typhoonBlock("grid", "Schedule Grid", typhoonGridTable(plan.grid))}
        ${typhoonBlock("meal", "Meal Plan", typhoonSectionNote(plan.meals.note) + typhoonFullMealPlan(plan))}
        ${typhoonBlock("report", "ReportNormal", typhoonReportTable(plan.report_normal))}
        ${typhoonBlock("onoff", "OnOffDuty", typhoonOnOffCards(plan.onoffduty, applied))}
        ${typhoonBlock("overtime", "Overtime 加班表", typhoonOvertimeTable(plan.overtime))}
        ${typhoonBlock("gc", "Google Calendar", typhoonGcTable(plan.gc))}
      </div>`;
      attachTyphoonInputs();
      typhoonAutoRecalcMeals(plan);
    }

    // 打字期間乜都唔做——成個畫面淨係喺你**撳走**（或者撳 Enter）先至更新一次。
    // 咁樣打到一半唔會俾人 re-render、唔會閃、亦唔會走去計啲你未打完嘅時間。
    function typhoonSignalChanged(input, mode) {
      typhoonSignal = input.value;
      if (mode === "typing") {
        // 淨係記低你打咗乜（個格照顯示原文，唔會中途幫你加冒號）。
        typhoonSignalCaret = input.selectionStart;
        typhoonSignalTyping = true;
        return;
      }
      // blur 同 change 兩個都可能 fire（或者只有一個），更新一次就夠。
      if (mode === "blur" && !typhoonSignalTyping) return;
      typhoonSignalCaret = null;
      typhoonSignalTyping = false;
      typhoonRefocusSignal = mode === "commit";  // 撳 Enter 留返個 cursor，撳走就唔搶
      refreshTyphoon();
    }

    function attachTyphoonInputs() {
      const out = document.getElementById("typhoon-out");
      if (out) {
        if (typeof applyFormColumnWidths === "function") applyFormColumnWidths(out);
        if (typeof attachFormColumnResizers === "function") attachFormColumnResizers(out);
        // 餐單張表用餐單頁嗰套欄闊（col-resizer + columnWidths），綁返落我哋張表度。
        if (out.querySelector("table.sheet")) {
          if (typeof applyColumnWidths === "function") applyColumnWidths();
          if (typeof attachColumnResizers === "function") attachColumnResizers(out);
        }
        if (typeof applyDutyBlockLayout === "function") applyDutyBlockLayout();
        // 計完餐單成張表插咗入去：如果 block 之前俾人拉矮咗，內容就會收埋喺入面
        // （要喺 block 裏面再捲先見到，好易以為「冇出到」）——清走個固定高度，等佢自己撐高。
        const mealBlock = out.querySelector('[data-duty-block="typhoon_meal"]');
        if (
          mealBlock
          && mealBlock.querySelector("table.sheet")
          && Number.isFinite(Number(formColumnWidths["duty_block_typhoon_meal_h"]))
          && mealBlock.scrollHeight > mealBlock.clientHeight + 2
        ) {
          delete formColumnWidths["duty_block_typhoon_meal_h"];
          applyDutyBlockLayout();
          persistColumnWidths();
        }
        if (typeof attachDutyBlockHandles === "function") attachDutyBlockHandles(out);
        typhoonBindGroupDrag(out);
        typhoonMarkSelection();
      }
      const signal = document.getElementById("typhoon-signal");
      if (signal) {
        if (typhoonRefocusSignal) {
          typhoonRefocusSignal = false;
          const caret = typhoonSignalCaret == null ? signal.value.length : typhoonSignalCaret;
          signal.focus();
          signal.setSelectionRange(caret, caret);
        }
        signal.addEventListener("input", () => typhoonSignalChanged(signal, "typing"));
        signal.addEventListener("change", () => typhoonSignalChanged(signal, "blur"));
        // 重畫會換走個 input，focus 過渡到新嗰個——所以撳走嗰陣 `change` 唔一定 fire
        // （新 element 由創建到失焦都冇改過值）。用 blur 兜底先 normalize 得返 HH:MM；
        // 拆走舊 element 嗰下唔算真係撳走，用 isConnected 篩走。
        signal.addEventListener("blur", () => {
          if (signal.isConnected) typhoonSignalChanged(signal, "blur");
        });
        signal.addEventListener("keydown", (ev) => {
          if (ev.key === "Enter") typhoonSignalChanged(signal, "commit");
        });
      }
      const picker = document.getElementById("typhoon-date");
      if (picker) {
        picker.addEventListener("change", () => {
          if (!picker.value) return;
          typhoonDate = picker.value === typhoonPlan.today_iso ? "" : picker.value;  // 落波日期
          typhoonCode = "";  // 換日 = 換更碼，手動揀嗰個唔再作準
          refreshTyphoon();
        });
      }
      const nameBox = document.getElementById("typhoon-name");
      if (nameBox) {
        if (typhoonRefocusName) {
          typhoonRefocusName = false;
          nameBox.focus();
          nameBox.setSelectionRange(nameBox.value.length, nameBox.value.length);
        }
        // 同落波時間一樣：打字唔更新，撳走／撳 Enter 先重算，
        // 加班表 block 到時就睇到真正會寫落去嗰句「颱風X」。
        nameBox.addEventListener("input", () => { typhoonName = nameBox.value; });
        nameBox.addEventListener("change", () => refreshTyphoon());
        nameBox.addEventListener("keydown", (ev) => {
          if (ev.key !== "Enter") return;
          typhoonRefocusName = true;
          refreshTyphoon();
        });
      }
      const dayOff = document.getElementById("typhoon-dayoff");
      if (dayOff) {
        dayOff.addEventListener("change", () => {
          typhoonDayOff = dayOff.checked;
          refreshTyphoon();
        });
      }
      const confirmed = document.getElementById("typhoon-confirmed");
      if (confirmed) {
        confirmed.addEventListener("change", () => {
          typhoonConfirmed = confirmed.checked;
          refreshTyphoon();
        });
      }
      const code = document.getElementById("typhoon-code");
      if (code) {
        code.addEventListener("change", () => {
          typhoonCode = code.value;
          refreshTyphoon();
        });
      }
    }

    let typhoonMealNonce = 0;

    async function typhoonRecalcMeals(newDraw = false) {
      const plan = typhoonPlan;
      if (!plan || !plan.ok || typhoonMealBusy) return;
      if (newDraw) typhoonMealNonce += 1;
      typhoonMealFailedKey = "";
      typhoonMealError = "";
      typhoonMealBusy = true;
      renderTyphoon();
      try {
        const payload = await postTyphoonMealPlan({
          dateIso: typhoonDate, signalTime: typhoonSignal || plan.signal_time,
          code: typhoonCode, dayOff: typhoonDayOff, rerollNonce: typhoonMealNonce,
        });
        typhoonMeal = {
          forDate: plan.date_iso,
          forStart: plan.start,
          forDayOff: !!plan.day_off,
          snack_note: String(payload.snack_note || ""),
          payload,
        };
        typhoonShowError("");
      } catch (e) {
        typhoonMeal = null;
        typhoonMealError = e && e.message ? e.message : String(e);
        typhoonMealFailedKey = typhoonMealKey(plan);
        typhoonShowError(typhoonMealError);
      } finally {
        typhoonMealBusy = false;
        renderTyphoon();
      }
    }

    // Apply 埋單：將畫面嗰份餐單寫入 memory payload，Menu Planner 同電話餐單 tab 就跟得到。
    async function typhoonSaveMealPlan(plan) {
      if (!typhoonMeal || typhoonMeal.forDate !== plan.date_iso || !typhoonMeal.payload) return "not computed";
      const payload = typhoonMeal.payload;
      const day = (payload.days || [])[0];
      if (!day) return "no day";
      try {
        await persistMemoryDays({
          headers: payload.headers || [],
          indicator_rows: payload.indicator_rows || {},
          nutrient_keys: payload.nutrient_keys || [],
          days: [day],
        });
        // 順手更新住喺 memory 嗰份，Menu Planner 唔使 reload 都見到。
        if (memoryPayload && Array.isArray(memoryPayload.days)) {
          const idx = memoryPayload.days.findIndex((d) => d && d.date === day.date);
          if (idx >= 0) memoryPayload.days[idx] = day;
          else memoryPayload.days.push(day);
        }
        return "saved";
      } catch (e) {
        return `failed: ${e && e.message ? e.message : e}`;
      }
    }

    // 日曆 token 過期就即刻問你登入，唔好靜靜哋當同步咗。
    async function typhoonHandleCalendarLogin(gc) {
      if (!gc || gc.status !== "needs_login") return;
      if (!window.confirm(`Google Calendar 登入過期／未登入，日曆未同步到。

${gc.detail || ""}

而家登入？`)) return;
      try {
        await connectGoogleCalendar();
        const again = await postGoogleCalendarRosterSync();
        window.alert(`Google Calendar: ${(again && again.status) || "ok"}`);
      } catch (e) {
        typhoonShowError(e && e.message ? e.message : String(e));
      }
    }

    async function typhoonApply() {
      const plan = typhoonPlan;
      if (!plan || !plan.can_apply) return;
      const lines = plan.day_off ? [
        `${plan.date_iso} · ${plan.roster_code} → ${plan.day_off_code}（颱風假）`,
        plan.day_off_note,
        "Any typhoon on-duty time already written to Overtime, and the day's ReportNormal overlay, get cleared",
        "ReportNormal / Meal Plan / Google Calendar / phone all follow the non-work code",
      ] : [
        `${plan.date_iso} · ${plan.roster_code}`,
        `Overtime start set to ${typhoonWhen(plan.start, plan.start_minutes)} (planned ${typhoonWhen(plan.planned_start, plan.planned_minutes)}), note 颱風${typhoonName.trim()}`,
        `ReportNormal: ${(plan.report_normal.extra_times || []).length} report(s) added, ${(plan.report_normal.skip_slot_ids || []).length} skipped — Schedule Grid is not touched`,
        "Meal Plan and Google Calendar follow this start",
        "OnOffDuty keeps auto-submitting — the on-duty time is settled and the off-duty time is unchanged",
      ].join("\n· ");
      if (!window.confirm(`Apply for real?\n· ${lines}`)) return;
      try {
        typhoonPlan = await postTyphoonApply({
          dateIso: typhoonDate,
          signalTime: typhoonSignal || plan.signal_time,
          code: typhoonCode,
          dayOff: typhoonDayOff,
          name: typhoonName,
        });
        typhoonShowError("");
        // 你喺畫面見到嗰份餐單，就係寫落去嗰份——唔會喺後端再抽一次抽到唔同嘢。
        const mealSaved = await typhoonSaveMealPlan(plan);
        renderTyphoon();
        const r = typhoonPlan.apply_result || {};
        const gc = r.google_calendar || {};
        const push = r.phone_push || {};
        const pushText = push.status === "ok"
          ? `pushed (${push.alarm_count == null ? "?" : push.alarm_count} alarms)`
          : `${push.status || "-"} · ${push.detail || ""}`;
        if (push.status === "other_day") typhoonShowError(push.detail || "");
        const tail = `\nMeal plan: ${mealSaved}\nGoogle Calendar: ${gc.status || "-"}\nPhone: ${pushText}`;
        window.alert(
          r.day_off
            ? `Applied\nRoster code → ${r.roster_code}（颱風假）${tail}\n${r.note || ""}`
            : `Applied\nOvertime start: ${r.overtime_start || "—"} · ${r.overtime_note || ""}` +
              `\nReports added: ${(r.reports_added || []).join(", ") || "none"} · skipped: ${r.reports_skipped || 0}` +
              tail
        );
        await typhoonHandleCalendarLogin(gc);
      } catch (e) {
        typhoonShowError(e && e.message ? e.message : String(e));
      }
    }

    document.addEventListener("keydown", (ev) => {
      if (typeof activePanel !== "undefined" && activePanel !== "typhoon") return;
      if (ev.key === "Escape") return typhoonClearSelection();
      if (!(ev.ctrlKey || ev.metaKey) || String(ev.key).toLowerCase() !== "a") return;
      // 打緊字嗰陣 Ctrl+A 照樣係「全選文字」，唔好搶。
      const tag = (ev.target && ev.target.tagName) || "";
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      ev.preventDefault();
      typhoonSelectAllBlocks();
    });

    document.addEventListener("DOMContentLoaded", () => {
      const out = document.getElementById("typhoon-out");
      if (!out) return;
      out.addEventListener("mousedown", (ev) => {
        // 撳空白位（唔喺任何 block 上面）＝ 取消揀選
        if (!ev.target.closest || !ev.target.closest("[data-duty-block]")) typhoonClearSelection();
      });
      out.addEventListener("click", (ev) => {
        const btn = ev.target.closest("[data-typhoon-action]");
        if (!btn) return;
        const action = btn.dataset.typhoonAction;
        if (action === "refresh") return refreshTyphoon();
        if (action === "date-prev") return typhoonShiftDate(-1);
        if (action === "date-next") return typhoonShiftDate(1);
        if (action === "date-today") { typhoonDate = ""; typhoonCode = ""; return refreshTyphoon(); }
        if (action === "recalc") return typhoonRecalcMeals();
        if (action === "meal-generate") return typhoonRecalcMeals(true);
        if (action === "apply") return typhoonApply();
      });
    });
