    function emptyNutCells(headers) {
      const n = (headers && headers.length) || 10;
      return Array.from({ length: n }, () => '<td class="nut">—</td>').join("");
    }

    const TOOLTIP_TRADITIONAL_CHAR_MAP = {
      嘱: "囑",
      议: "議",
      现: "現",
      纤: "纖",
      维: "維",
      质: "質",
      总: "總",
      胆: "膽",
      钠: "鈉",
      钙: "鈣",
      饱: "飽",
      转: "轉",
      体: "體",
      营: "營",
      养: "養",
      标: "標",
      设: "設",
      调: "調",
      剂: "劑",
      围: "圍",
      类: "類",
      龄: "齡",
      历: "歷",
      录: "錄",
      显: "顯",
      隐: "隱",
      删: "刪",
      选: "選",
      项: "項",
      输: "輸",
      览: "覽",
      预: "預",
      时: "時",
      间: "間",
      应: "應",
      义: "義",
      页: "頁",
      态: "態",
      错: "錯",
      认: "認",
      写: "寫",
      读: "讀",
      为: "為",
      与: "與",
      后: "後",
      发: "發",
      动: "動",
      运: "運",
      较: "較",
      轻: "輕",
      区: "區",
      权: "權",
      开: "開",
      关: "關",
      双: "雙",
      击: "擊",
      栏: "欄",
      宽: "寬",
      线: "線",
      图: "圖",
      复: "復",
      盘: "盤",
      师: "師",
      径: "徑",
      备: "備",
      导: "導",
      约: "約",
      强: "強",
      数: "數",
      据: "據",
      库: "庫",
    };

    function traditionalTooltipText(text) {
      return String(text || "").replace(/[嘱议现纤维质总胆钠钙饱转体营养标设调剂围类龄历录显隐删选项输览预时间应义页态错认写读为与后发动运较轻区权开关双击栏宽线图复盘师径备导约强数据库]/g, (ch) => TOOLTIP_TRADITIONAL_CHAR_MAP[ch] || ch);
    }

    let targetSelectedBlocks = new Set();
    let targetBlockSuppressNextClickClear = false;
    let targetSavedSnapshot = "";
    const TARGET_SETTING_DEFAULTS = {
      workday: {
        activity_factor: 1.35,
        calorie_range_band: 50,
        protein_g_per_kg: 1.75,
        protein_range_band: 10,
        carb_pct: 45,
        calcium_mg: 1200,
        sodium_mg: 2000,
        sugar_g: 35,
        cholesterol_mg: 200,
        fat_total_pct: 27.5,
        fat_sat_pct: 7,
        fat_trans_pct: 1,
      },
      nonworkday: {
        activity_factor: 1.2,
        calorie_range_band: 50,
        protein_g_per_kg: 1.75,
        protein_range_band: 10,
        carb_pct: 45,
        calcium_mg: 1000,
        sodium_mg: 1700,
        sugar_g: 50,
        cholesterol_mg: 200,
        fat_total_pct: 27.5,
        fat_sat_pct: 7,
        fat_trans_pct: 1,
      },
    };
    const TARGET_SETTING_ROWS = [
      { key: "activity_factor", label: "活動量<br>activity factor", text: "活動量 activity factor", guide: "活動量係用嚟由 BMR 推算 TDEE：TDEE = BMR * activity factor。佢唔係由身高體重直接計，而係按每日活動強度揀估算值再手動調整。常見參考：1.2 久坐/少活動；1.35 輕量活動；1.55 中等活動；1.725 高活動。現時預設：返工 1.35；非返工 1.20" },
      { key: "calorie_range_band", label: "卡路里<br>calorie range band", text: "卡路里 range band", guide: "建議：50 kcal" },
      { key: "protein_g_per_kg", label: "蛋白質<br>protein g/kg", text: "蛋白質 g/kg", guide: "建議：最低需要約 0.8 g/kg/day；一般保肌/日常活動約 1.2；返工活動多、運動或減脂保肌可用 1.6；認真重訓增肌約 1.6-2.0。現時預設：返工 1.6；非返工 1.2。腎病或醫生要求限制蛋白質時要跟醫囑", nutrient: "protein_g" },
      { key: "protein_range_band", label: "蛋白質範圍<br>protein range band", text: "蛋白質 range band", guide: "建議：10g；蛋白質 = 中位 ± range band", nutrient: "protein_g" },
      { key: "carb_pct", label: "碳水<br>carb % kcal", text: "碳水 % kcal", guide: "AMDR 建議範圍係總熱量 45-65%。45%：低端。較少運動、想留多啲熱量俾蛋白質/脂肪、或想控制飽腹感/血糖波動時用。50-55%：中間位。一般日常活動、冇特別訓練目標時較中性。60-65%：高端。高活動量、耐力運動、工作日消耗大，或者你主要靠全穀、豆類、水果蔬菜等高質碳水補能量時先用。WHO 2023 重點係碳水來源質素：全穀、蔬菜、水果、豆類同足夠膳食纖維。現時預設 45%。", nutrient: "carb_g" },
      { key: "sugar_g", label: "天然糖<br>natural sugar g", text: "天然糖 g", guide: "無 guideline；自訂", nutrient: "sugar_g" },
      { key: "cholesterol_mg", label: "膽固醇<br>cholesterol mg", text: "膽固醇 mg", guide: "無固定 guideline；自訂", nutrient: "cholesterol_mg" },
      { key: "sodium_mg", label: "鈉<br>sodium mg", text: "鈉 mg", guide: "14歲以上 guideline <2300", nutrient: "sodium_mg" },
      { key: "calcium_mg", label: "鈣<br>calcium mg", text: "鈣 mg", guide: "男19-70 >=1000；51+ 可用 >=1200", nutrient: "calcium_mg" },
      { key: "fat_total_pct", label: "總脂肪<br>total fat % kcal", text: "總脂肪 % kcal", guide: "guideline 20-35%", nutrient: "fat_total_g" },
      { key: "fat_sat_pct", label: "飽和脂肪<br>saturated fat % kcal", text: "飽和脂肪 % kcal", guide: "guideline <10%", nutrient: "fat_sat_g" },
      { key: "fat_trans_pct", label: "反式脂肪<br>trans fat % kcal", text: "反式脂肪 % kcal", guide: "越低越好", nutrient: "fat_trans_g" },
    ];
    const TARGET_NUTRIENT_HEADER_HTML = {
      kcal: "卡路里<br>calories kCal",
      protein_g: "蛋白質<br>protein g",
      carb_g: "碳水<br>carbs g",
      sugar_g: "天然糖<br>natural sugar g",
      cholesterol_mg: "膽固醇<br>cholesterol mg",
      sodium_mg: "鈉<br>sodium mg",
      calcium_mg: "鈣<br>calcium mg",
      fat_total_g: "總脂肪<br>total fat g",
      fat_sat_g: "飽和脂肪<br>saturated fat g",
      fat_trans_g: "反式脂肪<br>trans fat g",
    };

    function fmtNut(v) {
      if (v == null) return "—";
      const n = Number(v);
      if (!Number.isFinite(n)) return "—";
      return n.toFixed(1);
    }

    function nutCellsFromValues(values, rowStyle = "", redFlags = []) {
      const arr = Array.isArray(values) ? values : [];
      return arr.map((v, i) => {
        const isRed = Array.isArray(redFlags) && !!redFlags[i];
        const styleParts = [];
        if (rowStyle) styleParts.push(rowStyle);
        if (isRed) styleParts.push("color:#ff0000 !important;");
        const attr = styleParts.length ? ` style="${styleParts.join("")}"` : "";
        return `<td class="nut"${attr}>${esc(fmtNut(v))}</td>`;
      }).join("");
    }

    function nutHeaderCells(headers, cellStyle = "") {
      const h = headers && headers.length ? headers : Array(10).fill("—");
      const attr = cellStyle ? ` style="${cellStyle}"` : "";
      return h.map((x) => `<td class="nut nut-h"${attr}>${esc(x || "—")}</td>`).join("");
    }

    function nutTextCells(values, cellStyle = "") {
      const arr = Array.isArray(values) ? values : [];
      const attr = cellStyle ? ` style="${cellStyle}"` : "";
      return arr.map((v) => `<td class="nut"${attr}>${esc(v ?? "")}</td>`).join("");
    }

    function nutTargetInputCells(profile, values, cellStyle = "") {
      const arr = Array.isArray(values) ? values : [];
      const attr = cellStyle ? ` style="${cellStyle}"` : "";
      return arr.map((v, i) => `<td class="nut"${attr}><input class="target-inline-input" data-target-source="planner" data-target-profile="${esc(profile)}" data-target-index="${i}" value="${esc(v ?? "")}" /></td>`).join("");
    }

    function targetNutrientHeaderHtml(key, fallback) {
      return TARGET_NUTRIENT_HEADER_HTML[key] || esc(fallback || key || "");
    }

    const TARGET_GRID_INPUT_SELECTOR = 'input[data-target-source]:not([data-target-source="preview"]), input[data-target-setting-key]';
    const targetDirectKeyTimers = new WeakMap();

    function isTargetGridInput(input) {
      return !!(input && input.matches && input.matches(TARGET_GRID_INPUT_SELECTOR));
    }

    function targetGridInputsInRow(row) {
      return Array.from(row?.querySelectorAll(TARGET_GRID_INPUT_SELECTOR) || [])
        .filter((input) => !input.disabled && input.type !== "hidden");
    }

    function targetCellInputFrom(input, rowDelta, colDelta) {
      const row = input?.closest("tr");
      const table = input?.closest("table");
      if (!row || !table) return null;
      const currentRowInputs = targetGridInputsInRow(row);
      const colIdx = currentRowInputs.indexOf(input);
      if (colIdx < 0) return null;
      const rows = Array.from(table.querySelectorAll("tbody tr"));
      const rowIdx = rows.indexOf(row);
      const targetColIdx = colIdx + colDelta;
      if (rowDelta === 0) return currentRowInputs[targetColIdx] || null;
      const step = rowDelta > 0 ? 1 : -1;
      let remainingRows = Math.abs(rowDelta);
      for (let i = rowIdx + step; i >= 0 && i < rows.length; i += step) {
        const rowInputs = targetGridInputsInRow(rows[i]);
        if (!rowInputs.length) continue;
        remainingRows -= 1;
        if (remainingRows > 0) continue;
        return rowInputs[targetColIdx] || rowInputs[rowInputs.length - 1] || null;
      }
      return null;
    }

    function focusTargetCell(input) {
      if (!input) return;
      input.focus({ preventScroll: true });
      input.scrollIntoView({ block: "nearest", inline: "nearest" });
    }

    function focusTargetEditable(input) {
      if (!input) return;
      if (input.tagName === "SELECT") {
        const button = input.closest(".pickup-select")?.querySelector(".pickup-select-button");
        if (button) {
          button.focus({ preventScroll: true });
          button.scrollIntoView({ block: "nearest", inline: "nearest" });
          return;
        }
      }
      input.focus({ preventScroll: true });
      if (typeof input.select === "function") input.select();
      input.scrollIntoView({ block: "nearest", inline: "nearest" });
    }

    function focusTargetDob() {
      const dob = document.getElementById("target-profile-dob");
      if (dob) focusTargetEditable(dob);
    }

    function targetVisibleEditableForTab(el) {
      if (!el || el.disabled || el.type === "hidden") return null;
      if (el.readOnly && !el.hasAttribute("data-target-setting-key")) return null;
      if (el.tagName === "SELECT") {
        return el.closest(".pickup-select")?.querySelector(".pickup-select-button") || el;
      }
      return el;
    }

    function applyTargetConfigTabIndexes() {
      const root = document.querySelector(".target-config-blocks");
      if (!root) return;
      const order = targetConfigTabOrder();
      const ordered = new Set(order);
      root.querySelectorAll("input,select,textarea,button").forEach((el) => {
        const visible = targetVisibleEditableForTab(el);
        const target = visible && ordered.has(visible) ? visible : el;
        target.tabIndex = ordered.has(target) ? 0 : -1;
      });
      order.forEach((el) => {
        el.tabIndex = 0;
      });
    }

    function targetConfigTabOrder() {
      const profile = [
        document.getElementById("target-profile-dob"),
        document.getElementById("target-profile-gender"),
        document.getElementById("target-profile-height"),
        document.getElementById("target-profile-weight"),
        document.getElementById("target-profile-weight-change"),
      ];
      const settings = Array.from(document.querySelectorAll("#target-calc-settings input[data-target-setting-key]"));
      const weightHistory = Array.from(document.querySelectorAll("#target-weight-history input[data-weight-history-field]"));
      const seen = new Set();
      return [...profile, ...settings, ...weightHistory]
        .map(targetVisibleEditableForTab)
        .filter((item) => item && !seen.has(item) && seen.add(item));
    }

    function targetConfigControlFromEventTarget(target) {
      if (!target || !target.closest) return null;
      const pickup = target.closest(".pickup-select");
      if (pickup) {
        const select = pickup.querySelector("select");
        return targetVisibleEditableForTab(select) || target.closest("button,input,select,textarea");
      }
      return target.closest("input,select,textarea,button");
    }

    function bindTargetConfigTabOrder() {
      const root = document.querySelector(".target-config-blocks");
      if (!root || root.dataset.targetTabOrderBound === "1") return;
      root.dataset.targetTabOrderBound = "1";
      root.addEventListener("keydown", (ev) => {
        if (ev.key !== "Tab" || ev.ctrlKey || ev.altKey || ev.metaKey || ev.isComposing) return;
        const current = targetConfigControlFromEventTarget(ev.target);
        if (!current) return;
        const order = targetConfigTabOrder();
        applyTargetConfigTabIndexes();
        const idx = order.indexOf(current);
        if (idx < 0) return;
        const next = ev.shiftKey
          ? (order[idx - 1] || order[order.length - 1])
          : (order[idx + 1] || order[0]);
        if (!next) return;
        ev.preventDefault();
        focusTargetEditable(next);
      });
    }

    function nextTargetConfigOrderedCell(input, reverse = false) {
      const current = targetConfigControlFromEventTarget(input);
      if (!current) return null;
      const order = targetConfigTabOrder();
      const idx = order.indexOf(current);
      if (idx < 0) return null;
      return reverse ? (order[idx - 1] || order[order.length - 1] || null) : (order[idx + 1] || order[0] || null);
    }

    function normalizeTargetCellValue(input) {
      if (!input || !input.hasAttribute("data-target-setting-key")) return;
      const text = String(input.value || "").trim();
      input.value = text ? targetSettingInputValue(text) : "";
    }

    function markTargetCellChanged(input) {
      if (!input) return;
      markTargetDirtyIfChanged();
      if (input.hasAttribute("data-target-setting-key")) {
        renderTargetPreviewTable();
      }
    }

    function beginTargetCellEdit(input, replaceValue = false) {
      if (!isTargetGridInput(input)) return;
      input.dataset.targetOriginalValue = input.value;
      input.readOnly = false;
      input.dataset.targetEditing = "1";
      input.dataset.targetReplaceOnComposition = replaceValue ? "1" : "";
      input.focus({ preventScroll: true });
      if (replaceValue) input.value = "";
      const pos = replaceValue ? 0 : String(input.value || "").length;
      if (typeof input.setSelectionRange === "function") input.setSelectionRange(pos, pos);
    }

    function clearTargetDirectKeyTimer(input) {
      const timer = targetDirectKeyTimers.get(input);
      if (timer) clearTimeout(timer);
      targetDirectKeyTimers.delete(input);
    }

    function queueTargetDirectKey(input, key) {
      if (!input || !key) return;
      clearTargetDirectKeyTimer(input);
      input.dataset.targetPendingDirectKey = key;
      const timer = setTimeout(() => {
        targetDirectKeyTimers.delete(input);
        if (input.dataset.targetEditing !== "1" || input.dataset.targetPendingDirectKey !== key) return;
        input.value = `${key}${input.value || ""}`;
        delete input.dataset.targetPendingDirectKey;
        delete input.dataset.targetReplaceOnComposition;
        const pos = String(input.value || "").length;
        if (typeof input.setSelectionRange === "function") input.setSelectionRange(pos, pos);
        input.dispatchEvent(new Event("input", { bubbles: true }));
      }, 40);
      targetDirectKeyTimers.set(input, timer);
    }

    function endTargetCellEdit(input, options = {}) {
      if (!isTargetGridInput(input)) return;
      if (input.dataset.targetEditing !== "1") return;
      const oldValue = input.dataset.targetOriginalValue || "";
      if (options.cancel) {
        input.value = oldValue;
      } else {
        normalizeTargetCellValue(input);
      }
      input.readOnly = true;
      delete input.dataset.targetEditing;
      delete input.dataset.targetOriginalValue;
      delete input.dataset.targetReplaceOnComposition;
      delete input.dataset.targetPendingDirectKey;
      clearTargetDirectKeyTimer(input);
      if (!options.cancel && input.value !== oldValue) markTargetCellChanged(input);
    }

    function moveTargetActiveCell(input, key) {
      const delta = {
        ArrowUp: [-1, 0],
        ArrowDown: [1, 0],
        ArrowLeft: [0, -1],
        ArrowRight: [0, 1],
        Enter: [0, 1],
      }[key];
      if (!delta) return false;
      const next = targetCellInputFrom(input, delta[0], delta[1]);
      const fallback = key === "Enter" ? nextTargetConfigOrderedCell(input) : null;
      const target = next || fallback;
      if (!target) return false;
      focusTargetEditable(target);
      return true;
    }

    function targetInputClipboardValue(input) {
      return input ? input.value : "";
    }

    function pasteTargetInputValue(input, value) {
      if (!isTargetGridInput(input)) return;
      const oldValue = input.value;
      input.value = value;
      normalizeTargetCellValue(input);
      input.readOnly = true;
      if (input.value !== oldValue) markTargetCellChanged(input);
    }

    function targetClipboardMatrix(text) {
      return String(text || "")
        .replace(/\r/g, "")
        .replace(/\n$/, "")
        .split("\n")
        .map((line) => line.split("\t"));
    }

    function pasteTargetClipboard(startInput, text) {
      const matrix = targetClipboardMatrix(text);
      if (!matrix.length) return;
      let lastInput = startInput;
      matrix.forEach((values, rowIdx) => {
        values.forEach((value, colIdx) => {
          const input = targetCellInputFrom(startInput, rowIdx, colIdx);
          if (!input) return;
          pasteTargetInputValue(input, value);
          lastInput = input;
        });
      });
      focusTargetCell(lastInput);
    }

    function bindTargetEnterMoveRight(root) {
      root.querySelectorAll("input,select,textarea").forEach((input) => {
        if (input.dataset.targetEnterMoveBound === "1") return;
        input.dataset.targetEnterMoveBound = "1";
        if (isTargetGridInput(input)) {
          input.readOnly = true;
          input.addEventListener("focusout", () => endTargetCellEdit(input));
          input.addEventListener("keydown", (ev) => {
            if (input.dataset.targetEditing === "1") {
              if (ev.key === "Escape" || ev.key === "Enter" || ev.key === "ArrowUp" || ev.key === "ArrowDown") {
                ev.preventDefault();
                const next = ev.key === "Enter"
                  ? targetCellInputFrom(input, 0, 1)
                  : (ev.key === "ArrowUp" || ev.key === "ArrowDown" ? targetCellInputFrom(input, ev.key === "ArrowUp" ? -1 : 1, 0) : null);
                const fallback = ev.key === "Enter" ? nextTargetConfigOrderedCell(input) : null;
                endTargetCellEdit(input, { cancel: ev.key === "Escape" });
                focusTargetEditable(next || fallback || input);
              }
              return;
            }
            if (moveTargetActiveCell(input, ev.key)) {
              ev.preventDefault();
              return;
            }
            if (ev.key === "F2") {
              ev.preventDefault();
              beginTargetCellEdit(input);
              return;
            }
            if (ev.key === "Process" && !ev.ctrlKey && !ev.altKey && !ev.metaKey) {
              beginTargetCellEdit(input, true);
              return;
            }
            if (ev.key.length === 1 && !ev.ctrlKey && !ev.altKey && !ev.metaKey) {
              beginTargetCellEdit(input, true);
            }
          });
          input.addEventListener("dblclick", () => beginTargetCellEdit(input));
          input.addEventListener("compositionstart", () => {
            if (input.readOnly) beginTargetCellEdit(input, true);
            clearTargetDirectKeyTimer(input);
            delete input.dataset.targetPendingDirectKey;
            delete input.dataset.targetReplaceOnComposition;
          });
          input.addEventListener("copy", (ev) => {
            if (input.dataset.targetEditing === "1" || !ev.clipboardData) return;
            ev.preventDefault();
            ev.clipboardData.setData("text/plain", targetInputClipboardValue(input));
          });
          input.addEventListener("paste", (ev) => {
            if (input.dataset.targetEditing === "1" || !ev.clipboardData) return;
            ev.preventDefault();
            pasteTargetClipboard(input, ev.clipboardData.getData("text/plain"));
          });
          return;
        }
        input.addEventListener("keydown", (ev) => {
          if (ev.shiftKey || ev.ctrlKey || ev.altKey || ev.metaKey || ev.isComposing) return;
          if (ev.key === "Enter") {
            ev.preventDefault();
            const row = input.closest("tr");
            const inputs = Array.from(row?.querySelectorAll("input,select,textarea") || [])
              .filter((item) => !item.disabled && !item.readOnly && item.type !== "hidden");
            const next = inputs[inputs.indexOf(input) + 1];
            focusTargetEditable(next || nextTargetConfigOrderedCell(input) || input);
          }
        });
      });
    }

    function renderTargetEditorTable(editorId, data, inputSource) {
      const editor = document.getElementById(editorId);
      if (!editor) return;
      const headers = Array.isArray(data && data.headers) ? data.headers : [];
      const keys = Array.isArray(data && data.nutrient_keys) ? data.nutrient_keys : [];
      const rows = data && typeof data.indicator_rows === "object" && data.indicator_rows ? data.indicator_rows : {};
      const workday = Array.isArray(rows.workday) ? rows.workday : [];
      const nonworkday = Array.isArray(rows.nonworkday) ? rows.nonworkday : [];
      if (inputSource !== "preview") {
        targetPayload = {
          headers,
          nutrient_keys: keys,
          indicator_rows: { workday, nonworkday },
          profile: targetPayload.profile || {},
          target_settings: targetPayload.target_settings || cloneTargetSettingDefaults(),
        };
      }
      const n = Math.max(headers.length, keys.length, workday.length, nonworkday.length);
      const profileWidthKey = "target_profile";
      const nutrientWidthKey = "target_nutrient_value";
      const nutrientKey = (idx) => keys[idx] || `target_${idx}`;
      const headingCells = Array.from({ length: n }, (_, i) => {
        const key = nutrientKey(i);
        const title = inputSource === "preview" ? previewHeaderTooltip(key) : "Drag to resize column";
        return `<th data-target-col-key="${esc(nutrientWidthKey)}" title="${esc(traditionalTooltipText(title))}">${targetNutrientHeaderHtml(key, headers[i] || keys[i] || `Target ${i + 1}`)}<span class="target-col-resizer" title="Drag to resize column"></span></th>`;
      }).join("");
      const colCells = Array.from({ length: n }, (_, i) =>
        `<col data-target-col-key="${esc(nutrientWidthKey)}" />`
      ).join("");
      const rowCells = (profile, values) => Array.from({ length: n }, (_, i) =>
        `<td><input data-target-source="${esc(inputSource)}" data-target-profile="${esc(profile)}" data-target-index="${i}" value="${esc(values[i] ?? "")}" /></td>`
      ).join("");
      editor.innerHTML = `<table class="target-table">
        <colgroup><col class="target-profile-col" data-target-col-key="${esc(profileWidthKey)}" />${colCells}</colgroup>
        <thead><tr><th class="target-profile-head" data-target-col-key="${esc(profileWidthKey)}" title="Drag to resize column">目標<br>Target<span class="target-col-resizer" title="Drag to resize column"></span></th>${headingCells}</tr></thead>
        <tbody>
          <tr><th scope="row" class="target-profile-head">返工日<br>Workday</th>${rowCells("workday", workday)}</tr>
          <tr><th scope="row" class="target-profile-head">非返工日<br>Non-workday</th>${rowCells("nonworkday", nonworkday)}</tr>
        </tbody>
      </table>`;
      applyTargetEditorLayout();
      attachTargetEditorResizers();
      applyTableOffsets(editor);
      attachTableDragHandles();
      bindTargetEnterMoveRight(editor);
    }

    function renderTargetEditors(data) {
      const headers = Array.isArray(data && data.headers) ? data.headers : [];
      const keys = Array.isArray(data && data.nutrient_keys) ? data.nutrient_keys : [];
      const rows = data && typeof data.indicator_rows === "object" && data.indicator_rows ? data.indicator_rows : {};
      targetPayload = {
        headers,
        nutrient_keys: keys,
        indicator_rows: {
          workday: Array.isArray(rows.workday) ? rows.workday : [],
          nonworkday: Array.isArray(rows.nonworkday) ? rows.nonworkday : [],
        },
        profile: targetPayload.profile || {},
        target_settings: targetPayload.target_settings || cloneTargetSettingDefaults(),
      };
      fillTargetProfile(data && data.profile);
      renderTargetCalculationSettings(data && data.target_settings);
      renderTargetEditorTable("target-editor", data, "config");
      renderTargetPreviewTable();
      bindTargetApplyButton();
      bindTargetConfigTabOrder();
      applyTargetConfigTabIndexes();
      const targetBlocks = document.querySelector(".target-config-blocks");
      if (targetBlocks) attachFormColumnResizers(targetBlocks);
      applyTargetBlockLayout();
      attachTargetBlockDragHandles();
      setTimeout(applyTargetBlockLayout, 0);
      setTimeout(applyTargetBlockLayout, 100);
      resetTargetDirtySnapshot();
    }

    function cloneTargetSettingDefaults() {
      return {
        workday: { ...TARGET_SETTING_DEFAULTS.workday },
        nonworkday: { ...TARGET_SETTING_DEFAULTS.nonworkday },
      };
    }

    function normalizedTargetSettings(raw) {
      const out = cloneTargetSettingDefaults();
      const source = raw && typeof raw === "object" ? raw : {};
      ["workday", "nonworkday"].forEach((profile) => {
        const values = source[profile] && typeof source[profile] === "object" ? source[profile] : {};
        TARGET_SETTING_ROWS.forEach(({ key }) => {
          const n = Number(values[key]);
          if (Number.isFinite(n) && n >= 0) out[profile][key] = n;
        });
      });
      return out;
    }

    function targetSettingInputValue(value) {
      const n = Number(value);
      if (!Number.isFinite(n)) return "";
      return Number.isInteger(n) ? String(n) : String(Number(n.toFixed(3)));
    }

    function currentTargetIndicatorFor(nutrientKey, profile) {
      const keys = Array.isArray(targetPayload.nutrient_keys) ? targetPayload.nutrient_keys : [];
      const idx = keys.indexOf(nutrientKey);
      if (idx < 0) return "";
      const rows = targetPayload.indicator_rows && typeof targetPayload.indicator_rows === "object"
        ? targetPayload.indicator_rows
        : {};
      const values = Array.isArray(rows[profile]) ? rows[profile] : [];
      return String(values[idx] ?? "").trim();
    }

    function numericRangeFromTargetText(text) {
      const values = String(text || "").match(/\d+(?:\.\d+)?/g);
      if (!values || !values.length) return null;
      const lo = Number(values[0]);
      const hi = Number(values.length > 1 ? values[1] : values[0]);
      if (!Number.isFinite(lo) || !Number.isFinite(hi)) return null;
      return { lo, hi };
    }

    function macroPctFromTargetIndicators(macroText, kcalText, kcalPerUnit) {
      const macro = numericRangeFromTargetText(macroText);
      const kcal = numericRangeFromTargetText(kcalText);
      const factor = Number(kcalPerUnit);
      if (!macro || !kcal || !Number.isFinite(factor) || factor <= 0 || kcal.lo <= 0 || kcal.hi <= 0) {
        return "";
      }
      const lo = Math.round((macro.lo * factor / kcal.lo) * 100);
      const hi = Math.round((macro.hi * factor / kcal.hi) * 100);
      return lo === hi ? `${lo}%` : `${lo}-${hi}%`;
    }

    function currentTargetSettingValueFor(row, profile) {
      if (!row || !row.nutrient) return "";
      if (row.key === "carb_pct") {
        return macroPctFromTargetIndicators(
          currentTargetIndicatorFor("carb_g", profile),
          currentTargetIndicatorFor("kcal", profile),
          4
        );
      }
      return currentTargetIndicatorFor(row.nutrient, profile);
    }

    function targetSettingTooltip(row) {
      const base = String(row && row.guide ? row.guide : "").trim();
      if (!row || !row.nutrient) return base;
      const workday = currentTargetSettingValueFor(row, "workday");
      const nonworkday = currentTargetSettingValueFor(row, "nonworkday");
      const current = `現用：返工 ${workday || "-"}；非返工 ${nonworkday || "-"}`;
      return base ? `${base}；${current}` : current;
    }

    function targetReadonlyKcal(value) {
      if (value == null || value === "") return "";
      const n = Number(value);
      return Number.isFinite(n) ? String(Math.round(n)) : "";
    }

    function targetProteinMid(profile, values) {
      const weight = Number(profile.weight_kg);
      const gPerKg = Number(values && values.protein_g_per_kg);
      if (!Number.isFinite(weight) || !Number.isFinite(gPerKg) || weight <= 0 || gPerKg < 0) return null;
      return weight * gPerKg;
    }

    function targetCalculationReadonlyValue(profileKey, metric, settings) {
      const profile = currentTargetProfileFromInputs();
      const values = settings && settings[profileKey] ? settings[profileKey] : {};
      if (metric === "protein_mid") return targetReadonlyKcal(targetProteinMid(profile, values));
      const bmr = targetBmr(profile);
      if (bmr == null) return "";
      if (metric === "bmr") return targetReadonlyKcal(bmr);
      if (metric === "tdee") {
        const activity = Number(values.activity_factor);
        return Number.isFinite(activity) ? targetReadonlyKcal(bmr * activity) : "";
      }
      if (metric === "calorie_offset") {
        return targetReadonlyKcal(targetDailyCalorieOffset(profile));
      }
      return "";
    }

    function updateTargetCalculationReadonlyValues() {
      const settings = collectTargetSettings();
      document.querySelectorAll("[data-target-calc-readonly-profile][data-target-calc-readonly-metric]").forEach((cell) => {
        const profile = cell.getAttribute("data-target-calc-readonly-profile");
        const metric = cell.getAttribute("data-target-calc-readonly-metric");
        cell.textContent = targetCalculationReadonlyValue(profile, metric, settings);
      });
    }

    function renderTargetCalculationSettings(settings) {
      const box = document.getElementById("target-calc-settings");
      if (!box) return;
      const values = normalizedTargetSettings(settings);
      targetPayload.target_settings = values;
      const bmrTitle = "BMR = 10*體重 + 6.25*身高 - 5*年齡 +5(男) / -161(女)。唯讀，由個人資料計算。";
      const tdeeTitle = "TDEE = BMR * activity factor。唯讀，由 BMR 及該 row 活動量計算。";
      const calorieOffsetTitle = "Calorie offset = 每月體重變化 kg * 7700 / 30。負數代表減重熱量赤字，正數代表增重熱量盈餘。唯讀，由個人資料 weight change 計算。";
      const proteinMidTitle = "蛋白質中位 = 體重 * 蛋白質 g/kg。唯讀，由個人資料及該 row g/kg 計算。";
      const valueCol = () => `<col data-form-col-key="target_calc_value" data-form-col-default="72" />`;
      const settingCols = [
        valueCol(),
        ...TARGET_SETTING_ROWS.flatMap((row) => {
          if (row.key === "calorie_range_band") return [valueCol(), valueCol(), valueCol()];
          if (row.key === "protein_g_per_kg") return [valueCol(), valueCol()];
          return [valueCol()];
        }),
      ].join("");
      const settingHeads = [
        `<th data-form-col-key="target_calc_value" title="${esc(traditionalTooltipText(bmrTitle))}">基礎代謝<br>BMR kcal</th>`,
        ...TARGET_SETTING_ROWS.flatMap((row) => {
          const head = `<th data-form-col-key="target_calc_value" title="${esc(traditionalTooltipText(targetSettingTooltip(row)))}">${row.label}</th>`;
          if (row.key === "calorie_range_band") return [
            `<th data-form-col-key="target_calc_value" title="${esc(traditionalTooltipText(tdeeTitle))}">每日消耗<br>TDEE kcal</th>`,
            `<th data-form-col-key="target_calc_value" title="${esc(traditionalTooltipText(calorieOffsetTitle))}">卡路里調整<br>calorie offset kcal</th>`,
            head,
          ];
          if (row.key === "protein_g_per_kg") return [head, `<th data-form-col-key="target_calc_value" title="${esc(traditionalTooltipText(proteinMidTitle))}">蛋白質中位<br>protein mid g</th>`];
          return [head];
        }),
      ].join("");
      const readonlyCell = (profile, metric, title) => `
        <td class="target-calc-readonly" data-form-col-key="target_calc_value" data-target-calc-readonly-profile="${esc(profile)}" data-target-calc-readonly-metric="${esc(metric)}" title="${esc(traditionalTooltipText(title))}">${esc(targetCalculationReadonlyValue(profile, metric, values))}</td>
      `;
      const inputCell = (profile, key) => `
        <td data-form-col-key="target_calc_value">
          <input type="text" inputmode="decimal" data-target-setting-profile="${esc(profile)}" data-target-setting-key="${esc(key)}" value="${esc(targetSettingInputValue(values[profile][key]))}" />
        </td>
      `;
      const rowHtml = (profile, label) => {
        const cells = [
          readonlyCell(profile, "bmr", bmrTitle),
          ...TARGET_SETTING_ROWS.flatMap(({ key }) => {
            if (key === "calorie_range_band") return [
              readonlyCell(profile, "tdee", tdeeTitle),
              readonlyCell(profile, "calorie_offset", calorieOffsetTitle),
              inputCell(profile, key),
            ];
            if (key === "protein_g_per_kg") return [inputCell(profile, key), readonlyCell(profile, "protein_mid", proteinMidTitle)];
            return [inputCell(profile, key)];
          }),
        ].join("");
        return `
          <tr>
            <th scope="row" data-form-col-key="target_calc_profile">${label}</th>
            ${cells}
          </tr>
        `;
      };
      box.innerHTML = `<table class="target-calc-table" data-form-table>
        <colgroup>
          <col data-form-col-key="target_calc_profile" data-form-col-default="88" />
          ${settingCols}
        </colgroup>
        <thead><tr><th data-form-col-key="target_calc_profile">目標<br>Target</th>${settingHeads}</tr></thead>
        <tbody>${rowHtml("workday", "返工日<br>Workday")}${rowHtml("nonworkday", "非返工日<br>Non-workday")}</tbody>
      </table>`;
      box.querySelectorAll("input[data-target-setting-key]").forEach((input) => {
        const update = () => {
          renderTargetPreviewTable();
          markTargetDirtyIfChanged();
        };
        input.addEventListener("input", update);
        input.addEventListener("change", update);
      });
      bindTargetEnterMoveRight(box);
      applyFormColumnWidths(box);
      attachFormColumnResizers(box);
      applyTargetConfigTabIndexes();
    }

    function numberOrNull(raw) {
      const n = Number(raw);
      return Number.isFinite(n) ? n : null;
    }

    function currentTargetProfileFromInputs() {
      return {
        age: numberOrNull(document.getElementById("target-profile-age")?.value),
        dob: targetIsoDobFromInput(document.getElementById("target-profile-dob")?.value),
        gender: String(document.getElementById("target-profile-gender")?.value || "").trim(),
        height_cm: numberOrNull(document.getElementById("target-profile-height")?.value),
        weight_kg: numberOrNull(document.getElementById("target-profile-weight")?.value),
        monthly_weight_change_kg: numberOrNull(document.getElementById("target-profile-weight-change")?.value),
      };
    }

    function collectTargetSettings() {
      const settings = cloneTargetSettingDefaults();
      document.querySelectorAll("#target-calc-settings input[data-target-setting-profile][data-target-setting-key]").forEach((input) => {
        const profile = input.getAttribute("data-target-setting-profile");
        const key = input.getAttribute("data-target-setting-key");
        if (!settings[profile] || !Object.prototype.hasOwnProperty.call(settings[profile], key)) return;
        const n = Number(input.value);
        settings[profile][key] = Number.isFinite(n) ? n : NaN;
      });
      return settings;
    }

    function targetBmr(profile) {
      const age = Number(profile.age);
      const height = Number(profile.height_cm);
      const weight = Number(profile.weight_kg);
      if (!Number.isFinite(age) || !Number.isFinite(height) || !Number.isFinite(weight) || age <= 0 || height <= 0 || weight <= 0) return null;
      if (profile.gender === "male") return 10 * weight + 6.25 * height - 5 * age + 5;
      if (profile.gender === "female") return 10 * weight + 6.25 * height - 5 * age - 161;
      return null;
    }

    function roundedRange(lo, hi, suffix = "") {
      const a = Math.round(lo);
      const b = Math.round(hi);
      return a === b ? `${a}${suffix}` : `${a}-${b}${suffix}`;
    }

    function targetDailyCalorieOffset(profile) {
      const monthly = Number(profile && profile.monthly_weight_change_kg);
      return Number.isFinite(monthly) ? monthly * 7700 / 30 : 0;
    }

    function calculatedTargetRow(profileKey) {
      const profile = currentTargetProfileFromInputs();
      const settings = collectTargetSettings();
      const values = settings[profileKey] || {};
      const bmr = targetBmr(profile);
      if (bmr == null) return Array(10).fill("");
      const activity = Number(values.activity_factor);
      const band = Number(values.calorie_range_band);
      const hasKcal = Number.isFinite(activity) && Number.isFinite(band);
      const midKcal = hasKcal ? bmr * activity + targetDailyCalorieOffset(profile) : NaN;
      const kcalLo = hasKcal ? Math.max(0, midKcal - band) : NaN;
      const kcalHi = hasKcal ? midKcal + band : NaN;
      const protein = targetProteinMid(profile, values);
      const proteinBand = Number(values.protein_range_band);
      const carbPct = Number(values.carb_pct);
      const hasCarb = Number.isFinite(kcalLo) && Number.isFinite(kcalHi) && Number.isFinite(carbPct);
      const carbLo = hasCarb ? kcalLo * (carbPct / 100) / 4 : NaN;
      const carbHi = hasCarb ? kcalHi * (carbPct / 100) / 4 : NaN;
      const below = (value, unit) => Number.isFinite(Number(value)) ? `< ${Math.round(Number(value))}${unit}` : "";
      const above = (value, unit) => Number.isFinite(Number(value)) ? `> ${Math.round(Number(value))}${unit}` : "";
      const pctBelow = (value) => {
        const text = targetSettingInputValue(value);
        return text ? `< ${text}% kcal` : "";
      };
      return [
        hasKcal ? roundedRange(kcalLo, kcalHi) : "",
        Number.isFinite(protein) ? (Number.isFinite(proteinBand) && proteinBand > 0 ? roundedRange(Math.max(0, protein - proteinBand), protein + proteinBand) : `${Math.round(protein)}`) : "",
        hasCarb ? roundedRange(carbLo, carbHi) : "",
        below(values.sugar_g, "g"),
        below(values.cholesterol_mg, "mg"),
        below(values.sodium_mg, "mg"),
        above(values.calcium_mg, "mg"),
        pctBelow(values.fat_total_pct),
        pctBelow(values.fat_sat_pct),
        pctBelow(values.fat_trans_pct),
      ];
    }

    function previewHeaderTooltip(nutrientKey) {
      const profile = currentTargetProfileFromInputs();
      const bmr = targetBmr(profile);
      const base = bmr == null
        ? "需要 DOB、性別、身高、體重先可計算。"
        : `BMR = 10*體重 + 6.25*身高 - 5*年齡 ${profile.gender === "male" ? "+ 5" : "- 161"}。TDEE = BMR * activity factor。Calorie offset = 每月體重變化 kg * 7700 / 30。`;
      const pair = (settingKey, unit = "") => {
        const settings = collectTargetSettings();
        const w = targetSettingInputValue(settings.workday[settingKey]);
        const n = targetSettingInputValue(settings.nonworkday[settingKey]);
        return `返工 ${w}${unit}；非返工 ${n}${unit}`;
      };
      return {
        kcal: `${base} 卡路里 = TDEE + calorie offset ± range band；${pair("activity_factor")} activity factor；${pair("calorie_range_band", " kcal")} range band。`,
        protein_g: `蛋白質中位 = 最新體重 * g/kg；蛋白質 range = 中位 ± range band；${pair("protein_g_per_kg", " g/kg")}；${pair("protein_range_band", "g")} range band。`,
        carb_g: `碳水 = 卡路里 * 碳水% / 4；${pair("carb_pct", "%")}。`,
        sugar_g: `天然糖 = 自訂上限；${pair("sugar_g", "g")}。`,
        cholesterol_mg: `膽固醇 = 自訂上限；${pair("cholesterol_mg", "mg")}。`,
        sodium_mg: `鈉 = 自訂上限；14歲以上 guideline <2300mg；${pair("sodium_mg", "mg")}。`,
        calcium_mg: `鈣 = 自訂下限；男19-70 >=1000mg，51+ 可用 >=1200mg；${pair("calcium_mg", "mg")}。`,
        fat_total_g: `總脂肪 = 卡路里百分比上限；guideline 20-35%；${pair("fat_total_pct", "% kcal")}。`,
        fat_sat_g: `飽和脂肪 = 卡路里百分比上限；guideline <10%；${pair("fat_sat_pct", "% kcal")}。`,
        fat_trans_g: `反式脂肪 = 卡路里百分比上限；越低越好；${pair("fat_trans_pct", "% kcal")}。`,
      }[nutrientKey] || "Preview 指標由個人資料及計算設定產生。";
    }

    function renderTargetPreviewTable() {
      const editor = document.getElementById("target-preview-editor");
      if (!editor) return;
      const headers = targetPayload.headers || [];
      const keys = targetPayload.nutrient_keys || [];
      const data = {
        headers,
        nutrient_keys: keys,
        indicator_rows: {
          workday: calculatedTargetRow("workday"),
          nonworkday: calculatedTargetRow("nonworkday"),
        },
      };
      renderTargetEditorTable("target-preview-editor", data, "preview");
      editor.querySelectorAll("input").forEach((input) => {
        input.readOnly = true;
        input.tabIndex = -1;
      });
      updateTargetCalculationReadonlyValues();
    }

    function previewTargetRows() {
      return {
        workday: calculatedTargetRow("workday"),
        nonworkday: calculatedTargetRow("nonworkday"),
      };
    }

    async function applyPreviewTargetsToCurrentTargets() {
      const rows = previewTargetRows();
      const data = {
        headers: targetPayload.headers || [],
        nutrient_keys: targetPayload.nutrient_keys || [],
        indicator_rows: rows,
      };
      targetPayload.indicator_rows = {
        workday: [...data.indicator_rows.workday],
        nonworkday: [...data.indicator_rows.nonworkday],
      };
      renderTargetEditorTable("target-editor", data, "config");
      setUnsavedChanges("目標");
      applyTargetBlockLayout();
      await saveTargetEditor("config", { targetRows: rows });
    }

    function targetApplySizePx(axis, fallback) {
      const saved = Number(formColumnWidths[`target_apply_${axis}`]);
      return Number.isFinite(saved) && saved > 0 ? saved : fallback;
    }

    function applyTargetApplyButtonLayout() {
      const btn = document.getElementById("target-apply-preview");
      if (!btn) return;
      btn.style.width = `${targetApplySizePx("w", 88)}px`;
      btn.style.height = `${targetApplySizePx("h", 28)}px`;
    }

    function targetApplyPointerInResizeZone(btn, ev) {
      const rect = btn.getBoundingClientRect();
      return ev.clientX >= rect.right - 12 && ev.clientY >= rect.bottom - 12;
    }

    function moveTargetBlocksFromPointer(blockKey, startX, startY) {
      const dragKeys = targetSelectedBlocks.has(blockKey) && targetSelectedBlocks.size > 1
        ? Array.from(targetSelectedBlocks)
        : [blockKey];
      if (!targetSelectedBlocks.has(blockKey)) {
        targetSelectedBlocks.clear();
        updateTargetBlockSelection();
      }
      const startOffsets = new Map();
      dragKeys.forEach((key) => {
        const target = document.querySelector(`.target-section-block[data-target-block="${key}"]`);
        startOffsets.set(key, {
          x: targetBlockOffsetPx(key, "x", target?.offsetLeft || 0),
          y: targetBlockOffsetPx(key, "y", target?.offsetTop || 0),
        });
      });
      return (mv) => {
        const dx = mv.clientX - startX;
        const dy = mv.clientY - startY;
        startOffsets.forEach((start, key) => {
          formColumnWidths[`target_block_${key}_x`] = start.x + dx;
          formColumnWidths[`target_block_${key}_y`] = start.y + dy;
        });
        applyTargetBlockLayout();
      };
    }

    function bindTargetApplyButton() {
      const btn = document.getElementById("target-apply-preview");
      if (btn && btn.dataset.targetApplyBound !== "1") {
        btn.dataset.targetApplyBound = "1";
        btn.addEventListener("mousemove", (ev) => {
          btn.style.cursor = targetApplyPointerInResizeZone(btn, ev) ? "nwse-resize" : "";
        });
        btn.addEventListener("mouseleave", () => {
          btn.style.cursor = "";
        });
        btn.addEventListener("click", (ev) => {
          if (btn.dataset.targetApplySuppressClick === "1") {
            ev.preventDefault();
            ev.stopPropagation();
            delete btn.dataset.targetApplySuppressClick;
            return;
          }
          applyPreviewTargetsToCurrentTargets();
        });
        btn.addEventListener("mousedown", (ev) => {
          if (ev.button != null && ev.button !== 0) return;
          ev.preventDefault();
          ev.stopPropagation();
          const block = btn.closest(".target-section-block[data-target-block]");
          const blockKey = block && block.getAttribute("data-target-block");
          if (!blockKey) return;
          if (ev.ctrlKey) {
            btn.dataset.targetApplySuppressClick = "1";
            toggleTargetBlockSelection(blockKey);
            return;
          }
          const resizeMode = targetApplyPointerInResizeZone(btn, ev);
          if (!resizeMode) document.body.classList.add("is-dnd-dragging");
          btn.style.cursor = resizeMode ? "nwse-resize" : "";
          const startX = ev.clientX;
          const startY = ev.clientY;
          const startW = targetApplySizePx("w", 88);
          const startH = targetApplySizePx("h", 28);
          const moveBlocks = resizeMode ? null : moveTargetBlocksFromPointer(blockKey, startX, startY);
          let changed = resizeMode;
          const onMove = (mv) => {
            const dx = mv.clientX - startX;
            const dy = mv.clientY - startY;
            if (!changed && Math.abs(dx) <= 2 && Math.abs(dy) <= 2) return;
            changed = true;
            if (resizeMode) {
              formColumnWidths.target_apply_w = Math.max(48, startW + dx);
              formColumnWidths.target_apply_h = Math.max(22, startH + dy);
              applyTargetApplyButtonLayout();
              applyTargetBlockLayout();
            } else if (moveBlocks) {
              moveBlocks(mv);
            }
          };
          const onUp = () => {
            window.removeEventListener("mousemove", onMove);
            window.removeEventListener("mouseup", onUp);
            document.body.classList.remove("is-dnd-dragging");
            btn.style.cursor = "";
            if (changed) {
              btn.dataset.targetApplySuppressClick = "1";
              targetBlockSuppressNextClickClear = true;
              persistColumnWidths();
            }
          };
          window.addEventListener("mousemove", onMove);
          window.addEventListener("mouseup", onUp, { once: true });
        });
      }
      applyTargetApplyButtonLayout();
    }

    function fillTargetProfile(profile) {
      const data = profile && typeof profile === "object" ? profile : {};
      const dob = document.getElementById("target-profile-dob");
      const age = document.getElementById("target-profile-age");
      const gender = document.getElementById("target-profile-gender");
      const height = document.getElementById("target-profile-height");
      const weight = document.getElementById("target-profile-weight");
      const weightChange = document.getElementById("target-profile-weight-change");
      if (dob) {
        dob.value = targetDisplayDobFromIso(data.dob ?? "");
        dob.dataset.targetCommittedValue = dob.value;
      }
      if (age) age.value = data.dob ? (targetAgeFromDob(data.dob) ?? "") : (data.age ?? "");
      if (gender) gender.value = data.gender === "female" ? "female" : "male";
      if (height) height.value = data.height_cm ?? "";
      if (weight) {
        weight.value = data.weight_kg ?? "";
        weight.dataset.targetOriginalWeight = data.weight_kg ?? "";
      }
      if (weightChange) weightChange.value = data.monthly_weight_change_kg ?? 0;
      bindTargetProfileInputs();
      const history = Array.isArray(data.weight_history) ? data.weight_history : [];
      const visibleHistory = history.length || data.weight_kg == null ? history : [{
        weight_kg: data.weight_kg,
        recorded_at: data.last_updated || targetNowDateTimeText(),
      }];
      renderTargetWeightHistory(visibleHistory);
      targetPayload.profile = {
        age: data.age ?? null,
        dob: data.dob ?? "",
        gender: gender ? gender.value : (data.gender ?? ""),
        height_cm: data.height_cm ?? null,
        weight_kg: data.weight_kg ?? null,
        monthly_weight_change_kg: weightChange ? numberOrNull(weightChange.value) : (data.monthly_weight_change_kg ?? 0),
        last_updated: data.last_updated ?? "",
        weight_history: visibleHistory,
      };
    }

    function targetNowDateTimeText() {
      const now = new Date();
      const dateParts = new Intl.DateTimeFormat("en-CA", {
        timeZone: HK_TZ,
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      }).formatToParts(now);
      const timeParts = new Intl.DateTimeFormat("en-GB", {
        timeZone: HK_TZ,
        hourCycle: "h23",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      }).formatToParts(now);
      const part = (parts, type) => parts.find((item) => item.type === type)?.value || "";
      return `${part(dateParts, "year")}-${part(dateParts, "month")}-${part(dateParts, "day")} ${part(timeParts, "hour")}:${part(timeParts, "minute")}:${part(timeParts, "second")}`;
    }

    function targetIsoDobFromInput(dobValue) {
      const text = String(dobValue || "").trim();
      let match = text.match(/^(\d{4})-(\d{2})-(\d{2})(?:\s+[A-Za-z]{3})?$/);
      if (match) return `${match[1]}-${match[2]}-${match[3]}`;
      match = text.match(/^(\d{1,2})[\/-](\d{1,2})[\/-](\d{2}|\d{4})(?:\s+[A-Za-z]{3})?$/);
      if (!match) return text;
      const day = String(Number(match[1])).padStart(2, "0");
      const month = String(Number(match[2])).padStart(2, "0");
      const year = targetDobFullYear(match[3], Number(month), Number(day));
      return `${year}-${month}-${day}`;
    }

    function targetDobFullYear(yearText, month, day) {
      if (String(yearText).length === 4) return String(yearText);
      const yy = Number(yearText);
      const nowParts = new Intl.DateTimeFormat("en-CA", { timeZone: HK_TZ, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date());
      const todayY = Number(nowParts.find((part) => part.type === "year")?.value || 0);
      const todayM = Number(nowParts.find((part) => part.type === "month")?.value || 0);
      const todayD = Number(nowParts.find((part) => part.type === "day")?.value || 0);
      if (!Number.isFinite(yy) || !todayY) return String(yearText).padStart(4, "0");
      let year = Math.floor(todayY / 100) * 100 + yy;
      const candidate = new Date(Date.UTC(year, month - 1, day));
      const today = new Date(Date.UTC(todayY, todayM - 1, todayD));
      if (candidate > today) year -= 100;
      return String(year);
    }

    function targetValidIsoDateParts(iso) {
      const match = String(iso || "").match(/^(\d{4})-(\d{2})-(\d{2})$/);
      if (!match) return null;
      const y = Number(match[1]);
      const m = Number(match[2]);
      const d = Number(match[3]);
      const date = new Date(Date.UTC(y, m - 1, d));
      if (date.getUTCFullYear() !== y || date.getUTCMonth() !== m - 1 || date.getUTCDate() !== d) return null;
      return { y, m, d, date };
    }

    function targetWeekdayFromIso(iso) {
      const parts = targetValidIsoDateParts(iso);
      if (!parts) return "";
      return new Intl.DateTimeFormat("en-US", { timeZone: "UTC", weekday: "short" }).format(parts.date);
    }

    function targetDisplayDobFromIso(dobValue) {
      const iso = targetIsoDobFromInput(dobValue);
      const parts = targetValidIsoDateParts(iso);
      return parts ? `${String(parts.d).padStart(2, "0")}/${String(parts.m).padStart(2, "0")}/${parts.y} ${targetWeekdayFromIso(iso)}` : String(dobValue || "");
    }

    function normalizeTargetDobInput() {
      const dob = document.getElementById("target-profile-dob");
      if (!dob) return;
      const text = String(dob.value || "").trim();
      if (!text) return;
      const display = targetDisplayDobFromIso(text);
      if (display) dob.value = display;
    }

    function targetAgeFromDob(dobValue) {
      const text = targetIsoDobFromInput(dobValue);
      const match = text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
      if (!match) return null;
      const born = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
      if (born.getUTCFullYear() !== Number(match[1]) || born.getUTCMonth() !== Number(match[2]) - 1 || born.getUTCDate() !== Number(match[3])) return null;
      const nowParts = new Intl.DateTimeFormat("en-CA", { timeZone: HK_TZ, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date());
      const todayY = Number(nowParts.find((part) => part.type === "year")?.value || 0);
      const todayM = Number(nowParts.find((part) => part.type === "month")?.value || 0);
      const todayD = Number(nowParts.find((part) => part.type === "day")?.value || 0);
      if (!todayY || born > new Date(Date.UTC(todayY, todayM - 1, todayD))) return null;
      const hadBirthday = (todayM > Number(match[2])) || (todayM === Number(match[2]) && todayD >= Number(match[3]));
      return todayY - Number(match[1]) - (hadBirthday ? 0 : 1);
    }

    function syncTargetAgeFromDob() {
      const dob = document.getElementById("target-profile-dob");
      const age = document.getElementById("target-profile-age");
      if (!dob || !age) return;
      age.value = dob.value ? (targetAgeFromDob(dob.value) ?? "") : "";
      renderTargetPreviewTable();
      if (dob.value !== (dob.dataset.targetCommittedValue || "")) markTargetDirtyIfChanged();
    }

    function moveTargetProfileEnter(input) {
      focusTargetEditable(nextTargetConfigOrderedCell(input) || input);
    }

    function appendProfileWeightToHistory() {
      const input = document.getElementById("target-profile-weight");
      if (!input) return false;
      const weight = Number(input.value);
      const original = Number(input.dataset.targetOriginalWeight || "");
      if (!Number.isFinite(weight) || weight <= 0 || (Number.isFinite(original) && original === weight)) return false;
      const history = collectTargetWeightHistory();
      history.push({
        weight_kg: String(weight),
        recorded_at: targetNowDateTimeText(),
      });
      input.dataset.targetOriginalWeight = String(weight);
      renderTargetWeightHistory(history);
      markTargetDirtyIfChanged();
      renderTargetPreviewTable();
      return true;
    }

    function bindTargetProfileInputs() {
      const dob = document.getElementById("target-profile-dob");
      if (dob && dob.dataset.targetDobBound !== "1") {
        dob.dataset.targetDobBound = "1";
        dob.addEventListener("input", syncTargetAgeFromDob);
        const normalizeAndSync = () => {
          normalizeTargetDobInput();
          syncTargetAgeFromDob();
        };
        dob.addEventListener("change", normalizeAndSync);
        dob.addEventListener("blur", normalizeAndSync);
        dob.addEventListener("keydown", (ev) => {
          if (ev.key !== "Enter" || ev.shiftKey || ev.ctrlKey || ev.altKey || ev.metaKey || ev.isComposing) return;
          ev.preventDefault();
          normalizeTargetDobInput();
          syncTargetAgeFromDob();
          moveTargetProfileEnter(dob);
        });
      }
      ["target-profile-gender", "target-profile-height", "target-profile-weight", "target-profile-weight-change"].forEach((id) => {
        const input = document.getElementById(id);
        if (!input || input.dataset.targetProfilePreviewBound === "1") return;
        input.dataset.targetProfilePreviewBound = "1";
        input.addEventListener("input", () => {
          renderTargetPreviewTable();
          markTargetDirtyIfChanged();
        });
        input.addEventListener("keydown", (ev) => {
          if (ev.key !== "Enter" || ev.shiftKey || ev.ctrlKey || ev.altKey || ev.metaKey || ev.isComposing) return;
          ev.preventDefault();
          moveTargetProfileEnter(input);
        });
        input.addEventListener("change", () => {
          if (id === "target-profile-weight") {
            appendProfileWeightToHistory();
          } else {
            renderTargetPreviewTable();
            markTargetDirtyIfChanged();
          }
        });
        if (id === "target-profile-weight") {
          input.addEventListener("blur", appendProfileWeightToHistory);
        }
      });
    }

    function stampTargetWeightDate(input) {
      if (!input) return false;
      const value = String(input.value || "").trim();
      const original = String(input.dataset.weightOriginalValue || "").trim();
      if (!value || value === original) return false;
      const row = input.closest("tr[data-weight-history-row]");
      const date = row ? row.querySelector('input[data-weight-history-field="recorded_at"]') : null;
      if (!date) return false;
      date.value = targetNowDateTimeText();
      input.dataset.weightOriginalValue = value;
      date.dispatchEvent(new Event("input", { bubbles: true }));
      return true;
    }

    function stampChangedTargetWeightDates() {
      document.querySelectorAll('#target-weight-history input[data-weight-history-field="weight_kg"]').forEach(stampTargetWeightDate);
    }

    function latestTargetWeightHistoryEntry(history) {
      const rows = (Array.isArray(history) ? history : [])
        .map((item, idx) => {
          const weight = Number(item && item.weight_kg);
          const recordedAt = String(item && item.recorded_at || "").trim();
          return { item, idx, weight, recordedAt };
        })
        .filter((row) => Number.isFinite(row.weight) && row.weight > 0);
      if (!rows.length) return null;
      rows.sort((a, b) => {
        const aValid = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(a.recordedAt);
        const bValid = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(b.recordedAt);
        if (aValid && bValid && a.recordedAt !== b.recordedAt) return a.recordedAt.localeCompare(b.recordedAt);
        if (aValid !== bValid) return aValid ? 1 : -1;
        return a.idx - b.idx;
      });
      return rows[rows.length - 1].item;
    }

    function syncProfileWeightFromHistory(history = collectTargetWeightHistory()) {
      const input = document.getElementById("target-profile-weight");
      if (!input) return;
      const latest = latestTargetWeightHistoryEntry(history);
      const next = latest ? String(latest.weight_kg ?? "") : "";
      input.value = next;
      input.dataset.targetOriginalWeight = next;
      targetPayload.profile = {
        ...(targetPayload.profile || {}),
        weight_kg: next ? Number(next) : null,
        weight_history: history,
      };
    }

    function renderTargetWeightHistory(history) {
      const box = document.getElementById("target-weight-history");
      if (!box) return;
      const rowHtml = (item, idx, isNew = false) => `
        <tr data-weight-history-row="${idx}">
          <td class="target-weight-value">
            <input type="text" inputmode="decimal" data-weight-history-field="weight_kg" data-weight-history-index="${idx}" data-weight-original-value="${esc(item.weight_kg ?? "")}" value="${esc(item.weight_kg ?? "")}" />
          </td>
          <td class="target-weight-date">
            <input type="text" data-weight-history-field="recorded_at" data-weight-history-index="${idx}" value="${esc(item.recorded_at ?? "")}" />
          </td>
          <td class="target-weight-delete">
            <button type="button" class="target-weight-delete-btn" data-weight-history-delete="${idx}" title="Delete">🗑</button>
          </td>
        </tr>
      `;
      const rows = (Array.isArray(history) ? history : []).map((item, idx) => rowHtml(item, idx)).join("");
      box.innerHTML = `<table class="target-weight-history" data-form-table>
        <colgroup>
          <col data-form-col-key="target_weight_history_weight" data-form-col-default="90" />
          <col data-form-col-key="target_weight_history_date" data-form-col-default="150" />
          <col data-form-col-key="target_weight_history_delete" data-form-col-default="30" />
        </colgroup>
        <thead><tr><th data-form-col-key="target_weight_history_weight">體重<br>weight (kg)</th><th data-form-col-key="target_weight_history_date">更新日期<br>updated at</th><th data-form-col-key="target_weight_history_delete"></th></tr></thead>
        <tbody>${rows || `<tr><td colspan="3" class="target-empty-row">沒有體重記錄 / No weight history</td></tr>`}</tbody>
      </table>`;
      box.querySelectorAll('input[data-weight-history-field="weight_kg"]').forEach((input) => {
        input.addEventListener("input", () => {
          syncProfileWeightFromHistory();
          renderTargetPreviewTable();
          markTargetDirtyIfChanged();
        });
        input.addEventListener("change", () => {
          stampTargetWeightDate(input);
          syncProfileWeightFromHistory();
          renderTargetPreviewTable();
          markTargetDirtyIfChanged();
        });
      });
      box.querySelectorAll('input[data-weight-history-field="recorded_at"]').forEach((input) => {
        input.addEventListener("input", () => {
          syncProfileWeightFromHistory();
          renderTargetPreviewTable();
          markTargetDirtyIfChanged();
        });
        input.addEventListener("change", () => {
          syncProfileWeightFromHistory();
          renderTargetPreviewTable();
          markTargetDirtyIfChanged();
        });
      });
      box.querySelectorAll("button[data-weight-history-delete]").forEach((btn) => {
        btn.addEventListener("click", () => {
          btn.closest("tr[data-weight-history-row]")?.remove();
          syncProfileWeightFromHistory();
          markTargetDirtyIfChanged();
          renderTargetPreviewTable();
        });
      });
      bindTargetEnterMoveRight(box);
      applyFormColumnWidths(box);
      attachFormColumnResizers(box);
    }

    function targetBlockOffsetPx(blockKey, axis, fallback) {
      const saved = Number(formColumnWidths[`target_block_${blockKey}_${axis}`]);
      return Number.isFinite(saved) ? saved : fallback;
    }

    function targetBlockWidth(block) {
      const tables = Array.from(block.querySelectorAll("table[data-form-table], table.target-table"));
      let width = 0;
      for (const table of tables) {
        const targetTableBase = table.classList.contains("target-table") ? 96 : 0;
        const colWidth = Array.from(table.querySelectorAll("col[data-form-col-key], col[data-target-col-key]")).reduce((total, col) => {
          const formKey = col.getAttribute("data-form-col-key");
          const targetKey = col.getAttribute("data-target-col-key");
          if (formKey) {
            const fallback = Number(col.getAttribute("data-form-col-default")) || 120;
            return total + formColumnWidthPx(formKey, fallback);
          }
          if (targetKey) return total + targetColumnWidthPx(targetKey);
          return total;
        }, targetTableBase);
        const explicitWidth = Math.max(
          parseFloat(table.style.width || "0") || 0,
          parseFloat(table.closest(".target-editor")?.style.width || "0") || 0,
        );
        const renderedWidth = Math.max(table.scrollWidth || 0, table.getBoundingClientRect().width || 0);
        width = Math.max(width, colWidth || 0, explicitWidth, renderedWidth);
      }
      const style = getComputedStyle(block);
      const borderX = parseFloat(style.borderLeftWidth || "0") + parseFloat(style.borderRightWidth || "0");
      return width + borderX;
    }

    function resetLegacyTargetBlockLayout() {
      if (Number(formColumnWidths.target_block_layout_version) === 4) return false;
      ["profile", "weight", "calc", "targets", "preview"].forEach((blockKey) => {
        delete formColumnWidths[`target_block_${blockKey}_x`];
        delete formColumnWidths[`target_block_${blockKey}_y`];
      });
      formColumnWidths.target_block_layout_version = 4;
      return true;
    }

    function applyTargetBlockLayout() {
      const container = document.querySelector(".target-config-blocks");
      if (!container) return;
      if (!container.getClientRects().length) return;
      const resetLayout = resetLegacyTargetBlockLayout();
      applyTargetApplyButtonLayout();
      applyFormColumnWidths(container);
      container.classList.add("is-draggable-layout");
      const blocks = Array.from(container.querySelectorAll(".target-section-block[data-target-block]"));
      const defaultPositions = new Map();
      let stackedY = 0;
      blocks.forEach((block) => {
        const blockKey = block.getAttribute("data-target-block");
        const height = block.getBoundingClientRect().height;
        defaultPositions.set(blockKey, { x: 0, y: stackedY });
        stackedY += height + 8;
      });
      const targetsBlock = blocks.find((block) => block.getAttribute("data-target-block") === "targets");
      const applyBlock = blocks.find((block) => block.getAttribute("data-target-block") === "apply");
      if (targetsBlock && applyBlock) {
        const targetDefault = defaultPositions.get("targets") || { x: 0, y: 0 };
        defaultPositions.set("apply", {
          x: targetDefault.x + targetBlockWidth(targetsBlock) + 8,
          y: targetDefault.y,
        });
      }
      let maxRight = 0;
      let maxBottom = 0;
      blocks.forEach((block) => {
        const blockKey = block.getAttribute("data-target-block");
        const height = block.getBoundingClientRect().height;
        const width = targetBlockWidth(block);
        const defaults = defaultPositions.get(blockKey) || { x: 0, y: 0 };
        const x = targetBlockOffsetPx(blockKey, "x", defaults.x);
        const y = targetBlockOffsetPx(blockKey, "y", defaults.y);
        block.style.width = "";
        block.style.minWidth = "";
        block.style.left = `${x}px`;
        block.style.top = `${y}px`;
        block.classList.toggle("is-target-block-selected", targetSelectedBlocks.has(blockKey));
        maxRight = Math.max(maxRight, x + Math.max(width, block.getBoundingClientRect().width));
        maxBottom = Math.max(maxBottom, y + height);
      });
      container.style.width = `${Math.max(280, maxRight)}px`;
      container.style.height = `${Math.max(260, maxBottom)}px`;
      if (resetLayout) persistColumnWidths();
    }

    function updateTargetBlockSelection() {
      document.querySelectorAll(".target-section-block[data-target-block]").forEach((block) => {
        const blockKey = block.getAttribute("data-target-block");
        block.classList.toggle("is-target-block-selected", targetSelectedBlocks.has(blockKey));
      });
    }

    function targetBlocksVisible() {
      const root = document.querySelector('.config-view[data-config-view="targets"] .target-config-blocks');
      return !!(root && root.getClientRects().length);
    }

    function selectAllTargetBlocks() {
      targetSelectedBlocks.clear();
      document.querySelectorAll(".target-section-block[data-target-block]").forEach((block) => {
        const blockKey = block.getAttribute("data-target-block");
        if (blockKey) targetSelectedBlocks.add(blockKey);
      });
      updateTargetBlockSelection();
    }

    function toggleTargetBlockSelection(blockKey) {
      if (!blockKey) return;
      if (targetSelectedBlocks.has(blockKey)) {
        targetSelectedBlocks.delete(blockKey);
      } else {
        targetSelectedBlocks.add(blockKey);
      }
      updateTargetBlockSelection();
    }

    function clearTargetBlockSelection() {
      if (!targetSelectedBlocks.size) return;
      targetSelectedBlocks.clear();
      updateTargetBlockSelection();
    }

    function bindTargetBlockSelectionKeys() {
      if (document.body.dataset.targetBlockSelectionKeysBound === "1") return;
      document.body.dataset.targetBlockSelectionKeysBound = "1";
      document.addEventListener("keydown", (ev) => {
        if (ev.key !== "Escape") return;
        clearTargetBlockSelection();
      });
      document.addEventListener("keydown", (ev) => {
        if (!(ev.ctrlKey || ev.metaKey) || ev.altKey || String(ev.key).toLowerCase() !== "a") return;
        if (!targetBlocksVisible()) return;
        const active = document.activeElement;
        if (active && active.matches && active.matches("input,textarea") && active.dataset.targetEditing === "1") return;
        ev.preventDefault();
        selectAllTargetBlocks();
      });
      document.addEventListener("click", (ev) => {
        if (!targetSelectedBlocks.size || ev.ctrlKey) return;
        if (targetBlockSuppressNextClickClear) {
          targetBlockSuppressNextClickClear = false;
          return;
        }
        if (ev.button != null && ev.button !== 0) return;
        clearTargetBlockSelection();
      });
    }

    function attachTargetBlockDragHandles() {
      bindTargetBlockSelectionKeys();
      document.querySelectorAll(".target-section-block[data-target-block]").forEach((block) => {
        if (block.dataset.targetBlockSelectBound === "1") return;
        block.dataset.targetBlockSelectBound = "1";
        block.addEventListener("mousedown", (ev) => {
          if (!ev.ctrlKey || (ev.button != null && ev.button !== 0)) return;
          const interactive = ev.target && ev.target.closest
            ? ev.target.closest("input,textarea,select,button,a,.target-col-resizer,.form-col-resizer")
            : null;
          if (interactive) return;
          ev.preventDefault();
          ev.stopPropagation();
          toggleTargetBlockSelection(block.getAttribute("data-target-block"));
        });
      });
      document.querySelectorAll(".target-section-block[data-target-block] > h3").forEach((handle) => {
        if (handle.dataset.targetBlockDragBound === "1") return;
        handle.dataset.targetBlockDragBound = "1";
        handle.title = handle.title || "Drag to move block";
        handle.addEventListener("mousedown", (ev) => {
          if (ev.button != null && ev.button !== 0) return;
          ev.preventDefault();
          const block = handle.closest(".target-section-block[data-target-block]");
          const blockKey = block && block.getAttribute("data-target-block");
          if (!blockKey) return;
          if (ev.ctrlKey) {
            ev.stopPropagation();
            toggleTargetBlockSelection(blockKey);
            return;
          }
          const dragKeys = targetSelectedBlocks.has(blockKey) && targetSelectedBlocks.size > 1
            ? Array.from(targetSelectedBlocks)
            : [blockKey];
          if (!targetSelectedBlocks.has(blockKey)) {
            targetSelectedBlocks.clear();
            updateTargetBlockSelection();
          }
          const startX = ev.clientX;
          const startY = ev.clientY;
          let dragMoved = false;
          document.body.classList.add("is-dnd-dragging");
          const startOffsets = new Map();
          dragKeys.forEach((key) => {
            const target = document.querySelector(`.target-section-block[data-target-block="${key}"]`);
            startOffsets.set(key, {
              x: targetBlockOffsetPx(key, "x", target?.offsetLeft || 0),
              y: targetBlockOffsetPx(key, "y", target?.offsetTop || 0),
            });
          });
          const onMove = (mv) => {
            const dx = mv.clientX - startX;
            const dy = mv.clientY - startY;
            dragMoved = dragMoved || Math.abs(dx) > 2 || Math.abs(dy) > 2;
            startOffsets.forEach((start, key) => {
              formColumnWidths[`target_block_${key}_x`] = start.x + dx;
              formColumnWidths[`target_block_${key}_y`] = start.y + dy;
            });
            applyTargetBlockLayout();
          };
          const onUp = () => {
            window.removeEventListener("mousemove", onMove);
            window.removeEventListener("mouseup", onUp);
            document.body.classList.remove("is-dnd-dragging");
            if (dragMoved) targetBlockSuppressNextClickClear = true;
            persistColumnWidths();
          };
          window.addEventListener("mousemove", onMove);
          window.addEventListener("mouseup", onUp);
        });
        handle.addEventListener("click", (ev) => {
          if (!ev.ctrlKey) return;
          ev.preventDefault();
          ev.stopPropagation();
        });
        handle.addEventListener("dblclick", () => {
          const block = handle.closest(".target-section-block[data-target-block]");
          const blockKey = block && block.getAttribute("data-target-block");
          if (!blockKey) return;
          delete formColumnWidths[`target_block_${blockKey}_x`];
          delete formColumnWidths[`target_block_${blockKey}_y`];
          applyTargetBlockLayout();
          persistColumnWidths();
        });
      });
    }

    function targetColumnWidthPx(key) {
      const width = Number(targetColumnWidths[key]);
      if (Number.isFinite(width) && width >= 28) return width;
      return key === "target_profile" ? 84 : 82;
    }

    function applyTargetEditorLayout() {
      document.querySelectorAll(".target-editor").forEach((editor) => {
        let tableWidth = 0;
        editor.querySelectorAll("col[data-target-col-key]").forEach((col) => {
          const widthPx = targetColumnWidthPx(col.getAttribute("data-target-col-key"));
          tableWidth += widthPx;
          col.style.width = `${widthPx}px`;
        });
        editor.style.width = `${tableWidth}px`;
        const table = editor.querySelector("table.target-table");
        if (table) table.style.width = `${tableWidth}px`;
      });
      applyColumnWidths();
      applyTargetBlockLayout();
    }

    function attachTargetEditorResizers() {
      document.querySelectorAll(".target-editor").forEach((editor) => {
      editor.querySelectorAll("th[data-target-col-key]").forEach((cell) => {
        const grip = cell.querySelector(".target-col-resizer");
        if (!grip || grip.dataset.bound === "1") return;
        grip.dataset.bound = "1";
        grip.addEventListener("mousedown", (ev) => {
          ev.preventDefault();
          ev.stopPropagation();
          const key = cell.getAttribute("data-target-col-key");
          const startX = ev.clientX;
          const startWidth = cell.getBoundingClientRect().width;
          const onMove = (mv) => {
            targetColumnWidths[key] = Math.max(28, startWidth + (mv.clientX - startX));
            applyTargetEditorLayout();
          };
          const onUp = () => {
            window.removeEventListener("mousemove", onMove);
            window.removeEventListener("mouseup", onUp);
            persistColumnWidths();
          };
          window.addEventListener("mousemove", onMove);
          window.addEventListener("mouseup", onUp);
        });
      });
      });
    }

    function collectTargetValues(profile, source = "config") {
      const values = [];
      const selector = source === "planner"
        ? `#out input[data-target-source="planner"][data-target-profile="${profile}"]`
        : `.target-editor input[data-target-source="${source}"][data-target-profile="${profile}"]`;
      document.querySelectorAll(selector).forEach((input) => {
        const idx = Number(input.getAttribute("data-target-index"));
        if (Number.isInteger(idx) && idx >= 0) values[idx] = (input.value || "").trim();
      });
      return values;
    }

    function optionalNumberValue(id) {
      const text = String(document.getElementById(id)?.value || "").trim();
      if (!text) return null;
      const n = Number(text);
      return Number.isFinite(n) ? n : NaN;
    }

    function collectTargetProfile() {
      stampChangedTargetWeightDates();
      const weightHistory = collectTargetWeightHistory();
      const profileWeight = optionalNumberValue("target-profile-weight");
      return {
        dob: targetIsoDobFromInput(document.getElementById("target-profile-dob")?.value),
        gender: String(document.getElementById("target-profile-gender")?.value || "").trim(),
        height_cm: optionalNumberValue("target-profile-height"),
        weight_kg: profileWeight,
        monthly_weight_change_kg: optionalNumberValue("target-profile-weight-change"),
        weight_history: weightHistory,
      };
    }

    function collectTargetWeightHistory() {
      const rows = [];
      document.querySelectorAll("#target-weight-history tr[data-weight-history-row]").forEach((row) => {
        const weightText = String(row.querySelector('input[data-weight-history-field="weight_kg"]')?.value || "").trim();
        if (!weightText) return;
        const dateText = String(row.querySelector('input[data-weight-history-field="recorded_at"]')?.value || "").trim();
        rows.push({
          weight_kg: weightText,
          recorded_at: dateText,
        });
      });
      return rows;
    }

    function collectTargetProfileSnapshot() {
      return {
        dob: targetIsoDobFromInput(document.getElementById("target-profile-dob")?.value),
        gender: String(document.getElementById("target-profile-gender")?.value || "").trim(),
        height_cm: String(document.getElementById("target-profile-height")?.value || "").trim(),
        weight_kg: String(document.getElementById("target-profile-weight")?.value || "").trim(),
        monthly_weight_change_kg: String(document.getElementById("target-profile-weight-change")?.value || "").trim(),
        weight_history: collectTargetWeightHistory(),
      };
    }

    function collectTargetDirtySnapshot() {
      return JSON.stringify({
        profile: collectTargetProfileSnapshot(),
        target_settings: collectTargetSettings(),
        indicator_rows: {
          workday: collectTargetValues("workday", "config"),
          nonworkday: collectTargetValues("nonworkday", "config"),
        },
      });
    }

    function resetTargetDirtySnapshot() {
      targetSavedSnapshot = collectTargetDirtySnapshot();
    }

    function markTargetDirtyIfChanged() {
      if (!targetSavedSnapshot) return;
      const changed = collectTargetDirtySnapshot() !== targetSavedSnapshot;
      if (changed) {
        setUnsavedChanges("目標");
      } else {
        clearUnsavedChanges("目標");
        setTargetStatus("");
      }
    }

    function updateTargetPayloadAfterSave(saved, source, payload) {
      const rows = saved && saved.indicator_rows && typeof saved.indicator_rows === "object"
        ? saved.indicator_rows
        : { workday: payload.workday || [], nonworkday: payload.nonworkday || [] };
      targetPayload = {
        headers: Array.isArray(saved && saved.headers) ? saved.headers : (targetPayload.headers || []),
        nutrient_keys: Array.isArray(saved && saved.nutrient_keys) ? saved.nutrient_keys : (targetPayload.nutrient_keys || []),
        indicator_rows: {
          workday: Array.isArray(rows.workday) ? rows.workday : [],
          nonworkday: Array.isArray(rows.nonworkday) ? rows.nonworkday : [],
        },
        profile: source === "config" && saved && saved.profile ? saved.profile : (targetPayload.profile || {}),
        target_settings: source === "config" && saved && saved.target_settings ? saved.target_settings : (targetPayload.target_settings || cloneTargetSettingDefaults()),
      };
    }

    function resetTargetInputBaselinesAfterSave() {
      const dob = document.getElementById("target-profile-dob");
      if (dob) dob.dataset.targetCommittedValue = dob.value;
      const weight = document.getElementById("target-profile-weight");
      if (weight) weight.dataset.targetOriginalWeight = weight.value;
      document.querySelectorAll('#target-weight-history input[data-weight-history-field="weight_kg"]').forEach((input) => {
        input.dataset.weightOriginalValue = input.value;
      });
    }

    function showTargetError(message, source = "config") {
      const err = document.getElementById(source === "planner" ? "err" : "target-err");
      if (!err) return;
      err.textContent = message || "";
      err.style.display = message ? "block" : "none";
    }

    function setTargetStatus(message) {
      const status = document.getElementById("target-status");
      if (status) status.textContent = message || "";
    }

    function setDetailStatus(message) {
      const status = document.getElementById("detail-status");
      if (status) status.textContent = message || "";
    }

    function showDetailError(message) {
      const err = document.getElementById("detail-err");
      if (!err) return;
      err.textContent = message || "";
      err.style.display = message ? "block" : "none";
    }

    function detailBlockOffsetPx(blockKey, axis) {
      const saved = Number(formColumnWidths[`detail_block_${blockKey}_${axis}`]);
      return Number.isFinite(saved) ? saved : 0;
    }

    function detailBlockTableWidth(block) {
      const table = block && block.querySelector ? block.querySelector("table[data-form-table]") : null;
      if (!table) return 0;
      const tableWidth = Array.from(table.querySelectorAll("col[data-form-col-key]")).reduce((total, col) => {
        const key = col.getAttribute("data-form-col-key");
        const fallback = Number(col.getAttribute("data-form-col-default")) || 120;
        return total + formColumnWidthPx(key, fallback);
      }, 0);
      const style = getComputedStyle(block);
      const borderX = parseFloat(style.borderLeftWidth || "0") + parseFloat(style.borderRightWidth || "0");
      return tableWidth + borderX;
    }

    function applyDetailBlockLayout(root = document) {
      const container = document.querySelector(".detail-editor");
      if (!container) return;
      let editorWidth = 0;
      container.querySelectorAll(".detail-section-block[data-detail-block]").forEach((block) => {
        if (root !== document && !root.contains(block) && block !== root && !block.contains(root)) return;
        const blockKey = block.getAttribute("data-detail-block");
        const width = detailBlockTableWidth(block);
        const x = detailBlockOffsetPx(blockKey, "x");
        const y = detailBlockOffsetPx(blockKey, "y");
        if (width > 0) block.style.width = `${width}px`;
        block.style.left = `${x}px`;
        block.style.top = `${y}px`;
        editorWidth = Math.max(editorWidth, width + Math.max(0, x));
      });
      if (editorWidth > 0) container.style.width = `${editorWidth}px`;
    }

    function attachDetailBlockDragHandles(root = document) {
      document.querySelectorAll(".detail-section-block[data-detail-block] > h3").forEach((handle) => {
        if (root !== document && !root.contains(handle) && handle !== root) return;
        if (handle.dataset.detailBlockDragBound === "1") return;
        handle.dataset.detailBlockDragBound = "1";
        handle.title = handle.title || "Drag to move block";
        handle.addEventListener("mousedown", (ev) => {
          if (ev.button != null && ev.button !== 0) return;
          ev.preventDefault();
          const block = handle.closest(".detail-section-block[data-detail-block]");
          const blockKey = block && block.getAttribute("data-detail-block");
          if (!blockKey) return;
          const startX = ev.clientX;
          const startY = ev.clientY;
          const startOffsetX = detailBlockOffsetPx(blockKey, "x");
          const startOffsetY = detailBlockOffsetPx(blockKey, "y");
          document.body.classList.add("is-dnd-dragging");
          const onMove = (mv) => {
            formColumnWidths[`detail_block_${blockKey}_x`] = startOffsetX + (mv.clientX - startX);
            formColumnWidths[`detail_block_${blockKey}_y`] = startOffsetY + (mv.clientY - startY);
            applyDetailBlockLayout();
          };
          const onUp = () => {
            window.removeEventListener("mousemove", onMove);
            window.removeEventListener("mouseup", onUp);
            document.body.classList.remove("is-dnd-dragging");
            persistColumnWidths();
          };
          window.addEventListener("mousemove", onMove);
          window.addEventListener("mouseup", onUp);
        });
        handle.addEventListener("dblclick", () => {
          const block = handle.closest(".detail-section-block[data-detail-block]");
          const blockKey = block && block.getAttribute("data-detail-block");
          if (!blockKey) return;
          formColumnWidths[`detail_block_${blockKey}_x`] = 0;
          formColumnWidths[`detail_block_${blockKey}_y`] = 0;
          applyDetailBlockLayout();
          persistColumnWidths();
        });
      });
    }

    function fillDetailSettings(data) {
      const folders = data && typeof data.folders === "object" && data.folders ? data.folders : {};
      const rice = data && typeof data.rice === "object" && data.rice ? data.rice : {};
      const gcSync = data && typeof data.google_calendar_sync === "object" && data.google_calendar_sync ? data.google_calendar_sync : googleCalendarSync;
      const defs = Array.isArray(data && data.roster_code_definitions) ? data.roster_code_definitions : [];
      detailSettingsPayload = { folders, rice, google_calendar_sync: gcSync, roster_code_definitions: defs };
      googleCalendarSync = {
        ...(googleCalendarSync || {}),
        enabled: !!(gcSync && gcSync.enabled),
        write: !!(gcSync && gcSync.write),
        client_secret_file: String((gcSync && gcSync.client_secret_file) || ""),
        token_file: String((gcSync && gcSync.token_file) || ""),
        service_account_file: String((gcSync && gcSync.service_account_file) || ""),
        nonwork_calendar_id: String((gcSync && gcSync.nonwork_calendar_id) || ""),
      };
      const systemFolder = document.getElementById("detail-system-folder");
      const dataFolder = document.getElementById("detail-data-folder");
      const brown = document.getElementById("detail-rice-brown");
      const other = document.getElementById("detail-rice-other");
      const gcClientSecret = document.getElementById("detail-gc-client-secret");
      const gcTokenFile = document.getElementById("detail-gc-token-file");
      const gcNonworkCalendar = document.getElementById("detail-gc-nonwork-calendar");
      if (systemFolder) systemFolder.value = folders.system_folder ?? "";
      if (dataFolder) dataFolder.value = folders.data_folder ?? "";
      if (brown) brown.value = rice.cooked_to_raw_brown ?? "";
      if (other) other.value = rice.cooked_to_raw_other ?? "";
      if (gcClientSecret) gcClientSecret.value = googleCalendarSync.client_secret_file || "";
      if (gcTokenFile) gcTokenFile.value = googleCalendarSync.token_file || "";
      if (gcNonworkCalendar) gcNonworkCalendar.value = googleCalendarSync.nonwork_calendar_id || "";
      renderRosterCodeDefinitions(defs);
      const detailEditor = document.querySelector(".detail-editor");
      if (detailEditor) {
        applyFormColumnWidths(detailEditor);
        attachFormColumnResizers(detailEditor);
        applyDetailBlockLayout(detailEditor);
        attachDetailBlockDragHandles(detailEditor);
        applyTableOffsets(detailEditor);
        attachTableDragHandles();
      }
      refreshRosterMaintReport();
    }

    function renderRosterCodeDefinitions(defs) {
      const box = document.getElementById("detail-code-definitions");
      if (!box) return;
      const rows = (Array.isArray(defs) ? defs : []).map((row, idx) => `
        <tr data-detail-code-row="${idx}">
          <th scope="row">${idx + 1}</th>
          <td><textarea rows="1" data-detail-code-field="pattern" data-detail-code-index="${idx}" spellcheck="false">${esc(row.pattern ?? "")}</textarea></td>
          <td><textarea rows="1" data-detail-code-field="label" data-detail-code-index="${idx}" spellcheck="false">${esc(row.label ?? "")}</textarea></td>
        </tr>
      `).join("");
      box.innerHTML = `<table class="detail-code-table" data-form-table>
        <colgroup>
          <col data-form-col-key="detail_code_row" data-form-col-default="54" />
          <col data-form-col-key="detail_code_pattern" data-form-col-default="120" />
          <col data-form-col-key="detail_code_definition" data-form-col-default="306" />
        </colgroup>
        <thead><tr><th data-form-col-key="detail_code_row"></th><th data-form-col-key="detail_code_pattern">Pattern</th><th data-form-col-key="detail_code_definition">Definition</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="3" class="maint-empty">No code definitions</td></tr>'}</tbody>
      </table>`;
      applyFormColumnWidths(box);
      attachFormColumnResizers(box);
      applyDetailBlockLayout(document.querySelector(".detail-editor") || box);
      attachDetailBlockDragHandles(document.querySelector(".detail-editor") || box);
      applyTableOffsets(box);
      attachTableDragHandles();
      box.querySelectorAll("[data-detail-code-field]").forEach((input) => {
        input.addEventListener("input", () => {
          setUnsavedChanges("系統參數");
          refreshRosterMaintReport();
        });
      });
    }

    function emptyRosterCodeDefinition() {
      return { pattern: "", label: "" };
    }

    function hideDetailRowMenu() {
      const menu = document.getElementById("detail-row-menu");
      if (!menu) return;
      menu.hidden = true;
      menu.removeAttribute("data-detail-row-index");
    }

    function showDetailRowMenu(ev, rowIndex) {
      const menu = document.getElementById("detail-row-menu");
      if (!menu) return;
      ev.preventDefault();
      menu.hidden = false;
      menu.setAttribute("data-detail-row-index", Number.isInteger(rowIndex) ? String(rowIndex) : "-1");
      const rect = menu.getBoundingClientRect();
      const left = Math.max(2, Math.min(ev.clientX, window.innerWidth - rect.width - 2));
      const top = Math.max(2, Math.min(ev.clientY, window.innerHeight - rect.height - 2));
      menu.style.left = `${left}px`;
      menu.style.top = `${top}px`;
    }

    function applyDetailRowAction(action, rowIndex) {
      const rows = collectRosterCodeDefinitions();
      const idx = Number.isInteger(rowIndex) && rowIndex >= 0 ? rowIndex : rows.length;
      if (action === "insert") {
        rows.splice(Math.min(idx, rows.length), 0, emptyRosterCodeDefinition());
      } else if (action === "delete") {
        if (idx < rows.length) rows.splice(idx, 1);
      } else if (action === "append") {
        rows.push(emptyRosterCodeDefinition());
      }
      setUnsavedChanges("系統參數");
      detailSettingsPayload.roster_code_definitions = rows;
      renderRosterCodeDefinitions(rows);
      refreshRosterMaintReport();
    }

    function collectRosterCodeDefinitions() {
      const rows = [];
      document.querySelectorAll("#detail-code-definitions [data-detail-code-index]").forEach((input) => {
        const idx = Number(input.getAttribute("data-detail-code-index"));
        const field = input.getAttribute("data-detail-code-field");
        if (!Number.isInteger(idx) || idx < 0 || !field) return;
        while (rows.length <= idx) rows.push({ pattern: "", label: "" });
        rows[idx][field] = input.value.trim();
      });
      return rows.filter((row) => row.pattern || row.label);
    }

    async function refreshDetailSettings() {
      showDetailError("");
      setDetailStatus("");
      try {
        const data = await loadDetailSettings();
        fillDetailSettings(data);
        clearUnsavedChanges("系統參數");
      } catch (e) {
        showDetailError(String(e && e.message ? e.message : e));
      }
    }

    async function saveDetailSettings() {
      showDetailError("");
      setDetailStatus("Saving...");
      const systemFolder = String(document.getElementById("detail-system-folder")?.value || "").trim();
      const dataFolder = String(document.getElementById("detail-data-folder")?.value || "").trim();
      const brown = Number(document.getElementById("detail-rice-brown")?.value);
      const other = Number(document.getElementById("detail-rice-other")?.value);
      const gcClientSecret = String(document.getElementById("detail-gc-client-secret")?.value || "").trim();
      const gcTokenFile = String(document.getElementById("detail-gc-token-file")?.value || "").trim();
      const gcNonworkCalendar = String(document.getElementById("detail-gc-nonwork-calendar")?.value || "").trim();
      if (!systemFolder || !dataFolder) {
        setDetailStatus("");
        showDetailError("System folder and data folder are required.");
        return;
      }
      if (!Number.isFinite(brown) || brown <= 0 || !Number.isFinite(other) || other <= 0) {
        setDetailStatus("");
        showDetailError("Rice cooked-to-raw ratios must be greater than zero.");
        return;
      }
      try {
        const data = await persistDetailSettings({
          system_folder: systemFolder,
          data_folder: dataFolder,
          cooked_to_raw_brown: brown,
          cooked_to_raw_other: other,
          google_calendar_sync: {
            ...(googleCalendarSync || {}),
            client_secret_file: gcClientSecret,
            token_file: gcTokenFile,
            service_account_file: "",
            nonwork_calendar_id: gcNonworkCalendar,
          },
          roster_code_definitions: collectRosterCodeDefinitions(),
        });
        fillDetailSettings(data);
        clearUnsavedChanges("系統參數");
        shoppingRiceConfig = {
          ...(shoppingRiceConfig || {}),
          cooked_to_raw_brown: data.rice.cooked_to_raw_brown,
          cooked_to_raw_other: data.rice.cooked_to_raw_other,
        };
        setDetailStatus(`Save Detail Settings ${new Date().toLocaleTimeString("en-GB")}`);
      } catch (e) {
        setDetailStatus("");
        showDetailError(String(e && e.message ? e.message : e));
      }
    }

    const CATALOG_NUTRIENT_LABELS = {
      kcal: "卡路里 (kCal)",
      protein_g: "蛋白質 (g)",
      carb_g: "碳水 (g)",
      sugar_g: "天然糖 (g)",
      cholesterol_mg: "膽固醇 (mg)",
      sodium_mg: "鈉 (mg)",
      calcium_mg: "鈣 (mg)",
      fat_total_g: "總脂肪 (g)",
      fat_sat_g: "飽和脂肪 (g)",
      fat_trans_g: "反式脂肪 (g)",
    };

    function catalogText(value) {
      return value == null ? "" : String(value);
    }

    function catalogNutrientText(value) {
      const n = Number(value);
      if (!Number.isFinite(n)) return catalogText(value);
      return n === 0 ? "" : n.toFixed(1);
    }

    function catalogNumberText(value) {
      const n = Number(value);
      if (!Number.isFinite(n)) return catalogText(value);
      return n === 0 ? "" : catalogText(value);
    }

    function emptyCatalogRow() {
      const nutrients = {};
      for (const key of (nutritionCatalogPayload.nutrient_keys || [])) nutrients[key] = 0;
      return {
        row_index: "",
        paused: false,
        category: "",
        name: "",
        min_g: "",
        max_g: "",
        daymax_g: "",
        nutrients,
      };
    }

    function catalogRowHtml(row, idx, nutrientKeys) {
      const textInput = (field, value, cls = "") =>
        `<td class="${cls}"><input type="text" class="catalog-cell-input" data-catalog-row="${idx}" data-catalog-field="${esc(field)}" value="${esc(catalogText(value))}" readonly /></td>`;
      const numberInput = (field, value) =>
        `<td class="catalog-num"><input type="text" inputmode="decimal" class="catalog-cell-input" data-catalog-row="${idx}" data-catalog-field="${esc(field)}" value="${esc(catalogNumberText(value))}" readonly /></td>`;
      const nutrients = row && typeof row.nutrients === "object" && row.nutrients ? row.nutrients : {};
      const nutrientCells = nutrientKeys.map((key) =>
        `<td class="catalog-num"><input type="text" inputmode="decimal" class="catalog-cell-input" data-catalog-row="${idx}" data-catalog-nutrient="${esc(key)}" value="${esc(catalogNutrientText(nutrients[key] ?? 0))}" readonly /></td>`
      ).join("");
      return `<tr data-catalog-index="${idx}" data-catalog-search="${esc(`${row.category || ""} ${row.name || ""}`.toLowerCase())}">
        <td class="catalog-paused"><input type="checkbox" data-catalog-row="${idx}" data-catalog-field="paused"${row.paused ? " checked" : ""} /></td>
        ${textInput("category", row.category, "catalog-category")}
        ${textInput("name", row.name, "catalog-name")}
        ${nutrientCells}
        ${numberInput("min_g", row.min_g)}
        ${numberInput("max_g", row.max_g)}
        ${numberInput("daymax_g", row.daymax_g)}
      </tr>`;
    }

    function applyCatalogFilter() {
      const query = String(document.getElementById("catalog-filter")?.value || "").trim().toLowerCase();
      document.querySelectorAll("#catalog-editor tr[data-catalog-index]").forEach((row) => {
        row.style.display = !query || String(row.getAttribute("data-catalog-search") || "").includes(query) ? "" : "none";
      });
    }

    function renderNutritionCatalog(data) {
      const editor = document.getElementById("catalog-editor");
      if (!editor) return;
      const nutrientKeys = Array.isArray(data && data.nutrient_keys) ? data.nutrient_keys : [];
      const rows = Array.isArray(data && data.rows) ? data.rows : [];
      nutritionCatalogPayload = { nutrient_keys: nutrientKeys, rows };
      const baseColumns = [
        ["paused", "暫停"],
        ["category", "類別"],
        ["name", "名稱"],
      ];
      const gramColumns = [
        ["min_g", "Min (g)"],
        ["max_g", "Max (g)"],
        ["daymax_g", "DayMax (g)"],
      ];
      const allColumns = [
        ...baseColumns,
        ...nutrientKeys.map((key) => [key, CATALOG_NUTRIENT_LABELS[key] || key]),
        ...gramColumns,
      ];
      const colGroup = allColumns.map(([key]) => `<col data-catalog-col-key="${esc(key)}" />`).join("");
      const headerCells = allColumns.map(([key, label]) =>
        `<th data-catalog-col-key="${esc(key)}">${esc(label)}<span class="catalog-col-resizer" title="Drag to resize column"></span></th>`
      ).join("");
      editor.innerHTML = `<table class="catalog-table">
        <colgroup>${colGroup}</colgroup>
        <thead><tr>${headerCells}</tr></thead>
        <tbody>${rows.map((row, idx) => catalogRowHtml(row, idx, nutrientKeys)).join("")}</tbody>
      </table>`;
      applyCatalogColumnWidths();
      attachCatalogColumnResizers();
      applyTableOffsets(editor);
      attachTableDragHandles();
      applyCatalogFilter();
    }

    function catalogColumnWidthPx(key) {
      const saved = Number(catalogColumnWidths[key]);
      if (Number.isFinite(saved)) return saved;
      if (key === "name") return 240;
      if (key === "category") return 110;
      if (key === "paused") return 58;
      return 82;
    }

    function applyCatalogColumnWidths() {
      let totalWidth = 0;
      document.querySelectorAll("#catalog-editor col[data-catalog-col-key]").forEach((col) => {
        const key = col.getAttribute("data-catalog-col-key");
        const width = catalogColumnWidthPx(key);
        totalWidth += width;
        col.style.width = `${width}px`;
      });
      const table = document.querySelector("#catalog-editor table.catalog-table");
      if (table && totalWidth > 0) table.style.width = `${totalWidth}px`;
    }

    function attachCatalogColumnResizers() {
      document.querySelectorAll("#catalog-editor th[data-catalog-col-key]").forEach((cell) => {
        const grip = cell.querySelector(".catalog-col-resizer");
        if (!grip || grip.dataset.bound === "1") return;
        grip.dataset.bound = "1";
        grip.addEventListener("mousedown", (ev) => {
          ev.preventDefault();
          ev.stopPropagation();
          const key = cell.getAttribute("data-catalog-col-key");
          const startX = ev.clientX;
          const startW = cell.getBoundingClientRect().width;
          const onMove = (mv) => {
            catalogColumnWidths[key] = Math.max(0, startW + (mv.clientX - startX));
            applyCatalogColumnWidths();
          };
          const onUp = () => {
            window.removeEventListener("mousemove", onMove);
            window.removeEventListener("mouseup", onUp);
            persistColumnWidths();
          };
          window.addEventListener("mousemove", onMove);
          window.addEventListener("mouseup", onUp);
        });
      });
    }

    function collectNutritionCatalogRows() {
      return (nutritionCatalogPayload.rows || []).map((row, idx) => {
        const next = {
          row_index: row.row_index,
          paused: !!document.querySelector(`#catalog-editor input[data-catalog-row="${idx}"][data-catalog-field="paused"]`)?.checked,
          category: document.querySelector(`#catalog-editor input[data-catalog-row="${idx}"][data-catalog-field="category"]`)?.value || "",
          name: document.querySelector(`#catalog-editor input[data-catalog-row="${idx}"][data-catalog-field="name"]`)?.value || "",
          min_g: document.querySelector(`#catalog-editor input[data-catalog-row="${idx}"][data-catalog-field="min_g"]`)?.value || "",
          max_g: document.querySelector(`#catalog-editor input[data-catalog-row="${idx}"][data-catalog-field="max_g"]`)?.value || "",
          daymax_g: document.querySelector(`#catalog-editor input[data-catalog-row="${idx}"][data-catalog-field="daymax_g"]`)?.value || "",
          nutrients: {},
        };
        for (const key of (nutritionCatalogPayload.nutrient_keys || [])) {
          next.nutrients[key] = document.querySelector(`#catalog-editor input[data-catalog-row="${idx}"][data-catalog-nutrient="${key}"]`)?.value || "0";
        }
        return next;
      });
    }

    function showCatalogError(message) {
      const err = document.getElementById("catalog-err");
      if (!err) return;
      err.textContent = message || "";
      err.style.display = message ? "block" : "none";
    }

    function setCatalogStatus(message) {
      const status = document.getElementById("catalog-status");
      if (status) status.textContent = message || "";
    }

    async function refreshNutritionCatalog() {
      try {
        showCatalogError("");
        renderNutritionCatalog(await loadNutritionCatalog());
        clearUnsavedChanges("營養清單");
      } catch (x) {
        showCatalogError(String(x));
      }
    }

    function activeCatalogRowIndex() {
      const activeRow = document.activeElement && document.activeElement.closest
        ? document.activeElement.closest("#catalog-editor tr[data-catalog-index]")
        : null;
      const activeIndex = activeRow ? Number(activeRow.getAttribute("data-catalog-index")) : NaN;
      if (Number.isInteger(activeIndex) && activeIndex >= 0) return activeIndex;
      return Number.isInteger(catalogCursorRowIndex) && catalogCursorRowIndex >= 0
        ? catalogCursorRowIndex
        : null;
    }

    function insertNutritionCatalogRow() {
      const rows = collectNutritionCatalogRows();
      const cursorIndex = activeCatalogRowIndex();
      const insertIndex = cursorIndex == null ? rows.length : Math.min(cursorIndex, rows.length);
      rows.splice(insertIndex, 0, emptyCatalogRow());
      nutritionCatalogPayload.rows = rows;
      renderNutritionCatalog(nutritionCatalogPayload);
      setUnsavedChanges("營養清單");
      catalogCursorRowIndex = insertIndex;
      document.querySelector(`#catalog-editor tr[data-catalog-index="${insertIndex}"] input[data-catalog-field="category"]`)?.focus();
    }

    function removeNutritionCatalogRow(idx) {
      nutritionCatalogPayload.rows = collectNutritionCatalogRows().filter((_, rowIdx) => rowIdx !== idx);
      renderNutritionCatalog(nutritionCatalogPayload);
      setUnsavedChanges("營養清單");
      setCatalogStatus("Row removed locally. Save Catalog to persist.");
    }

    function hideCatalogRowMenu() {
      const menu = document.getElementById("catalog-row-menu");
      if (!menu) return;
      menu.hidden = true;
      menu.removeAttribute("data-catalog-index");
    }

    function showCatalogRowMenu(ev, idx) {
      const menu = document.getElementById("catalog-row-menu");
      if (!menu) return;
      catalogCursorRowIndex = idx;
      menu.hidden = false;
      menu.setAttribute("data-catalog-index", String(idx));
      const rect = menu.getBoundingClientRect();
      const left = Math.max(2, Math.min(ev.clientX, window.innerWidth - rect.width - 2));
      const top = Math.max(2, Math.min(ev.clientY, window.innerHeight - rect.height - 2));
      menu.style.left = `${left}px`;
      menu.style.top = `${top}px`;
    }

    function catalogCellInputFrom(input, rowDelta, colDelta) {
      const row = input && input.closest ? input.closest("tr[data-catalog-index]") : null;
      const cell = input && input.closest ? input.closest("td") : null;
      if (!row || !cell) return null;
      const rows = Array.from(document.querySelectorAll("#catalog-editor tr[data-catalog-index]"))
        .filter((item) => item.style.display !== "none");
      const rowPos = rows.indexOf(row);
      const targetRow = rows[rowPos + rowDelta];
      const targetCell = (targetRow || row).cells[cell.cellIndex + colDelta];
      return targetCell ? targetCell.querySelector("input") : null;
    }

    function focusCatalogCell(input) {
      if (!input) return;
      input.focus();
      input.scrollIntoView({ block: "nearest", inline: "nearest" });
    }

    const catalogDirectKeyTimers = new WeakMap();

    function beginCatalogCellEdit(input, replaceValue = false) {
      if (!input || input.type === "checkbox") return;
      input.dataset.catalogOriginalValue = input.value;
      input.readOnly = false;
      input.dataset.catalogEditing = "1";
      input.dataset.catalogReplaceOnComposition = replaceValue ? "1" : "";
      input.focus();
      if (replaceValue) {
        input.value = "";
      }
      const pos = replaceValue ? 0 : input.value.length;
      input.setSelectionRange(pos, pos);
    }

    function queueCatalogDirectKey(input, key) {
      if (!input || !key) return;
      const oldTimer = catalogDirectKeyTimers.get(input);
      if (oldTimer) clearTimeout(oldTimer);
      input.dataset.catalogPendingDirectKey = key;
      const timer = setTimeout(() => {
        catalogDirectKeyTimers.delete(input);
        if (input.dataset.catalogEditing !== "1" || input.dataset.catalogPendingDirectKey !== key) return;
        input.value = `${key}${input.value || ""}`;
        delete input.dataset.catalogPendingDirectKey;
        delete input.dataset.catalogReplaceOnComposition;
        const pos = String(input.value || "").length;
        input.setSelectionRange(pos, pos);
        input.dispatchEvent(new Event("input", { bubbles: true }));
      }, 40);
      catalogDirectKeyTimers.set(input, timer);
    }

    function normalizeCatalogInputValue(input) {
      if (!input) return;
      if (input.hasAttribute("data-catalog-nutrient")) {
        input.value = catalogNutrientText(input.value);
        return;
      }
      const field = input.getAttribute("data-catalog-field");
      if (field === "min_g" || field === "max_g" || field === "daymax_g") {
        input.value = catalogNumberText(input.value);
      }
    }

    function endCatalogCellEdit(input, options = {}) {
      if (!input || input.type === "checkbox") return;
      if (options.cancel) {
        input.value = input.dataset.catalogOriginalValue || "";
        input.readOnly = true;
        delete input.dataset.catalogEditing;
        delete input.dataset.catalogOriginalValue;
        delete input.dataset.catalogReplaceOnComposition;
        delete input.dataset.catalogPendingDirectKey;
        const timer = catalogDirectKeyTimers.get(input);
        if (timer) clearTimeout(timer);
        catalogDirectKeyTimers.delete(input);
        return;
      }
      normalizeCatalogInputValue(input);
      input.readOnly = true;
      delete input.dataset.catalogEditing;
      delete input.dataset.catalogOriginalValue;
      delete input.dataset.catalogReplaceOnComposition;
      delete input.dataset.catalogPendingDirectKey;
      const timer = catalogDirectKeyTimers.get(input);
      if (timer) clearTimeout(timer);
      catalogDirectKeyTimers.delete(input);
    }

    function moveCatalogActiveCell(input, key) {
      const delta = {
        ArrowUp: [-1, 0],
        ArrowDown: [1, 0],
        ArrowLeft: [0, -1],
        ArrowRight: [0, 1],
        Enter: [0, 1],
      }[key];
      if (!delta) return false;
      const next = catalogCellInputFrom(input, delta[0], delta[1]);
      if (!next) return false;
      if (input.dataset) input.dataset.skipAutosaveOnce = "1";
      focusCatalogCell(next);
      return true;
    }

    function catalogInputClipboardValue(input) {
      if (!input) return "";
      return input.type === "checkbox" ? (input.checked ? "TRUE" : "FALSE") : input.value;
    }

    function pasteCatalogInputValue(input, value) {
      if (!input) return;
      if (input.type === "checkbox") {
        input.checked = /^(1|true|yes|y|checked)$/i.test(String(value || "").trim());
        setUnsavedChanges("營養清單");
        return;
      }
      input.value = value;
      endCatalogCellEdit(input);
      setUnsavedChanges("營養清單");
    }

    function catalogClipboardMatrix(text) {
      return String(text || "")
        .replace(/\r/g, "")
        .replace(/\n$/, "")
        .split("\n")
        .map((line) => line.split("\t"));
    }

    function pasteCatalogClipboard(startInput, text) {
      const matrix = catalogClipboardMatrix(text);
      if (!matrix.length) return;
      let lastInput = startInput;
      matrix.forEach((values, rowIdx) => {
        values.forEach((value, colIdx) => {
          const input = catalogCellInputFrom(startInput, rowIdx, colIdx);
          if (!input) return;
          pasteCatalogInputValue(input, value);
          lastInput = input;
        });
      });
      focusCatalogCell(lastInput);
    }

    function saveActiveEditor() {
      if (activePanel === "planner") {
        return saveTargetEditor("planner");
      }
      if (activePanel === "maint") {
        return saveMaintEditor();
      }
      if (activePanel !== "config") return Promise.resolve();
      const catalog = document.querySelector('.config-view[data-config-view="catalog"]');
      if (catalog && catalog.style.display !== "none") {
        return saveNutritionCatalog();
      } else if (document.querySelector('.config-view[data-config-view="details"]')?.style.display !== "none") {
        return saveDetailSettings();
      } else {
        return saveTargetEditor("config");
      }
    }

    async function saveNutritionCatalog() {
      const btn = document.getElementById("catalog-save");
      if (btn) btn.disabled = true;
      showCatalogError("");
      setCatalogStatus("");
      try {
        const saved = await persistNutritionCatalog({ rows: collectNutritionCatalogRows() });
        renderNutritionCatalog(saved);
        clearUnsavedChanges("營養清單");
        shoppingCatalogByName = {};
        setCatalogStatus(`Save Catalog ${new Date().toLocaleTimeString("en-GB")}`);
      } catch (x) {
        showCatalogError(String(x));
      } finally {
        if (btn) btn.disabled = false;
      }
    }

    async function refreshTargetEditor(options = {}) {
      try {
        showTargetError("");
        renderTargetEditors(await loadTargets());
        clearUnsavedChanges("目標");
        if (options && options.focusDob) requestAnimationFrame(focusTargetDob);
      } catch (x) {
        showTargetError(String(x));
      }
    }

    async function saveTargetEditor(source = "config", options = {}) {
      const btn = document.getElementById(source === "planner" ? "planner-target-save" : "target-save");
      if (btn) btn.disabled = true;
      const applyBtn = document.getElementById("target-apply-preview");
      if (source === "config" && applyBtn) applyBtn.disabled = true;
      showTargetError("", source);
      setTargetStatus("");
      try {
        const profile = source === "config" ? collectTargetProfile() : (targetPayload.profile || {});
        const targetSettings = source === "config" ? collectTargetSettings() : (targetPayload.target_settings || cloneTargetSettingDefaults());
        if (source === "config") {
          if (profile.dob && targetAgeFromDob(profile.dob) == null) {
            throw new Error("DOB must be a valid date and cannot be in the future.");
          }
          if (profile.gender && !["male", "female"].includes(profile.gender)) {
            throw new Error("性別 must be 男 or 女.");
          }
          if (profile.height_cm != null && (!Number.isFinite(profile.height_cm) || profile.height_cm <= 0)) {
            throw new Error("身高 must be greater than zero.");
          }
          if (profile.weight_kg != null && (!Number.isFinite(profile.weight_kg) || profile.weight_kg <= 0)) {
            throw new Error("體重 must be greater than zero.");
          }
          if (profile.monthly_weight_change_kg != null && !Number.isFinite(profile.monthly_weight_change_kg)) {
            throw new Error("體重變化 must be numeric.");
          }
          (profile.weight_history || []).forEach((row, idx) => {
            const weight = Number(row.weight_kg);
            if (!Number.isFinite(weight) || weight <= 0) {
              throw new Error(`體重記錄 row ${idx + 1} must be greater than zero.`);
            }
            if (!/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(String(row.recorded_at || ""))) {
              throw new Error(`體重記錄 row ${idx + 1} 更新日期 must use YYYY-MM-DD HH:MM:SS.`);
            }
          });
          ["workday", "nonworkday"].forEach((profileKey) => {
            TARGET_SETTING_ROWS.forEach(({ key, text, label }) => {
              const value = Number(targetSettings[profileKey] && targetSettings[profileKey][key]);
              if (!Number.isFinite(value) || value < 0) {
                throw new Error(`${profileKey} ${(text || label || "").replace(/<br>/g, " ")} must be zero or greater.`);
              }
            });
          });
        }
        const payload = {
          headers: targetPayload.headers || [],
          workday: Array.isArray(options.targetRows && options.targetRows.workday)
            ? options.targetRows.workday
            : collectTargetValues("workday", source),
          nonworkday: Array.isArray(options.targetRows && options.targetRows.nonworkday)
            ? options.targetRows.nonworkday
            : collectTargetValues("nonworkday", source),
        };
        if (source === "config") {
          payload.profile = profile;
          payload.target_settings = targetSettings;
        }
        const saved = await persistTargets(payload);
        if (source === "config" && (!saved.profile || typeof saved.profile !== "object")) {
          throw new Error("Save failed: server response did not include profile. Restart the Meal Planner server and save again.");
        }
        if (source === "config" && (!saved.target_settings || typeof saved.target_settings !== "object")) {
          throw new Error("Save failed: server response did not include target settings. Restart the Meal Planner server and save again.");
        }
        updateTargetPayloadAfterSave(saved, source, payload);
        resetTargetInputBaselinesAfterSave();
        resetTargetDirtySnapshot();
        clearUnsavedChanges("目標");
        setTargetStatus(`${options.statusPrefix || "儲存指標 / Save Targets"} ${new Date().toLocaleTimeString("en-GB")}`);
        return true;
      } catch (x) {
        showTargetError(String(x), source);
        setUnsavedChanges("目標");
        return false;
      } finally {
        if (btn) btn.disabled = false;
        if (source === "config" && applyBtn) applyBtn.disabled = false;
      }
    }

