// Offline production-service checks. Requires Node.js 22.6+ for TS stripping.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { stripTypeScriptTypes } = require('node:module');

function load(fetch, endpoint = 'https://fixture.invalid/prod/') {
  const sandbox = { fetch, URLSearchParams, AbortController, setTimeout, clearTimeout,
    console: { error() {} }, process: { env: {
      REACT_APP_API_ENDPOINT: endpoint,
    } } };
  vm.createContext(sandbox);
  for (const filename of ['routeSafety.ts', 'graphhopper.ts']) {
    let source = fs.readFileSync(path.join(__dirname, '../src/services', filename), 'utf8');
    source = source.replace(/^import .*$/mg, '').replace(/export /g, '');
    vm.runInContext(stripTypeScriptTypes(source), sandbox);
  }
  return sandbox;
}

function route(offset, minutes) {
  return { distance: 1000, time: minutes * 60000, points: { coordinates:
    [[-122.42, 37.77 + offset], [-122.41, 37.77 + offset]] } };
}
function fixture(paths, assessment) {
  const calls = [];
  const fetch = async (url, options) => {
    calls.push({ url, options });
    if (url.includes('/geocode')) return { ok: true, json: async () => ({ hits: [{ point: { lat: 37.77, lng: -122.42 } }] }) };
    if (url.endsWith('/routing/route')) return { ok: true, json: async () => ({ paths }) };
    return { ok: true, json: async () => assessment };
  };
  return { fetch, calls };
}
function assessment(risks) {
  return { assessedAt: '2026-10-10T02:00:00Z', dataFetchedAt: '2026-10-10T01:59:00Z', sources: { policeCalls: 3, open311Reports: 1 },
    routes: risks.map((risk, index) => ({ id: index + 1, totalRisk: risk, crimeRisk: risk,
      hazardRisk: 0, safetyScore: 100 / (1 + risk) })) };
}

test('rank by backend risk, preserving geometry and identifying actual fastest', async () => {
  const f = fixture([route(0, 10), route(.01, 20), route(.02, 15)], assessment([9, 0, 2]));
  const result = await load(f.fetch).calculateRoutes('Origin', 'Destination');
  assert.deepEqual(Array.from(result.routes, r => r.id), [2, 3, 1]);
  assert.equal(result.routes[0].name, 'Lowest Reported Risk');
  assert.equal(result.routes[2].name, 'Fastest Route');
  assert.equal(result.routes[0].coordinates[0].lat, 37.78);
  assert.equal(result.routes[0].safetyScore, 100);
  assert.equal(result.routes[0].waypoints.length, 0);
  const scoring = f.calls.find(call => call.url.endsWith('/score-routes'));
  assert.equal(scoring.url, 'https://fixture.invalid/prod/score-routes');
  assert.equal(scoring.options.method, 'POST');
  assert.equal(JSON.parse(scoring.options.body).routes.length, 3);
});

test('one actual route stays one route; repeated alternatives are removed', async () => {
  const one = route(0, 10);
  const f = fixture([one, one], assessment([1]));
  const result = await load(f.fetch).calculateRoutes('Origin', 'Destination');
  assert.equal(result.routes.length, 1);
  assert.equal(result.routes[0].name, 'Lowest Risk · Fastest');
});

test('source failure propagates, never substitutes simulated scores', async () => {
  const f = fixture([route(0, 10)], assessment([0]));
  const client = load(async (url, options) => url.includes('/score-routes')
    ? { ok: false, status: 503 } : f.fetch(url, options));
  await assert.rejects(client.calculateRoutes('Origin', 'Destination'), /Safety data is unavailable/);
});

test('missing endpoint prevents any safety request', async () => {
  let requested = false;
  const client = load(async () => { requested = true; }, '');
  await assert.rejects(client.assessRouteSafety([]), /not configured/);
  assert.equal(requested, false);
});

test('invalid or mismatched response IDs are rejected', async () => {
  const data = assessment([0, 2]); data.routes[1].id = 1;
  const f = fixture([route(0, 10), route(.01, 15)], data);
  await assert.rejects(load(f.fetch).calculateRoutes('Origin', 'Destination'), /invalid assessment/);
});

test('equal risks choose faster route first', async () => {
  const f = fixture([route(0, 20), route(.01, 10)], assessment([0, 0]));
  const result = await load(f.fetch).calculateRoutes('Origin', 'Destination');
  assert.equal(result.routes[0].id, 2);
});

test('an oversized provider route shows the proxy complexity message without calling the scorer', async () => {
  const f = fixture([route(0, 10)], assessment([0]));
  let scoringRequested = false;
  const client = load(async (url, options) => {
    if (url.endsWith('/score-routes')) scoringRequested = true;
    return url.endsWith('/routing/route') ? { ok: false, status: 422 } : f.fetch(url, options);
  });
  await assert.rejects(client.calculateRoutes('Origin', 'Destination'), /too detailed.*closer locations/);
  assert.equal(scoringRequested, false);
});

 test('routing requests use only the backend, without a browser API key', async () => {
  const f = fixture([route(0, 10)], assessment([1]));
  await load(f.fetch).calculateRoutes('Origin', 'Destination');
  for (const call of f.calls) {
    assert.ok(call.url.startsWith('https://fixture.invalid/prod/'));
    assert.equal(call.options.method, 'POST');
    assert.ok(!call.url.includes('key='));
    assert.ok(!call.options.body.includes('GRAPHHOPPER'));
  }
  const routing = f.calls.find(call => call.url.endsWith('/routing/route'));
  assert.deepEqual(JSON.parse(routing.options.body), {
    origin: { lat: 37.77, lng: -122.42 }, destination: { lat: 37.77, lng: -122.42 },
  });
});
