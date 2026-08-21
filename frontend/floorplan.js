function buildApiBases() {
  const params = new URLSearchParams(window.location.search);
  const override = params.get('apiBase');
  if (override) return [override.replace(/\/$/, '')];
  if (window.location.protocol === 'file:' || ['localhost', '127.0.0.1'].includes(window.location.hostname)) return ['http://127.0.0.1:8000'];
  const sameOrigin = window.location.origin.replace(/\/$/, '');
  const wifiBackend = `${window.location.protocol}//${window.location.hostname}:8000`;
  return [...new Set(window.location.port === '5500' ? [wifiBackend, sameOrigin, '/api'] : [sameOrigin, '/api'])];
}

const apiBases = buildApiBases();
const state = { project: null, plan: null, start: null, current: null, distance: 0, heading: 0, viewer: null, timer: null };
const byId = (id) => document.getElementById(id);

function setStatus(text) { byId('plan-status').textContent = text; }
function headers(options = {}) { const result = new Headers(options.headers || {}); result.set('x-user-id', 'demo'); return result; }

async function apiRequest(path, options = {}) {
  let lastError = null;
  for (const base of apiBases) {
    try {
      const response = await fetch(`${base}${path}`, { ...options, headers: headers(options) });
      const payload = await response.json().catch(() => null);
      if (response.ok) return payload;
      if (response.status === 404 && base !== apiBases[apiBases.length - 1]) { lastError = new Error('Not found'); continue; }
      throw new Error(payload?.error?.message || `Request failed (${response.status})`);
    } catch (error) { lastError = error; }
  }
  throw lastError || new Error('Unable to reach the API.');
}

function renderPlan() {
  const wrap = byId('plan-wrap');
  if (!state.plan) { wrap.innerHTML = '<div class="plan-empty">Your floor plan will appear here.<br />For clickable waypoints, upload a JPG or PNG export of the plan.</div>'; return; }
  if (state.plan.content_type === 'application/pdf' || state.plan.filename.toLowerCase().endsWith('.pdf')) {
    wrap.innerHTML = '<div class="plan-stage"><canvas id="plan-canvas" aria-label="Uploaded floor plan"></canvas><div id="waypoint-layer"></div></div>';
    if (!window.pdfjsLib) { wrap.innerHTML = `<iframe title="Floor plan PDF" src="${state.plan.media_url}" style="width:100%;height:70vh;border:0;background:white;"></iframe>`; return; }
    window.pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
    window.pdfjsLib.getDocument(state.plan.media_url).promise.then((pdf) => pdf.getPage(1)).then((page) => {
      const viewport = page.getViewport({ scale: 1.5 }); const canvas = byId('plan-canvas');
      canvas.width = viewport.width; canvas.height = viewport.height; canvas.style.maxWidth = 'min(100%, 1000px)'; canvas.style.height = 'auto';
      return page.render({ canvasContext: canvas.getContext('2d'), viewport }).promise;
    }).then(renderWaypoints).catch(() => { setStatus('The PDF viewer could not render this plan. Export it as JPG or PNG for clickable waypoints.'); });
    return;
  }
  wrap.innerHTML = '<div class="plan-stage"><img id="plan-image" alt="Uploaded floor plan" /><div id="waypoint-layer"></div></div>';
  byId('plan-image').src = state.plan.media_url;
  renderWaypoints();
}

function renderWaypoints() {
  const layer = byId('waypoint-layer');
  if (!layer) return;
  layer.innerHTML = '';
  (state.project?.pins || []).forEach((pin, index) => {
    if (pin.position_x == null || pin.position_y == null) return;
    const dot = document.createElement('button');
    dot.type = 'button'; dot.className = 'waypoint'; dot.dataset.label = `#${index + 1}`;
    dot.style.left = `${pin.position_x * 100}%`; dot.style.top = `${pin.position_y * 100}%`;
    dot.title = `Open capture ${index + 1}`;
    dot.addEventListener('click', (event) => { event.stopPropagation(); openCapture(pin, index + 1); });
    layer.appendChild(dot);
  });
  if (state.current && !state.current.saved) {
    const current = document.createElement('div'); current.className = 'waypoint current'; current.dataset.label = 'Current';
    current.style.left = `${state.current.x * 100}%`; current.style.top = `${state.current.y * 100}%`; layer.appendChild(current);
  }
  byId('waypoint-count').textContent = String((state.project?.pins || []).filter((pin) => pin.position_x != null).length);
}

function setCurrent(x, y, isStart = false) {
  state.current = { x: Math.max(0, Math.min(1, x)), y: Math.max(0, Math.min(1, y)), saved: false };
  if (isStart) state.start = { ...state.current };
  byId('walk-step').disabled = false; byId('save-waypoint').disabled = false;
  renderWaypoints();
}

function handlePlanClick(event) {
  const drawing = byId('plan-image') || byId('plan-canvas');
  if (!drawing) return;
  const rect = drawing.getBoundingClientRect();
  setCurrent((event.clientX - rect.left) / rect.width, (event.clientY - rect.top) / rect.height, !state.start);
  setStatus(state.start && state.distance ? 'Current route position updated.' : 'Starting point set. Walk a step or save a capture.');
}

function stepRoute() {
  if (!state.current) { setStatus('Click the drawing first to choose a starting point.'); return; }
  const feet = Number(byId('step-distance').value) || 0;
  const planWidth = Math.max(1, Number(byId('plan-width').value) || 120);
  const radians = state.heading * Math.PI / 180;
  const delta = feet / planWidth;
  setCurrent(state.current.x + Math.sin(radians) * delta, state.current.y - Math.cos(radians) * delta);
  state.distance += feet;
  byId('route-distance').textContent = `${state.distance.toFixed(1)} ft`;
  const scale = Number(byId('scale-select').value) || 0.125;
  setStatus(`Moved ${feet} ft (${(feet * scale).toFixed(3)} drawing inches) using the calibrated route heading.`);
}

async function uploadPlan(file) {
  if (!state.project || !file) return;
  const form = new FormData(); form.append('file', file);
  setStatus('Uploading floor plan...');
  try { state.plan = await apiRequest(`/projects/${state.project.id}/floor-plan-upload`, { method: 'POST', body: form }); renderPlan(); setStatus(`Plan loaded: ${state.plan.filename}`); }
  catch (error) { setStatus(`Floor plan upload failed: ${error.message}`); }
}

async function saveWaypoint() {
  if (!state.project || !state.current) { setStatus('Choose a project and click the plan first.'); return; }
  const x = state.current.x; const y = state.current.y;
  setStatus('Saving waypoint...');
  try {
    const pin = await apiRequest(`/projects/${state.project.id}/pins`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ latitude: Number((5.55 + y * 0.02).toFixed(6)), longitude: Number((-0.25 + x * 0.02).toFixed(6)), heading: state.heading, position_x: x, position_y: y, captured_on: new Date().toISOString().slice(0, 10), media_type: 'insta360' }) });
    const photo = byId('photo-file').files[0]; const native = byId('native-file').files[0];
    if (photo) { const form = new FormData(); form.append('file', photo); await apiRequest(`/projects/${state.project.id}/pins/${pin.id}/upload`, { method: 'POST', body: form }); }
    if (native) { const form = new FormData(); form.append('file', native); await apiRequest(`/projects/${state.project.id}/pins/${pin.id}/native-upload`, { method: 'POST', body: form }); }
    state.project.pins.push({ ...pin, position_x: x, position_y: y, photo_key: photo ? `uploads/${state.project.id}/${pin.id}/${photo.name}` : null, native_file_key: native ? `uploads/${state.project.id}/${pin.id}/native/${native.name}` : null });
    state.current.saved = true; renderWaypoints(); setStatus('Waypoint saved. Click its dot to open the capture.'); byId('photo-file').value = ''; byId('native-file').value = '';
  } catch (error) { setStatus(`Waypoint save failed: ${error.message}`); }
}

function mediaUrl(key) { return key ? `${apiBases[0]}/media/${key}` : null; }
function openCapture(pin, number) {
  byId('viewer-title').textContent = `Capture #${number} · heading ${pin.heading || 0}°`;
  byId('viewer-modal').classList.add('open');
  const imageUrl = mediaUrl(pin.photo_key || pin.thumbnail_key);
  byId('plain-preview').style.display = 'none'; byId('panorama').style.display = 'block';
  if (state.viewer) { state.viewer.destroy(); state.viewer = null; }
  if (imageUrl && window.pannellum && pin.media_type === 'insta360') state.viewer = pannellum.viewer('panorama', { type: 'equirectangular', panorama: imageUrl, autoLoad: true, yaw: pin.heading || 0 });
  else if (imageUrl) { byId('panorama').style.display = 'none'; byId('plain-preview').src = imageUrl; byId('plain-preview').style.display = 'block'; }
  else { byId('panorama').innerHTML = '<div style="color:white;padding:4rem 1rem;text-align:center">The original .insp file is saved, but it needs an exported preview image to display in this browser demo.</div>'; }
}

async function loadProjects() {
  try {
    const projects = await apiRequest('/projects'); const select = byId('project-select'); select.innerHTML = '';
    projects.forEach((project) => { const option = document.createElement('option'); option.value = project.id; option.textContent = `${project.title} (${project.pin_count} pins)`; select.appendChild(option); });
    if (!projects.length) { setStatus('Create a project on the dashboard first.'); return; }
    await selectProject(projects[0].id);
  } catch (error) { setStatus(`Could not load projects: ${error.message}`); }
}

async function selectProject(projectId) {
  try { state.project = await apiRequest(`/projects/${projectId}/review`); state.start = null; state.current = null; state.distance = 0; byId('route-distance').textContent = '0.0 ft'; renderPlan(); renderWaypoints(); setStatus(`${state.project.title} loaded. Upload a plan or choose a saved route.`); }
  catch (error) { setStatus(`Could not load project: ${error.message}`); }
}

function enableSensors() {
  if (!window.DeviceOrientationEvent) { byId('telemetry-status').textContent = 'This browser does not provide device heading sensors.'; return; }
  window.addEventListener('deviceorientationabsolute', (event) => { if (typeof event.alpha === 'number') { state.heading = event.alpha; byId('heading').value = String(Math.round(state.heading)); byId('heading-value').textContent = `${Math.round(state.heading)}°`; } }, true);
  byId('telemetry-status').textContent = 'Device heading enabled when supported by the browser.';
}

byId('project-select').addEventListener('change', (event) => selectProject(event.target.value));
byId('floor-plan-file').addEventListener('change', (event) => uploadPlan(event.target.files[0]));
byId('plan-wrap').addEventListener('click', handlePlanClick);
byId('heading').addEventListener('input', (event) => { state.heading = Number(event.target.value); byId('heading-value').textContent = `${state.heading}°`; });
byId('walk-step').addEventListener('click', stepRoute);
byId('save-waypoint').addEventListener('click', saveWaypoint);
byId('update-mode').addEventListener('change', (event) => {
  if (state.timer) { clearInterval(state.timer); state.timer = null; }
  if (event.target.value === 'interval') {
    state.timer = setInterval(() => { if (state.current) stepRoute(); }, 5000);
    setStatus('Interval mode enabled. The route advances every 5 seconds after a starting point is set.');
  }
});
byId('enable-sensors').addEventListener('click', enableSensors);
byId('set-gps').addEventListener('click', () => { if (!navigator.geolocation) { byId('telemetry-status').textContent = 'GPS is not available in this browser.'; return; } navigator.geolocation.getCurrentPosition(() => { byId('telemetry-status').textContent = 'GPS is available. Click the plan to calibrate its matching starting point.'; }, () => { byId('telemetry-status').textContent = 'GPS permission was unavailable; the calibrated demo route is still ready.'; }); });
byId('close-viewer').addEventListener('click', () => { byId('viewer-modal').classList.remove('open'); if (state.viewer) { state.viewer.destroy(); state.viewer = null; } });
loadProjects();
