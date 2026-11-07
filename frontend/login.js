function buildApiBases() {
  const params = new URLSearchParams(window.location.search);
  const override = params.get('apiBase');
  if (override) return [override.replace(/\/$/, '')];
  if (window.location.protocol === 'file:' || ['localhost', '127.0.0.1'].includes(window.location.hostname)) {
    return ['http://127.0.0.1:8000'];
  }
  const sameOrigin = window.location.origin.replace(/\/$/, '');
  const wifiBackend = `${window.location.protocol}//${window.location.hostname}:8000`;
  return [...new Set(window.location.port === '5500' ? [wifiBackend, sameOrigin, '/api'] : [sameOrigin, '/api'])];
}

const apiBases = buildApiBases();
const status = document.getElementById('auth-status');
const loginForm = document.getElementById('login-form');
const accountPanel = document.getElementById('account-panel');
const createUserForm = document.getElementById('create-user-form');
const params = new URLSearchParams(window.location.search);
const requestedNext = params.get('next') || 'index.html';
const nextPath = requestedNext.startsWith('/') && !requestedNext.startsWith('//') ? requestedNext : 'index.html';

function setStatus(message) { status.textContent = message; }

async function apiRequest(path, options = {}) {
  let lastError = null;
  for (const base of apiBases) {
    try {
      const response = await fetch(`${base}${path}`, { ...options, credentials: 'include' });
      const payload = await response.json().catch(() => null);
      if (response.ok) return payload;
      if (response.status === 404 && base !== apiBases[apiBases.length - 1]) {
        lastError = new Error(payload?.error?.message || 'Not found');
        continue;
      }
      throw new Error(payload?.error?.message || `Request failed (${response.status})`);
    } catch (error) { lastError = error; }
  }
  throw lastError || new Error('Unable to reach the API.');
}

async function loadCurrentUser() {
  try {
    const user = await apiRequest('/auth/me');
    loginForm.hidden = true;
    accountPanel.hidden = false;
    document.getElementById('account-name').textContent = user.name;
    document.getElementById('account-email').textContent = user.email;
    createUserForm.hidden = !user.is_admin;
    setStatus(user.is_admin ? 'Signed in as administrator.' : 'Signed in.');
  } catch (error) {
    loginForm.hidden = false;
    accountPanel.hidden = true;
    if (!/sign in|session|401/i.test(error.message)) setStatus(`Unable to load account: ${error.message}`);
  }
}

loginForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  setStatus('Signing in...');
  try {
    await apiRequest('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: document.getElementById('login-email').value,
        password: document.getElementById('login-password').value,
      }),
    });
    window.location.assign(nextPath);
  } catch (error) { setStatus(`Sign-in failed: ${error.message}`); }
});

document.getElementById('logout-button').addEventListener('click', async () => {
  try { await apiRequest('/auth/logout', { method: 'POST' }); }
  catch (error) { setStatus(`Sign-out failed: ${error.message}`); return; }
  loginForm.hidden = false;
  accountPanel.hidden = true;
  loginForm.reset();
  setStatus('Signed out.');
});

createUserForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  setStatus('Creating account...');
  try {
    const user = await apiRequest('/auth/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: document.getElementById('new-user-name').value,
        email: document.getElementById('new-user-email').value,
        password: document.getElementById('new-user-password').value,
        is_admin: document.getElementById('new-user-admin').checked,
      }),
    });
    createUserForm.reset();
    setStatus(`Account created for ${user.email}.`);
  } catch (error) { setStatus(`Account creation failed: ${error.message}`); }
});

loadCurrentUser();
