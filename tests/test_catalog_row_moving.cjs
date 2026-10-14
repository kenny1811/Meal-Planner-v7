const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

const source = readFileSync(join(__dirname, '../meal_planner/web/planner-config.js'), 'utf8');
const dragSource = source.slice(source.indexOf('    function attachCatalogRowMoving()'),
  source.indexOf('    function removeNutritionCatalogRow('));

function setup() {
  const listeners = new Map();
  const classes = new Set();
  const calls = { moves: [], ended: 0, timersCleared: 0 };
  const timeouts = new Map();
  let timeoutId = 0;
  const input = { value: 'edited ingredient', checked: false, matches: () => true };
  const rows = [0, 1, 2].map(index => ({
    dataset: { catalogIndex: String(index) },
    classList: { add() {}, remove() {} },
    getBoundingClientRect: () => ({ top: 100 + 20 * index, height: 20 }),
    closest() { return this; },
  }));
  const editor = {
    scrollTop: 0,
    querySelectorAll: () => rows,
    contains: row => rows.includes(row),
    getBoundingClientRect: () => ({ top: 90, bottom: 180, left: 0, right: 300 }),
    addEventListener: (name, fn) => { listeners.set(`editor:${name}`, fn); },
  };
  const document = {
    activeElement: input,
    getElementById: () => editor,
    elementFromPoint: (x, y) => x < 0 || x > 300 ? null : rows.find((_, i) => y >= 100 + i * 20 && y < 120 + i * 20),
    body: { classList: { add: name => classes.add(name), remove: name => classes.delete(name) } },
  };
  const context = vm.createContext({
    document,
    window: {
      addEventListener: (name, fn) => { listeners.set(name, fn); },
      removeEventListener: name => { listeners.delete(name); },
    },
    catalogCursorRowIndex: null,
    updateCatalogRowSelection() {}, hideCatalogRowMenu() {},
    endCatalogCellEdit: el => { assert.equal(el, input); calls.ended++; },
    moveNutritionCatalogRow: (from, to) => { if (to !== null && from !== to) calls.moves.push([from, to]); },
    setTimeout: (fn, delay) => { timeouts.set(++timeoutId, { fn, delay }); return timeoutId; },
    clearTimeout: id => { timeouts.delete(id); },
    setInterval: fn => { calls.tick = fn; return 7; },
    clearInterval: id => { assert.equal(id, 7); calls.timersCleared++; },
  });
  vm.runInContext(`${dragSource}\nattachCatalogRowMoving();`, context);
  const start = index => {
    const cell = {
      closest: () => rows[index],
      focus: () => { document.activeElement = cell; },
    };
    listeners.get('editor:pointerdown')({
      button: 0, clientX: 10, clientY: 110 + index * 20,
      pointerId: 1, isPrimary: true,
      target: { closest: () => cell }, preventDefault() {}, stopPropagation() {},
    });
  };
  const hold = () => {
    const entry = Array.from(timeouts.entries()).find(([, item]) => item.delay === 450);
    assert.ok(entry, 'long-press timer exists');
    timeouts.delete(entry[0]);
    entry[1].fn();
  };
  const pointer = (x, y, id = 1) => ({ clientX: x, clientY: y, pointerId: id, preventDefault() {} });
  const click = () => {
    let blocked = false;
    listeners.get('editor:click')({ preventDefault: () => { blocked = true; }, stopImmediatePropagation() {} });
    if (!blocked) input.checked = !input.checked;
    return blocked;
  };
  const clean = (intervals = 1) => {
    for (const name of ['pointermove', 'pointerup', 'pointercancel', 'keydown', 'blur']) assert.equal(listeners.has(name), false);
    assert.equal(classes.size, 0);
    assert.equal(calls.timersCleared, intervals);
    assert.ok(Array.from(timeouts.values()).every(timer => timer.delay === 0));
  };
  return { calls, listeners, document, input, start, hold, pointer, click, clean, classes };
}

test('drag commits current cell and Escape cancels only row movement', () => {
  const ui = setup();
  ui.start(1);
  ui.hold();
  assert.equal(ui.calls.ended, 1);
  assert.notEqual(ui.document.activeElement, ui.input);
  ui.listeners.get('pointermove')(ui.pointer(10, 101));
  ui.listeners.get('keydown')({ key: 'Escape', preventDefault() {} });
  ui.listeners.get('pointerup')(ui.pointer(10, 101));
  assert.equal(ui.click(), true);
  assert.equal(ui.input.checked, false);
  assert.equal(ui.input.value, 'edited ingredient');
  assert.deepEqual(ui.calls.moves, []);
  ui.clean();
});

test('drop after last row moves the first row to the end', () => {
  const ui = setup();
  ui.start(0);
  ui.hold();
  ui.listeners.get('pointerup')(ui.pointer(10, 159));
  assert.deepEqual(ui.calls.moves, [[0, 2]]);
  ui.clean();
});

test('drop before first row moves the last row to the start', () => {
  const ui = setup();
  ui.start(2);
  ui.hold();
  ui.listeners.get('pointerup')(ui.pointer(10, 101));
  assert.deepEqual(ui.calls.moves, [[2, 0]]);
  ui.clean();
});

test('release outside table cancels the last indicated drop', () => {
  const ui = setup();
  ui.start(2);
  ui.hold();
  ui.listeners.get('pointermove')(ui.pointer(10, 101));
  ui.listeners.get('pointerup')(ui.pointer(400, 101));
  assert.deepEqual(ui.calls.moves, []);
  ui.clean();
});

test('losing window focus cancels and cleans all drag resources', () => {
  const ui = setup();
  ui.start(2);
  ui.hold();
  ui.listeners.get('pointermove')(ui.pointer(10, 101));
  ui.listeners.get('blur')();
  assert.deepEqual(ui.calls.moves, []);
  ui.clean();
});

test('short click toggles pause without starting a drag', () => {
  const ui = setup();
  ui.start(1);
  ui.listeners.get('pointerup')(ui.pointer(10, 130));
  assert.equal(ui.click(), false);
  assert.equal(ui.input.checked, true);
  assert.equal(ui.calls.ended, 0);
  assert.equal(ui.classes.size, 0);
  assert.deepEqual(ui.calls.moves, []);
  ui.clean(0);
});

test('long press without moving keeps pause unchanged', () => {
  const ui = setup();
  ui.start(1);
  ui.hold();
  assert.equal(ui.classes.has('catalog-row-dragging'), true);
  ui.listeners.get('pointerup')(ui.pointer(10, 130));
  assert.equal(ui.click(), true);
  assert.equal(ui.input.checked, false);
  assert.deepEqual(ui.calls.moves, []);
  ui.clean();
});

test('moving before the hold threshold cancels both hold and release click', () => {
  const ui = setup();
  ui.start(1);
  ui.listeners.get('pointermove')(ui.pointer(10, 159));
  ui.listeners.get('pointerup')(ui.pointer(10, 159));
  assert.equal(ui.click(), true);
  assert.equal(ui.input.checked, false);
  assert.deepEqual(ui.calls.moves, []);
  ui.clean(0);
});

test('other pointers cannot finish or change the active row drag', () => {
  const ui = setup();
  ui.start(2);
  ui.hold();
  ui.listeners.get('pointerup')(ui.pointer(10, 101, 2));
  assert.equal(ui.listeners.has('pointerup'), true);
  assert.deepEqual(ui.calls.moves, []);
  ui.listeners.get('pointerup')(ui.pointer(10, 101));
  assert.deepEqual(ui.calls.moves, [[2, 0]]);
  ui.clean();
});

test('pointer cancellation cleans hold timer and all listeners', () => {
  const ui = setup();
  ui.start(1);
  ui.listeners.get('pointercancel')(ui.pointer(10, 130));
  assert.deepEqual(ui.calls.moves, []);
  ui.clean(0);
});

test('Escape before the hold threshold also suppresses the release click', () => {
  const ui = setup();
  ui.start(1);
  ui.listeners.get('keydown')({ key: 'Escape', preventDefault() {} });
  ui.listeners.get('pointerup')(ui.pointer(10, 130));
  assert.equal(ui.click(), true);
  assert.equal(ui.input.checked, false);
  assert.deepEqual(ui.calls.moves, []);
  ui.clean(0);
});

test('long-press context menu cannot interrupt a started row drag', () => {
  const ui = setup();
  ui.start(1);
  ui.hold();
  let prevented = false;
  let stopped = false;
  ui.listeners.get('editor:contextmenu')({
    preventDefault: () => { prevented = true; },
    stopImmediatePropagation: () => { stopped = true; },
  });
  assert.equal(prevented, true);
  assert.equal(stopped, true);
  ui.listeners.get('pointerup')(ui.pointer(10, 159));
  assert.deepEqual(ui.calls.moves, [[1, 2]]);
  ui.clean();
});
