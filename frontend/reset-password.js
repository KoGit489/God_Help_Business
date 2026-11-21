const requestForm = document.getElementById('reset-request-form');
const confirmForm = document.getElementById('reset-confirm-form');
const resetStatus = document.getElementById('reset-status');
let token = null;

function readResetLink() {
  if (!window.location.hash) return;
  token = new URLSearchParams(window.location.hash.slice(1)).get('token');
  history.replaceState(null, '', `${window.location.pathname}${window.location.search}`);
  if (token) {
    requestForm.hidden = true;
    confirmForm.hidden = false;
  }
}
window.addEventListener('hashchange', readResetLink);
readResetLink();

async function postReset(path, data) {
  const response = await fetch(path, {
    method: 'POST', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new Error(payload?.error?.message || `Request failed (${response.status})`);
  return payload;
}

requestForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = requestForm.querySelector('button[type="submit"]');
  button.disabled = true;
  resetStatus.textContent = 'Sending request...';
  try {
    await postReset('/auth/password-reset/request', { email: document.getElementById('reset-email').value });
    resetStatus.textContent = 'If the account exists, a reset email will be sent.';
    requestForm.reset();
  } catch (error) {
    resetStatus.textContent = `Unable to request a reset: ${error.message}`;
  } finally {
    button.disabled = false;
  }
});

confirmForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const password = document.getElementById('reset-password').value;
  if (password !== document.getElementById('reset-password-confirm').value) {
    resetStatus.textContent = 'The passwords do not match.';
    return;
  }
  const button = confirmForm.querySelector('button[type="submit"]');
  button.disabled = true;
  resetStatus.textContent = 'Updating password...';
  try {
    await postReset('/auth/password-reset/confirm', { token, password });
    confirmForm.reset();
    confirmForm.hidden = true;
    resetStatus.textContent = 'Password updated. Sign in with your new password.';
  } catch (error) {
    resetStatus.textContent = `Unable to reset password: ${error.message}`;
  } finally {
    button.disabled = false;
  }
});