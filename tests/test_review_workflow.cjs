const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

test('creating a share link preserves completed capture checklist items', async () => {
  const elements = new Map();
  const createElement = () => ({
    innerHTML: '', textContent: '', value: '7', style: {}, children: [],
    addEventListener() {},
    appendChild(child) { this.children.push(child); this.textContent = child.textContent; },
  });
  const context = vm.createContext({
    URLSearchParams,
    window: { location: { search: '', protocol: 'https:', hostname: 'example.com', origin: 'https://example.com' } },
    document: {
      getElementById(id) {
        if (!elements.has(id)) elements.set(id, createElement());
        return elements.get(id);
      },
      createElement,
    },
  });
  const source = fs.readFileSync(path.join(__dirname, '../frontend/review.js'), 'utf8');
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../frontend/security.js'), 'utf8'), context);
  vm.runInContext(source.replace(/loadProjectList\(\);\s*$/, ''), context);
  vm.runInContext(`
    activeProjectId = 'audit';
    apiRequest = async (url, options) => url.endsWith('/share-link')
      ? { share_token: 'audit-token', share_link: '/share.html?token=audit-token', expires_at: '2026-10-10T00:00:00Z' }
      : { title: 'Audit', status: 'draft', pin_count: 1, pins: [{ native_file_key: 'native.insp' }] };
  `, context);
  await vm.runInContext('createShareLink()', context);
  const checklist = elements.get('onboarding-checklist').innerHTML;
  assert.equal((checklist.match(/class="done"/g) || []).length, 4);
  assert.equal(elements.get('copy-share-link').style.display, 'inline-block');
  assert.equal(elements.get('revoke-share-link').style.display, 'inline-block');
  assert.ok(elements.get('share-expiry-text').textContent.startsWith('Expires '));
  assert.ok(elements.get('review-summary').innerHTML.includes('1 pins captured'));
});

test('revoking a share link hides the link and sends DELETE', async () => {
  const elements = new Map();
  const createElement = () => ({
    innerHTML: '', textContent: '', value: '7', style: {}, children: [],
    addEventListener() {}, appendChild(child) { this.children.push(child); this.textContent = child.textContent; },
  });
  const context = vm.createContext({
    URLSearchParams,
    window: { location: { search: '', protocol: 'https:', hostname: 'example.com', origin: 'https://example.com' } },
    document: {
      getElementById(id) {
        if (!elements.has(id)) elements.set(id, createElement());
        return elements.get(id);
      },
      createElement,
    },
  });
  const source = fs.readFileSync(path.join(__dirname, '../frontend/review.js'), 'utf8');
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../frontend/security.js'), 'utf8'), context);
  vm.runInContext(source.replace(/loadProjectList\(\);\s*$/, ''), context);
  vm.runInContext(`
    activeProjectId = 'audit';
    activeShareToken = 'audit-token';
    apiRequest = async (url, options = {}) => {
      if (options.method === 'DELETE') return null;
      return { title: 'Audit', status: 'draft', pin_count: 1, pins: [{ native_file_key: 'native.insp' }] };
    };
  `, context);
  await vm.runInContext('revokeShareLink()', context);
  assert.equal(elements.get('share-box').style.display, 'none');
  assert.equal(elements.get('revoke-share-link').style.display, 'none');
  assert.ok(elements.get('onboarding-checklist').innerHTML.includes('pending'));
});

test('review renders malicious stored project and capture content as text', async () => {
  const elements = new Map();
  const context = vm.createContext({
    URLSearchParams,
    window: { location: { search: '', protocol: 'https:', hostname: 'example.com', origin: 'https://example.com' } },
    document: {
      getElementById(id) {
        if (!elements.has(id)) elements.set(id, { innerHTML: '', textContent: '', style: {}, addEventListener() {} });
        return elements.get(id);
      },
    },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../frontend/security.js'), 'utf8'), context);
  const source = fs.readFileSync(path.join(__dirname, '../frontend/review.js'), 'utf8');
  vm.runInContext(source.replace(/loadProjectList\(\);\s*$/, ''), context);
  vm.runInContext(`
    activeProjectId = 'security';
    apiRequest = async () => ({
      title: '<img src=x onerror=alert(1)>', description: '<script>alert(2)</script>',
      status: 'draft', pin_count: 1,
      pins: [{ captured_on: '<img src=x onerror=alert(3)>', media_type: '<svg/onload=alert(4)>', heading: 0 }],
    });
  `, context);
  await vm.runInContext("renderProject('security')", context);
  const summary = elements.get('review-summary').innerHTML;
  const pins = elements.get('review-pins').innerHTML;
  assert.ok(summary.includes('&lt;img src=x onerror=alert(1)&gt;'));
  assert.ok(summary.includes('&lt;script&gt;alert(2)&lt;/script&gt;'));
  assert.ok(pins.includes('&lt;img src=x onerror=alert(3)&gt;'));
  assert.ok(pins.includes('&lt;svg/onload=alert(4)&gt;'));
  assert.ok(!summary.includes('<script>') && !pins.includes('<svg/'));
});

test('API base overrides cannot redirect credentials to a foreign origin', () => {
  const context = vm.createContext({ URL, window: { location: { href: 'https://example.com/login.html', origin: 'https://example.com' } } });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../frontend/security.js'), 'utf8'), context);
  assert.equal(vm.runInContext("safeApiBase('https://attacker.example')", context), null);
  assert.equal(vm.runInContext("safeApiBase('//attacker.example')", context), null);
  assert.equal(vm.runInContext("safeApiBase('https://example.com.attacker.example')", context), null);
  assert.equal(vm.runInContext("safeApiBase('https://user@example.com')", context), null);
  assert.equal(vm.runInContext("safeApiBase('https://example.com/api')", context), 'https://example.com/api');
  assert.equal(vm.runInContext("safeLocalRedirect('/floorplan.html?project=1')", context), '/floorplan.html?project=1');
  assert.equal(vm.runInContext("safeLocalRedirect('//attacker.example')", context), 'index.html');
  assert.equal(vm.runInContext("safeLocalRedirect('/\\\\attacker.example')", context), 'index.html');
});

test('sign-in preserves the server error without retrying another API base', async () => {
  const requests = [];
  const elements = new Map();
  const context = vm.createContext({
    URL, URLSearchParams,
    window: { location: { search: '', protocol: 'https:', hostname: 'example.com', origin: 'https://example.com', href: 'https://example.com/login.html', port: '' } },
    document: { getElementById(id) { if (!elements.has(id)) elements.set(id, { addEventListener() {} }); return elements.get(id); } },
    fetch: async (url) => { requests.push(url); return { ok: false, status: 401, json: async () => ({ error: { message: 'Email or password is incorrect.' } }) }; },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../frontend/security.js'), 'utf8'), context);
  const source = fs.readFileSync(path.join(__dirname, '../frontend/login.js'), 'utf8');
  vm.runInContext(source.replace(/loadCurrentUser\(\);\s*$/, ''), context);
  await assert.rejects(vm.runInContext("apiRequest('/auth/login', { method: 'POST' })", context), /Email or password is incorrect/);
  assert.deepEqual(requests, ['https://example.com/auth/login']);
});

for (const isAdmin of [false, true]) {
  test(`account creation uses the ${isAdmin ? 'administrator' : 'public'} endpoint`, async () => {
    const requests = [];
    const elements = new Map();
    function element(id) {
      if (!elements.has(id)) elements.set(id, {
        value: '', hidden: true, disabled: true, checked: false, textContent: '',
        addEventListener(type, handler) { this[type] = handler; },
        reset() { this.resetCalled = true; },
      });
      return elements.get(id);
    }
    element('registration-name').value = 'New User';
    element('registration-email').value = 'new@example.com';
    element('registration-password').value = 'a secure new passphrase';
    element('registration-confirm').value = 'a secure new passphrase';
    element('registration-admin').checked = true;
    const context = vm.createContext({
      document: { getElementById: element },
      fetch: async (url, options) => {
        requests.push({ url, options });
        if (url === '/auth/me') return isAdmin
          ? { ok: true, status: 200, json: async () => ({ is_admin: true }) }
          : { ok: false, status: 401 };
        if (url === '/auth/registration') return { ok: true, status: 200, json: async () => ({ available: true }) };
        return { ok: true, status: isAdmin ? 201 : 202, json: async () => ({ message: 'Check your inbox.' }) };
      },
    });
    const source = fs.readFileSync(path.join(__dirname, '../frontend/register.js'), 'utf8');
    vm.runInContext(source.replace(/initializeRegistration\(\);\s*$/, ''), context);
    await vm.runInContext('initializeRegistration()', context);
    assert.equal(element('registration-admin-option').hidden, !isAdmin);
    await element('registration-form').submit({ preventDefault() {} });
    const request = requests[requests.length - 1];
    assert.equal(request.url, isAdmin ? '/auth/users' : '/auth/register');
    assert.equal(request.options.credentials, 'same-origin');
    const payload = JSON.parse(request.options.body);
    assert.equal(payload.is_admin, isAdmin ? true : undefined);
    assert.equal(element('registration-form').resetCalled, true);
    assert.equal(element('registration-submit').disabled, false);
  });
}

test('disabled public registration is explained before submission', async () => {
  const elements = new Map();
  const context = vm.createContext({
    document: { getElementById(id) {
      if (!elements.has(id)) elements.set(id, { hidden: true, disabled: true, textContent: '', addEventListener() {} });
      return elements.get(id);
    } },
    fetch: async (url) => url === '/auth/me'
      ? { ok: false, status: 401 }
      : { ok: true, status: 200, json: async () => ({ available: false }) },
  });
  const source = fs.readFileSync(path.join(__dirname, '../frontend/register.js'), 'utf8');
  vm.runInContext(source.replace(/initializeRegistration\(\);\s*$/, ''), context);
  await vm.runInContext('initializeRegistration()', context);
  assert.equal(elements.get('registration-submit').disabled, true);
  assert.match(elements.get('registration-status').textContent, /unavailable/);
});

test('frontend assets do not contain common private credential formats', () => {
  const directory = path.join(__dirname, '../frontend');
  const patterns = [
    /(?:AKIA|ASIA)[A-Z0-9]{16}/,
    /ghp_[A-Za-z0-9]{36,}/,
    /github_pat_[A-Za-z0-9_]{22,}/,
    /sk_(?:live|test)_[A-Za-z0-9]{16,}/,
    /AIza[0-9A-Za-z_-]{35}/,
    /\bDO00[A-Z0-9]{16,}\b/,
    /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/,
    /\b(?:AWS_SECRET_ACCESS_KEY|SMTP_PASSWORD|MFA_ENCRYPTION_KEY|SENTRY_DSN)\b/,
  ];
  for (const filename of fs.readdirSync(directory).filter(name => /\.(?:html|js|css)$/.test(name))) {
    const source = fs.readFileSync(path.join(directory, filename), 'utf8');
    assert.ok(!patterns.some(pattern => pattern.test(source)), `Potential private credential in frontend asset: ${filename}`);
  }
});