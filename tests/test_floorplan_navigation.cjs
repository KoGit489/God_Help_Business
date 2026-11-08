const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function loadFloorplan({ panorama = false } = {}) {
  const elements = new Map();
  const created = [];
  function createElement() {
    const classes = new Set();
    const listeners = new Map();
    const node = {
      disabled: true, style: {}, value: '', textContent: '', children: [],
      className: '', classList: { add: (name) => classes.add(name), contains: (name) => classes.has(name), remove: (name) => classes.delete(name) },
      addEventListener: (name, callback) => listeners.set(name, callback),
      appendChild(child) { child.parent = this; this.children.push(child); },
      replaceChildren(...children) { this.children = children; },
      querySelector() { return this.tip ||= { style: {} }; },
      setAttribute(name, value) { this[name] = value; },
      remove() { if (this.parent) this.parent.children = this.parent.children.filter((child) => child !== this); },
      click() { listeners.get('click')?.({ stopPropagation() {}, target: this }); },
      dispatchEvent(event) { listeners.get(event.type)?.(event); },
    };
    created.push(node);
    return node;
  }
  function element(id) {
    if (!elements.has(id)) elements.set(id, createElement());
    return elements.get(id);
  }
  const panoramas = [];
  const pannellum = { viewer: (id, config) => { panoramas.push(config); return { destroy() {}, getYaw: () => config.yaw }; } };
  const context = vm.createContext({
    URLSearchParams,
    pannellum,
    window: { pannellum: panorama ? pannellum : null, location: { search: '', protocol: 'https:', hostname: 'example.com', origin: 'https://example.com' } },
    document: { getElementById: element, querySelectorAll: () => created.filter((node) => node.parent && node.className.includes('nav-arrow')), createElement },
  });
  const source = fs.readFileSync(path.join(__dirname, '../frontend/floorplan.js'), 'utf8');
  vm.runInContext(source.replace(/loadProjects\(\);\s*$/, ''), context);
  vm.runInContext('renderWaypoints = () => {};', context);
  return { element, panoramas, run: (code) => vm.runInContext(code, context) };
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

test('panorama uses only anchored floor hotspots with reverse navigation', () => {
  const { element, panoramas, run } = loadFloorplan({ panorama: true });
  run("state.project = { pins: [{ id: 'one', position_x: 0.2, position_y: 0.5, heading: 90, photo_key: 'one.jpg', media_type: 'insta360' }, { id: 'two', position_x: 0.4, position_y: 0.5, heading: 90, photo_key: 'two.jpg', media_type: 'insta360' }] }; openCapture(state.project.pins[0], 1);");
  assert.equal(panoramas[0].hotSpots.length, 1);
  assert.equal(panoramas[0].hotSpots[0].cssClass, 'nav-hotspot');
  assert.equal(element('prev-capture').disabled, true);
  panoramas[0].hotSpots[0].clickHandlerFunc();
  assert.equal(run('state.viewerPin.id'), 'two');
  assert.equal(panoramas[1].hotSpots.length, 1);
  assert.equal(panoramas[1].hotSpots[0].cssClass, 'nav-hotspot back');
  assert.equal(element('next-capture').disabled, true);
  assert.equal(element('capture-media').children.length, 0);
  panoramas[1].hotSpots[0].clickHandlerFunc();
  assert.equal(run('state.viewerPin.id'), 'one');
  assert.equal(panoramas[2].hotSpots[0].cssClass, 'nav-hotspot');
  assert.equal(panoramas[2].hotSpots.length, 1);
});

test('regular previews use the shared floor-arrow shape and direction filtering', () => {
  const { element, run } = loadFloorplan();
  run("state.project = { pins: [{ id: 'one', position_x: 0.2, position_y: 0.5, heading: 90, photo_key: 'one.jpg' }, { id: 'two', position_x: 0.4, position_y: 0.5, heading: 270, photo_key: 'two.jpg' }] }; openCapture(state.project.pins[0], 1);");
  const forward = element('capture-media').children[0];
  assert.equal(forward.className, 'nav-arrow');
  assert.equal(forward.innerHTML, '<span class="floor-arrow"></span>');
  forward.click();
  const backward = element('capture-media').children[0];
  assert.equal(backward.className, 'nav-arrow back');
  assert.equal(backward.innerHTML, forward.innerHTML);
  backward.click();
  assert.equal(run('state.viewerPin.id'), 'one');
});

test('floor-arrow presses do not start panorama dragging', () => {
  const { element, run } = loadFloorplan();
  run("createFloorArrow(document.getElementById('hotspot'), { back: true, number: 1 })");
  const hotspot = element('hotspot');
  assert.equal(hotspot.role, 'button');
  assert.equal(hotspot['aria-label'], 'Back to capture #1');
  assert.equal(hotspot.children[0].className, 'floor-arrow');
  for (const type of ['mousedown', 'pointerdown', 'touchstart']) {
    let stopped = false;
    hotspot.dispatchEvent({ type, stopPropagation() { stopped = true; } });
    assert.equal(stopped, true, type);
  }
});

test('panorama floor hotspots retain heading-relative forward and back bearings', () => {
  const { run } = loadFloorplan();
  run("state.project = { pins: [{ id: 'one', position_x: 0.2, position_y: 0.5, heading: 90 }, { id: 'two', position_x: 0.4, position_y: 0.5, heading: 90 }, { id: 'three', position_x: 0.6, position_y: 0.5, heading: 90 }] }; trackNavHistory(state.project.pins[0]); trackNavHistory(state.project.pins[1]);");
  assert.equal(run('buildNavHotspots(state.project.pins[1])[0].yaw'), -180);
  assert.equal(run('buildNavHotspots(state.project.pins[1])[0].cssClass'), 'nav-hotspot back');
  assert.equal(run('buildNavHotspots(state.project.pins[1])[1].yaw'), 0);
});

test('panorama transitions face the clicked white or yellow arrow', () => {
  const { panoramas, run } = loadFloorplan({ panorama: true });
  run("state.project = { pins: [{ id: 'one', position_x: 0.2, position_y: 0.5, heading: 0, photo_key: 'one.jpg', media_type: 'insta360' }, { id: 'two', position_x: 0.4, position_y: 0.5, heading: 0, photo_key: 'two.jpg', media_type: 'insta360' }] }; openCapture(state.project.pins[0], 1);");

  const forward = panoramas[0].hotSpots[0];
  assert.equal(forward.cssClass, 'nav-hotspot');
  panoramas[0].yaw = -90;
  forward.clickHandlerFunc();
  assert.equal(run('state.viewerPin.id'), 'two');
  assert.equal(panoramas[1].yaw, 90);

  const backward = panoramas[1].hotSpots[0];
  assert.equal(backward.cssClass, 'nav-hotspot back');
  panoramas[1].yaw = 90;
  backward.clickHandlerFunc();
  assert.equal(run('state.viewerPin.id'), 'one');
  assert.equal(panoramas[2].yaw, -90);
});

test('walking heading changes do not rotate panorama arrows away from capture one alignment', () => {
  const { panoramas, run } = loadFloorplan({ panorama: true });
  run("state.project = { pins: [{ id: 'one', position_x: 0.05753747768000021, position_y: 0.7572884547124815, heading: 0, photo_key: 'one.jpg', media_type: 'insta360' }, { id: 'two', position_x: 0.08757929725839059, position_y: 0.7572884547124815, heading: 90, photo_key: 'two.jpg', media_type: 'insta360' }, { id: 'three', position_x: 0.11757929725839059, position_y: 0.7572884547124815, heading: 90, photo_key: 'three.jpg', media_type: 'insta360' }] }; openCapture(state.project.pins[0], 1);");
  assert.equal(panoramas[0].hotSpots[0].yaw, 90);
  run('openCapture(state.project.pins[1], 2)');
  assert.equal(panoramas[1].yaw, 90);
  const backward = panoramas[1].hotSpots.find((hotspot) => hotspot.cssClass === 'nav-hotspot back');
  const forward = panoramas[1].hotSpots.find((hotspot) => hotspot.cssClass === 'nav-hotspot');
  assert.equal(backward.yaw, -90);
  assert.equal(forward.yaw, 90);
  forward.clickHandlerFunc();
  assert.equal(run('state.viewerPin.id'), 'three');
  assert.equal(panoramas[2].yaw, 90);
  assert.equal(panoramas[2].hotSpots[0].yaw, -90);
  panoramas[2].yaw = -90;
  panoramas[2].hotSpots[0].clickHandlerFunc();
  assert.equal(run('state.viewerPin.id'), 'two');
  assert.equal(panoramas[3].yaw, -90);
  assert.equal(run('state.project.pins[1].heading'), 90);
  assert.equal(run('state.project.pins[0].heading'), 0);
});

test('viewing history never turns the forward destination white on the first capture', () => {
  const { panoramas, run } = loadFloorplan({ panorama: true });
  run("state.project = { pins: [{ id: 'one', position_x: 0.2, position_y: 0.5, photo_key: 'one.jpg', media_type: 'insta360' }, { id: 'two', position_x: 0.4, position_y: 0.5, photo_key: 'two.jpg', media_type: 'insta360' }] }; openCapture(state.project.pins[1], 2); openCapture(state.project.pins[0], 1);");
  const hotspots = panoramas[1].hotSpots;
  assert.equal(hotspots.length, 1);
  assert.equal(hotspots[0].cssClass, 'nav-hotspot');
  hotspots[0].clickHandlerFunc();
  assert.equal(run('state.viewerPin.id'), 'two');
});

test('previous and next commands do not wrap across route endpoints', () => {
  const { element, run } = loadFloorplan();
  run("state.project = { pins: [{ id: 'one', position_x: 0.2, position_y: 0.5 }, { id: 'two', position_x: 0.4, position_y: 0.5 }] }; openCapture(state.project.pins[0], 1); stepViewer(-1);");
  assert.equal(run('state.viewerPin.id'), 'one');
  assert.equal(element('prev-capture').disabled, true);
  run('stepViewer(1); stepViewer(1)');
  assert.equal(run('state.viewerPin.id'), 'two');
  assert.equal(element('next-capture').disabled, true);
});

test('switching projects clears the previous drawing, walking and editing state', async () => {
  const { element, run } = loadFloorplan();
  run("renderPlan = () => {}; apiRequest = async (url) => url.endsWith('/annotations') ? [] : { id: 'next', title: 'Next project', pins: [] }; state.plan = { filename: 'old.png' }; state.editingPin = { id: 'old-pin' }; state.navHistory = ['old-pin']; setCurrent(0.5, 0.5, true);");
  await run("selectProject('next')");
  assert.equal(element('walk-step').disabled, true);
  assert.equal(element('save-waypoint').disabled, true);
  assert.equal(run('state.current'), null);
  assert.equal(run('state.plan'), null);
  assert.equal(run('state.editingPin'), null);
  assert.equal(run('state.navHistory.length'), 0);
  assert.equal(element('edit-panel').style.display, 'none');
});

test('opening a native capture automatically processes and opens its preview once', async () => {
  const { panoramas, run } = loadFloorplan({ panorama: true });
  run(`
    globalThis.requests = [];
    state.project = { id: 'project', pins: [{ id: 'native', native_file_key: 'capture.insp', position_x: 0.4, position_y: 0.5, media_type: 'insta360' }] };
    apiRequest = async (url, options = {}) => {
      requests.push({ url, method: options.method || 'GET' });
      return url.endsWith('/process') ? {} : { preview_url: '/media/preview.jpg' };
    };
    openCapture(state.project.pins[0], 1, -90);
  `);
  await new Promise(setImmediate);
  assert.equal(run('requests.length'), 2);
  assert.equal(run('requests[0].method'), 'POST');
  assert.equal(run('requests[0].url'), '/projects/project/pins/native/process');
  assert.equal(panoramas[0].panorama, '/media/preview.jpg');
  assert.equal(panoramas[0].yaw, -90);
  assert.equal(run('state.previewGeneration.size'), 0);
  run('openCapture(state.project.pins[0], 1)');
  assert.equal(run('requests.length'), 2);
});

test('failed automatic preview generation shows an error and clears its pending state', async () => {
  const { element, run } = loadFloorplan();
  run("state.project = { id: 'project', pins: [{ id: 'native', native_file_key: 'capture.insp', position_x: 0.4, position_y: 0.5 }] }; apiRequest = async () => { throw new Error('Audit preview failure'); }; openCapture(state.project.pins[0], 1);");
  await new Promise(setImmediate);
  assert.equal(run('state.previewGeneration.size'), 0);
  assert.ok(element('panorama').children[0].textContent.includes('Audit preview failure'));
});