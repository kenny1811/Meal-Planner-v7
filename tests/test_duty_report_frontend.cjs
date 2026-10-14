const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

const source = readFileSync(join(__dirname, '../meal_planner/web/planner-duty.js'), 'utf8');

function setup(status = 'sent', time = '21:30') {
  const handlers = {};
  let ready;
  let timer;
  const calls = { begin: 0, post: 0, load: 0 };
  const input = {
    tagName: 'INPUT', readOnly: true, value: time,
    dataset: { catalogEditing: '0', catalogOriginalValue: time },
    getAttribute: (name) => name === 'data-duty-time-slot' ? `VOC@${time}` : null,
    hasAttribute: (name) => name === 'data-duty-time-slot',
    matches: (selector) => selector.includes('input[data-duty-time-slot]'),
    closest: (selector) => selector.includes('input[data-duty-time-slot]') ? input : null,
    classList: { contains: () => false },
  };
  const out = {
    innerHTML: '', contains: (el) => el === input,
    querySelectorAll: () => [],
    addEventListener: (name, fn) => { handlers[name] = fn; },
  };
  const plan = {
    date_iso: '2026-10-03', today_iso: '2026-10-03', relation: 'today',
    now_iso: '2026-10-03T12:00:00+08:00', segments: [], mapping: {}, events: [],
    source: 'roster', mode: 'auto', slots: [{
      id: `VOC@${time}`, time, original_time: time, status, group: 'test',
      content: time === '09:15' ? '報開工, 報平安更'
        : time === '21:30' ? '報收工, 報平安更' : '中途報平安更',
      message: 'test',
    }],
  };
  const document = {
    activeElement: null,
    getElementById: (id) => id === 'duty-report-out' ? out : null,
    addEventListener: (name, fn) => { if (name === 'DOMContentLoaded') ready = fn; },
  };
  const context = vm.createContext({
    document, activePanel: 'duty_report', incomingPlan: plan, input,
    esc: (text) => String(text ?? ''),
    setInterval: (fn) => { timer = fn; },
    beginCatalogCellEdit: (el) => { calls.begin++; el.readOnly = false; el.dataset.catalogEditing = '1'; },
    endCatalogCellEdit: (el) => { el.readOnly = true; el.dataset.catalogEditing = '0'; },
    postDutyReportOverride: async () => { calls.post++; return plan; },
    loadDutyReportPlan: async () => { calls.load++; return context.incomingPlan; },
  });
  const run = (script) => vm.runInContext(script, context);
  run(source);
  run('dutyReportPlan = incomingPlan;');
  ready();
  return { context, calls, input, out, document, handlers, run, poll: () => timer() };
}

test('sent start and end render as text without a time editor', () => {
  for (const time of ['09:15', '21:30']) {
    const ui = setup('sent', time);
    ui.run('renderDutyReport()');
    assert.ok(!ui.out.innerHTML.includes('data-duty-time-slot='));
    assert.ok(ui.out.innerHTML.includes(time));
  }
});

test('sent time rejects F2, typing, double click, IME and stale commit in the frontend', () => {
  const ui = setup();
  for (const key of ['F2', '2']) {
    ui.handlers.keydown({ target: ui.input, key, preventDefault() {} });
  }
  ui.handlers.dblclick({ target: ui.input, preventDefault() {} });
  ui.handlers.compositionstart({ target: ui.input });
  ui.input.value = '22:00';
  ui.run('dutyCommitCell(input, null)');
  assert.equal(ui.calls.begin, 0);
  assert.equal(ui.calls.post, 0);
});

test('polling still runs while a time input is focused and locks it after sent', async () => {
  const ui = setup('pending');
  ui.document.activeElement = ui.input;
  ui.input.dataset.catalogEditing = '1';
  ui.input.readOnly = false;
  ui.context.incomingPlan = { ...ui.context.incomingPlan,
    slots: [{ ...ui.context.incomingPlan.slots[0], status: 'sent' }] };
  ui.poll();
  await new Promise(setImmediate);
  assert.equal(ui.calls.load, 1);
  assert.equal(ui.input.dataset.catalogEditing, '0');
  assert.ok(!ui.out.innerHTML.includes('data-duty-time-slot='));
  assert.equal(ui.calls.post, 0);
});

test('polling preserves an unsent edit and its typed value', async () => {
  const ui = setup('pending', '12:30');
  ui.document.activeElement = ui.input;
  ui.input.value = '22:00';
  ui.input.dataset.catalogEditing = '1';
  ui.out.innerHTML = 'existing editor';
  await ui.run('refreshDutyReport(false, true)');
  assert.equal(ui.input.value, '22:00');
  assert.equal(ui.out.innerHTML, 'existing editor');
  ui.handlers.keydown({ target: ui.input, key: 'F2', preventDefault() {} });
  ui.run('dutyBeginCellEdit(input)');
  assert.equal(ui.calls.begin, 1);
});

test('pending report start and end times are read only while message stays editable', () => {
  for (const time of ['09:15', '21:30']) {
    const ui = setup('pending', time);
    ui.run('renderDutyReport()');
    assert.ok(!ui.out.innerHTML.includes('data-duty-time-slot='));
    assert.ok(ui.out.innerHTML.includes('data-duty-msg-slot='));
    ui.handlers.keydown({ target: ui.input, key: 'F2', preventDefault() {} });
    ui.run('dutyCommitCell(input, null)');
    assert.equal(ui.calls.begin, 0);
    assert.equal(ui.calls.post, 0);
  }
});
