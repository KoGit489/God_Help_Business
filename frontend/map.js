const apiBase = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? 'http://127.0.0.1:8000'
  : '/api';

const message = document.getElementById('message');
const recent = document.getElementById('recent-pins');
const mapSurface = document.getElementById('map-surface');
const mapDot = document.getElementById('map-dot');
const headingInput = document.getElementById('heading');
const headingReadout = document.getElementById('heading-readout');
const photoInput = document.getElementById('photo');
const photoPreview = document.getElementById('photo-preview');

function setMessage(text) {
  message.textContent = text;
}

function updateHeadingReadout(value) {
  const heading = Number(value) || 0;
  headingReadout.value = `${heading}°`;
  mapDot.style.transform = `translate(-50%, -50%) rotate(${heading}deg)`;
}

function buildHeaders(options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set('x-user-id', 'demo');
  return headers;
}

async function apiRequest(path, options = {}) {
  const response = await fetch(`${apiBase}${path}`, { ...options, headers: buildHeaders(options) });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const apiMessage = payload?.error?.message || `Request failed with status ${response.status}`;
    throw new Error(apiMessage);
  }
  return payload;
}

function setMapPositionFromClick(event) {
  const rect = mapSurface.getBoundingClientRect();
  const x = Math.min(Math.max(event.clientX - rect.left, 0), rect.width);
  const y = Math.min(Math.max(event.clientY - rect.top, 0), rect.height);
  const ratioX = x / rect.width;
  const ratioY = y / rect.height;

  const latitude = 5.6037 + (0.0018 * (0.5 - ratioY));
  const longitude = -0.1870 + (0.0028 * (ratioX - 0.5));

  document.getElementById('latitude').value = latitude.toFixed(4);
  document.getElementById('longitude').value = longitude.toFixed(4);
  mapDot.style.left = `${ratioX * 100}%`;
  mapDot.style.top = `${ratioY * 100}%`;
  setMessage('Location pinned on the map.');
}

function renderPhotoPreview(file) {
  if (!file) {
    photoPreview.style.display = 'none';
    photoPreview.src = '';
    return;
  }

  const reader = new FileReader();
  reader.onload = (event) => {
    photoPreview.src = event.target?.result || '';
    photoPreview.style.display = 'block';
  };
  reader.readAsDataURL(file);
}

async function loadProjects() {
  const select = document.getElementById('project-select');
  select.innerHTML = '<option>Loading projects...</option>';

  try {
    const projects = await apiRequest('/projects');
    select.innerHTML = '';

    if (!projects.length) {
      const option = document.createElement('option');
      option.textContent = 'Create a project first';
      select.appendChild(option);
      recent.innerHTML = '<strong>No project selected yet.</strong>';
      return;
    }

    projects.forEach((project) => {
      const option = document.createElement('option');
      option.value = project.id;
      option.textContent = `${project.title} (${project.status})`;
      select.appendChild(option);
    });
    await loadRecentPins(projects[0].id);
  } catch (error) {
    select.innerHTML = '<option>Unable to load projects</option>';
    recent.innerHTML = '<strong>Could not load recent pins.</strong>';
    setMessage(`Error: ${error.message}`);
  }
}

async function loadRecentPins(projectId) {
  if (!projectId || projectId === 'Create a project first') {
    recent.innerHTML = '<strong>No saved pins yet.</strong>';
    return;
  }

  recent.innerHTML = '<strong>Loading pins...</strong>';
  try {
    const pins = await apiRequest(`/projects/${projectId}/pins`);
    if (!pins.length) {
      recent.innerHTML = '<strong>No saved pins yet.</strong>';
      return;
    }

    recent.innerHTML = `<strong>Recent pins</strong><ul>${pins
      .slice(-3)
      .map((pin) => `<li>${pin.captured_on} · heading ${pin.heading}° · ${pin.media_type || 'photo'}</li>`)
      .join('')}</ul>`;
  } catch (error) {
    recent.innerHTML = '<strong>Unable to load recent pins.</strong>';
    setMessage(`Error: ${error.message}`);
  }
}

async function capturePin() {
  const projectId = document.getElementById('project-select').value;
  const latitude = document.getElementById('latitude').value;
  const longitude = document.getElementById('longitude').value;
  const heading = document.getElementById('heading').value;
  const capturedOn = document.getElementById('captured_on').value;
  const mediaType = document.getElementById('media-type').value;
  const nativeFileKey = document.getElementById('native-file-key').value.trim();
  const thumbnailKey = document.getElementById('thumbnail-key').value.trim();
  const photoInputFile = photoInput.files && photoInput.files[0];

  if (!projectId || projectId === 'Create a project first') {
    setMessage('Create a project first before capturing a pin.');
    return;
  }

  setMessage('Saving pin...');

  try {
    const pin = await apiRequest(`/projects/${projectId}/pins`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        latitude: Number(latitude),
        longitude: Number(longitude),
        heading: Number(heading),
        captured_on: capturedOn,
        photo_key: photoInputFile ? `uploads/${projectId}/${Date.now()}/${photoInputFile.name}` : null,
        media_type: mediaType,
        native_file_key: nativeFileKey || null,
        thumbnail_key: thumbnailKey || null,
      }),
    });

    if (photoInputFile) {
      setMessage('Uploading media...');
      const formData = new FormData();
      formData.append('file', photoInputFile);
      const upload = await apiRequest(`/projects/${projectId}/pins/${pin.id}/upload`, { method: 'POST', body: formData });
      setMessage(`Pin saved and uploaded: ${upload.photo_key}`);
    } else {
      setMessage(`Pin saved without a file: ${pin.id}`);
    }

    await loadRecentPins(projectId);
  } catch (error) {
    setMessage(`Unable to capture pin: ${error.message}`);
  }
}

mapSurface.addEventListener('click', setMapPositionFromClick);
headingInput.addEventListener('input', (event) => updateHeadingReadout(event.target.value));
photoInput.addEventListener('change', (event) => renderPhotoPreview(event.target.files?.[0] || null));
document.getElementById('capture-btn').addEventListener('click', capturePin);
document.getElementById('project-select').addEventListener('change', (event) => loadRecentPins(event.target.value));

updateHeadingReadout(headingInput.value);
loadProjects();
