const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

test('creating a share link preserves completed capture checklist items', async () => {
  const elements = new Map();
  const context = vm.createContext({
    URLSearchParams,
    window: { location: { search: '', protocol: 'https:', hostname: 'example.com', origin: 'https://example.com' } },
    document: {
      getElementById(id) {
        if (!elements.has(id)) elements.set(id, { innerHTML: '', style: {}, addEventListener() {} });
        return elements.get(id);
      },
    },
  });
  const source = fs.readFileSync(path.join(__dirname, '../frontend/review.js'), 'utf8');
  vm.runInContext(source.replace(/loadProjectList\(\);\s*$/, ''), context);
  vm.runInContext(`
    activeProjectId = 'audit';
    apiRequest = async (url) => url.endsWith('/share-link')
      ? { share_token: 'audit-token', share_link: '/share.html?token=audit-token' }
      : { title: 'Audit', status: 'draft', pin_count: 1, pins: [{ native_file_key: 'native.insp' }] };
  `, context);
  await vm.runInContext('createShareLink()', context);
  const checklist = elements.get('onboarding-checklist').innerHTML;
  assert.equal((checklist.match(/class="done"/g) || []).length, 4);
  assert.equal(elements.get('copy-share-link').style.display, 'inline-block');
  assert.ok(elements.get('review-summary').innerHTML.includes('1 pins captured'));
});