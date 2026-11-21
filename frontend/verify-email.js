const requestForm = document.getElementById('verification-request-form');
const confirmForm = document.getElementById('verification-confirm-form');
const verificationStatus = document.getElementById('verification-status');
let token = null;

function readVerificationLink() {
  if (!window.location.hash) return;
  token = new URLSearchParams(window.location.hash.slice(1)).get('token');
  history.replaceState(null, '', `${window.location.pathname}${window.location.search}`);
  if (token) {
    requestForm.hidden = true;
    confirmForm.hidden = false;
  }
}
window.addEventListener('hashchange', readVerificationLink);
readVerificationLink();

async function postVerification(path, data) {
  const response = await fetch(path, {
    method: 'POST', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new Error(payload?.error?.message || `Request failed (${response.status})`);
}

requestForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = requestForm.querySelector('button[type="submit"]');
  button.disabled = true;
  verificationStatus.textContent = 'Sending request...';
  try {
    await postVerification('/auth/email-verification/request', { email: document.getElementById('verification-email').value });
    verificationStatus.textContent = 'If the account needs verification, an email will be sent.';
    requestForm.reset();
  } catch (error) {
    verificationStatus.textContent = `Unable to request verification: ${error.message}`;
  } finally {
    button.disabled = false;
  }
});

confirmForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = confirmForm.querySelector('button[type="submit"]');
  button.disabled = true;
  verificationStatus.textContent = 'Verifying email...';
  try {
    await postVerification('/auth/email-verification/confirm', { token });
    confirmForm.hidden = true;
    verificationStatus.textContent = 'Email verified. You can now sign in.';
  } catch (error) {
    verificationStatus.textContent = `Unable to verify email: ${error.message}`;
  } finally {
    button.disabled = false;
  }
});