const BASE = 'https://graphhopper.com/api/1/';
const ORIGIN = 'https://aws-hackathon2025.vercel.app';
// Match the Python scorer's bounded per-route workload.
export const MAX_ROUTE_COORDINATES = 2000;

function response(statusCode, body) {
  return { statusCode, headers: { 'content-type': 'application/json', 'cache-control': 'no-store' }, body: JSON.stringify(body) };
}
function point(p) {
  return p && typeof p.lat === 'number' && typeof p.lng === 'number' &&
    Number.isFinite(p.lat) && Number.isFinite(p.lng) &&
    p.lat >= 37.70 && p.lat <= 37.83 && p.lng >= -122.53 && p.lng <= -122.35;
}

export async function handler(event) {
  const method = event.requestContext?.http?.method;
  const route = event.routeKey;
  if (method !== 'POST' || !['POST /routing/geocode', 'POST /routing/route'].includes(route)) {
    return response(404, { error: 'Not found.' });
  }
  const origin = Object.entries(event.headers || {}).find(([name]) => name.toLowerCase() === 'origin')?.[1];
  if (origin && origin !== ORIGIN && !/^http:\/\/localhost:(3000|4190|4192)$/.test(origin)) {
    return response(403, { error: 'Origin is not allowed.' });
  }
  let body;
  try {
    const raw = event.isBase64Encoded ? Buffer.from(event.body || '', 'base64').toString('utf8') : event.body || '';
    if (Buffer.byteLength(raw) > 2048) return response(413, { error: 'Request is too large.' });
    body = JSON.parse(raw);
    if (!body || typeof body !== 'object' || Array.isArray(body)) throw new Error();
  } catch { return response(400, { error: 'Invalid JSON request.' }); }

  const url = new URL(route.endsWith('/geocode') ? 'geocode' : 'route', BASE);
  if (route.endsWith('/geocode')) {
    if (Object.keys(body).some(key => key !== 'address') || typeof body.address !== 'string' ||
        !body.address.trim() || body.address.length > 300) {
      return response(400, { error: 'Provide an address of 1 to 300 characters.' });
    }
    const address = body.address.trim();
    const contextual = /san francisco|\bsf\b|,\s*ca\b|california/i.test(address);
    url.searchParams.set('q', contextual ? address : `${address}, San Francisco, CA`);
    url.searchParams.set('point', '37.7749,-122.4194');
    url.searchParams.set('locale', 'en-US');
    url.searchParams.set('limit', '5');
  } else {
    if (Object.keys(body).some(key => !['origin', 'destination'].includes(key)) || !point(body.origin) || !point(body.destination)) {
      return response(400, { error: 'Walking routes must start and end within San Francisco.' });
    }
    url.searchParams.set('vehicle', 'foot');
    url.searchParams.set('locale', 'en');
    url.searchParams.set('points_encoded', 'false');
    url.searchParams.set('algorithm', 'alternative_route');
    url.searchParams.set('alternative_route.max_paths', '3');
    for (const p of [body.origin, body.destination]) url.searchParams.append('point', `${p.lat},${p.lng}`);
  }
  const key = process.env.GRAPHHOPPER_API_KEY;
  if (!key) return response(503, { error: 'Routing service is not configured.' });
  url.searchParams.set('key', key);
  try {
    const upstream = await fetch(url, { signal: AbortSignal.timeout(18000), redirect: 'error' });
    if (!upstream.ok) {
      // Never relay upstream errors: they may echo the authenticated request URL.
      return response(upstream.status === 429 ? 429 : 502, { error: 'Routing provider is unavailable. Please try again.' });
    }
    const data = await upstream.json();
    if (route.endsWith('/geocode')) {
      if (!Array.isArray(data.hits)) throw new Error();
      return response(200, { hits: data.hits.filter(hit => point(hit.point)).slice(0, 5).map(hit => ({ point: { lat: hit.point.lat, lng: hit.point.lng } })) });
    }
    if (!Array.isArray(data.paths)) throw new Error();
    const alternatives = data.paths.slice(0, 3);
    if (alternatives.some(path => Array.isArray(path?.points?.coordinates) && path.points.coordinates.length > MAX_ROUTE_COORDINATES)) {
      return response(422, { error: 'This route is too detailed to analyse. Please choose closer locations.' });
    }
    const paths = alternatives.map(path => {
      if (![path.distance, path.time].every(n => typeof n === 'number' && Number.isFinite(n) && n >= 0) ||
          !Array.isArray(path.points?.coordinates) || path.points.coordinates.length < 2 ||
          path.points.coordinates.some(c =>
            !Array.isArray(c) || c.length < 2 || !point({ lng: c[0], lat: c[1] }))) throw new Error();
      return { distance: path.distance, time: path.time, points: { coordinates: path.points.coordinates.map(c => [c[0], c[1]]) } };
    });
    return response(200, { paths });
  } catch {
    // No request URLs, credentials, address bodies, or upstream payloads are logged.
    return response(502, { error: 'Could not retrieve a walking route. Please try again.' });
  }
}
