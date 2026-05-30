/* Shopping list rendering and column resizing. */
    function shopColWidthPx(key) {
      const v = columnWidths[key];
      if (typeof v === "number" && Number.isFinite(v) && v >= 80) return v;
      if (key === "shop_category") return 180;
      if (key === "shop_name") return 420;
      if (key === "shop_total_g") return 160;
      return 160;
    }

    function shoppingColumnWidthTotalPx() {
      return ["shop_category", "shop_name", "shop_total_g"].reduce((total, key) => total + shopColWidthPx(key), 0);
    }

    function escAttr(s) {
      return esc(s).replace(/"/g, "&quot;");
    }

    function attachShoppingResizers() {
      const table = document.querySelector("table.sheet.shopping-table");
      if (!table) return;
      const hdr = table.querySelector("tr.hdr-labels");
      if (!hdr) return;
      hdr.querySelectorAll("td[data-shop-col-key]").forEach((cell) => {
        if (cell.querySelector(".shop-col-resizer")) return;
        const key = cell.getAttribute("data-shop-col-key");
        cell.style.position = "relative";
        const grip = document.createElement("div");
        grip.className = "shop-col-resizer";
        grip.addEventListener("mousedown", (ev) => {
          ev.preventDefault();
          const startX = ev.clientX;
          const startW = shopColWidthPx(key);
          const onMove = (mv) => {
            columnWidths[key] = Math.max(80, startW + (mv.clientX - startX));
            applyColumnWidths();
          };
          const onUp = () => {
            window.removeEventListener("mousemove", onMove);
            window.removeEventListener("mouseup", onUp);
            persistColumnWidths();
          };
          window.addEventListener("mousemove", onMove);
          window.addEventListener("mouseup", onUp);
        });
        cell.appendChild(grip);
      });
    }

    function datePlusDaysIso(iso, days) {
      const dt = new Date(`${iso}T00:00:00`);
      if (Number.isNaN(dt.getTime())) return "";
      dt.setDate(dt.getDate() + days);
      return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}-${String(dt.getDate()).padStart(2, "0")}`;
    }

    function tomorrowIsoHK() {
      const fmt = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Hong_Kong", year: "numeric", month: "2-digit", day: "2-digit" });
      const p = fmt.formatToParts(new Date());
      const y = p.find((x) => x.type === "year").value;
      const m = p.find((x) => x.type === "month").value;
      const d = p.find((x) => x.type === "day").value;
      return datePlusDaysIso(`${y}-${m}-${d}`, 1);
    }

    function nextMonthDayIso(baseIso, day) {
      const dt = new Date(`${baseIso}T00:00:00`);
      if (Number.isNaN(dt.getTime())) return "";
      const next = new Date(dt.getFullYear(), dt.getMonth() + 1, day);
      return `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, "0")}-${String(next.getDate()).padStart(2, "0")}`;
    }

    function maxIsoDate(a, b) {
      if (!a) return b || "";
      if (!b) return a || "";
      return a > b ? a : b;
    }

    function riceRawGrams(name, cookedGrams) {
      if (!shoppingRiceConfig || typeof cookedGrams !== "number" || !Number.isFinite(cookedGrams)) return null;
      const text = String(name || "");
      const markers = Array.isArray(shoppingRiceConfig.note_name_contains)
        ? shoppingRiceConfig.note_name_contains.map((x) => String(x || "")).filter(Boolean)
        : [];
      if (!markers.some((marker) => text.includes(marker))) return null;
      const brownMarker = String(shoppingRiceConfig.brown_name_contains || "");
      const brownRatio = Number(shoppingRiceConfig.cooked_to_raw_brown);
      const otherRatio = Number(shoppingRiceConfig.cooked_to_raw_other);
      const ratio = brownMarker && text.includes(brownMarker) ? brownRatio : otherRatio;
      if (!Number.isFinite(ratio) || ratio <= 0) return null;
      return cookedGrams / ratio;
    }

    let shoppingStartWasAuto = true;
    let shoppingEndWasAuto = true;

    function syncDefaultShoppingEnd() {
      const start = document.getElementById("shop_start");
      const end = document.getElementById("shop_end");
      if (!start || !end || !start.value) return;
      const suggested = datePlusDaysIso(start.value, 6);
      if (!suggested) return;
      if (shoppingEndWasAuto || !end.value) {
        end.value = suggested;
        shoppingEndWasAuto = true;
      }
      end.min = start.value;
    }

    function seedShoppingDateRange() {
      const days = sortDaysByDate(memoryPayload.days || []);
      const start = document.getElementById("shop_start");
      const end = document.getElementById("shop_end");
      if (!start || !end || !days.length) return;
      const minDate = String(days[0].date || "");
      const maxDate = String(days[days.length - 1].date || "");
      const defaultStart = tomorrowIsoHK();
      const maxSelectable = maxIsoDate(maxDate, nextMonthDayIso(todayIsoHK(), 7));
      if (shoppingStartWasAuto || !start.value) {
        start.value = defaultStart || minDate;
        shoppingStartWasAuto = true;
        shoppingEndWasAuto = true;
      }
      start.min = minDate; start.max = maxSelectable;
      end.min = minDate; end.max = maxSelectable;
      syncDefaultShoppingEnd();
    }

    function generateShoppingList() {
      const out = document.getElementById("shopping-out");
      const start = document.getElementById("shop_start");
      const end = document.getElementById("shop_end");
      const startV = String((start && start.value) || "");
      const endV = String((end && end.value) || "");
      if (!startV) {
        out.innerHTML = '<div class="err" style="display:block;">Please provide start date.</div>';
        return;
      }
      if (!endV) {
        out.innerHTML = '<div class="err" style="display:block;">Please provide end date.</div>';
        return;
      }
      const dt = new Date(`${startV}T00:00:00`);
      const endDt = new Date(`${endV}T00:00:00`);
      if (Number.isNaN(dt.getTime()) || Number.isNaN(endDt.getTime())) {
        out.innerHTML = '<div class="err" style="display:block;">Invalid date range.</div>';
        return;
      }
      if (endV < startV) {
        out.innerHTML = '<div class="err" style="display:block;">End date cannot be before start date.</div>';
        return;
      }
      const days = sortDaysByDate(memoryPayload.days || []).filter((d) => {
        const ds = String((d && d.date) || "");
        return ds >= startV && ds <= endV;
      });
      const byPair = new Map();
      const unknown = new Map();
      for (const d of days) {
        const mealItems = d && d.meal_plan && d.meal_plan.meal_items ? d.meal_plan.meal_items : {};
        for (const meal of MEALS) {
          const items = Array.isArray(mealItems[meal]) ? mealItems[meal] : [];
          for (const it of items) {
            const name = String((it && it.name) || "").trim();
            const grams = it ? it.grams : null;
            if (!name) continue;
            if (typeof grams === "number" && Number.isFinite(grams)) {
              const cat = String(shoppingCatalogByName[name] || "Uncategorized");
              const key = `${cat}\u0000${name}`;
              const rawRiceGrams = riceRawGrams(name, grams);
              const shopGrams = rawRiceGrams == null ? grams : rawRiceGrams;
              const old = byPair.get(key) || {
                category: cat,
                name,
                display_name: rawRiceGrams == null ? name : `${name} (raw weight)`,
                grams: 0,
                sources: [],
              };
              old.grams += shopGrams;
              old.sources.push({
                date: String((d && d.date) || ""),
                meal,
                grams: shopGrams,
                cooked_grams: rawRiceGrams == null ? null : grams,
              });
              byPair.set(key, old);
            } else {
              unknown.set(name, (unknown.get(name) || 0) + 1);
            }
          }
        }
      }
      const rows = Array.from(byPair.values()).sort((a, b) => {
        const c = String(a.category).localeCompare(String(b.category), "zh-HK");
        if (c !== 0) return c;
        return String(a.name).localeCompare(String(b.name), "zh-HK");
      });
      const unknownRows = Array.from(unknown.entries()).sort((a, b) => a[0].localeCompare(b[0]));
      const totalItems = rows.reduce((s, x) => s + x.grams, 0);
      const sourceTitle = (sources) => (Array.isArray(sources) ? sources : [])
        .map((x) => {
          const raw = `${esc(x.date)} ${esc(x.meal)} ${esc(Number(x.grams).toFixed(0))}g`;
          return x.cooked_grams == null ? raw : `${raw} raw weight (cooked ${esc(Number(x.cooked_grams).toFixed(0))}g)`;
        })
        .join("\n");
      const table = rows.length
        ? `<table class="sheet shopping-table" style="width:${shoppingColumnWidthTotalPx()}px">
            <colgroup>
              <col data-shop-col-key="shop_category" style="width:${shopColWidthPx("shop_category")}px">
              <col data-shop-col-key="shop_name" style="width:${shopColWidthPx("shop_name")}px">
              <col data-shop-col-key="shop_total_g" style="width:${shopColWidthPx("shop_total_g")}px">
            </colgroup>
            <tbody>
            <tr class="hdr-labels">
              <td data-shop-col-key="shop_category">Category</td>
              <td data-shop-col-key="shop_name">Name</td>
              <td data-shop-col-key="shop_total_g" class="c-right">Total g</td>
            </tr>
            ${rows.map((x) => `<tr class="shop-data-row" title="${escAttr(sourceTitle(x.sources))}"><td>${esc(x.category)}</td><td>${esc(x.display_name || x.name)}</td><td class="c-right">${esc(x.grams.toFixed(1))}</td></tr>`).join("")}
            <tr class="sum"><td></td><td>Total</td><td class="c-right">${esc(totalItems.toFixed(1))}</td></tr>
          </tbody></table>`
        : `<div class="hint">No gram-based items in selected range.</div>`;
      const notes = unknownRows.length
        ? `<div class="hint" style="margin-top:6px;">Items without grams: ${unknownRows.map(([n, c]) => `${esc(n)} x${c}`).join(", ")}</div>`
        : "";
      out.innerHTML = `<div class="hint">Range: ${esc(startV)} to ${esc(endV)} | Days: ${days.length}</div>${table}${notes}`;
      applyColumnWidths();
      attachShoppingResizers();
      applyTableOffsets(out);
      attachTableDragHandles();
    }
