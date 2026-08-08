const apiBase = 'http://127.0.0.1:8000';

async function loadUser() {
  const response = await fetch(`${apiBase}/auth/me`);
  const user = await response.json();
  document.getElementById('user-name').textContent = user.name;
  document.getElementById('user-email').textContent = user.email;
}

async function loadProjects() {
  const response = await fetch(`${apiBase}/projects`);
  const projects = await response.json();
  const list = document.getElementById('project-list');
  const projectCount = document.getElementById('project-count');
  const pinCount = document.getElementById('pin-count');
  const reviewReady = document.getElementById('review-ready');

  list.innerHTML = '';

  if (!projects.length) {
    list.innerHTML = '<li>No projects yet.</li>';
    projectCount.textContent = '0';
    pinCount.textContent = '0';
    reviewReady.textContent = '0';
    return;
  }

  const totalPins = projects.reduce((sum, project) => sum + project.pin_count, 0);
  projectCount.textContent = projects.length;
  pinCount.textContent = totalPins;
  reviewReady.textContent = projects.filter((project) => project.pin_count > 0).length;

  projects.forEach((project) => {
    const item = document.createElement('li');
    item.innerHTML = `<strong>${project.title}</strong> — ${project.description || 'No description'} <span>(${project.pin_count} pins)</span> · <a href="review.html">Review</a>`;
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, description }),
  });

  if (response.ok) {
    document.getElementById('project-form').reset();
    loadProjects();
  }
}

async function addSamplePin() {
  const projects = await (await fetch(`${apiBase}/projects`)).json();
  if (!projects.length) {
    return;
  }

  const project = projects[0];
  await fetch(`${apiBase}/projects/${project.id}/pins`, {
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

  loadProjects();
}

document.getElementById('project-form').addEventListener('submit', createProject);
document.getElementById('sample-pin').addEventListener('click', addSamplePin);

loadUser();
loadProjects();
