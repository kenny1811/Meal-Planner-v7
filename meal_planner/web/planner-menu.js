    function menuButtonForKey(key) {
      if (key === "planner") return document.getElementById("menu-planner");
      if (key === "shopping") return document.getElementById("menu-shopping");
      if (key === "alarm_sync") return document.getElementById("menu-alarm-sync");
      if (key === "target") return document.getElementById("menu-config-target");
      if (key === "catalog") return document.getElementById("menu-config-catalog");
      if (key === "details") return document.getElementById("menu-config-details");
      if (maintSheetKeys().includes(key)) {
        const sheetBtn = document.querySelector(`.menu-item[data-maint-sheet-key="${CSS.escape(key)}"]`);
        if (sheetBtn) return sheetBtn;
      }
      return document.querySelector(`.menu-item[data-menu-key="${CSS.escape(key)}"]`);
    }
    function existingMenuNodeForKey(key) {
      if (key === "config") return document.getElementById("config-menu-tree");
      if (key === "maint") return document.getElementById("maint-menu-tree");
      return menuButtonForKey(key);
    }
    function createCustomMenuButton(key) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "menu-item menu-custom-item";
      btn.setAttribute("data-menu-key", key);
      btn.setAttribute("data-menu-custom", "1");
      btn.innerHTML = `<span class="menu-drag-handle" draggable="true" title="Drag to reorder" aria-hidden="true"></span><span class="menu-item-label"></span>`;
      return btn;
    }

    function staticMenuDefaultLabel(key) {
      const menuItem = document.querySelector(`.menu-item[data-menu-key="${CSS.escape(key)}"]`);
      const menuText = menuItem ? menuItem.querySelector(".menu-item-label")?.textContent : "";
      if (menuText && menuText.trim()) return menuText.trim();
      const titleNode = document.querySelector(`[data-title-key="${CSS.escape(key)}"]`);
      const titleText = titleNode ? titleNode.textContent : "";
      return titleText ? titleText.trim() : "";
    }

    function defaultMenuLabel(key) {
      if (key === "config") return "Config";
      if (key === "maint") return "Maint";
      if (key === "planner") return "Menu Planner";
      if (key === "shopping") return "Shopping List";
      if (key === "alarm_sync") {
        const staticLabel = staticMenuDefaultLabel(key);
        if (staticLabel) return staticLabel;
        return "alarm_sync";
      }
      if (key === "target") return "Target";
      if (key === "catalog") return "Catalog";
      if (key === "details") return "Detail Settings";
      const sheet = (maintSheets || []).find((item) => item && item.sheet_key === key);
      if (sheet) return MAINT_SHEET_LABELS[key] || sheet.display_name || key;
      return String(menuLabels[key] || key);
    }

    function restoreDefaultMenuLabel(key) {
      delete menuLabels[key];
      applyMenuLabels();
      persistMenuLayout();
    }

    function menuLabel(key) {
      const custom = menuLabels && typeof menuLabels === "object" ? String(menuLabels[key] || "").trim() : "";
      return custom || defaultMenuLabel(key);
    }

    function applyMenuLabels() {
      document.querySelectorAll(".menu-item[data-menu-key]").forEach((item) => {
        const key = item.getAttribute("data-menu-key");
        const label = item.querySelector(".menu-item-label");
        if (key && label) label.textContent = menuLabel(key);
      });
      document.querySelectorAll("[data-title-key]").forEach((item) => {
        const key = item.getAttribute("data-title-key");
        if (key) item.textContent = menuLabel(key);
      });
    }

    function menuNodeForKey(key) {
      if (key === "config") return document.getElementById("config-menu-tree");
      if (key === "maint") return document.getElementById("maint-menu-tree");
      return menuButtonForKey(key) || createCustomMenuButton(key);
    }

    function menuContainerForGroup(group) {
      if (group === "config") return document.querySelector("#config-menu-tree .menu-tree-children");
      if (group === "maint") return document.getElementById("maint-menu-children");
      return document.querySelector(".sidebar .menu-list");
    }

    function removeDuplicateMenuNodes(preferredByKey = {}) {
      const seen = new Map();
      document.querySelectorAll(".menu-item[data-menu-key]").forEach((item) => {
        const key = item.getAttribute("data-menu-key");
        if (!key) return;
        const preferred = preferredByKey[key];
        if (preferred && item !== preferred) {
          item.remove();
          return;
        }
        if (!seen.has(key)) {
          seen.set(key, item);
          return;
        }
        item.remove();
      });
    }

    function cleanMenuOrder() {
      const validLeafKeys = allMenuLeafKeys();
      const validKeys = MENU_TREE_KEYS.concat(validLeafKeys);
      const used = new Set();
      const next = { top: [], config: [], maint: [] };
      const hidden = new Set(Array.isArray(menuHiddenKeys) ? menuHiddenKeys.map(String) : []);

      const add = (group, key) => {
        if (used.has(key) || hidden.has(key)) return;
        if (isMenuTreeKey(key) && group !== "top") group = "top";
        next[group].push(key);
        used.add(key);
      };

      for (const group of ["top", "config", "maint"]) {
        const saved = Array.isArray(menuOrder[group]) ? menuOrder[group] : [];
        saved.forEach((key) => add(group, String(key)));
      }
      validKeys.forEach((key) => add(defaultMenuGroup(key), key));
      menuOrder = next;
      return next;
    }

    function removeKeyFromMenuOrder(key) {
      for (const group of ["top", "config", "maint"]) {
        menuOrder[group] = (Array.isArray(menuOrder[group]) ? menuOrder[group] : []).filter((item) => item !== key);
      }
    }

    function menuGroupForKey(key) {
      const order = cleanMenuOrder();
      for (const group of ["top", "config", "maint"]) {
        if (order[group].includes(key)) return group;
      }
      return defaultMenuGroup(key);
    }

    function setMenuItemGroupClass(item, group) {
      if (!item) return;
      item.setAttribute("data-menu-group", group);
      item.classList.toggle("menu-child", group !== "top");
    }

    function normalizeMenuOrder(group, keys) {
      const saved = Array.isArray(menuOrder[group]) ? menuOrder[group].filter((key) => keys.includes(key)) : [];
      return saved.concat(keys.filter((key) => !saved.includes(key)));
    }

    function applyMenuOrder() {
      const order = cleanMenuOrder();
      removeDuplicateMenuNodes();
      const visible = new Set(["top", "config", "maint"].flatMap((group) => order[group] || []));
      const hidden = new Set(Array.isArray(menuHiddenKeys) ? menuHiddenKeys.map(String) : []);
      hidden.forEach((key) => {
        const node = existingMenuNodeForKey(key);
        if (node) node.style.display = "none";
      });
      document.querySelectorAll(".menu-custom-item[data-menu-key]").forEach((item) => {
        const key = item.getAttribute("data-menu-key");
        if (!key || !visible.has(key)) item.remove();
      });
      for (const group of ["top", "config", "maint"]) {
        const container = menuContainerForGroup(group);
        if (!container) continue;
        order[group].forEach((key) => {
          const node = menuNodeForKey(key);
          if (!node) return;
          node.style.display = "";
          if (!isMenuTreeKey(key)) setMenuItemGroupClass(node, group);
          container.appendChild(node);
        });
      }
      applyMenuLabels();
      attachMenuDragHandles();
    }

    function menuDropPosition(item, clientY) {
      if (!item || !Number.isFinite(clientY)) return "before";
      const rect = item.getBoundingClientRect();
      return clientY > rect.top + rect.height / 2 ? "after" : "before";
    }

    function markMenuDropTarget(item, position) {
      document.querySelectorAll(".menu-item.is-menu-drag-over,.menu-item.is-menu-drop-after").forEach((el) => {
        el.classList.remove("is-menu-drag-over", "is-menu-drop-after");
      });
      if (!item) return;
      item.classList.add(position === "after" ? "is-menu-drop-after" : "is-menu-drag-over");
    }

    function moveMenuItem(fromKey, toGroup, toKey = null, position = "before") {
      if (!fromKey || !toGroup || !["top", "config", "maint"].includes(toGroup)) return;
      if (isMenuTreeKey(fromKey)) toGroup = "top";
      const order = cleanMenuOrder();
      for (const group of ["top", "config", "maint"]) {
        order[group] = order[group].filter((key) => key !== fromKey);
      }
      const targetOrder = order[toGroup];
      const toIdx = toKey ? targetOrder.indexOf(toKey) : -1;
      if (toIdx >= 0) {
        targetOrder.splice(position === "after" ? toIdx + 1 : toIdx, 0, fromKey);
      } else {
        targetOrder.push(fromKey);
      }
      menuOrder = order;
      applyMenuOrder();
      persistMenuOrder();
    }

    function hideMenuContextMenu() {
      const menu = document.getElementById("menu-context-menu");
      if (!menu) return;
      menu.hidden = true;
      menu.removeAttribute("data-menu-key");
      menu.removeAttribute("data-menu-group");
    }

    function showMenuContextMenu(ev, item) {
      const menu = document.getElementById("menu-context-menu");
      if (!menu || !item) return;
      ev.preventDefault();
      ev.stopPropagation();
      menu.hidden = false;
      menu.setAttribute("data-menu-key", item.getAttribute("data-menu-key") || "");
      menu.setAttribute("data-menu-group", item.getAttribute("data-menu-group") || "top");
      menu.style.left = `${ev.clientX}px`;
      menu.style.top = `${ev.clientY}px`;
    }

    function renameMenuItem(key) {
      const current = menuLabel(key);
      const next = window.prompt("Menu display name（留空回復預設）", current);
      if (next == null) return;
      const clean = String(next).trim();
      if (clean && clean !== defaultMenuLabel(key)) {
        menuLabels[key] = clean;
      } else {
        restoreDefaultMenuLabel(key);
        return;
      }
      applyMenuLabels();
      persistMenuLayout();
    }

    function hiddenMenuChoicesText() {
      const hidden = Array.isArray(menuHiddenKeys) ? menuHiddenKeys.filter(Boolean) : [];
      if (!hidden.length) return "";
      return `\nHidden: ${hidden.map((key) => `${menuLabel(key)} (${key})`).join(", ")}`;
    }

    function resolveInsertedMenuKey(input) {
      const clean = String(input || "").trim();
      if (!clean) return "";
      const hidden = Array.isArray(menuHiddenKeys) ? menuHiddenKeys.map(String) : [];
      const lower = clean.toLowerCase();
      const match = hidden.find((key) => key.toLowerCase() === lower || menuLabel(key).toLowerCase() === lower);
      if (match) {
        menuHiddenKeys = hidden.filter((key) => key !== match);
        return match;
      }
      const key = `custom_${Date.now()}`;
      menuLabels[key] = clean;
      return key;
    }

    function insertMenuItemNear(anchorKey, anchorGroup, position) {
      const input = window.prompt(`Item name or hidden item key${hiddenMenuChoicesText()}`, "");
      const key = resolveInsertedMenuKey(input);
      if (!key) return;
      moveMenuItem(key, anchorGroup || "top", anchorKey, position);
      persistMenuLayout();
    }

    function deleteMenuItem(key) {
      if (!key) return;
      removeKeyFromMenuOrder(key);
      if (key.startsWith("custom_")) {
        delete menuLabels[key];
      } else if (!menuHiddenKeys.includes(key)) {
        menuHiddenKeys.push(key);
      }
      applyMenuOrder();
      persistMenuLayout();
    }

    function attachMenuContextMenuActions() {
      const menu = document.getElementById("menu-context-menu");
      if (!menu || menu.dataset.bound === "1") return;
      menu.dataset.bound = "1";
      menu.addEventListener("click", (ev) => {
        const btn = ev.target && ev.target.closest ? ev.target.closest("[data-menu-context-action]") : null;
        if (!btn) return;
        const action = btn.getAttribute("data-menu-context-action");
        const key = menu.getAttribute("data-menu-key");
        const group = menu.getAttribute("data-menu-group") || menuGroupForKey(key);
        hideMenuContextMenu();
        if (action === "insert-before") insertMenuItemNear(key, group, "before");
        if (action === "insert-after") insertMenuItemNear(key, group, "after");
        if (action === "rename") renameMenuItem(key);
        if (action === "delete") deleteMenuItem(key);
      });
      document.addEventListener("mousedown", (ev) => {
        if (!ev.target || !ev.target.closest || !ev.target.closest("#menu-context-menu")) hideMenuContextMenu();
      });
      document.addEventListener("keydown", (ev) => {
        if (ev.key === "Escape") hideMenuContextMenu();
      });
    }

    function createMenuDragGhost(item, ev) {
      const ghost = document.createElement("div");
      ghost.className = "menu-drag-ghost";
      ghost.textContent = item.textContent.trim();
      ghost.style.width = `${Math.min(260, Math.max(120, item.getBoundingClientRect().width))}px`;
      document.body.appendChild(ghost);
      moveMenuDragGhost(ghost, ev);
      return ghost;
    }

    function moveMenuDragGhost(ghost, ev) {
      if (!ghost) return;
      ghost.style.transform = `translate(${ev.clientX + 14}px, ${ev.clientY + 12}px)`;
    }

    function startPointerMenuDrag(handle, ev) {
      const item = handle.closest(".menu-item[data-menu-group][data-menu-key]");
      if (!item || (ev.button != null && ev.button !== 0)) return;
      ev.preventDefault();
      ev.stopPropagation();
      const group = item.getAttribute("data-menu-group");
      const fromKey = item.getAttribute("data-menu-key");
      let targetItem = item;
      let targetGroup = group;
      let targetKey = fromKey;
      let targetPosition = "before";
      menuDragState = { group, key: fromKey };
      item.classList.add("is-menu-dragging");
      const ghost = createMenuDragGhost(item, ev);
      const onMove = (mv) => {
        mv.preventDefault();
        moveMenuDragGhost(ghost, mv);
        const hit = document.elementFromPoint(mv.clientX, mv.clientY);
        const next = hit && hit.closest ? hit.closest(".menu-item[data-menu-group][data-menu-key]") : null;
        const container = hit && hit.closest ? hit.closest("[data-menu-drop-group]") : null;
        if (next) {
          targetItem = next;
          targetGroup = next.getAttribute("data-menu-group");
          targetKey = next.getAttribute("data-menu-key");
          targetPosition = menuDropPosition(next, mv.clientY);
          markMenuDropTarget(next, targetPosition);
        } else if (container) {
          targetItem = null;
          targetGroup = container.getAttribute("data-menu-drop-group") || "top";
          targetKey = null;
          targetPosition = "before";
          markMenuDropTarget(null, targetPosition);
        }
      };
      const onUp = (up) => {
        up.preventDefault();
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
        document.querySelectorAll(".menu-item.is-menu-dragging,.menu-item.is-menu-drag-over,.menu-item.is-menu-drop-after").forEach((el) => {
          el.classList.remove("is-menu-dragging", "is-menu-drag-over", "is-menu-drop-after");
        });
        ghost.remove();
        menuDragState = null;
        moveMenuItem(fromKey, targetGroup, targetKey, targetPosition);
      };
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    }

    function attachMenuDragHandles(root = document) {
      attachMenuContextMenuActions();
      root.querySelectorAll(".menu-drag-handle").forEach((handle) => {
        if (handle.dataset.menuDragBound === "1") return;
        handle.dataset.menuDragBound = "1";
        handle.addEventListener("click", (ev) => {
          ev.preventDefault();
          ev.stopPropagation();
        });
        handle.addEventListener("mousedown", (ev) => {
          startPointerMenuDrag(handle, ev);
        });
        handle.addEventListener("dragstart", (ev) => {
          const item = handle.closest(".menu-item[data-menu-group][data-menu-key]");
          if (!item || !ev.dataTransfer) return;
          ev.stopPropagation();
          menuDragState = {
            group: item.getAttribute("data-menu-group"),
            key: item.getAttribute("data-menu-key"),
          };
          ev.dataTransfer.effectAllowed = "move";
          ev.dataTransfer.setData("application/x-menu-group", menuDragState.group);
          ev.dataTransfer.setData("application/x-menu-key", menuDragState.key);
        });
        handle.addEventListener("dragend", () => {
          menuDragState = null;
          document.querySelectorAll(".menu-item.is-menu-drag-over").forEach((el) => el.classList.remove("is-menu-drag-over"));
        });
      });
      root.querySelectorAll(".menu-item[data-menu-group][data-menu-key]").forEach((item) => {
        if (item.dataset.menuDropBound === "1") return;
        item.dataset.menuDropBound = "1";
        item.addEventListener("dragover", (ev) => {
          const fromKey = menuDragState && menuDragState.key;
          if (fromKey) {
            ev.preventDefault();
            if (ev.dataTransfer) ev.dataTransfer.dropEffect = "move";
            markMenuDropTarget(item, menuDropPosition(item, ev.clientY));
          }
        });
        item.addEventListener("dragleave", () => {
          item.classList.remove("is-menu-drag-over", "is-menu-drop-after");
        });
        item.addEventListener("drop", (ev) => {
          const fromKey = (menuDragState && menuDragState.key) || (ev.dataTransfer && ev.dataTransfer.getData("application/x-menu-key"));
          const toGroup = item.getAttribute("data-menu-group");
          const position = menuDropPosition(item, ev.clientY);
          item.classList.remove("is-menu-drag-over", "is-menu-drop-after");
          menuDragState = null;
          if (!fromKey || !toGroup) return;
          ev.preventDefault();
          moveMenuItem(fromKey, toGroup, item.getAttribute("data-menu-key"), position);
        });
        item.addEventListener("contextmenu", (ev) => {
          showMenuContextMenu(ev, item);
        });
      });
    }

    function setConfigView(viewName) {
      document.querySelectorAll(".config-view[data-config-view]").forEach((view) => {
        view.style.display = view.getAttribute("data-config-view") === viewName ? "" : "none";
      });
    }

    function persistActiveConfigView() {
      try {
        window.localStorage.setItem("mealplanner_active_config_view", activeConfigView);
      } catch (_) {}
      persistActiveConfigViewState();
    }

    function leafKeyForConfigView(viewName) {
      if (viewName === "targets") return "target";
      if (viewName === "details") return "details";
      return "catalog";
    }

    function configViewForLeafKey(key) {
      if (key === "target") return "targets";
      if (key === "details") return "details";
      if (key === "catalog") return "catalog";
      return "";
    }

    function openMenuTreeForGroup(group, persist = true) {
      if (group === "config") setConfigMenuTreeOpen(true, persist);
      if (group === "maint") setMaintMenuTreeOpen(true, persist);
    }

    function setActiveMenuPathForKey(key) {
      if (!key) return;
      activeMenuPath = [menuGroupForKey(key), key];
      try {
        window.localStorage.setItem("mealplanner_active_menu_path", activeMenuPath.join("/"));
      } catch (_) {}
      persistActiveMenuPathState();
    }

    function applyActiveMenuPathToState() {
      if (!Array.isArray(activeMenuPath) || !activeMenuPath.length) return;
      const key = activeMenuPath[activeMenuPath.length - 1];
      const configView = configViewForLeafKey(key);
      if (configView) {
        activePanel = "config";
        activeConfigView = configView;
        return;
      }
      if (["planner", "shopping", "alarm_sync"].includes(key)) {
        activePanel = key;
        return;
      }
      if (key === "maint") {
        activePanel = "maint";
        return;
      }
      if (maintSheetKeys().includes(key)) {
        activePanel = "maint";
        activeMaintSheetKey = key;
      }
    }

    function applyActiveMenuPathTree() {
      if (!Array.isArray(activeMenuPath) || !activeMenuPath.length) return;
      openMenuTreeForGroup(activeMenuPath[0], false);
    }

    function applyActiveConfigView(refresh = false) {
      const viewName = ["targets", "catalog", "details"].includes(activeConfigView) ? activeConfigView : "targets";
      activeConfigView = viewName;
      setConfigView(viewName);
      document.getElementById("menu-config").classList.remove("active");
      document.getElementById("menu-config-target").classList.toggle("active", viewName === "targets");
      document.getElementById("menu-config-catalog").classList.toggle("active", viewName === "catalog");
      document.getElementById("menu-config-details").classList.toggle("active", viewName === "details");
      if (!refresh) return;
      if (viewName === "targets") refreshTargetEditor();
      if (viewName === "catalog") refreshNutritionCatalog();
      if (viewName === "details") refreshDetailSettings();
    }

    async function openConfigChild(viewName) {
      if (!(await resolveUnsavedBeforeLeaving())) return;
      activeConfigView = ["targets", "catalog", "details"].includes(viewName) ? viewName : "targets";
      persistActiveConfigView();
      const leafKey = leafKeyForConfigView(activeConfigView);
      setActiveMenuPathForKey(leafKey);
      setActivePanel("config");
      openMenuTreeForGroup(menuGroupForKey(leafKey));
      applyActiveConfigView(true);
    }

    function setMaintStatus(message) {
      const status = document.getElementById("maint-status");
      if (status) status.textContent = message || "";
    }

    function showMaintError(message) {
      const err = document.getElementById("maint-err");
      if (!err) return;
      err.textContent = message || "";
      err.style.display = message ? "block" : "none";
    }

    function setAlarmSyncStatus(message) {
      const status = document.getElementById("alarm-sync-status");
      if (status) status.textContent = message || "";
    }

    function showAlarmSyncError(message) {
      const err = document.getElementById("alarm-sync-err");
      if (!err) return;
      err.textContent = message || "";
      err.style.display = message ? "block" : "none";
    }

    async function openAlarmSyncPanel() {
      if (!(await resolveUnsavedBeforeLeaving())) return;
      setActiveMenuPathForKey("alarm_sync");
      setActivePanel("alarm_sync");
      showAlarmSyncError("");
      setAlarmSyncStatus("");
      syncAutoDeviceStateFromUi();
      if (typeof syncAutoServerSuggestionFromBackend === "function") await syncAutoServerSuggestionFromBackend();
      if (typeof clearAlarmSyncPreview === "function") {
        clearAlarmSyncPreview();
      }
      if (typeof clearAlarmMealPlanPreview === "function") {
        clearAlarmMealPlanPreview();
      }
      {
        const display = document.getElementById("alarm-sync-server-ip");
        if (display) {
          display.textContent = "偵測中...";
          try {
            const r = await fetch("/api/network-info");
            const data = await r.json().catch(() => ({}));
            if (!r.ok) {
              const msg = String(data.detail || data.message || "").trim();
              display.textContent = msg ? `無法取得 (${msg})` : "無法取得";
            } else {
              const suggested = String(data.suggested_auto_server || "").trim();
              const lanIps = Array.isArray(data.lan_ips) ? data.lan_ips : [];
              const port = Number.isFinite(Number(data.port)) ? Number(data.port) : 8765;
              display.textContent = suggested || (lanIps.length ? `http://${lanIps[0]}:${port}` : "未有可用 LAN IP");
            }
          } catch (_) {
            display.textContent = "無法取得";
          }
        }
      }
      const panel = document.getElementById("alarm-sync-panel");
      if (panel) {
        applyFormColumnWidths(panel);
        attachFormColumnResizers(panel);
        applyTableOffsets(panel);
        attachTableDragHandles(panel);
      }
    }

    function renderMaintMenu() {
      const box = document.getElementById("maint-menu-children");
      if (!box) return;
      const byKey = new Map((maintSheets || []).map((sheet) => [sheet.sheet_key, sheet]));
      const preferredByKey = {};
      for (const sheet of (maintSheets || [])) {
        if (!sheet || !sheet.sheet_key) continue;
        let btn = document.querySelector(`.menu-item[data-maint-sheet-key="${CSS.escape(sheet.sheet_key)}"]`)
          || document.querySelector(`.menu-item[data-menu-key="${CSS.escape(sheet.sheet_key)}"]`);
        if (!btn) {
          btn = document.createElement("button");
          btn.type = "button";
          btn.className = "menu-item";
          btn.innerHTML = `<span class="menu-drag-handle" draggable="true" title="Drag to reorder" aria-hidden="true"></span><span class="menu-item-label"></span>`;
          box.appendChild(btn);
        }
        btn.classList.remove("menu-custom-item");
        btn.removeAttribute("data-menu-custom");
        btn.setAttribute("data-maint-sheet-key", sheet.sheet_key);
        btn.setAttribute("data-menu-key", sheet.sheet_key);
        preferredByKey[sheet.sheet_key] = btn;
        btn.querySelector(".menu-item-label").textContent = menuLabel(sheet.sheet_key);
      }
      removeDuplicateMenuNodes(preferredByKey);
      document.querySelectorAll("[data-maint-sheet-key]").forEach((btn) => {
        const key = btn.getAttribute("data-maint-sheet-key");
        if (key && !byKey.has(key)) btn.remove();
      });
      document.querySelectorAll("[data-maint-sheet-key]").forEach((btn) => {
        if (btn.dataset.maintClickBound === "1") return;
        btn.dataset.maintClickBound = "1";
        btn.addEventListener("click", () => openMaintSheet(btn.getAttribute("data-maint-sheet-key")));
      });
      applyMenuOrder();
      attachMenuDragHandles();
      setActivePanel(activePanel, false);
    }

    function maintColumnCount(rows) {
      const n = (rows || []).reduce((max, row) => Math.max(max, Array.isArray(row) ? row.length : 0), 0);
      return Math.max(1, n);
    }

    function formColumnWidthPx(key, fallback = 120) {
      const saved = Number(formColumnWidths[key]);
      if (Number.isFinite(saved)) return saved;
      return fallback;
    }

    function autoResizeTextarea(el) {
      if (!el || el.tagName !== "TEXTAREA") return;
      if (el.offsetParent === null) return; // Skip if hidden (e.g., filtered out)
      const cell = el.closest("td");
      if (cell) {
        const style = getComputedStyle(cell);
        const padX = parseFloat(style.paddingLeft || "0") + parseFloat(style.paddingRight || "0");
        el.style.width = `${Math.max(0, cell.clientWidth - padX)}px`;
      }
      el.style.height = "0px";
      el.style.height = `${el.scrollHeight}px`;
    }

    function autoResizeTextareas(root = document) {
      root.querySelectorAll("textarea[data-auto-row-height]").forEach(autoResizeTextarea);
    }

    function applyFormColumnWidths(root = document) {
      root.querySelectorAll("col[data-form-col-key]").forEach((col) => {
        const key = col.getAttribute("data-form-col-key");
        const fallback = Number(col.getAttribute("data-form-col-default")) || 120;
        col.style.width = `${formColumnWidthPx(key, fallback)}px`;
      });
      root.querySelectorAll("table[data-form-table]").forEach((table) => {
        let total = 0;
        table.querySelectorAll("col[data-form-col-key]").forEach((col) => {
          const key = col.getAttribute("data-form-col-key");
          const fallback = Number(col.getAttribute("data-form-col-default")) || 120;
          total += formColumnWidthPx(key, fallback);
        });
        if (total > 0) table.style.width = `${total}px`;
      });
    }

    function formOffsetPx(key) {
      const saved = Number(formColumnWidths[key]);
      return Number.isFinite(saved) ? saved : 0;
    }

    function applyTableOffsets(root = document) {
      const targets = [
        ["#catalog-editor table.catalog-table", "table_offset_catalog"],
        [".detail-editor", "table_offset_detail"],
        ["#detail-code-definitions table.detail-code-table", "table_offset_detail_codes"],
        ["#maint-editor table.maint-table", "table_offset_maint_sheet"],
        ["#maint-editor table.maint-roster-table", "table_offset_maint_roster"],
        ["#shopping-out table.shopping-table", "table_offset_shopping"],
        ["#alarm-sync-form", "table_offset_alarm_sync"],
      ];
      for (const [selector, key] of targets) {
        document.querySelectorAll(selector).forEach((el) => {
          if (root !== document && !root.contains(el) && el !== root) return;
          el.style.marginLeft = `${formOffsetPx(key)}px`;
        });
      }
      applyRosterReportOffset();
    }

    function attachHorizontalDragHandle(handle, key, applyFn) {
      if (!handle || handle.dataset.horizontalDragBound === "1") return;
      handle.dataset.horizontalDragBound = "1";
      handle.classList.add("table-drag-handle");
      handle.title = handle.title || "Drag left or right to move table";
      handle.addEventListener("mousedown", (ev) => {
        if (ev.button != null && ev.button !== 0) return;
        const interactive = ev.target && ev.target.closest
          ? ev.target.closest("button,input,textarea,select,a,.target-col-resizer,.catalog-col-resizer,.form-col-resizer,.col-resizer,.shop-col-resizer")
          : null;
        if (interactive) return;
        ev.preventDefault();
        const startX = ev.clientX;
        const startOffset = formOffsetPx(key);
        const onMove = (mv) => {
          formColumnWidths[key] = startOffset + (mv.clientX - startX);
          applyFn();
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
        formColumnWidths[key] = 0;
        applyFn();
        persistColumnWidths();
      });
    }

    function attachTableDragHandles(root = document) {
      const configs = [
        ['.config-view[data-config-view="catalog"] h2', "table_offset_catalog"],
        ['.config-view[data-config-view="details"] h2', "table_offset_detail"],
        ["#maint-editor .maint-sheet-title", "table_offset_maint_sheet"],
        ["#maint-editor .maint-roster-pane:first-child .maint-pane-title", "table_offset_maint_roster"],
        ["#shopping-panel h1", "table_offset_shopping"],
        ["#alarm-sync-panel h1", "table_offset_alarm_sync"],
      ];
      for (const [selector, key] of configs) {
        document.querySelectorAll(selector).forEach((handle) => {
          if (root !== document && !root.contains(handle) && handle !== root) return;
          attachHorizontalDragHandle(handle, key, () => applyTableOffsets(root));
        });
      }
    }

    function attachFormColumnResizers(root = document) {
      root.querySelectorAll("th[data-form-col-key], td[data-form-col-key]").forEach((cell) => {
        if (cell.querySelector(".form-col-resizer")) return;
        const key = cell.getAttribute("data-form-col-key");
        const grip = document.createElement("span");
        grip.className = "form-col-resizer";
        grip.title = "Drag to resize column";
        grip.addEventListener("mousedown", (ev) => {
          ev.preventDefault();
          ev.stopPropagation();
          const startX = ev.clientX;
          const startW = cell.getBoundingClientRect().width;
          const onMove = (mv) => {
            formColumnWidths[key] = Math.max(0, startW + (mv.clientX - startX));
            applyFormColumnWidths(root);
            if (typeof applyDetailBlockLayout === "function") applyDetailBlockLayout(root);
            autoResizeTextareas(root);
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

    function bindAutoRowHeight(root = document) {
      root.querySelectorAll("textarea[data-auto-row-height]").forEach((ta) => {
        if (ta.dataset.autoHeightBound !== "1") {
          ta.dataset.autoHeightBound = "1";
          ta.addEventListener("input", () => autoResizeTextarea(ta));
        }
        autoResizeTextarea(ta);
      });
    }
