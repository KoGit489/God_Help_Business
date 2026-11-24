function buildApiBases() {
  const params = new URLSearchParams(window.location.search);
  const override = safeApiBase(params.get('apiBase'));
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
let showOnboardingNext = false;
let analyticsEnabled = false;

function analyticsConsent() {
  try { return window.localStorage.getItem('casai.analytics.consent') === 'yes'; }
  catch { return false; }
}

function trackAnalytics(event) {
  if (!analyticsEnabled || !analyticsConsent()) return;
  apiRequest('/analytics/events', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    referrerPolicy: 'no-referrer',
    body: JSON.stringify({ event, consent: true }),
  }).catch(() => {});
}

async function initializeAnalytics(isAdmin) {
  try {
    const config = await apiRequest('/analytics/config', { referrerPolicy: 'no-referrer' });
    if (!config.enabled) return;
    analyticsEnabled = true;
    const settings = document.getElementById('analytics-settings');
    const consent = document.getElementById('analytics-consent');
    const status = document.getElementById('analytics-status');
    settings.hidden = false;
    consent.checked = analyticsConsent();
    consent.addEventListener('change', () => {
      try {
        if (consent.checked) window.localStorage.setItem('casai.analytics.consent', 'yes');
        else window.localStorage.removeItem('casai.analytics.consent');
        status.textContent = consent.checked ? 'Optional usage counts enabled on this browser.' : 'Optional usage counts disabled on this browser.';
        if (consent.checked) trackAnalytics('dashboard_opened');
      } catch {
        analyticsEnabled = false;
        consent.checked = false;
        status.textContent = 'Your preference could not be saved. Usage counts are off on this page; check your browser storage settings.';
      }
    });
    trackAnalytics('dashboard_opened');
    if (isAdmin) {
      try {
        const summary = await apiRequest('/analytics/summary', { referrerPolicy: 'no-referrer' });
        const totals = document.getElementById('analytics-totals');
        totals.replaceChildren();
        for (const row of summary.daily) {
          const item = document.createElement('li');
          item.textContent = `${row.day}: ${row.event.replaceAll('_', ' ')}: ${row.count}`;
          totals.appendChild(item);
        }
        if (!summary.daily.length) totals.textContent = 'No usage counts yet.';
        document.getElementById('analytics-summary').hidden = false;
      } catch {
        document.getElementById('analytics-summary').hidden = true;
      }
    }
  } catch {
    analyticsEnabled = false;
  }
}

function showOnboarding(stage) {
  const panel = document.getElementById('onboarding');
  panel.hidden = !stage;
  if (!stage) return;
  document.getElementById('onboarding-title').textContent = stage === 'create' ? 'Create your first project' : 'Your project is ready';
  document.getElementById('onboarding-copy').textContent = stage === 'create' ? 'Start with a project name and the site you are documenting.' : 'Open the floor-plan walkthrough to add your drawing and captures.';
  const action = document.getElementById('onboarding-action');
  action.textContent = stage === 'create' ? 'Create project' : 'Open floor plan';
  action.href = stage === 'create' ? '#create-project' : 'floorplan.html';
}

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

function redirectToLogin() {
  if (window.location.pathname.endsWith('/login.html')) return;
  const next = encodeURIComponent(`${window.location.pathname}${window.location.search}`);
  window.location.assign(`/login.html?next=${next}`);
}

async function apiRequest(path, options = {}) {
  let lastError = null;

  for (const base of apiBases) {
    try {
      const response = await fetch(`${base}${path}`, { ...options, credentials: 'include' });
      const payload = await response.json().catch(() => null);
      if (response.ok) {
        return payload;
      }

      if (response.status === 401) {
        redirectToLogin();
        throw Object.assign(new Error('Sign-in is required.'), { authRequired: true });
      }

      const message = payload?.error?.message || `Request failed with status ${response.status}`;
      if (response.status === 404 && base !== apiBases[apiBases.length - 1]) {
        lastError = new Error(message);
        continue;
      }
      throw Object.assign(new Error(message), { apiResponse: true });
    } catch (error) {
      if (error.authRequired || error.apiResponse || !['GET', 'HEAD'].includes((options.method || 'GET').toUpperCase())) throw error;
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
    initializeAnalytics(user.is_admin);
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
      showOnboarding('create');
      list.innerHTML = '<li>No projects yet.</li>';
      projectCount.textContent = '0';
      pinCount.textContent = '0';
      reviewReady.textContent = '0';
      setDashboardMessage('Create your first project to get started.');
      return;
    }

    showOnboarding(showOnboardingNext ? 'plan' : null);

    const totalPins = projects.reduce((sum, project) => sum + project.pin_count, 0);
    projectCount.textContent = String(projects.length);
    pinCount.textContent = String(totalPins);
    reviewReady.textContent = String(projects.filter((project) => project.status === 'ready_for_review').length);

    list.innerHTML = '';
    projects.forEach((project) => {
      const item = document.createElement('li');
      item.innerHTML = `<strong>${escapeHtml(project.title)}</strong> — ${escapeHtml(project.description || 'No description')} <span>(${escapeHtml(project.pin_count)} pins)</span> · <span>Status: ${escapeHtml(project.status)}</span> · <a href="review.html">Review</a>`;
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
  const submitButton = document.querySelector('#project-form button[type="submit"]');
  submitButton.disabled = true;
  try {
    const firstProject = Number(projectCount.textContent) === 0;
    await apiRequest('/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, description }),
    });
    trackAnalytics('project_created');
    document.getElementById('project-form').reset();
    showOnboardingNext = firstProject;
    setDashboardMessage('Project created.');
    await loadProjects();
  } catch (error) {
    setDashboardMessage(`Unable to create project: ${error.message}`);
  } finally {
    submitButton.disabled = false;
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
