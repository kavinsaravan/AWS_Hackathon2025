// Protect the archived optional client against reintroducing simulated safety data.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { stripTypeScriptTypes } = require('node:module');

function load(fetch, endpoint = 'https://fixture.invalid/prod') {
  const sandbox = { fetch, URLSearchParams, process: { env: { REACT_APP_API_ENDPOINT: endpoint } } };
  vm.createContext(sandbox);
  const source = fs.readFileSync(path.join(__dirname, '../legacy/frontend/src/services/hotspotService.ts'), 'utf8');
  vm.runInContext(stripTypeScriptTypes(source.replace(/export /g, '')), sandbox);
  return sandbox;
}

test('missing hotspot configuration rejects without making a request', async () => {
  let requested = false;
  await assert.rejects(load(async () => { requested = true; }, '').fetchHotspots(), /not configured/);
  assert.equal(requested, false);
});

test('HTTP hotspot failures reject instead of returning simulated incidents', async () => {
  await assert.rejects(load(async () => ({ ok: false, status: 503 })).fetchHotspots(), /HTTP 503/);
});

test('network hotspot failures propagate instead of returning simulated incidents', async () => {
  const failure = new Error('network unavailable');
  await assert.rejects(load(async () => { throw failure; }).fetchHotspots(), error => error === failure);
});

test('successful hotspot responses preserve actual provider data, including empty results', async () => {
  const actual = { type: 'FeatureCollection', features: [] };
  const client = load(async () => ({ ok: true, json: async () => actual }));
  assert.equal(await client.fetchHotspots(), actual);
});
