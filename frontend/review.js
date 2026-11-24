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
let activeProjectId = null;
let activeShareToken = null;
let activeShareExpiresAt = null;

function redirectToLogin() {
  if (window.location.pathname.endsWith('/login.html')) return;
  const next = encodeURIComponent(`${window.location.pathname}${window.location.search}`);
  window.location.assign(`/login.html?next=${next}`);
}

function setReviewStatus(message, kind = '') {
  const status = document.getElementById('review-status');
  if (status) {
    status.textContent = message || '';
    status.className = kind ? `review-status is-${kind}` : 'review-status';
  }
  if (!activeProjectId) {
    document.getElementById('review-summary').textContent = message;
  }
}

function renderOnboardingChecklist(project) {
  const checklist = document.getElementById('onboarding-checklist');
  if (!checklist) return;

  const items = [
    { label: 'Project created and titled', done: Boolean(project && project.title) },
    { label: 'Technician confirmed location + heading', done: Boolean(project && project.pin_count > 0) },
    { label: 'Native 360 file preserved when needed', done: Boolean(project && project.pins && project.pins.some((pin) => pin.native_file_key || pin.media_type === 'insta360')) },
    { label: 'Share link generated for review', done: Boolean(activeShareToken) },
  ];

  checklist.innerHTML = items.map((item) => `<li class="${item.done ? 'done' : 'pending'}">${item.done ? '✓' : '•'} ${item.label}</li>`).join('');
}

function buildHeaders(options = {}) {
  const headers = new Headers(options.headers || {});
  return headers;
}

async function apiRequest(path, options = {}) {
  let lastError = null;

  for (const base of apiBases) {
    try {
      const response = await fetch(`${base}${path}`, { ...options, headers: buildHeaders(options), credentials: 'include' });
      const payload = await response.json().catch(() => null);
      if (response.ok) {
        return payload;
      }

      if (response.status === 401) {
        redirectToLogin();
        throw Object.assign(new Error('Sign-in is required.'), { authRequired: true });
      }

      const apiMessage = payload?.error?.message || `Request failed with status ${response.status}`;
      if (response.status === 404 && base !== apiBases[apiBases.length - 1]) {
        lastError = new Error(apiMessage);
        continue;
      }
      throw Object.assign(new Error(apiMessage), { apiResponse: true });
    } catch (error) {
      if (error.authRequired || error.apiResponse || !['GET', 'HEAD'].includes((options.method || 'GET').toUpperCase())) throw error;
      lastError = error;
    }
  }

  throw lastError || new Error('Unable to reach the API service.');
}

async function loadProjectList() {
  const list = document.getElementById('project-list');
  list.innerHTML = '<div class="muted">Loading projects...</div>';

  try {
    const projects = await apiRequest('/projects');
    list.innerHTML = '';

    if (!projects.length) {
      list.innerHTML = '<div class="muted">No projects yet — create one to start the review flow.</div>';
      setReviewStatus('No project selected.');
      return;
    }

    projects.forEach((project) => {
      const item = document.createElement('div');
      item.className = `project-pill${project.id === activeProjectId ? ' is-active' : ''}`;
      item.innerHTML = `<span><strong>${escapeHtml(project.title)}</strong><br /><span class="muted">${escapeHtml(project.pin_count)} pins · ${escapeHtml(project.status)}</span></span><button type="button">Open</button>`;
      item.querySelector('button').addEventListener('click', () => {
        activeProjectId = project.id;
        activeShareToken = null;
        activeShareExpiresAt = null;
        document.getElementById('share-box').style.display = 'none';
        document.getElementById('copy-share-link').style.display = 'none';
        document.getElementById('revoke-share-link').style.display = 'none';
        setReviewStatus('');
        list.querySelectorAll('.project-pill').forEach((node) => node.classList.remove('is-active'));
        item.classList.add('is-active');
        renderProject(project.id);
      });
      list.appendChild(item);
    });
  } catch (error) {
    list.innerHTML = `<div class="muted">Unable to load projects: ${escapeHtml(error.message)}</div>`;
    setReviewStatus(`Unable to load projects: ${error.message}`, 'error');
  }
}

async function createReviewProject() {
  const title = document.getElementById('review-title').value.trim();
  const description = document.getElementById('review-description').value.trim();
  if (!title) {
    setReviewStatus('Project title is required.', 'error');
    return;
  }

  setReviewStatus('Creating project...', 'loading');
  try {
    const project = await apiRequest('/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, description }),
    });
    activeProjectId = project.id;
    activeShareToken = null;
    document.getElementById('review-title').value = '';
    document.getElementById('review-description').value = '';
    await loadProjectList();
    await renderProject(project.id);
    setReviewStatus('Project created.', 'success');
  } catch (error) {
    setReviewStatus(`Unable to create project: ${error.message}`, 'error');
  }
}

async function createShareLink() {
  if (!activeProjectId) {
    setReviewStatus('Open a project before creating a share link.', 'error');
    return;
  }

  setReviewStatus('Creating share link...', 'loading');
  try {
    const expiresInDays = Number(document.getElementById('share-expiration').value);
    const payload = await apiRequest(`/projects/${activeProjectId}/share-link`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ expires_in_days: expiresInDays }),
    });
    activeShareToken = payload.share_token;
    activeShareExpiresAt = payload.expires_at;
    document.getElementById('share-box').style.display = 'block';
    const linkText = document.getElementById('share-link-text');
    linkText.innerHTML = '';
    const link = document.createElement('a');
    link.href = payload.share_link;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = payload.share_link;
    linkText.appendChild(link);
    document.getElementById('share-expiry-text').textContent = `Expires ${new Date(activeShareExpiresAt).toLocaleString()}`;
    document.getElementById('copy-share-link').style.display = 'inline-block';
    document.getElementById('revoke-share-link').style.display = 'inline-block';
    await renderProject(activeProjectId);
    setReviewStatus('Share link ready.', 'success');
  } catch (error) {
    setReviewStatus(`Unable to create share link: ${error.message}`, 'error');
  }
}

async function copyShareLink() {
  const shareLink = document.getElementById('share-link-text').textContent.trim();
  if (!shareLink) {
    setReviewStatus('Create a share link before copying it.', 'error');
    return;
  }

  try {
    await navigator.clipboard.writeText(shareLink);
    setReviewStatus('Share link copied to the clipboard.', 'success');
  } catch (error) {
    setReviewStatus('Copy failed. You can still open the share link manually.', 'error');
  }
}

async function revokeShareLink() {
  if (!activeProjectId || !activeShareToken) return;

  setReviewStatus('Revoking share link...', 'loading');
  try {
    await apiRequest(`/projects/${activeProjectId}/share-link`, { method: 'DELETE' });
    activeShareToken = null;
    activeShareExpiresAt = null;
    document.getElementById('share-box').style.display = 'none';
    document.getElementById('copy-share-link').style.display = 'none';
    document.getElementById('revoke-share-link').style.display = 'none';
    await renderProject(activeProjectId);
    setReviewStatus('Share link revoked.', 'success');
  } catch (error) {
    setReviewStatus(`Unable to revoke share link: ${error.message}`, 'error');
  }
}

async function markReadyForReview() {
  if (!activeProjectId) {
    setReviewStatus('Open a project before updating status.', 'error');
    return;
  }

  setReviewStatus('Updating status...', 'loading');
  try {
    await apiRequest(`/projects/${activeProjectId}/status`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'ready_for_review' }),
    });
    await loadProjectList();
    await renderProject(activeProjectId);
    setReviewStatus('Marked ready for review.', 'success');
  } catch (error) {
    setReviewStatus(`Unable to update project status: ${error.message}`, 'error');
  }
}

async function renderProject(projectId) {
  document.getElementById('review-summary').innerHTML = 'Loading project review...';
  const pinList = document.getElementById('review-pins');
  pinList.innerHTML = '<li class="muted">Loading pins...</li>';

  try {
    const query = activeShareToken ? `?share_token=${encodeURIComponent(activeShareToken)}` : '';
    const project = await apiRequest(`/projects/${projectId}/review${query}`);
    document.getElementById('review-summary').innerHTML = `<div class="status-pill">${escapeHtml(project.status)}</div><strong>${escapeHtml(project.title)}</strong><br />${escapeHtml(project.description || 'No description')}<br /><span>${escapeHtml(project.pin_count)} pins captured</span>`;
    renderOnboardingChecklist(project);

    if (!project.pins.length) {
      pinList.innerHTML = '<li class="muted">No pins yet for this project.</li>';
      return;
    }

    pinList.innerHTML = project.pins
      .map((pin) => {
        const mediaLabel = pin.media_type || 'photo';
        const mediaKey = pin.photo_key || pin.native_file_key || 'No media stored';
        const nativeTag = pin.native_file_key || pin.media_type === 'insta360'
          ? '<span class="badge">360</span>'
          : '';
        return `
        <li>
          <div class="pin-card">
            <div class="mini-map" style="--heading:${Number.isFinite(Number(pin.heading)) ? Number(pin.heading) : 0}deg" aria-hidden="true"></div>
            <div class="pin-body">
              <strong>${escapeHtml(pin.captured_on)}</strong>
              <div class="pin-meta">Heading ${escapeHtml(pin.heading || 0)}° · ${escapeHtml(mediaLabel)}</div>
              <div class="pin-meta coord">${escapeHtml(pin.latitude)}, ${escapeHtml(pin.longitude)}</div>
              <div class="pin-meta"><code>${escapeHtml(mediaKey)}</code></div>
              <div class="pin-tags">${nativeTag}<span class="badge">${escapeHtml(mediaLabel)}</span></div>
            </div>
          </div>
        </li>`;
      })
      .join('');
  } catch (error) {
    document.getElementById('review-summary').textContent = `Unable to load review: ${error.message}`;
    pinList.innerHTML = '<li class="muted">Unable to load pins.</li>';
    setReviewStatus(`Unable to load review: ${error.message}`, 'error');
  }
}

document.getElementById('create-review-project').addEventListener('click', createReviewProject);
document.getElementById('create-share-link').addEventListener('click', createShareLink);
document.getElementById('copy-share-link').addEventListener('click', copyShareLink);
document.getElementById('revoke-share-link').addEventListener('click', revokeShareLink);
document.getElementById('mark-ready').addEventListener('click', markReadyForReview);

loadProjectList();
