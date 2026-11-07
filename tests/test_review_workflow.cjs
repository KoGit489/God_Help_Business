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