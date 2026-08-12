const apiBase = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? 'http://127.0.0.1:8000'
  : '/api';
let activeProjectId = null;
let activeShareToken = null;

function setReviewStatus(message) {
  const summary = document.getElementById('review-summary');
  if (!activeProjectId) {
    summary.innerHTML = message;
  }
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
      item.className = 'project-pill';
      item.innerHTML = `<span><strong>${project.title}</strong><br /><span class="muted">${project.pin_count} pins captured · ${project.status}</span></span><button type="button" style="padding: 0.45rem 0.7rem;">Open</button>`;
      item.querySelector('button').addEventListener('click', () => {
        activeProjectId = project.id;
        activeShareToken = null;
        renderProject(project.id);
      });
      list.appendChild(item);
    });
  } catch (error) {
    list.innerHTML = `<div class="muted">Unable to load projects: ${error.message}</div>`;
  }
}

async function createReviewProject() {
  const title = document.getElementById('review-title').value.trim();
  const description = document.getElementById('review-description').value.trim();
  if (!title) {
    setReviewStatus('Project title is required.');
    return;
  }

  setReviewStatus('Creating project...');
  try {
    const project = await apiRequest('/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, description }),
    });
    activeProjectId = project.id;
    activeShareToken = null;
    await loadProjectList();
    await renderProject(project.id);
  } catch (error) {
    setReviewStatus(`Unable to create project: ${error.message}`);
  }
}

async function createShareLink() {
  if (!activeProjectId) {
    setReviewStatus('Open a project before creating a share link.');
    return;
  }

  try {
    const payload = await apiRequest(`/projects/${activeProjectId}/share-link`, { method: 'POST' });
    activeShareToken = payload.share_token;
    document.getElementById('share-box').style.display = 'block';
    document.getElementById('share-link-text').innerHTML = `<a href="${payload.share_link}" target="_blank">${payload.share_link}</a>`;
  } catch (error) {
    setReviewStatus(`Unable to create share link: ${error.message}`);
  }
}

async function markReadyForReview() {
  if (!activeProjectId) {
    setReviewStatus('Open a project before updating status.');
    return;
  }

  try {
    await apiRequest(`/projects/${activeProjectId}/status`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'ready_for_review' }),
    });
    await loadProjectList();
    await renderProject(activeProjectId);
  } catch (error) {
    setReviewStatus(`Unable to update project status: ${error.message}`);
  }
}

async function renderProject(projectId) {
  document.getElementById('review-summary').innerHTML = 'Loading project review...';
  const pinList = document.getElementById('review-pins');
  pinList.innerHTML = '<li>Loading pins...</li>';

  try {
    const query = activeShareToken ? `?share_token=${encodeURIComponent(activeShareToken)}` : '';
    const project = await apiRequest(`/projects/${projectId}/review${query}`);
    document.getElementById('review-summary').innerHTML = `<div class="status-pill">${project.status}</div><strong>${project.title}</strong><br />${project.description || 'No description'}<br /><span>${project.pin_count} pins captured</span>`;

    if (!project.pins.length) {
      pinList.innerHTML = '<li>No pins yet for this project.</li>';
      return;
    }

    pinList.innerHTML = project.pins
      .map((pin) => `
        <li>
          <div class="pin-card">
            <div class="mini-map" style="--heading:${pin.heading || 0}deg"></div>
            <div>
              <strong>${pin.captured_on}</strong><br />
              <span class="muted">Heading ${pin.heading || 0}° · ${pin.media_type || 'photo'}</span><br />
              <span class="muted">${pin.latitude}, ${pin.longitude}</span><br />
              <span class="muted">${pin.photo_key || pin.native_file_key || 'No media stored'}</span>
            </div>
          </div>
        </li>
      `)
      .join('');
  } catch (error) {
    document.getElementById('review-summary').innerHTML = `Unable to load review: ${error.message}`;
    pinList.innerHTML = '<li>Unable to load pins.</li>';
  }
}

document.getElementById('create-review-project').addEventListener('click', createReviewProject);
document.getElementById('create-share-link').addEventListener('click', createShareLink);
document.getElementById('mark-ready').addEventListener('click', markReadyForReview);

loadProjectList();
