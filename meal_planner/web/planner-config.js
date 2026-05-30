    function emptyNutCells(headers) {
      const n = (headers && headers.length) || 10;
      return Array.from({ length: n }, () => '<td class="nut">—</td>').join("");
    }

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

    function renderTargetEditorTable(editorId, data, inputSource) {
      const editor = document.getElementById(editorId);
      if (!editor) return;
      const headers = Array.isArray(data && data.headers) ? data.headers : [];
      const keys = Array.isArray(data && data.nutrient_keys) ? data.nutrient_keys : [];
      const rows = data && typeof data.indicator_rows === "object" && data.indicator_rows ? data.indicator_rows : {};
      const workday = Array.isArray(rows.workday) ? rows.workday : [];
      const nonworkday = Array.isArray(rows.nonworkday) ? rows.nonworkday : [];
      targetPayload = { headers, nutrient_keys: keys, indicator_rows: { workday, nonworkday } };
      const n = Math.max(headers.length, keys.length, workday.length, nonworkday.length);
      const widthKey = (idx) => keys[idx] || `target_${idx}`;
      const headingCells = Array.from({ length: n }, (_, i) =>
        `<th data-target-col-key="${esc(widthKey(i))}">${esc(headers[i] || keys[i] || `Target ${i + 1}`)}<span class="target-col-resizer" title="Drag to resize column"></span></th>`
      ).join("");
      const colCells = Array.from({ length: n }, (_, i) =>
        `<col data-target-col-key="${esc(widthKey(i))}" />`
      ).join("");
      const rowCells = (profile, values) => Array.from({ length: n }, (_, i) =>
        `<td><input data-target-source="${esc(inputSource)}" data-target-profile="${esc(profile)}" data-target-index="${i}" value="${esc(values[i] ?? "")}" /></td>`
      ).join("");
      editor.innerHTML = `<table class="target-table">
        <colgroup><col class="target-profile-col" />${colCells}</colgroup>
        <thead><tr><th class="target-profile-head">Target</th>${headingCells}</tr></thead>
        <tbody>
          <tr><th scope="row" class="target-profile-head">Workday</th>${rowCells("workday", workday)}</tr>
          <tr><th scope="row" class="target-profile-head">Non-workday</th>${rowCells("nonworkday", nonworkday)}</tr>
        </tbody>
      </table>`;
      applyTargetEditorLayout();
      attachTargetEditorResizers();
      applyTableOffsets(editor);
      attachTableDragHandles();
    }

    function renderTargetEditors(data) {
      renderTargetEditorTable("target-editor", data, "config");
    }

    function targetColumnWidthPx(key) {
      const width = Number(targetColumnWidths[key]);
      return Number.isFinite(width) ? width : 82;
    }

    function applyTargetEditorLayout() {
      document.querySelectorAll(".target-editor").forEach((editor) => {
        let tableWidth = 96;
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
            targetColumnWidths[key] = Math.max(0, startWidth + (mv.clientX - startX));
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

    function fillDetailSettings(data) {
      const rice = data && typeof data.rice === "object" && data.rice ? data.rice : {};
      const defs = Array.isArray(data && data.roster_code_definitions) ? data.roster_code_definitions : [];
      detailSettingsPayload = { rice, roster_code_definitions: defs };
      const brown = document.getElementById("detail-rice-brown");
      const other = document.getElementById("detail-rice-other");
      if (brown) brown.value = rice.cooked_to_raw_brown ?? "";
      if (other) other.value = rice.cooked_to_raw_other ?? "";
      renderRosterCodeDefinitions(defs);
      const detailEditor = document.querySelector(".detail-editor");
      if (detailEditor) {
        applyFormColumnWidths(detailEditor);
        attachFormColumnResizers(detailEditor);
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
          <td><textarea data-auto-row-height data-detail-code-field="pattern" data-detail-code-index="${idx}" spellcheck="false">${esc(row.pattern ?? "")}</textarea></td>
          <td><textarea data-auto-row-height data-detail-code-field="label" data-detail-code-index="${idx}" spellcheck="false">${esc(row.label ?? "")}</textarea></td>
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
      bindAutoRowHeight(box);
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
      const brown = Number(document.getElementById("detail-rice-brown")?.value);
      const other = Number(document.getElementById("detail-rice-other")?.value);
      if (!Number.isFinite(brown) || brown <= 0 || !Number.isFinite(other) || other <= 0) {
        setDetailStatus("");
        showDetailError("Rice cooked-to-raw ratios must be greater than zero.");
        return;
      }
      try {
        const data = await persistDetailSettings({
          cooked_to_raw_brown: brown,
          cooked_to_raw_other: other,
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

    function beginCatalogCellEdit(input, replaceValue = false) {
      if (!input || input.type === "checkbox") return;
      input.readOnly = false;
      input.dataset.catalogEditing = "1";
      input.focus();
      if (replaceValue) {
        input.value = "";
      }
      const pos = replaceValue ? 0 : input.value.length;
      input.setSelectionRange(pos, pos);
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

    function endCatalogCellEdit(input) {
      if (!input || input.type === "checkbox") return;
      normalizeCatalogInputValue(input);
      input.readOnly = true;
      delete input.dataset.catalogEditing;
    }

    function moveCatalogActiveCell(input, key) {
      const delta = {
        ArrowUp: [-1, 0],
        ArrowDown: [1, 0],
        ArrowLeft: [0, -1],
        ArrowRight: [0, 1],
      }[key];
      if (!delta) return false;
      const next = catalogCellInputFrom(input, delta[0], delta[1]);
      if (!next) return false;
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
        saveTargetEditor("planner");
        return;
      }
      if (activePanel === "maint") {
        saveMaintEditor();
        return;
      }
      if (activePanel !== "config") return;
      const catalog = document.querySelector('.config-view[data-config-view="catalog"]');
      if (catalog && catalog.style.display !== "none") {
        saveNutritionCatalog();
      } else if (document.querySelector('.config-view[data-config-view="details"]')?.style.display !== "none") {
        saveDetailSettings();
      } else {
        saveTargetEditor("config");
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

    async function refreshTargetEditor() {
      try {
        showTargetError("");
        renderTargetEditors(await loadTargets());
        clearUnsavedChanges("目標");
      } catch (x) {
        showTargetError(String(x));
      }
    }

    async function saveTargetEditor(source = "config") {
      const btn = document.getElementById(source === "planner" ? "planner-target-save" : "target-save");
      if (btn) btn.disabled = true;
      showTargetError("", source);
      setTargetStatus("");
      try {
        const saved = await persistTargets({
          headers: targetPayload.headers || [],
          workday: collectTargetValues("workday", source),
          nonworkday: collectTargetValues("nonworkday", source),
        });
        renderTargetEditors(saved);
        clearUnsavedChanges("目標");
        await loadMemoryPayload();
        renderFromMemory(captureViewportAnchor());
        setTargetStatus(`Save Targets ${new Date().toLocaleTimeString("en-GB")}`);
      } catch (x) {
        showTargetError(String(x), source);
      } finally {
        if (btn) btn.disabled = false;
      }
    }

