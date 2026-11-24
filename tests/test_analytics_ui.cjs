const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function dashboard({ enabled = true, consent = null } = {}) {
  const elements = new Map();
  const storage = new Map();
  if (consent) storage.set('casai.analytics.consent', consent);
  function element(id) {
    if (!elements.has(id)) elements.set(id, {
      hidden: true, checked: false, textContent: '', listeners: {},
      addEventListener(name, callback) { this.listeners[name] = callback; },
      replaceChildren() {}, appendChild() {},
    });
    return elements.get(id);
  }
  const requests = [];
  const context = vm.createContext({
    URLSearchParams,
    window: {
      location: { search: '', protocol: 'https:', hostname: 'example.com', origin: 'https://example.com' },
      localStorage: {
        getItem: key => storage.get(key) || null,
        setItem: (key, value) => storage.set(key, value),
        removeItem: key => storage.delete(key),
      },
    },
    document: { getElementById: element, createElement: () => element('created') },
  });
  const source = fs.readFileSync(path.join(__dirname, '../frontend/app.js'), 'utf8')
    .replace(/loadUser\(\);\s*loadProjects\(\);\s*$/, '');
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../frontend/security.js'), 'utf8'), context);
  vm.runInContext(source, context);
  context.mockRequest = async (url, options) => {
    requests.push({ url, options });
    return url === '/analytics/config' ? { enabled } : { daily: [] };
  };
  vm.runInContext('apiRequest = mockRequest', context);
  return { element, requests, run: code => vm.runInContext(code, context) };
}

test('analytics sends no events before consent and stops after withdrawal', async () => {
  const app = dashboard();
  await app.run('initializeAnalytics(false)');
  assert.deepEqual(app.requests.map(request => request.url), ['/analytics/config']);
  const control = app.element('analytics-consent');
  control.checked = true;
  control.listeners.change();
  assert.equal(app.requests[1].url, '/analytics/events');
  assert.equal(app.requests[1].options.referrerPolicy, 'no-referrer');
  assert.deepEqual(JSON.parse(app.requests[1].options.body), { event: 'dashboard_opened', consent: true });
  control.checked = false;
  control.listeners.change();
  app.run("trackAnalytics('project_created')");
  assert.equal(app.requests.length, 2);
});

test('disabled analytics does not show consent or submit events', async () => {
  const app = dashboard({ enabled: false, consent: 'yes' });
  await app.run('initializeAnalytics(false)');
  app.run("trackAnalytics('project_created')");
  assert.equal(app.element('analytics-settings').hidden, true);
  assert.deepEqual(app.requests.map(request => request.url), ['/analytics/config']);
});