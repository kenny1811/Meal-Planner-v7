    function menuButtonForKey(key) {
      if (isRemovedMenuKey(key)) return null;
      if (key === "planner") return document.getElementById("menu-planner");
      if (key === "shopping") return document.getElementById("menu-shopping");
      if (key === "target") return document.getElementById("menu-config-target");
      if (key === "catalog") return document.getElementById("menu-config-catalog");
      if (key === "details") return document.getElementById("menu-config-details");
      if (key === "shift_code_analysis") return document.getElementById("menu-report-shift-code-analysis");
      if (key === "duty_report") return document.getElementById("menu-duty-report");
      if (maintSheetKeys().includes(key)) {
        const sheetBtn = document.querySelector(`.menu-item[data-maint-sheet-key="${CSS.escape(key)}"]`);
        if (sheetBtn) return sheetBtn;
      }
      return document.querySelector(`.menu-item[data-menu-key="${CSS.escape(key)}"]`);
    }
    function existingMenuNodeForKey(key) {
      if (key === "config") return document.getElementById("config-menu-tree");
      if (key === "maint") return document.getElementById("maint-menu-tree");
      if (key === "reports") return document.getElementById("reports-menu-tree");
      if (isMenuTreeKey(key)) return document.querySelector(`.menu-tree[data-menu-tree-key="${CSS.escape(key)}"]`);
      return menuButtonForKey(key);
    }

    function menuAttr(value) {
      return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      }[ch]));
    }

    function createCustomMenuTree(key) {
      const oldButton = menuButtonForKey(key);
      if (oldButton) oldButton.remove();
      const tree = document.createElement("div");
      tree.className = "menu-tree menu-custom-tree is-open";
      tree.setAttribute("data-menu-tree-key", key);
      tree.innerHTML = `<button type="button" class="menu-item menu-tree-toggle" data-menu-group="top" data-menu-key="${menuAttr(key)}" aria-expanded="true">
        <span class="menu-drag-handle" draggable="true" title="Drag to reorder" aria-hidden="true"></span><span class="menu-item-label"></span><span class="menu-tree-mark" aria-hidden="true"></span>
      </button>
      <div class="menu-tree-children" data-menu-drop-group="${menuAttr(key)}"></div>`;
      return tree;
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
      if (key === "reports") return "報表";
      if (key === "planner") return "Menu Planner";
      if (key === "shopping") return "Shopping List";
      if (key === "target") return "營養指標 / Targets";
      if (key === "catalog") return "Catalog";
      if (key === "details") return "Detail Settings";
      if (key === "shift_code_analysis") return "更碼分析";
      if (key === "duty_report") return "ReportNormal";
      if (key === "onoffduty") return "OnOffDuty";
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
      if (key === "target" && ["Target", "Targets"].includes(custom)) return defaultMenuLabel(key);
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
      if (key === "reports") return document.getElementById("reports-menu-tree");
      if (isMenuTreeKey(key)) return existingMenuNodeForKey(key) || createCustomMenuTree(key);
      return menuButtonForKey(key) || createCustomMenuButton(key);
    }

    function menuContainerForGroup(group) {
      if (group === "config") return document.querySelector("#config-menu-tree .menu-tree-children");
      if (group === "maint") return document.getElementById("maint-menu-children");
      if (group === "reports") return document.querySelector("#reports-menu-tree .menu-tree-children");
      if (group && group !== "top") return document.querySelector(`[data-menu-drop-group="${CSS.escape(group)}"]`);
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

    function menuGroups() {
      const groups = ["top", "config", "maint", "reports"];
      Object.keys(menuOrder || {}).forEach((key) => {
        if (key && !groups.includes(key)) groups.push(key);
      });
      return groups;
    }

    function customMenuTreeKeys() {
      return Object.keys(menuOrder || {}).filter((key) => key && key !== "top" && !MENU_TREE_KEYS.includes(key) && !menuNodeHasContent(key));
    }

    function menuContainsKey(group, key, seen = new Set()) {
      if (!group || !key || seen.has(group)) return false;
      seen.add(group);
      const children = Array.isArray(menuOrder[group]) ? menuOrder[group] : [];
      for (const child of children) {
        if (child === key) return true;
        if (isMenuTreeKey(child) && menuContainsKey(child, key, seen)) return true;
      }
      return false;
    }

    function cleanMenuOrder() {
      const validLeafKeys = allMenuLeafKeys();
      const validKeys = MENU_TREE_KEYS.concat(customMenuTreeKeys(), validLeafKeys);
      const used = new Set();
      const next = Object.fromEntries(menuGroups().map((group) => [group, []]));
      const hidden = new Set(Array.isArray(menuHiddenKeys) ? menuHiddenKeys.map(String) : []);

      const add = (group, key) => {
        if (isRemovedMenuKey(key)) return;
        if (used.has(key) || hidden.has(key)) return;
        if (!next[group]) next[group] = [];
        next[group].push(key);
        used.add(key);
      };

      for (const group of menuGroups()) {
        const saved = Array.isArray(menuOrder[group]) ? menuOrder[group] : [];
        saved.forEach((key) => add(group, String(key)));
      }
      validKeys.forEach((key) => add(defaultMenuGroup(key), key));
      menuOrder = next;
      return next;
    }

    function removeKeyFromMenuOrder(key) {
      for (const group of menuGroups()) {
        menuOrder[group] = (Array.isArray(menuOrder[group]) ? menuOrder[group] : []).filter((item) => item !== key);
      }
    }

    function menuGroupForKey(key) {
      const order = cleanMenuOrder();
      for (const group of menuGroups()) {
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
      const visible = new Set(menuGroups().flatMap((group) => order[group] || []));
      const hidden = new Set(Array.isArray(menuHiddenKeys) ? menuHiddenKeys.map(String) : []);
      hidden.forEach((key) => {
        const node = existingMenuNodeForKey(key);
        if (node) node.style.display = "none";
      });
      document.querySelectorAll(".menu-custom-item[data-menu-key]").forEach((item) => {
        const key = item.getAttribute("data-menu-key");
        if (!key || !visible.has(key)) item.remove();
      });
      document.querySelectorAll(".menu-custom-tree[data-menu-tree-key]").forEach((item) => {
        const key = item.getAttribute("data-menu-tree-key");
        if (!key || !visible.has(key)) item.remove();
      });
      for (const group of menuGroups()) {
        const container = menuContainerForGroup(group);
        if (!container) continue;
        order[group].forEach((key) => {
          const node = menuNodeForKey(key);
          if (!node) return;
          node.style.display = "";
          if (isMenuTreeKey(key)) {
            const toggle = node.querySelector(".menu-item[data-menu-key]");
            if (toggle) setMenuItemGroupClass(toggle, group);
          } else {
            setMenuItemGroupClass(node, group);
          }
          container.appendChild(node);
        });
      }
      applyMenuLabels();
      attachMenuDragHandles();
    }

    function menuDropPosition(item, clientY, fromKey = "") {
      if (!item || !Number.isFinite(clientY)) return "none";
      const rect = item.getBoundingClientRect();
      const toKey = item.getAttribute("data-menu-key") || "";
      const y = clientY - rect.top;
      if (!toKey || toKey === fromKey) return "none";
      if (toKey && toKey !== fromKey && !menuNodeHasContent(toKey) && !menuContainsKey(fromKey, toKey)) {
        if (y >= rect.height * 0.25 && y <= rect.height * 0.75) return "inside";
      }
      if (y < rect.height * 0.25) return "before";
      if (y > rect.height * 0.75) return "after";
      if (menuNodeHasContent(toKey)) return "none";
      return clientY > rect.top + rect.height / 2 ? "after" : "before";
    }

    function markMenuDropTarget(item, position) {
      document.querySelectorAll(".menu-item.is-menu-drag-over,.menu-item.is-menu-drop-after,.menu-item.is-menu-drop-inside").forEach((el) => {
        el.classList.remove("is-menu-drag-over", "is-menu-drop-after", "is-menu-drop-inside");
      });
      document.querySelectorAll(".is-menu-drop-zone-active").forEach((el) => {
        el.classList.remove("is-menu-drop-zone-active");
      });
      if (!item) return;
      if (position === "none") return;
      if (position === "inside") {
        item.classList.add("is-menu-drop-inside");
        return;
      }
      item.classList.add(position === "after" ? "is-menu-drop-after" : "is-menu-drag-over");
    }

    function markMenuDropContainer(container) {
      markMenuDropTarget(null, "before");
      if (container) container.classList.add("is-menu-drop-zone-active");
    }

    function moveMenuItem(fromKey, toGroup, toKey = null, position = "before") {
      if (!fromKey || !toGroup) return;
      if (position === "none") return;
      if (menuContainsKey(fromKey, toGroup)) return;
      if (position === "inside" && toKey && toKey !== fromKey && !menuNodeHasContent(toKey) && !menuContainsKey(fromKey, toKey)) {
        toGroup = toKey;
        toKey = null;
      } else if (position === "inside") {
        position = "before";
      }
      if (!menuOrder[toGroup]) menuOrder[toGroup] = [];
      const order = cleanMenuOrder();
      if (!order[toGroup]) order[toGroup] = [];
      for (const group of menuGroups()) {
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
      const key = item.getAttribute("data-menu-key") || "";
      menu.hidden = false;
      menu.setAttribute("data-menu-key", key);
      menu.setAttribute("data-menu-group", item.getAttribute("data-menu-group") || "top");
      const deleteBtn = menu.querySelector("[data-menu-context-delete]");
      if (deleteBtn) deleteBtn.hidden = !isCustomMenuKey(key);
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

    function isCustomMenuKey(key) {
      return !!key && !MENU_TREE_KEYS.includes(key) && !menuNodeHasContent(key);
    }

    function deleteMenuItem(key) {
      if (!isCustomMenuKey(key)) return;
      const label = menuLabel(key);
      if (!window.confirm(`Delete “${label}”? Any items inside move back to their default menu.`)) return;
      const node = existingMenuNodeForKey(key);
      delete menuLabels[key];
      delete menuTreeOpen[key];
      delete menuOrder[key];
      removeKeyFromMenuOrder(key);
      if (node) {
        const list = document.querySelector(".sidebar .menu-list");
        if (list) {
          node.querySelectorAll(".menu-item[data-menu-key]").forEach((child) => {
            if (child.getAttribute("data-menu-key") !== key) list.appendChild(child);
          });
        }
        node.remove();
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

    function setCustomMenuTreeOpen(key, open, persist = true) {
      const tree = document.querySelector(`.menu-tree[data-menu-tree-key="${CSS.escape(key)}"]`);
      const toggle = tree ? tree.querySelector(".menu-tree-toggle") : null;
      const isOpen = !!open;
      menuTreeOpen[key] = isOpen;
      if (!tree || !toggle) return;
      tree.classList.toggle("is-open", isOpen);
      toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
      if (persist) persistMenuTreeOpen();
    }

    function setAnyMenuTreeOpen(key, open, persist = true) {
      if (key === "config") return setConfigMenuTreeOpen(open, persist);
      if (key === "maint") return setMaintMenuTreeOpen(open, persist);
      if (key === "reports") return setReportsMenuTreeOpen(open, persist);
      return setCustomMenuTreeOpen(key, open, persist);
    }

    function createMenuItem() {
      const next = window.prompt("Menu item name", "");
      if (next == null) return;
      const clean = String(next).trim();
      if (!clean) return;
      const key = `custom_menu_${Date.now()}`;
      menuLabels[key] = clean;
      if (!Array.isArray(menuOrder.top)) menuOrder.top = [];
      if (!menuOrder.top.includes(key)) menuOrder.top.push(key);
      menuOrder[key] = [];
      menuTreeOpen[key] = true;
      applyMenuOrder();
      setAnyMenuTreeOpen(key, true, false);
      persistMenuLayout();
    }

    function attachMenuAddButton() {
      const btn = document.getElementById("menu-add");
      if (!btn || btn.dataset.menuAddBound === "1") return;
      btn.dataset.menuAddBound = "1";
      btn.addEventListener("click", (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        createMenuItem();
      });
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
      document.body.classList.add("is-dnd-dragging");
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
          targetPosition = menuDropPosition(next, mv.clientY, fromKey);
          if (targetPosition === "inside") openMenuTreeForGroup(targetKey, false);
          if (targetPosition === "none") {
            targetGroup = group;
            targetKey = fromKey;
          }
          markMenuDropTarget(next, targetPosition);
        } else if (container) {
          targetItem = null;
          targetGroup = container.getAttribute("data-menu-drop-group") || "top";
          targetKey = null;
          targetPosition = "before";
          markMenuDropContainer(container);
        }
      };
      const onUp = (up) => {
        up.preventDefault();
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
        document.querySelectorAll(".menu-item.is-menu-dragging,.menu-item.is-menu-drag-over,.menu-item.is-menu-drop-after,.menu-item.is-menu-drop-inside").forEach((el) => {
          el.classList.remove("is-menu-dragging", "is-menu-drag-over", "is-menu-drop-after", "is-menu-drop-inside");
        });
        document.querySelectorAll(".is-menu-drop-zone-active").forEach((el) => el.classList.remove("is-menu-drop-zone-active"));
        ghost.remove();
        menuDragState = null;
        document.body.classList.remove("is-dnd-dragging");
        moveMenuItem(fromKey, targetGroup, targetKey, targetPosition);
      };
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    }

    function attachMenuDropContainers(root = document) {
      root.querySelectorAll("[data-menu-drop-group]").forEach((container) => {
        if (container.dataset.menuContainerDropBound === "1") return;
        container.dataset.menuContainerDropBound = "1";
        container.addEventListener("dragover", (ev) => {
          const fromKey = menuDragState && menuDragState.key;
          if (!fromKey) return;
          ev.preventDefault();
          ev.stopPropagation();
          if (ev.dataTransfer) ev.dataTransfer.dropEffect = "move";
          markMenuDropContainer(container);
        });
        container.addEventListener("dragleave", (ev) => {
          if (container.contains(ev.relatedTarget)) return;
          container.classList.remove("is-menu-drop-zone-active");
        });
        container.addEventListener("drop", (ev) => {
          const fromKey = (menuDragState && menuDragState.key) || (ev.dataTransfer && ev.dataTransfer.getData("application/x-menu-key"));
          const toGroup = container.getAttribute("data-menu-drop-group") || "top";
          if (!fromKey || !toGroup) return;
          ev.preventDefault();
          ev.stopPropagation();
          container.classList.remove("is-menu-drop-zone-active");
          menuDragState = null;
          document.body.classList.remove("is-dnd-dragging");
          moveMenuItem(fromKey, toGroup, null, "before");
        });
      });
    }

    function attachMenuDragHandles(root = document) {
      attachMenuContextMenuActions();
      attachMenuAddButton();
      attachMenuDropContainers(root);
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
          document.body.classList.add("is-dnd-dragging");
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
          document.body.classList.remove("is-dnd-dragging");
          document.querySelectorAll(".menu-item.is-menu-drag-over,.menu-item.is-menu-drop-after,.menu-item.is-menu-drop-inside").forEach((el) => el.classList.remove("is-menu-drag-over", "is-menu-drop-after", "is-menu-drop-inside"));
          document.querySelectorAll(".is-menu-drop-zone-active").forEach((el) => el.classList.remove("is-menu-drop-zone-active"));
        });
      });
      root.querySelectorAll(".menu-item[data-menu-group][data-menu-key]").forEach((item) => {
        if (item.dataset.menuDropBound === "1") return;
        item.dataset.menuDropBound = "1";
        item.addEventListener("click", (ev) => {
          const key = item.getAttribute("data-menu-key");
          if (!key || !isMenuTreeKey(key) || MENU_TREE_KEYS.includes(key)) return;
          ev.preventDefault();
          ev.stopPropagation();
          const tree = item.closest(".menu-tree");
          setAnyMenuTreeOpen(key, !(tree && tree.classList.contains("is-open")));
        });
        item.addEventListener("dragover", (ev) => {
          const fromKey = menuDragState && menuDragState.key;
          if (fromKey) {
            ev.preventDefault();
            ev.stopPropagation();
            const position = menuDropPosition(item, ev.clientY, fromKey);
            if (position === "none") {
              if (ev.dataTransfer) ev.dataTransfer.dropEffect = "none";
              markMenuDropTarget(null, position);
              return;
            }
            if (ev.dataTransfer) ev.dataTransfer.dropEffect = "move";
            if (position === "inside") openMenuTreeForGroup(item.getAttribute("data-menu-key"), false);
            markMenuDropTarget(item, position);
          }
        });
        item.addEventListener("dragleave", () => {
          item.classList.remove("is-menu-drag-over", "is-menu-drop-after", "is-menu-drop-inside");
        });
        item.addEventListener("drop", (ev) => {
          const fromKey = (menuDragState && menuDragState.key) || (ev.dataTransfer && ev.dataTransfer.getData("application/x-menu-key"));
          const toGroup = item.getAttribute("data-menu-group");
          const position = menuDropPosition(item, ev.clientY, fromKey);
          item.classList.remove("is-menu-drag-over", "is-menu-drop-after", "is-menu-drop-inside");
          menuDragState = null;
          if (!fromKey || !toGroup || position === "none") return;
          ev.preventDefault();
          ev.stopPropagation();
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
      if (!group || group === "top") return;
      setAnyMenuTreeOpen(group, true, persist);
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
      if (["planner", "shopping", "duty_report"].includes(key)) {
        activePanel = key;
        return;
      }
      if (key === "shift_code_analysis") {
        activePanel = "reports";
        return;
      }
      if (key === "maint") {
        activePanel = "maint";
        return;
      }
      if (key === "reports") {
        activePanel = "reports";
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

    function applyActiveConfigView(refresh = false, options = {}) {
      const viewName = ["targets", "catalog", "details"].includes(activeConfigView) ? activeConfigView : "targets";
      activeConfigView = viewName;
      setConfigView(viewName);
      document.getElementById("menu-config").classList.remove("active");
      document.getElementById("menu-config-target").classList.toggle("active", viewName === "targets");
      document.getElementById("menu-config-catalog").classList.toggle("active", viewName === "catalog");
      document.getElementById("menu-config-details").classList.toggle("active", viewName === "details");
      if (!refresh) return;
      if (viewName === "targets") return refreshTargetEditor(options);
      if (viewName === "catalog") return refreshNutritionCatalog();
      if (viewName === "details") return refreshDetailSettings();
    }

    async function openConfigChild(viewName) {
      if (!(await resolveUnsavedBeforeLeaving())) return;
      activeConfigView = ["targets", "catalog", "details"].includes(viewName) ? viewName : "targets";
      persistActiveConfigView();
      const leafKey = leafKeyForConfigView(activeConfigView);
      setActiveMenuPathForKey(leafKey);
      setActivePanel("config");
      openMenuTreeForGroup(menuGroupForKey(leafKey));
      await applyActiveConfigView(true, { focusDob: activeConfigView === "targets" });
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

    function renderMaintMenu() {
      const box = document.getElementById("maint-menu-children");
      if (!box) return;
      const menuSheets = (maintSheets || []).filter((sheet) => sheet && sheet.sheet_key && !isRemovedMenuKey(sheet.sheet_key));
      const byKey = new Map(menuSheets.map((sheet) => [sheet.sheet_key, sheet]));
      const preferredByKey = {};
      for (const sheet of menuSheets) {
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
      const minHeight = parseFloat(getComputedStyle(el).minHeight || "0");
      el.style.height = `${Math.max(el.scrollHeight, Number.isFinite(minHeight) ? minHeight : 0)}px`;
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
        ["#maint-editor .maint-sheet-title:not(.maint-roster-title)", "table_offset_maint_sheet"],
        ["#maint-editor table.maint-roster-table", "table_offset_maint_roster"],
        ["#maint-editor .maint-roster-pane:first-child .maint-pane-title", "table_offset_maint_roster"],
        ["#shopping-content", "table_offset_shopping"],
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
        document.body.classList.add("is-horizontal-dragging");
        const startX = ev.clientX;
        const startOffset = formOffsetPx(key);
        const onMove = (mv) => {
          formColumnWidths[key] = startOffset + (mv.clientX - startX);
          applyFn();
        };
        const onUp = () => {
          window.removeEventListener("mousemove", onMove);
          window.removeEventListener("mouseup", onUp);
          document.body.classList.remove("is-horizontal-dragging");
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
        ["#maint-editor .maint-sheet-title:not(.maint-roster-title)", "table_offset_maint_sheet"],
        ["#maint-editor .maint-roster-pane:first-child .maint-pane-title", "table_offset_maint_roster"],
        ["#shopping-panel h1", "table_offset_shopping"],
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
            if (typeof applyShiftCodeAnalysisBlockLayout === "function") applyShiftCodeAnalysisBlockLayout(root);
            if (typeof applyDutyBlockLayout === "function") applyDutyBlockLayout();
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
