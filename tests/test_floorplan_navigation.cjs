const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function loadFloorplan() {
  const elements = new Map();
  function element(id) {
    if (!elements.has(id)) {
      elements.set(id, {
        disabled: true, style: {}, value: '', textContent: '',
        classList: { add() {} }, addEventListener() {}, replaceChildren() {},
      });
    }
    return elements.get(id);
  }
  const context = vm.createContext({
    URLSearchParams,
    window: { location: { search: '', protocol: 'https:', hostname: 'example.com', origin: 'https://example.com' } },
    document: { getElementById: element, querySelectorAll: () => [], createElement: () => ({ style: {} }) },
  });
  const source = fs.readFileSync(path.join(__dirname, '../frontend/floorplan.js'), 'utf8');
  vm.runInContext(source.replace(/loadProjects\(\);\s*$/, ''), context);
  vm.runInContext('renderWaypoints = () => {}; updateNavButtons = () => {};', context);
  return { element, run: (code) => vm.runInContext(code, context) };
}

test('opening a saved waypoint enables walking from its position', () => {
  const { element, run } = loadFloorplan();
  assert.equal(element('walk-step').disabled, true);
  run("state.project = { pins: [{ id: 'one', position_x: 0.2, position_y: 0.7 }] }; openCapture(state.project.pins[0], 1);");
  assert.equal(element('walk-step').disabled, false);
  assert.equal(element('save-waypoint').disabled, false);
  assert.equal(run('state.current.x'), 0.2);
  assert.equal(run('state.start.y'), 0.7);
  assert.equal(run('state.current.saved'), true);
  element('step-distance').value = '3.6';
  element('plan-width').value = '120';
  element('scale-select').value = '0.125';
  run('state.heading = 90; stepRoute();');
  assert.ok(Math.abs(run('state.current.x') - 0.23) < 1e-9);
  assert.equal(run('state.current.y'), 0.7);
  assert.equal(run('state.current.saved'), false);
  assert.equal(run('state.distance'), 3.6);
});

test('a capture without drawing coordinates does not enable walking', () => {
  const { element, run } = loadFloorplan();
  run("state.project = { pins: [{ id: 'one', position_x: null, position_y: null }] }; openCapture(state.project.pins[0], 1);");
  assert.equal(element('walk-step').disabled, true);
  assert.equal(run('state.current'), null);
});