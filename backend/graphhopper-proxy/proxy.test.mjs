import { test, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { handler } from './index.mjs';
const originalFetch = globalThis.fetch;
const originalKey = process.env.GRAPHHOPPER_API_KEY;
afterEach(() => { globalThis.fetch = originalFetch; if (originalKey === undefined) delete process.env.GRAPHHOPPER_API_KEY; else process.env.GRAPHHOPPER_API_KEY = originalKey; });
function event(body, route = 'geocode') {
  return { routeKey: `POST /routing/${route}`, requestContext: { http: { method: 'POST' } }, headers: { origin: 'https://aws-hackathon2025.vercel.app' }, body: JSON.stringify(body) };
}
function ready(callback) { process.env.GRAPHHOPPER_API_KEY = 'test-private-key'; globalThis.fetch = callback; }
test('geocoding authenticates upstream only, adds SF bias, removes upstream metadata', async () => {
  ready(async url => {
    assert.equal(url.origin, 'https://graphhopper.com');
    assert.equal(url.searchParams.get('key'), 'test-private-key');
    assert.equal(url.searchParams.get('q'), 'Ferry Building, San Francisco, CA');
    return { ok: true, json: async () => ({ hits: [{ point: { lat: 37.79, lng: -122.39 }, key: 'test-private-key' }, { point: { lat: 0, lng: 0 } }], debug: 'test-private-key' }) };
  });
  const result = await handler(event({ address: 'Ferry Building' }));
  assert.equal(result.statusCode, 200);
  assert.deepEqual(JSON.parse(result.body), { hits: [{ point: { lat: 37.79, lng: -122.39 } }] });
  assert.ok(!result.body.includes('test-private-key'));
});
test('walking requests force foot and bounded alternatives, preserve geometry', async () => {
  ready(async url => {
    assert.equal(url.searchParams.get('vehicle'), 'foot');
    assert.deepEqual(url.searchParams.getAll('point'), ['37.77,-122.42', '37.79,-122.39']);
    assert.equal(url.searchParams.get('alternative_route.max_paths'), '3');
    return { ok: true, json: async () => ({ paths: [{ distance: 1000, time: 60000, points: { coordinates: [[-122.42, 37.77], [-122.39, 37.79]] }, debug: 'test-private-key' }] }) };
  });
  const result = await handler(event({ origin: { lat: 37.77, lng: -122.42 }, destination: { lat: 37.79, lng: -122.39 } }, 'route'));
  assert.equal(result.statusCode, 200);
  assert.equal(JSON.parse(result.body).paths[0].points.coordinates.length, 2);
  assert.ok(!result.body.includes('test-private-key'));
});
test('rejects malformed, oversized, unknown parameters and out-of-city inputs without calling upstream', async () => {
  let calls = 0; ready(async () => { calls++; });
  const cases = [event({ address: '' }), event({ address: 'a', key: 'injected' }), event({ address: 'a', url: 'https://evil.invalid' }), event({ origin: { lat: 0, lng: 0 }, destination: { lat: 37.79, lng: -122.39 } }, 'route')];
  for (const request of cases) assert.equal((await handler(request)).statusCode, 400);
  assert.equal((await handler({ ...event({}), body: '{' })).statusCode, 400);
  assert.equal((await handler(event({ address: 'a'.repeat(3000) }))).statusCode, 413);
  assert.equal(calls, 0);
});
test('rejects other origins and methods', async () => {
  ready(async () => { throw new Error('must not fetch'); });
  assert.equal((await handler({ ...event({ address: 'a' }), headers: { origin: 'https://evil.invalid' } })).statusCode, 403);
  assert.equal((await handler({ ...event({ address: 'a' }), requestContext: { http: { method: 'GET' } } })).statusCode, 404);
});
test('supports API Gateway base64 body', async () => {
  ready(async () => ({ ok: true, json: async () => ({ hits: [] }) }));
  const request = event({ address: 'Ferry Building' });
  request.body = Buffer.from(request.body).toString('base64'); request.isBase64Encoded = true;
  assert.equal((await handler(request)).statusCode, 200);
});
test('missing server key fails closed', async () => {
  delete process.env.GRAPHHOPPER_API_KEY;
  assert.equal((await handler(event({ address: 'a' }))).statusCode, 503);
});
test('provider errors and exceptions never echo authenticated URL or key', async () => {
  ready(async () => ({ ok: false, status: 401, json: async () => ({ message: 'test-private-key' }) }));
  let result = await handler(event({ address: 'a' }));
  assert.equal(result.statusCode, 502); assert.ok(!result.body.includes('test-private-key'));
  ready(async () => { throw new Error('https://graphhopper.com?key=test-private-key'); });
  result = await handler(event({ address: 'a' }));
  assert.equal(result.statusCode, 502); assert.ok(!result.body.includes('test-private-key'));
  ready(async () => ({ ok: false, status: 429 }));
  assert.equal((await handler(event({ address: 'a' }))).statusCode, 429);
});
test('rejects malformed provider geometry instead of forwarding it', async () => {
  ready(async () => ({ ok: true, json: async () => ({ paths: [{ distance: 1, time: 1, points: { coordinates: [[0, 0], [1, 1]] } }] }) }));
  const result = await handler(event({ origin: { lat: 37.77, lng: -122.42 }, destination: { lat: 37.79, lng: -122.39 } }, 'route'));
  assert.equal(result.statusCode, 502);
});
