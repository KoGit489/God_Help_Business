const registrationForm = document.getElementById('registration-form');
const registrationStatus = document.getElementById('registration-status');
const registrationSubmit = document.getElementById('registration-submit');
const adminOption = document.getElementById('registration-admin-option');
let isAdmin = false;

async function initializeRegistration() {
  try {
    const response = await fetch('/auth/me', { credentials: 'same-origin' });
    if (response.ok) {
      const user = await response.json();
      isAdmin = user.is_admin === true;
      adminOption.hidden = !isAdmin;
    } else if (response.status !== 401) {
      throw new Error('Unable to check account status. Please try again.');
    }
    if (!isAdmin) {
      const availability = await fetch('/auth/registration', { credentials: 'same-origin' });
      if (!availability.ok) throw new Error('Unable to check registration availability.');
      const settings = await availability.json();
      if (settings.available !== true) {
        registrationStatus.textContent = 'Account registration is unavailable. Contact an administrator.';
        return;
      }
    }
    registrationSubmit.disabled = false;
  } catch {
    registrationStatus.textContent = 'Unable to check account status. Please refresh and try again.';
  }
}

registrationForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const password = document.getElementById('registration-password').value;
  if (password !== document.getElementById('registration-confirm').value) {
    registrationStatus.textContent = 'Passwords do not match.';
    return;
  }
  const payload = {
    name: document.getElementById('registration-name').value,
    email: document.getElementById('registration-email').value,
    password,
  };
  if (isAdmin) payload.is_admin = document.getElementById('registration-admin').checked;
  registrationSubmit.disabled = true;
  registrationStatus.textContent = 'Creating account...';
  try {
    const response = await fetch(isAdmin ? '/auth/users' : '/auth/register', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    });
    const result = await response.json().catch(() => null);
    if (!response.ok) throw new Error(result?.error?.message || `Request failed (${response.status})`);
    registrationForm.reset();
    registrationStatus.textContent = isAdmin
      ? 'Account created. Email verification may be required before sign-in.'
      : result.message;
  } catch (error) {
    registrationStatus.textContent = `Unable to create account: ${error.message}`;
  } finally {
    registrationSubmit.disabled = false;
  }
});

initializeRegistration();