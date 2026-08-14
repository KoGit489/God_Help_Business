function buildApiBases() {
  const params = new URLSearchParams(window.location.search);
  const override = params.get('apiBase');
  if (override) {
    return [override.replace(/\/$/, '')];
  }

  if (window.location.protocol === 'file:') {
    return ['http://127.0.0.1:8000'];
  }

  const isLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
  if (isLocalhost) {
    return ['http://127.0.0.1:8000'];
  }

  const sameOrigin = window.location.origin.replace(/\/$/, '');
  const wifiBackend = `${window.location.protocol}//${window.location.hostname}:8000`;
  const candidates = window.location.port === '5500'
    ? [wifiBackend, sameOrigin, '/api']
    : [sameOrigin, '/api'];

  return [...new Set(candidates)];
}

const apiBases = buildApiBases();

const list = document.getElementById('project-list');
const projectCount = document.getElementById('project-count');
const pinCount = document.getElementById('pin-count');
const reviewReady = document.getElementById('review-ready');

function setDashboardMessage(message) {
  const existing = document.getElementById('dashboard-message');
  if (existing) {
    existing.textContent = message;
    return;
  }

  const messageBox = document.createElement('p');
  messageBox.id = 'dashboard-message';
  messageBox.style.marginTop = '0.75rem';
  messageBox.style.color = '#475569';
  messageBox.textContent = message;
  document.querySelector('.card').appendChild(messageBox);
}

async function apiRequest(path, options = {}) {
  let lastError = null;

  for (const base of apiBases) {
    try {
      const response = await fetch(`${base}${path}`, options);
      const payload = await response.json().catch(() => null);
      if (response.ok) {
        return payload;
      }

      const message = payload?.error?.message || `Request failed with status ${response.status}`;
      if (response.status === 404 && base !== apiBases[apiBases.length - 1]) {
        lastError = new Error(message);
        continue;
      }
      throw new Error(message);
    } catch (error) {
      lastError = error;
    }
  }

  throw lastError || new Error('Unable to reach the API service.');
}

async function loadUser() {
  setDashboardMessage('Loading user...');
  try {
    const user = await apiRequest('/auth/me');
    document.getElementById('user-name').textContent = user.name;
    document.getElementById('user-email').textContent = user.email;
    setDashboardMessage('User loaded.');
  } catch (error) {
    document.getElementById('user-name').textContent = 'Unavailable';
    document.getElementById('user-email').textContent = '';
    setDashboardMessage(`Unable to load user: ${error.message}`);
  }
}

async function loadProjects() {
  list.innerHTML = '<li>Loading projects...</li>';
  try {
    const projects = await apiRequest('/projects');

    if (!projects.length) {
      list.innerHTML = '<li>No projects yet.</li>';
      projectCount.textContent = '0';
      pinCount.textContent = '0';
      reviewReady.textContent = '0';
      setDashboardMessage('Create your first project to get started.');
      return;
    }

    const totalPins = projects.reduce((sum, project) => sum + project.pin_count, 0);
    projectCount.textContent = String(projects.length);
    pinCount.textContent = String(totalPins);
    reviewReady.textContent = String(projects.filter((project) => project.status === 'ready_for_review').length);

    list.innerHTML = '';
    projects.forEach((project) => {
      const item = document.createElement('li');
      item.innerHTML = `<strong>${project.title}</strong> — ${project.description || 'No description'} <span>(${project.pin_count} pins)</span> · <span>Status: ${project.status}</span> · <a href="review.html">Review</a>`;
      list.appendChild(item);
    });
    setDashboardMessage('Projects loaded.');
  } catch (error) {
    list.innerHTML = '<li>Unable to load projects.</li>';
    setDashboardMessage(`Error loading projects: ${error.message}`);
  }
}

async function createProject(event) {
  event.preventDefault();
  const title = document.getElementById('title').value.trim();
  const description = document.getElementById('description').value.trim();
  if (!title) {
    setDashboardMessage('Project title is required.');
    return;
  }

  setDashboardMessage('Creating project...');
  try {
    await apiRequest('/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, description }),
    });
    document.getElementById('project-form').reset();
    setDashboardMessage('Project created.');
    await loadProjects();
  } catch (error) {
    setDashboardMessage(`Unable to create project: ${error.message}`);
  }
}

async function addSamplePin() {
  setDashboardMessage('Adding demo pin...');
  try {
    const projects = await apiRequest('/projects');
    if (!projects.length) {
      setDashboardMessage('Create a project before adding a demo pin.');
      return;
    }

    const project = projects[0];
    await apiRequest(`/projects/${project.id}/pins`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        latitude: 5.6037,
        longitude: -0.187,
        heading: 35,
        captured_on: '2026-08-07',
        photo_key: 'photos/demo.jpg',
      }),
    });

    setDashboardMessage('Demo pin added.');
    await loadProjects();
  } catch (error) {
    setDashboardMessage(`Unable to add demo pin: ${error.message}`);
  }
}

document.getElementById('project-form').addEventListener('submit', createProject);
document.getElementById('sample-pin').addEventListener('click', addSamplePin);

loadUser();
loadProjects();
