    function emptyNutCells(headers) {
      const n = (headers && headers.length) || 10;
      return Array.from({ length: n }, () => '<td class="nut">—</td>').join("");
    }

    let targetSelectedBlocks = new Set();
    let targetBlockSuppressNextClickClear = false;
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
      { key: "protein_g_per_kg", label: "蛋白質<br>protein g/kg", text: "蛋白質 g/kg", guide: "建議：1.2-1.6", nutrient: "protein_g" },
      { key: "protein_range_band", label: "蛋白質範圍<br>protein range band", text: "蛋白質 range band", guide: "建議：10g；蛋白質 = 中位 ± range band", nutrient: "protein_g" },
      { key: "carb_pct", label: "碳水<br>carb % kcal", text: "碳水 % kcal", guide: "建議：45-65%", nutrient: "carb_g" },
      { key: "calcium_mg", label: "鈣<br>calcium mg", text: "鈣 mg", guide: "男19-70 >=1000；51+ 可用 >=1200", nutrient: "calcium_mg" },
      { key: "sodium_mg", label: "鈉<br>sodium mg", text: "鈉 mg", guide: "14歲以上 guideline <2300", nutrient: "sodium_mg" },
      { key: "sugar_g", label: "天然糖<br>natural sugar g", text: "天然糖 g", guide: "無 guideline；自訂", nutrient: "sugar_g" },
      { key: "cholesterol_mg", label: "膽固醇<br>cholesterol mg", text: "膽固醇 mg", guide: "無固定 guideline；自訂", nutrient: "cholesterol_mg" },
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

    function targetEditableInputsInRow(row) {
      return Array.from(row?.querySelectorAll("input,select,textarea") || [])
        .filter((input) => !input.disabled && !input.readOnly && input.type !== "hidden");
    }

    function moveTargetEditableCellRight(input) {
      const row = input?.closest("tr");
      const table = input?.closest("table");
      if (!row || !table) return false;
      const sameRow = targetEditableInputsInRow(row);
      const idx = sameRow.indexOf(input);
      const nextInRow = idx >= 0 ? sameRow[idx + 1] : null;
      let next = nextInRow || null;
      if (!next) {
        const rows = Array.from(table.querySelectorAll("tbody tr"));
        const rowIdx = rows.indexOf(row);
        for (let i = rowIdx + 1; i < rows.length; i += 1) {
          const first = targetEditableInputsInRow(rows[i])[0];
          if (first) {
            next = first;
            break;
          }
        }
      }
      if (!next) return false;
      next.focus({ preventScroll: true });
      if (typeof next.select === "function") next.select();
      return true;
    }

    function bindTargetEnterMoveRight(root) {
      root.querySelectorAll("input,select,textarea").forEach((input) => {
        if (input.dataset.targetEnterMoveBound === "1") return;
        input.dataset.targetEnterMoveBound = "1";
        input.addEventListener("keydown", (ev) => {
          if (ev.key !== "Enter" || ev.shiftKey || ev.ctrlKey || ev.altKey || ev.metaKey || ev.isComposing) return;
          ev.preventDefault();
          input.dispatchEvent(new Event("change", { bubbles: true }));
          moveTargetEditableCellRight(input);
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
        return `<th data-target-col-key="${esc(nutrientWidthKey)}" title="${esc(title)}">${targetNutrientHeaderHtml(key, headers[i] || keys[i] || `Target ${i + 1}`)}<span class="target-col-resizer" title="Drag to resize column"></span></th>`;
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
          <tr><th scope="row" class="target-profile-head">Workday</th>${rowCells("workday", workday)}</tr>
          <tr><th scope="row" class="target-profile-head">Non-workday</th>${rowCells("nonworkday", nonworkday)}</tr>
        </tbody>
      </table>`;
      applyTargetEditorLayout();
      attachTargetEditorResizers();
      applyTableOffsets(editor);
      attachTableDragHandles();
      bindTargetEnterMoveRight(editor);
    }

    function renderTargetEditors(data) {
      fillTargetProfile(data && data.profile);
      renderTargetCalculationSettings(data && data.target_settings);
      renderTargetEditorTable("target-editor", data, "config");
      renderTargetPreviewTable();
      const targetBlocks = document.querySelector(".target-config-blocks");
      if (targetBlocks) attachFormColumnResizers(targetBlocks);
      applyTargetBlockLayout();
      attachTargetBlockDragHandles();
      setTimeout(applyTargetBlockLayout, 0);
      setTimeout(applyTargetBlockLayout, 100);
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

    function targetSettingTooltip(row) {
      const base = String(row && row.guide ? row.guide : "").trim();
      if (!row || !row.nutrient) return base;
      const workday = currentTargetIndicatorFor(row.nutrient, "workday");
      const nonworkday = currentTargetIndicatorFor(row.nutrient, "nonworkday");
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
      const proteinMidTitle = "蛋白質中位 = 體重 * 蛋白質 g/kg。唯讀，由個人資料及該 row g/kg 計算。";
      const valueCol = () => `<col data-form-col-key="target_calc_value" data-form-col-default="72" />`;
      const settingCols = [
        valueCol(),
        ...TARGET_SETTING_ROWS.flatMap((row) => {
          if (row.key === "calorie_range_band") return [valueCol(), valueCol()];
          if (row.key === "protein_g_per_kg") return [valueCol(), valueCol()];
          return [valueCol()];
        }),
      ].join("");
      const settingHeads = [
        `<th data-form-col-key="target_calc_value" title="${esc(bmrTitle)}">基礎代謝<br>BMR kcal</th>`,
        ...TARGET_SETTING_ROWS.flatMap((row) => {
          const head = `<th data-form-col-key="target_calc_value" title="${esc(targetSettingTooltip(row))}">${row.label}</th>`;
          if (row.key === "calorie_range_band") return [`<th data-form-col-key="target_calc_value" title="${esc(tdeeTitle)}">每日消耗<br>TDEE kcal</th>`, head];
          if (row.key === "protein_g_per_kg") return [head, `<th data-form-col-key="target_calc_value" title="${esc(proteinMidTitle)}">蛋白質中位<br>protein mid g</th>`];
          return [head];
        }),
      ].join("");
      const readonlyCell = (profile, metric, title) => `
        <td class="target-calc-readonly" data-form-col-key="target_calc_value" data-target-calc-readonly-profile="${esc(profile)}" data-target-calc-readonly-metric="${esc(metric)}" title="${esc(title)}">${esc(targetCalculationReadonlyValue(profile, metric, values))}</td>
      `;
      const inputCell = (profile, key) => `
        <td data-form-col-key="target_calc_value">
          <input type="number" step="0.001" min="0" data-target-setting-profile="${esc(profile)}" data-target-setting-key="${esc(key)}" value="${esc(targetSettingInputValue(values[profile][key]))}" />
        </td>
      `;
      const rowHtml = (profile, label) => {
        const cells = [
          readonlyCell(profile, "bmr", bmrTitle),
          ...TARGET_SETTING_ROWS.flatMap(({ key }) => {
            if (key === "calorie_range_band") return [readonlyCell(profile, "tdee", tdeeTitle), inputCell(profile, key)];
            if (key === "protein_g_per_kg") return [inputCell(profile, key), readonlyCell(profile, "protein_mid", proteinMidTitle)];
            return [inputCell(profile, key)];
          }),
        ].join("");
        return `
          <tr>
            <th scope="row" data-form-col-key="target_calc_profile">${esc(label)}</th>
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
        <tbody>${rowHtml("workday", "Workday")}${rowHtml("nonworkday", "Non-workday")}</tbody>
      </table>`;
      box.querySelectorAll("input[data-target-setting-key]").forEach((input) => {
        input.addEventListener("input", renderTargetPreviewTable);
        input.addEventListener("change", renderTargetPreviewTable);
      });
      bindTargetEnterMoveRight(box);
      applyFormColumnWidths(box);
      attachFormColumnResizers(box);
    }

    function numberOrNull(raw) {
      const n = Number(raw);
      return Number.isFinite(n) ? n : null;
    }

    function currentTargetProfileFromInputs() {
      return {
        age: numberOrNull(document.getElementById("target-profile-age")?.value),
        dob: String(document.getElementById("target-profile-dob")?.value || "").trim(),
        gender: String(document.getElementById("target-profile-gender")?.value || "").trim(),
        height_cm: numberOrNull(document.getElementById("target-profile-height")?.value),
        weight_kg: numberOrNull(document.getElementById("target-profile-weight")?.value),
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

    function calculatedTargetRow(profileKey) {
      const profile = currentTargetProfileFromInputs();
      const settings = collectTargetSettings();
      const values = settings[profileKey] || {};
      const bmr = targetBmr(profile);
      if (bmr == null) return Array(10).fill("");
      const activity = Number(values.activity_factor);
      const band = Number(values.calorie_range_band);
      const hasKcal = Number.isFinite(activity) && Number.isFinite(band);
      const midKcal = hasKcal ? bmr * activity : NaN;
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
        : `BMR = 10*體重 + 6.25*身高 - 5*年齡 ${profile.gender === "male" ? "+ 5" : "- 161"}。TDEE = BMR * activity factor。`;
      const pair = (settingKey, unit = "") => {
        const settings = collectTargetSettings();
        const w = targetSettingInputValue(settings.workday[settingKey]);
        const n = targetSettingInputValue(settings.nonworkday[settingKey]);
        return `返工 ${w}${unit}；非返工 ${n}${unit}`;
      };
      return {
        kcal: `${base} 卡路里 = TDEE ± range band；${pair("activity_factor")} activity factor；${pair("calorie_range_band", " kcal")} range band。`,
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

    function fillTargetProfile(profile) {
      const data = profile && typeof profile === "object" ? profile : {};
      const dob = document.getElementById("target-profile-dob");
      const age = document.getElementById("target-profile-age");
      const gender = document.getElementById("target-profile-gender");
      const height = document.getElementById("target-profile-height");
      const weight = document.getElementById("target-profile-weight");
      if (dob) dob.value = data.dob ?? "";
      if (age) age.value = data.dob ? (targetAgeFromDob(data.dob) ?? "") : (data.age ?? "");
      if (gender) gender.value = data.gender ?? "";
      if (height) height.value = data.height_cm ?? "";
      if (weight) {
        weight.value = data.weight_kg ?? "";
        weight.dataset.targetOriginalWeight = data.weight_kg ?? "";
      }
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
        gender: data.gender ?? "",
        height_cm: data.height_cm ?? null,
        weight_kg: data.weight_kg ?? null,
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

    function targetAgeFromDob(dobValue) {
      const text = String(dobValue || "").trim();
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
      setUnsavedChanges("目標");
      renderTargetPreviewTable();
      return true;
    }

    function bindTargetProfileInputs() {
      const dob = document.getElementById("target-profile-dob");
      if (dob && dob.dataset.targetDobBound !== "1") {
        dob.dataset.targetDobBound = "1";
        dob.addEventListener("input", syncTargetAgeFromDob);
        dob.addEventListener("change", syncTargetAgeFromDob);
      }
      ["target-profile-gender", "target-profile-height", "target-profile-weight"].forEach((id) => {
        const input = document.getElementById(id);
        if (!input || input.dataset.targetProfilePreviewBound === "1") return;
        input.dataset.targetProfilePreviewBound = "1";
        input.addEventListener("input", renderTargetPreviewTable);
        input.addEventListener("change", () => {
          if (id === "target-profile-weight") {
            appendProfileWeightToHistory();
          } else {
            renderTargetPreviewTable();
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
            <input type="number" step="0.1" inputmode="decimal" data-weight-history-field="weight_kg" data-weight-history-index="${idx}" data-weight-original-value="${esc(item.weight_kg ?? "")}" value="${esc(item.weight_kg ?? "")}" />
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
        <thead><tr><th data-form-col-key="target_weight_history_weight">體重 (kg)</th><th data-form-col-key="target_weight_history_date">更新日期</th><th data-form-col-key="target_weight_history_delete"></th></tr></thead>
        <tbody>${rows || `<tr><td colspan="3" class="target-empty-row">No weight history</td></tr>`}</tbody>
      </table>`;
      box.querySelectorAll('input[data-weight-history-field="weight_kg"]').forEach((input) => {
        input.addEventListener("input", () => {
          syncProfileWeightFromHistory();
          renderTargetPreviewTable();
        });
        input.addEventListener("change", () => {
          stampTargetWeightDate(input);
          syncProfileWeightFromHistory();
          renderTargetPreviewTable();
        });
      });
      box.querySelectorAll('input[data-weight-history-field="recorded_at"]').forEach((input) => {
        input.addEventListener("input", () => {
          syncProfileWeightFromHistory();
          renderTargetPreviewTable();
        });
        input.addEventListener("change", () => {
          syncProfileWeightFromHistory();
          renderTargetPreviewTable();
        });
      });
      box.querySelectorAll("button[data-weight-history-delete]").forEach((btn) => {
        btn.addEventListener("click", () => {
          btn.closest("tr[data-weight-history-row]")?.remove();
          syncProfileWeightFromHistory();
          setUnsavedChanges("目標");
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
      applyFormColumnWidths(container);
      container.classList.add("is-draggable-layout");
      let defaultY = 0;
      let maxRight = 0;
      let maxBottom = 0;
      container.querySelectorAll(".target-section-block[data-target-block]").forEach((block) => {
        const blockKey = block.getAttribute("data-target-block");
        const height = block.getBoundingClientRect().height;
        const width = targetBlockWidth(block);
        const x = targetBlockOffsetPx(blockKey, "x", 0);
        const y = targetBlockOffsetPx(blockKey, "y", defaultY);
        block.style.width = "";
        block.style.minWidth = "";
        block.style.left = `${x}px`;
        block.style.top = `${y}px`;
        block.classList.toggle("is-target-block-selected", targetSelectedBlocks.has(blockKey));
        maxRight = Math.max(maxRight, x + Math.max(width, block.getBoundingClientRect().width));
        maxBottom = Math.max(maxBottom, y + height);
        defaultY += height + 8;
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
        dob: String(document.getElementById("target-profile-dob")?.value || "").trim(),
        gender: String(document.getElementById("target-profile-gender")?.value || "").trim(),
        height_cm: optionalNumberValue("target-profile-height"),
        weight_kg: profileWeight,
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
          const onMove = (mv) => {
            formColumnWidths[`detail_block_${blockKey}_x`] = startOffsetX + (mv.clientX - startX);
            formColumnWidths[`detail_block_${blockKey}_y`] = startOffsetY + (mv.clientY - startY);
            applyDetailBlockLayout();
          };
          const onUp = () => {
            window.removeEventListener("mousemove", onMove);
            window.removeEventListener("mouseup", onUp);
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
      const defs = Array.isArray(data && data.roster_code_definitions) ? data.roster_code_definitions : [];
      detailSettingsPayload = { folders, rice, roster_code_definitions: defs };
      const systemFolder = document.getElementById("detail-system-folder");
      const dataFolder = document.getElementById("detail-data-folder");
      const brown = document.getElementById("detail-rice-brown");
      const other = document.getElementById("detail-rice-other");
      if (systemFolder) systemFolder.value = folders.system_folder ?? "";
      if (dataFolder) dataFolder.value = folders.data_folder ?? "";
      if (brown) brown.value = rice.cooked_to_raw_brown ?? "";
      if (other) other.value = rice.cooked_to_raw_other ?? "";
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
          workday: collectTargetValues("workday", source),
          nonworkday: collectTargetValues("nonworkday", source),
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

