function buildApiBases() {
  const params = new URLSearchParams(window.location.search);
  const override = safeApiBase(params.get('apiBase'));
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
const deleteAccountForm = document.getElementById('delete-account-form');
const mfaSetupForm = document.getElementById('mfa-setup-form');
const mfaEnableForm = document.getElementById('mfa-enable-form');
const mfaDisableForm = document.getElementById('mfa-disable-form');
const params = new URLSearchParams(window.location.search);
const requestedNext = params.get('next') || 'index.html';
const nextPath = safeLocalRedirect(requestedNext);

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
      throw Object.assign(new Error(payload?.error?.message || `Request failed (${response.status})`), { apiResponse: true });
    } catch (error) {
      if (error.apiResponse || !['GET', 'HEAD'].includes((options.method || 'GET').toUpperCase())) throw error;
      lastError = error;
    }
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
    document.getElementById('account-verification').textContent = user.email_verified ? 'Email verified or grandfathered.' : 'Email not yet verified.';
    document.getElementById('account-verify-link').hidden = user.email_verified;
    createUserForm.hidden = !user.is_admin;
    setStatus(user.is_admin ? 'Signed in as administrator.' : 'Signed in.');
    await loadMfaStatus();
  } catch (error) {
    loginForm.hidden = false;
    accountPanel.hidden = true;
    if (!/sign in|session|401/i.test(error.message)) setStatus(`Unable to load account: ${error.message}`);
  }
}

async function loadMfaStatus() {
  const mfaStatus = document.getElementById('mfa-status');
  try {
    const mfa = await apiRequest('/auth/mfa');
    mfaSetupForm.hidden = mfa.enabled || !mfa.available;
    mfaDisableForm.hidden = !mfa.enabled;
    document.getElementById('delete-account-mfa-label').hidden = !mfa.enabled;
    document.getElementById('delete-account-mfa-code').required = mfa.enabled;
    mfaStatus.textContent = mfa.enabled ? 'Two-step sign-in is enabled.' : mfa.available ? 'Two-step sign-in is off.' : 'Authenticator setup is not configured. Contact your administrator.';
  } catch (error) {
    mfaSetupForm.hidden = true;
    mfaDisableForm.hidden = true;
    mfaStatus.textContent = `Unable to load two-step sign-in: ${error.message}`;
  }
}

loginForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const submitButton = loginForm.querySelector('button[type="submit"]');
  submitButton.disabled = true;
  setStatus('Signing in...');
  try {
    await apiRequest('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: document.getElementById('login-email').value,
        password: document.getElementById('login-password').value,
        mfa_code: document.getElementById('login-mfa-code').value.trim() || null,
      }),
    });
    window.location.assign(nextPath);
  } catch (error) { setStatus(`Sign-in failed: ${error.message}`); }
  finally { submitButton.disabled = false; }
});

document.getElementById('logout-button').addEventListener('click', async () => {
  try { await apiRequest('/auth/logout', { method: 'POST' }); }
  catch (error) { setStatus(`Sign-out failed: ${error.message}`); return; }
  loginForm.hidden = false;
  accountPanel.hidden = true;
  deleteAccountForm.hidden = true;
  deleteAccountForm.reset();
  mfaSetupForm.reset();
  mfaEnableForm.reset();
  mfaDisableForm.reset();
  document.getElementById('mfa-secret').textContent = '';
  document.getElementById('mfa-secret-panel').hidden = true;
  document.getElementById('mfa-recovery-codes').value = '';
  document.getElementById('mfa-recovery-panel').hidden = true;
  loginForm.reset();
  setStatus('Signed out.');
});

createUserForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const submitButton = createUserForm.querySelector('button[type="submit"]');
  submitButton.disabled = true;
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
    setStatus(`Account created for ${user.email}. Email verification is not yet complete.`);
  } catch (error) { setStatus(`Account creation failed: ${error.message}`); }
  finally { submitButton.disabled = false; }
});

document.getElementById('delete-account-toggle').addEventListener('click', () => {
  deleteAccountForm.hidden = false;
  document.getElementById('delete-account-password').focus();
});

document.getElementById('delete-account-cancel').addEventListener('click', () => {
  deleteAccountForm.reset();
  deleteAccountForm.hidden = true;
});

deleteAccountForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (!window.confirm('Delete your account and sign out of all sessions? This cannot be undone.')) return;
  const submitButton = deleteAccountForm.querySelector('button[type="submit"]');
  submitButton.disabled = true;
  setStatus('Deleting account...');
  try {
    await apiRequest('/auth/me', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: document.getElementById('delete-account-password').value, mfa_code: document.getElementById('delete-account-mfa-code').value.trim() || null }),
    });
    deleteAccountForm.reset();
    window.location.assign('/login.html');
  } catch (error) {
    setStatus(`Account deletion failed: ${error.message}`);
  } finally {
    submitButton.disabled = false;
  }
});

mfaSetupForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = mfaSetupForm.querySelector('button[type="submit"]');
  button.disabled = true;
  setStatus('Preparing authenticator...');
  try {
    const result = await apiRequest('/auth/mfa/setup', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: document.getElementById('mfa-setup-password').value }),
    });
    mfaSetupForm.reset();
    mfaSetupForm.hidden = true;
    document.getElementById('mfa-secret').textContent = result.secret;
    document.getElementById('mfa-secret-panel').hidden = false;
    setStatus('Enter the current code from your authenticator.');
  } catch (error) { setStatus(`Authenticator setup failed: ${error.message}`); }
  finally { button.disabled = false; }
});

mfaEnableForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = mfaEnableForm.querySelector('button[type="submit"]');
  button.disabled = true;
  setStatus('Enabling two-step sign-in...');
  try {
    const result = await apiRequest('/auth/mfa/enable', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: document.getElementById('mfa-enable-code').value.trim() }),
    });
    mfaEnableForm.reset();
    document.getElementById('mfa-secret').textContent = '';
    document.getElementById('mfa-secret-panel').hidden = true;
    document.getElementById('mfa-recovery-codes').value = result.recovery_codes.join('\n');
    document.getElementById('mfa-recovery-panel').hidden = false;
    await loadMfaStatus();
    setStatus('Two-step sign-in is enabled. Save your recovery codes now.');
  } catch (error) { setStatus(`Unable to enable two-step sign-in: ${error.message}`); }
  finally { button.disabled = false; }
});

document.getElementById('mfa-copy-recovery').addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(document.getElementById('mfa-recovery-codes').value);
    setStatus('Recovery codes copied. Store them securely.');
  } catch { setStatus('Copy failed. Select and copy the recovery codes.'); }
});

document.getElementById('mfa-recovery-done').addEventListener('click', () => {
  if (!window.confirm('Have you saved the recovery codes? They will not be shown again.')) return;
  document.getElementById('mfa-recovery-codes').value = '';
  document.getElementById('mfa-recovery-panel').hidden = true;
});

mfaDisableForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (!window.confirm('Turn off two-step sign-in for this account?')) return;
  const button = mfaDisableForm.querySelector('button[type="submit"]');
  button.disabled = true;
  setStatus('Turning off two-step sign-in...');
  try {
    await apiRequest('/auth/mfa/disable', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: document.getElementById('mfa-disable-password').value, mfa_code: document.getElementById('mfa-disable-code').value.trim() }),
    });
    mfaDisableForm.reset();
    await loadMfaStatus();
    setStatus('Two-step sign-in is off.');
  } catch (error) { setStatus(`Unable to turn off two-step sign-in: ${error.message}`); }
  finally { button.disabled = false; }
});

loadCurrentUser();
