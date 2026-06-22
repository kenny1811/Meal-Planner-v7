
    const DESKTOP_LAN_SERVER = "http://192.168.15.125:8765";
    let rerollNonce = 0;

    document.addEventListener("contextmenu", (ev) => {
      const insideApp = ev.target && ev.target.closest && ev.target.closest(".app-shell");
      if (insideApp) ev.preventDefault();
    });

    document.getElementById("go").addEventListener("click", async () => {
      const err = document.getElementById("err");
      const go = document.getElementById("go");
      err.style.display = "none";
      err.textContent = "";
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
        const data = await r.json().catch(() => ({}));
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
        lastData = data;
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
      if (el) el.addEventListener("input", updateGenerateButtonState);
      if (el) el.addEventListener("change", updateGenerateButtonState);
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
        const data = await r.json().catch(() => ({}));
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
      } catch (x) {
        err.textContent = String(x);
        err.style.display = "block";
      } finally {
        btn.disabled = false;
      }
    });

    function renderAlarmPreview(plan) {
      const wrap = document.getElementById("alarm-preview-wrap");
      const title = document.getElementById("alarm-preview-title");
      const body = document.getElementById("alarm-preview-body");
      if (!wrap || !title || !body || !plan) return;
      const alarms = Array.isArray(plan.alarms) ? plan.alarms : [];
      const dateText = alarmSyncDateLabel(plan.date);
      const roster = plan.roster_code ? ` / ${plan.roster_code}` : "";
      title.textContent = `將發送鬧鐘：${dateText}${roster}`;
      body.innerHTML = "";
      if (!alarms.length) {
        const tr = document.createElement("tr");
        const td = document.createElement("td");
        td.colSpan = 5;
        td.textContent = "呢日未有可同步鬧鐘";
        td.className = "alarm-preview-empty";
        tr.appendChild(td);
        body.appendChild(tr);
        applyFormColumnWidths(wrap);
        attachFormColumnResizers(wrap);
        return;
      }
      for (const alarm of alarms) {
        const t = String(alarm.trigger_at || "");
        const label = String(alarm.label || "");
        const displayTime = t.includes("T") ? t.split("T")[1].slice(0, 5) : "";
        const duration = (label.match(/(?:^|\s)(\d+)\s*$/) || [])[1] || "";
        const tr = document.createElement("tr");
        [
          plan.roster_code || "",
          displayTime,
          label,
          duration,
          alarmSyncDateLabel(plan.date),
        ].forEach((value, idx) => {
          const td = document.createElement("td");
          td.textContent = value;
          if (idx === 1) td.className = "alarm-preview-time";
          if (idx === 3) td.className = "alarm-preview-duration";
          tr.appendChild(td);
        });
        body.appendChild(tr);
      }
      applyFormColumnWidths(wrap);
      attachFormColumnResizers(wrap);
    }

    function isScheduleGridHeaderRow(row) {
      if (!Array.isArray(row) || row.length < 5) return false;
      const headers = ["更碼", "時間", "內容", "時長", "生效日期"];
      return headers.every((value, idx) => String(row[idx] || "").trim() === value);
    }

    function normalizeScheduleGridDate(value) {
      const text = String(value || "").trim();
      if (!text) return "";
      const iso = text.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
      if (iso) {
        return `${iso[1]}-${String(iso[2]).padStart(2, "0")}-${String(iso[3]).padStart(2, "0")}`;
      }
      const dmy = text.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
      if (dmy) {
        return `${dmy[3]}-${String(dmy[2]).padStart(2, "0")}-${String(dmy[1]).padStart(2, "0")}`;
      }
      return text;
    }

    function renderScheduleGridPreview(payload) {
      const wrap = document.getElementById("alarm-preview-wrap");
      const title = document.getElementById("alarm-preview-title");
      const body = document.getElementById("alarm-preview-body");
      if (!wrap || !title || !body) return;

      let rows = Array.isArray((payload || {}).rows) ? payload.rows.filter((row) => Array.isArray(row)) : [];
      if (rows.length && isScheduleGridHeaderRow(rows[0])) {
        rows = rows.slice(1);
      }

      title.textContent = "行位表內容";
      body.innerHTML = "";
      if (!rows.length) {
        const tr = document.createElement("tr");
        const td = document.createElement("td");
        td.colSpan = 5;
        td.textContent = "未有可顯示行位表資料";
        td.className = "alarm-preview-empty";
        tr.appendChild(td);
        body.appendChild(tr);
        applyFormColumnWidths(wrap);
        attachFormColumnResizers(wrap);
        return;
      }

      for (const row of rows) {
        const line = row.map((value) => String(value || "").trim());
        const dateText = line[4] ? alarmSyncDateLabel(normalizeScheduleGridDate(line[4])) : "";
        const tr = document.createElement("tr");
        [line[0], line[1], line[2], line[3], dateText].forEach((value, idx) => {
          const td = document.createElement("td");
          td.textContent = value;
          if (idx === 1) td.className = "alarm-preview-time";
          if (idx === 3) td.className = "alarm-preview-duration";
          tr.appendChild(td);
        });
        body.appendChild(tr);
      }
      applyFormColumnWidths(wrap);
      attachFormColumnResizers(wrap);
    }

    function clearAlarmSyncPreview() {
      const wrap = document.getElementById("alarm-preview-wrap");
      const title = document.getElementById("alarm-preview-title");
      const body = document.getElementById("alarm-preview-body");
      if (!wrap || !title || !body) return;
      title.textContent = "行位表內容";
      body.innerHTML = "";
      applyFormColumnWidths(wrap);
      attachFormColumnResizers(wrap);
    }

    function clearAlarmMealPlanPreview() {
      const panel = document.getElementById("alarm-meal-plan-preview");
      const title = document.getElementById("alarm-meal-plan-title");
      const content = document.getElementById("alarm-meal-plan-content");
      if (!panel || !title || !content) return;
      title.textContent = "餐單預覽";
      content.textContent = "";
      panel.style.display = "none";
    }

    function renderAlarmMealPlanTextPreview(payload) {
      const panel = document.getElementById("alarm-meal-plan-preview");
      const title = document.getElementById("alarm-meal-plan-title");
      const content = document.getElementById("alarm-meal-plan-content");
      if (!panel || !title || !content) return;

      const rawText = String(
        (payload && payload.meal_plan_text) ||
          (payload && payload.meal_plan && payload.meal_plan.text) ||
          (payload && payload.note) ||
          ""
      ).trim();
      title.textContent = `餐單預覽（${alarmSyncDateLabel(payload && payload.date)}）`;

      if (!rawText) {
        content.textContent = "未有可同步餐單內容";
        panel.style.display = "";
        return;
      }

      content.textContent = rawText;
      panel.style.display = "";
    }

    function buildAlarmSyncImportedPayload(sheetPayload, importedVersions) {
      const versionSet = Array.isArray(importedVersions)
        ? new Set(importedVersions.map((v) => String(v || "").trim()))
        : new Set();
      const rawRows = Array.isArray((sheetPayload || {}).rows)
        ? sheetPayload.rows.filter((row) => Array.isArray(row))
        : [];
      if (!rawRows.length) return { rows: [] };
      if (!versionSet.size) return { rows: rawRows };
      const hasHeader = isScheduleGridHeaderRow(rawRows[0]);
      const dataRows = hasHeader ? rawRows.slice(1) : rawRows;
      const filtered = dataRows.filter((row) => versionSet.has(
        row.length >= 5 ? normalizeScheduleGridDate(row[4]) : ""
      ));
      return { rows: hasHeader ? [rawRows[0], ...filtered] : filtered };
    }

    function alarmSyncDateLabel(iso) {
      const text = String(iso || "").trim();
      const m = text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
      if (!m) return text || "未指定日期";
      const year = Number(m[1]);
      const month = Number(m[2]);
      const day = Number(m[3]);
      if (typeof dateDmyDow === "function") return dateDmyDow(year, month, day);
      return `${String(day).padStart(2, "0")}/${String(month).padStart(2, "0")}/${year} ${dowZh(text)}`;
    }

    function autoSyncDeviceId() {
      const input = document.getElementById("auto-sync-device");
      const inputRaw = input ? String(input.value || "").trim() : "";
      if (inputRaw) {
        return inputRaw;
      }
      const stored = (window.localStorage && window.localStorage.getItem("mealplanner_auto_sync_device")) || "";
      return String(stored || "default").trim();
    }

    function syncAutoDeviceStateFromUi() {
      const input = document.getElementById("auto-sync-device");
      const serverInput = document.getElementById("auto-sync-server");
      if (!window.localStorage) return;
      if (!input && !serverInput) return;
      const stored = window.localStorage.getItem("mealplanner_auto_sync_device") || "";
      const storedServer = window.localStorage.getItem("mealplanner_auto_sync_server") || "";
      if (input) {
        if (!input.value && stored) {
          input.value = stored;
        }
        if (!input.value) {
          input.value = "default";
        }
        if (input.dataset.autoSyncBound !== "1") {
          input.dataset.autoSyncBound = "1";
          input.addEventListener("input", () => {
            if (!window.localStorage) return;
            window.localStorage.setItem("mealplanner_auto_sync_device", String(input.value || "").trim() || "default");
          });
        }
      }
      if (serverInput) {
        serverInput.value = DESKTOP_LAN_SERVER;
        if (storedServer !== DESKTOP_LAN_SERVER) {
          window.localStorage.setItem("mealplanner_auto_sync_server", DESKTOP_LAN_SERVER);
        }
        if (serverInput.dataset.autoSyncBound !== "1") {
          serverInput.dataset.autoSyncBound = "1";
          serverInput.addEventListener("input", () => {
            if (!window.localStorage) return;
            window.localStorage.setItem("mealplanner_auto_sync_server", String(serverInput.value || "").trim());
          });
        }
      }
    }

    function autoSyncServerUrl() {
      const input = document.getElementById("auto-sync-server");
      const inputRaw = input ? String(input.value || "").trim() : "";
      if (inputRaw) {
        return inputRaw;
      }
      return DESKTOP_LAN_SERVER;
    }

    function alarmSyncTargetDate() {
      if (typeof currentDateFromFocusOrViewport === "function") {
        const focused = currentDateFromFocusOrViewport();
        if (focused) return focused;
      }
      const firstDay = (memoryPayload && Array.isArray(memoryPayload.days) && memoryPayload.days[0]) || null;
      if (firstDay && firstDay.date) return firstDay.date;
      return isoFromYmd(ymdNow());
    }

    async function syncAutoServerSuggestionFromBackend() {
      const input = document.getElementById("auto-sync-server");
      if (!input) return;
      const current = String(input.value || "").trim();
      if (current === DESKTOP_LAN_SERVER) return;
      try {
        const r = await fetch("/api/network-info");
        const data = await r.json().catch(() => ({}));
        const suggested = String(data.suggested_auto_server || "").trim();
        if (!r.ok || !suggested) return;
        input.value = suggested;
        if (window.localStorage) {
          window.localStorage.setItem("mealplanner_auto_sync_server", suggested);
        }
      } catch (_) {}
    }

    async function refreshAlarmSyncServerDisplay() {
      const display = document.getElementById("alarm-sync-server-ip");
      if (!display) return;
      display.textContent = "偵測中...";
      try {
        const r = await fetch("/api/network-info");
        const data = await r.json().catch(() => ({}));
        if (!r.ok) {
          const msg = String(data.detail || data.message || "").trim();
          display.textContent = msg ? `無法取得 (${msg})` : "無法取得";
          return;
        }
        const suggested = String(data.suggested_auto_server || "").trim();
        const lanIps = Array.isArray(data.lan_ips) ? data.lan_ips : [];
        const port = Number.isFinite(Number(data.port)) ? Number(data.port) : 8765;
        if (suggested) {
          display.textContent = suggested;
          return;
        }
        display.textContent = lanIps.length
          ? `http://${lanIps[0]}:${port}`
          : "未有可用 LAN IP";
      } catch (_) {
        display.textContent = "無法取得";
      }
    }

    const previewPlanBtn = document.getElementById("alarm-sync-preview-plan");
    if (previewPlanBtn) {
      previewPlanBtn.addEventListener("click", async () => {
        const status = document.getElementById("alarm-sync-status");
        const err = document.getElementById("alarm-sync-err");
        const dateIso = alarmSyncTargetDate();
        if (status) status.textContent = "載入鬧鐘預覽中...";
        if (err) {
          err.style.display = "none";
          err.textContent = "";
        }
        previewPlanBtn.disabled = true;
        try {
          const data = await loadAlarmPlan(dateIso);
          renderAlarmPreview(data);
          renderAlarmMealPlanTextPreview(data);
          if (status) status.textContent = `已載入 ${alarmSyncDateLabel(data.date || dateIso)} 鬧鐘預覽`;
        } catch (x) {
          if (err) {
            err.textContent = String(x && x.message ? x.message : x);
            err.style.display = "block";
          }
          if (status) status.textContent = "";
        } finally {
          previewPlanBtn.disabled = false;
        }
      });
    }

    const publishPlanBtn = document.getElementById("alarm-sync-publish");
    if (publishPlanBtn) {
      publishPlanBtn.addEventListener("click", async () => {
        const status = document.getElementById("alarm-sync-status");
        const err = document.getElementById("alarm-sync-err");
        const dateIso = alarmSyncTargetDate();
        if (status) status.textContent = "發布同步資料中...";
        if (err) {
          err.style.display = "none";
          err.textContent = "";
        }
        publishPlanBtn.disabled = true;
        try {
          const data = await publishAlarmPlan(dateIso, autoSyncDeviceId(), autoSyncServerUrl());
          renderAlarmPreview(data);
          renderAlarmMealPlanTextPreview(data);
          if (status) status.textContent = `已發布：${data.sync_pull_hint || data.auto_device || "default"}`;
        } catch (x) {
          if (err) {
            err.textContent = String(x && x.message ? x.message : x);
            err.style.display = "block";
          }
          if (status) status.textContent = "";
        } finally {
          publishPlanBtn.disabled = false;
        }
      });
    }

    const usbSendBtn = document.getElementById("alarm-sync-send-usb");
    if (usbSendBtn) {
      usbSendBtn.addEventListener("click", async () => {
        const status = document.getElementById("alarm-sync-status");
        const err = document.getElementById("alarm-sync-err");
        const dateIso = alarmSyncTargetDate();
        if (status) status.textContent = "USB 發送中...";
        if (err) {
          err.style.display = "none";
          err.textContent = "";
        }
        usbSendBtn.disabled = true;
        try {
          const data = await sendAlarmPlanUsb(dateIso);
          renderAlarmPreview(data);
          renderAlarmMealPlanTextPreview(data);
          if (status) status.textContent = `已發送到 USB 裝置 ${data.adb_serial || ""}`.trim();
        } catch (x) {
          if (err) {
            err.textContent = String(x && x.message ? x.message : x);
            err.style.display = "block";
          }
          if (status) status.textContent = "";
        } finally {
          usbSendBtn.disabled = false;
        }
      });
    }

    const xmlImportBtn = document.getElementById("alarm-sync-import-xml");
    if (xmlImportBtn) {
      xmlImportBtn.addEventListener("click", async () => {
        const status = document.getElementById("alarm-sync-status");
        const err = document.getElementById("alarm-sync-err");
        const confirmBtn = document.getElementById("alarm-sync-confirm-import");
        if (status) status.textContent = "";
        if (err) {
          err.style.display = "none";
          err.textContent = "";
        }
        if (confirmBtn) confirmBtn.style.display = "none";
        xmlImportBtn.disabled = true;
        try {
          const data = await importScheduleGridFromAdbPhone();
          const importedRows = Number.isFinite(Number(data.row_count)) ? Number(data.row_count) : null;
          const phoneUrl = String(data.phone_url || "").trim();
          if (status) {
            const prefix = phoneUrl ? `已從電話 ${phoneUrl} 載入：` : "已從電話載入：";
            status.textContent = importedRows === null
              ? `${prefix}請檢查列表，確認後按 confirm`
              : `${prefix}${importedRows} 行；確認後按 confirm 更新行位表`;
          }
          renderScheduleGridPreview(data);
          if (confirmBtn) confirmBtn.style.display = "";
        } catch (x) {
          if (err) {
            err.textContent = String(x && x.message ? x.message : x);
            err.style.display = "block";
          }
          if (status) status.textContent = "";
        } finally {
          xmlImportBtn.disabled = false;
        }
      });
    }

    const confirmImportBtn = document.getElementById("alarm-sync-confirm-import");
    if (confirmImportBtn) {
      confirmImportBtn.addEventListener("click", async () => {
        const status = document.getElementById("alarm-sync-status");
        const err = document.getElementById("alarm-sync-err");
        if (status) status.textContent = "更新行位表中...";
        if (err) {
          err.style.display = "none";
          err.textContent = "";
        }
        confirmImportBtn.disabled = true;
        try {
          const data = await confirmScheduleGridFromPhoneIp();
          const importedRows = Number.isFinite(Number(data.imported_row_count)) ? Number(data.imported_row_count) : null;
          const replacedRows = Number.isFinite(Number(data.replaced_row_count)) ? Number(data.replaced_row_count) : null;
          if (status) {
            status.textContent = importedRows === null || replacedRows === null
              ? "已更新行位表"
              : `已更新行位表：${importedRows} 行；取代舊版：${replacedRows} 行`;
          }
          confirmImportBtn.style.display = "none";
          try {
            const sheetPayload = await loadMaintSheet("schedule_grid");
            const importedVersions = Array.isArray(data.imported_versions) ? data.imported_versions : [];
            renderScheduleGridPreview(buildAlarmSyncImportedPayload(sheetPayload, importedVersions));
          } catch (x) {
            if (status) {
              status.textContent = `${status.textContent}；未能列出行位表：${String(x && x.message ? x.message : x)}`;
            }
          }
        } catch (x) {
          if (err) {
            err.textContent = String(x && x.message ? x.message : x);
            err.style.display = "block";
          }
          if (status) status.textContent = "";
        } finally {
          confirmImportBtn.disabled = false;
        }
      });
    }

    document.getElementById("show_past").addEventListener("change", async (ev) => {
      showPast = !!ev.target.checked;
      const anchor = captureViewportAnchor();
      renderFromMemory(anchor);
      await persistColumnWidths();
    });
    document.addEventListener("input", (ev) => {
      const area = editableAreaName(ev.target);
      if (area) {
        if (ev.target && ev.target.dataset) ev.target.dataset.autosaveDirty = "1";
        setUnsavedChanges(area);
      }
    });
    document.addEventListener("change", (ev) => {
      const area = editableAreaName(ev.target);
      if (area) {
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
      await openConfigChild("targets");
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
    document.getElementById("menu-shopping").addEventListener("click", async () => {
      if (!(await resolveUnsavedBeforeLeaving())) return;
      setActiveMenuPathForKey("shopping");
      setActivePanel("shopping");
      seedShoppingDateRange();
      if (!Object.keys(shoppingCatalogByName).length) loadShoppingCatalog();
    });
    document.getElementById("menu-alarm-sync").addEventListener("click", openAlarmSyncPanel);
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
    const maintImport = document.getElementById("maint-import");
    if (maintImport) maintImport.addEventListener("click", importActiveMaintSheet);
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
    document.getElementById("catalog-filter").addEventListener("input", applyCatalogFilter);
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
    });
    document.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape") hideCatalogRowMenu();
      if (ev.key === "Escape") hideMaintRowMenu();
      if (ev.key === "Escape") hideDetailRowMenu();
    });
    document.getElementById("catalog-editor").addEventListener("scroll", hideCatalogRowMenu);
    document.getElementById("maint-editor").addEventListener("scroll", hideMaintRowMenu);
    document.querySelector(".detail-editor")?.addEventListener("scroll", hideDetailRowMenu);
    document.addEventListener("keydown", (ev) => {
      if ((ev.ctrlKey || ev.metaKey) && !ev.altKey && String(ev.key).toLowerCase() === "s") {
        ev.preventDefault();
        saveActiveEditor();
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

    (async function bootUi() {
      await loadUiState();
      applyMenuOrder();
      applyMenuTreeOpen();
      attachMenuDragHandles();
      await loadMemoryPayload();
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
      if (activePanel === "config") applyActiveConfigView(false);
      if (activePanel === "maint" && activeMaintSheetKey) {
        try {
          await openMaintSheet(activeMaintSheetKey, false);
        } catch (_) {
          if (maintSheets.length) await openMaintSheet(maintSheets[0].sheet_key, false);
        }
      }
      if (activePanel === "alarm_sync") await openAlarmSyncPanel();
      applyTableOffsets();
      attachTableDragHandles();
      applyFormColumnWidths();
      attachFormColumnResizers();
      applyMenuOrder();
      applyMenuTreeOpen();
      attachMenuDragHandles();
      applySidebarWidth();
      attachSidebarResizer();
      window.addEventListener("resize", syncPanelGutter);
      startTopRightClock();
    })();

    // Auto format 4-digit time on blur. Saving is explicit via Save, Ctrl+S, or the unsaved-change prompt.
    document.addEventListener("focusout", (ev) => {
      const el = ev.target;
      if (!el || (el.tagName !== "INPUT" && el.tagName !== "TEXTAREA" && el.tagName !== "SELECT")) return;
      if (el.closest && el.closest(".maint-filter-select")) return;

      if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") {
        const val = el.value.trim();
        if (/^\d{4}$/.test(val)) {
          const h = Number(val.slice(0, 2));
          const m = Number(val.slice(2, 4));
          if (h >= 0 && h <= 23 && m >= 0 && m <= 59) {
            el.value = `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
            el.dispatchEvent(new Event("input", { bubbles: true }));
          }
        }
      }

      if (el.dataset) delete el.dataset.skipAutosaveOnce;
    });
