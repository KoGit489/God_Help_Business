const apiBase = 'http://127.0.0.1:8000';

async function loadProjects() {
  const response = await fetch(`${apiBase}/projects`);
  const projects = await response.json();
  const select = document.getElementById('project-select');
  select.innerHTML = '';

  if (!projects.length) {
    const option = document.createElement('option');
    option.textContent = 'Create a project first';
    select.appendChild(option);
    return;
  }

  projects.forEach((project) => {
    const option = document.createElement('option');
    option.value = project.id;
    option.textContent = project.title;
    select.appendChild(option);
  });
}

async function loadRecentPins(projectId) {
  const response = await fetch(`${apiBase}/projects/${projectId}/pins`);
  const pins = await response.json();
  const recent = document.getElementById('recent-pins');

  if (!pins.length) {
    recent.innerHTML = '<strong>No saved pins yet.</strong>';
    return;
  }

  recent.innerHTML = `<strong>Recent pins</strong><ul>${pins
    .slice(-3)
    .map((pin) => `<li>${pin.captured_on} · heading ${pin.heading}° · ${pin.photo_key || 'no photo'}</li>`)
    .join('')}</ul>`;
}

async function capturePin() {
  const projectId = document.getElementById('project-select').value;
  const latitude = document.getElementById('latitude').value;
  const longitude = document.getElementById('longitude').value;
  const heading = document.getElementById('heading').value;
  const capturedOn = document.getElementById('captured_on').value;
  const photoInput = document.getElementById('photo');
  const message = document.getElementById('message');

  if (!projectId || projectId === 'Create a project first') {
    message.textContent = 'Create a project first before capturing a pin.';
    return;
  }

  const pinResponse = await fetch(`${apiBase}/projects/${projectId}/pins`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ latitude: Number(latitude), longitude: Number(longitude), heading: Number(heading), captured_on: capturedOn, photo_key: null }),
  });
  const pin = await pinResponse.json();

  if (photoInput.files && photoInput.files[0]) {
    const formData = new FormData();
    formData.append('file', photoInput.files[0]);
    const uploadResponse = await fetch(`${apiBase}/projects/${projectId}/pins/${pin.id}/upload`, { method: 'POST', body: formData });
    const upload = await uploadResponse.json();
    message.textContent = `Captured pin ${pin.id} and uploaded ${upload.photo_key}`;
  } else {
    message.textContent = `Captured pin ${pin.id} without a photo`;
  }

  await loadRecentPins(projectId);
}

document.getElementById('capture-btn').addEventListener('click', capturePin);
document.getElementById('project-select').addEventListener('change', (event) => loadRecentPins(event.target.value));

loadProjects();
