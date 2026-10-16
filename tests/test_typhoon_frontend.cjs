const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

const source = readFileSync(join(__dirname, '../meal_planner/web/planner-typhoon.js'), 'utf8');

function setup(name = '杜鵑') {
  const box = { value: name, title: '' };
  const status = { textContent: '', title: '' };
  const listeners = {};
  const out = { innerHTML: '', addEventListener: (key, fn) => { listeners[key] = fn; } };
  const calls = { names: [], plans: [], saves: [] };
  let ready;
  const context = vm.createContext({
    activePanel: 'typhoon', typhoonSavedState: { name }, initialName: name,
    response: { status: 'none', name: '', names: [], note: 'No active cyclone.', checked_at: '2026-10-16T23:30:00+08:00' },
    document: {
      getElementById: (id) => ({ 'typhoon-name': box, 'typhoon-name-status': status, 'typhoon-out': out })[id] || null,
      addEventListener: (key, fn) => { if (key === 'DOMContentLoaded') ready = fn; },
    },
    esc: (value) => String(value ?? ''),
    loadTyphoonCurrentName: async (force) => { calls.names.push(force); return context.response; },
    loadTyphoonPlan: async (params) => {
      calls.plans.push(params);
      return { ok: false, date_iso: '2026-10-16', today_iso: '2026-10-16', relation: 'today' };
    },
    persistUiState: (value) => { calls.saves.push(value); },
    setActivePanel: (value) => { context.activePanel = value; },
    currentMinutesHK: () => 600, clockFromMinutes: () => '10:00',
  });
  const run = (code) => vm.runInContext(code, context);
  run(source);
  // Layout and meal rendering are outside this name-status regression suite.
  run('attachTyphoonInputs = () => {}; typhoonName = initialName;');
  ready();
  return { box, status, out, calls, context, listeners, run };
}

test('no cyclone keeps the saved name, displays 已過, and saves only the plain name', async () => {
  const ui = setup();
  await ui.run('openTyphoonPanel()');
  assert.equal(ui.box.value, '杜鵑');
  assert.equal(ui.status.textContent, '(已過)');
  await ui.run('refreshTyphoon()');
  assert.match(ui.out.innerHTML, /id="typhoon-name-status"[^>]*>\(已過\)/);
  assert.equal(ui.calls.saves.at(-1).typhoon_state.name, '杜鵑');
  assert.equal(ui.calls.plans.at(-1).name, '杜鵑');
});

test('no saved name does not invent a previous cyclone', async () => {
  const ui = setup('');
  await ui.run('fillTyphoonNameFromObservatory()');
  assert.equal(ui.box.value, '');
  assert.equal(ui.status.textContent, '(no active typhoon)');
});

test('new active cyclone replaces the old name and removes 已過', async () => {
  const ui = setup();
  await ui.run('fillTyphoonNameFromObservatory()');
  ui.context.response = { status: 'active', name: '薔琵', names: [{ zh: '薔琵', en: 'CHAMPI' }] };
  await ui.run('fillTyphoonNameFromObservatory()');
  assert.equal(ui.box.value, '薔琵');
  assert.equal(ui.status.textContent, '');
  assert.equal(ui.calls.plans.at(-1).name, '薔琵');
  assert.equal(ui.calls.saves.at(-1).typhoon_state.name, '薔琵');
});

test('source failure and network failure preserve the name without labelling it 已過', async () => {
  const ui = setup();
  ui.context.response = { status: 'error', name: '', names: [], note: 'Timeout' };
  await ui.run('fillTyphoonNameFromObservatory()');
  assert.equal(ui.box.value, '杜鵑');
  assert.equal(ui.status.textContent, '(check failed)');
  assert.match(ui.status.title, /Timeout/);
  ui.context.loadTyphoonCurrentName = async () => { throw new Error('Offline'); };
  await ui.run('fillTyphoonNameFromObservatory()');
  assert.equal(ui.status.textContent, '(check failed)');
  assert.equal(ui.status.title, 'Offline');
});

test('Simulate forces a new name lookup before calculating the plan', async () => {
  const ui = setup();
  ui.context.response = { status: 'active', name: '薔琵', names: [{ zh: '薔琵' }] };
  await ui.listeners.click({ target: { closest: () => ({ dataset: { typhoonAction: 'refresh' } }) } });
  assert.deepEqual(ui.calls.names, [true]);
  assert.equal(ui.calls.plans.length, 1);
  assert.equal(ui.calls.plans[0].name, '薔琵');
});

test('a slow response cannot overwrite a manual edit made while checking', async () => {
  const ui = setup();
  let finish;
  ui.context.loadTyphoonCurrentName = () => new Promise((resolve) => { finish = resolve; });
  const pending = ui.run('fillTyphoonNameFromObservatory()');
  ui.run('typhoonName = "手動名"; typhoonNameEdit += 1;');
  ui.box.value = '手動名';
  finish({ status: 'active', name: '薔琵', names: [{ zh: '薔琵' }] });
  await pending;
  assert.equal(ui.box.value, '手動名');
  assert.equal(ui.calls.plans.length, 0);
});

test('late older responses cannot replace a newer name or update a closed panel', async () => {
  const ui = setup();
  let finish;
  ui.context.loadTyphoonCurrentName = () => new Promise((resolve) => { finish = resolve; });
  const pending = ui.run('fillTyphoonNameFromObservatory()');
  ui.context.loadTyphoonCurrentName = async () => ({ status: 'active', name: '薔琵', names: [{ zh: '薔琵' }] });
  await ui.run('fillTyphoonNameFromObservatory()');
  finish({ status: 'none', name: '', names: [] });
  await pending;
  assert.equal(ui.box.value, '薔琵');
  assert.equal(ui.status.textContent, '');
  ui.context.loadTyphoonCurrentName = () => new Promise((resolve) => { finish = resolve; });
  const leaving = ui.run('fillTyphoonNameFromObservatory()');
  ui.run('leaveTyphoonPanel(); activePanel = "other";');
  finish({ status: 'none', name: '', names: [] });
  await leaving;
  assert.equal(ui.status.textContent, '');
});
