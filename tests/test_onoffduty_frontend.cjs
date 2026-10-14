const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

const source = readFileSync(join(__dirname, '../meal_planner/web/planner-onoffduty.js'), 'utf8');

function setup() {
  let ready;
  let poll;
  const listeners = {};
  const calls = { load: 0, log: 0, copied: [] };
  const out = {
    innerHTML: '',
    addEventListener: (name, fn) => { listeners[name] = fn; },
    querySelector: () => null,
  };
  const plan = {
    date_iso: '2026-10-04', today_iso: '2026-10-04', relation: 'today',
    roster_code: 'VOC', actions: [{
      kind: 'end', label: 'Off Duty', time: '21:30', status: '', history: [],
      url: 'https://example.test/form?time=21%3A30',
    }],
  };
  const context = vm.createContext({
    document: {
      getElementById: (id) => id === 'onoffduty-out' ? out : null,
      addEventListener: (name, fn) => { if (name === 'DOMContentLoaded') ready = fn; },
    },
    activePanel: 'onoffduty', incomingPlan: plan,
    esc: (value) => String(value ?? ''),
    setInterval: (fn) => { poll = fn; },
    setTimeout() {},
    navigator: { clipboard: { writeText: async (value) => { calls.copied.push(value); } } },
    loadOnOffDutyPlan: async () => { calls.load++; return context.incomingPlan; },
    postOnOffDutyLog: async () => { calls.log++; return context.incomingPlan; },
    applyDutyBlockLayout() {}, attachDutyBlockHandles() {},
  });
  const run = (code) => vm.runInContext(code, context);
  run(source);
  run('onoffPlan = incomingPlan');
  ready();
  return { calls, context, out, listeners, run, poll: () => poll() };
}

function clickTarget(selector, attrs = {}) {
  const node = {
    textContent: 'Copy link',
    getAttribute: (name) => attrs[name] || null,
  };
  return { closest: (query) => query === selector ? node : null };
}

test('desktop card displays time and links without time edit controls', () => {
  const ui = setup();
  ui.run('renderOnOffDuty()');
  assert.match(ui.out.innerHTML, /21:30/);
  assert.match(ui.out.innerHTML, /form\?time=21%3A30/);
  for (const action of ['time-edit', 'time-save', 'time-reset']) {
    assert.ok(!ui.out.innerHTML.includes(`data-onoff-action="${action}"`));
  }
  assert.doesNotMatch(ui.out.innerHTML, /data-onoff-time-input=/);
});

test('poll renders phone-updated time and Open/Copy Form URL', async () => {
  const ui = setup();
  ui.run('renderOnOffDuty()');
  const newUrl = 'https://example.test/form?time=25%3A30';
  ui.context.incomingPlan = { ...ui.context.incomingPlan, actions: [{
    ...ui.context.incomingPlan.actions[0], time: '25:30', url: newUrl,
  }] };
  ui.poll();
  await new Promise(setImmediate);
  assert.equal(ui.calls.load, 1);
  assert.match(ui.out.innerHTML, /25:30/);
  assert.ok(ui.out.innerHTML.includes(`href="${newUrl}"`));
  assert.ok(ui.out.innerHTML.includes(`data-onoff-copy="${newUrl}"`));
  assert.ok(!ui.out.innerHTML.includes('form?time=21%3A30'));
});

test('late Open form log response cannot replace newer polled plan', async () => {
  const ui = setup();
  const oldPlan = ui.context.incomingPlan;
  let finishLog;
  ui.context.postOnOffDutyLog = () => new Promise((resolve) => { finishLog = resolve; });
  ui.listeners.click({ target: clickTarget('a.onoff-open[data-onoff-kind]', { 'data-onoff-kind': 'end' }) });
  const newUrl = 'https://example.test/form?time=25%3A30';
  ui.context.incomingPlan = { ...oldPlan, actions: [{ ...oldPlan.actions[0], time: '25:30', url: newUrl }] };
  await ui.run('refreshOnOffDuty(false)');
  finishLog(oldPlan);
  await new Promise(setImmediate);
  assert.equal(ui.run('onoffPlan.actions[0].time'), '25:30');
  assert.ok(ui.out.innerHTML.includes(newUrl));
});

test('Open and Copy are blocked while poll is loading', async () => {
  const ui = setup();
  ui.run('renderOnOffDuty()');
  ui.run('onoffLoading = true');
  let openBlocked = false;
  ui.listeners.click({
    target: clickTarget('a.onoff-open[data-onoff-kind]', { 'data-onoff-kind': 'end' }),
    preventDefault: () => { openBlocked = true; },
  });
  let copyBlocked = false;
  ui.listeners.click({
    target: clickTarget('[data-onoff-copy]', { 'data-onoff-copy': 'https://example.test/form?time=21%3A30' }),
    preventDefault: () => { copyBlocked = true; },
  });
  await new Promise(setImmediate);
  assert.equal(openBlocked, true);
  assert.equal(copyBlocked, true);
  assert.equal(ui.calls.log, 0);
  assert.deepEqual(ui.calls.copied, []);
});
