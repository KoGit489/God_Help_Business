const apiBase = 'http://127.0.0.1:8000';
let activeProjectId = null;
let activeShareToken = null;

async function loadProjectList() {
  const response = await fetch(`${apiBase}/projects`);
  const projects = await response.json();
  const list = document.getElementById('project-list');
  list.innerHTML = '';

  if (!projects.length) {
    list.innerHTML = '<div class="muted">No projects yet — create one to start the review flow.</div>';
    return;
  }

  projects.forEach((project) => {
    const item = document.createElement('div');
    item.className = 'project-pill';
    item.innerHTML = `<span><strong>${project.title}</strong><br /><span class="muted">${project.pin_count} pins captured</span></span><button type="button" style="padding: 0.45rem 0.7rem;">Open</button>`;
    item.querySelector('button').addEventListener('click', () => {
      activeProjectId = project.id;
      activeShareToken = null;
      renderProject(project.id);
    });
    list.appendChild(item);
  });
}

async function createReviewProject() {
  const title = document.getElementById('review-title').value.trim();
  const description = document.getElementById('review-description').value.trim();
  if (!title) return;

  const response = await fetch(`${apiBase}/projects`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, description }),
  });
  const project = await response.json();
  activeProjectId = project.id;
  activeShareToken = null;
  await loadProjectList();
  await renderProject(project.id);
}

async function createShareLink() {
  if (!activeProjectId) return;
  const response = await fetch(`${apiBase}/projects/${activeProjectId}/share-link`, { method: 'POST' });
  const payload = await response.json();
  activeShareToken = payload.share_token;
  document.getElementById('share-box').style.display = 'block';
  document.getElementById('share-link-text').innerHTML = `<a href="${payload.share_link}" target="_blank">${payload.share_link}</a>`;
}

async function markReadyForReview() {
  if (!activeProjectId) return;
  const response = await fetch(`${apiBase}/projects/${activeProjectId}/status`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status: 'ready_for_review' }),
  });
  const payload = await response.json();
  if (payload.status) {
    await renderProject(activeProjectId);
  }
}

async function renderProject(projectId) {
  const response = await fetch(`${apiBase}/projects/${projectId}/review${activeShareToken ? `?share_token=${activeShareToken}` : ''}`);
  const project = await response.json();
  document.getElementById('review-summary').innerHTML = `<div class="status-pill">${project.status}</div><strong>${project.title}</strong><br />${project.description || 'No description'}<br /><span>${project.pin_count} pins captured</span>`;

  const pinList = document.getElementById('review-pins');
  if (!project.pins.length) {
    pinList.innerHTML = '<li>No pins yet for this project.</li>';
    return;
  }

  pinList.innerHTML = project.pins
    .map((pin) => `<li><strong>${pin.captured_on}</strong> — heading ${pin.heading}° · ${pin.photo_key || 'no photo'}</li>`)
    .join('');
}

document.getElementById('create-review-project').addEventListener('click', createReviewProject);
document.getElementById('create-share-link').addEventListener('click', createShareLink);
document.getElementById('mark-ready').addEventListener('click', markReadyForReview);

loadProjectList();
