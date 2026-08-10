const apiBase = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? 'http://127.0.0.1:8000'
  : '/api';

const message = document.getElementById('message');
const recent = document.getElementById('recent-pins');

function setMessage(text) {
  message.textContent = text;
}

async function apiRequest(path, options) {
  const response = await fetch(`${apiBase}${path}`, options);
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const apiMessage = payload?.error?.message || `Request failed with status ${response.status}`;
    throw new Error(apiMessage);
  }
  return payload;
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
      .map((pin) => `<li>${pin.captured_on} · heading ${pin.heading}° · ${pin.photo_key || 'no photo'}</li>`)
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
  const photoInput = document.getElementById('photo');

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
        photo_key: null,
      }),
    });

    if (photoInput.files && photoInput.files[0]) {
      setMessage('Uploading photo...');
      const formData = new FormData();
      formData.append('file', photoInput.files[0]);
      const upload = await apiRequest(`/projects/${projectId}/pins/${pin.id}/upload`, { method: 'POST', body: formData });
      setMessage(`Captured pin ${pin.id} and uploaded ${upload.photo_key}`);
    } else {
      setMessage(`Captured pin ${pin.id} without a photo`);
    }

    await loadRecentPins(projectId);
  } catch (error) {
    setMessage(`Unable to capture pin: ${error.message}`);
  }
}

document.getElementById('capture-btn').addEventListener('click', capturePin);
document.getElementById('project-select').addEventListener('change', (event) => loadRecentPins(event.target.value));

loadProjects();
