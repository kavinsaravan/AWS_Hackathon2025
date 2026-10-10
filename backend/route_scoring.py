"""POST /score-routes: validate GraphHopper paths and score live DataSF records."""

import math
import json
import time
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from path_risk_analysis import (calculate_risk_score, fetch_crime_data, fetch_311_data,
                                incident_coordinates, IncidentDataUnavailable)


def validate_routes(payload):
    routes = payload.get('routes') if isinstance(payload, dict) else None
    if not isinstance(routes, list) or not 1 <= len(routes) <= 3:
        raise ValueError('Provide one to three routes')
    validated = []
    ids = set()
    for route in routes:
        if not isinstance(route, dict):
            raise ValueError('Invalid route')
        route_id, coordinates = route.get('id'), route.get('coordinates')
        if isinstance(route_id, bool) or not isinstance(route_id, int) or route_id in ids:
            raise ValueError('Route IDs must be unique integers')
        if not isinstance(coordinates, list) or not 2 <= len(coordinates) <= 2000:
            raise ValueError('Each route must have 2 to 2000 coordinates')
        path = []
        for coord in coordinates:
            if not isinstance(coord, dict):
                raise ValueError('Invalid coordinate')
            lat, lng = coord.get('lat'), coord.get('lng')
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (lat, lng)):
                raise ValueError('Coordinates must be finite numbers')
            if not (37.70 <= lat <= 37.83 and -122.53 <= lng <= -122.35):
                raise ValueError('Route scoring is available within San Francisco only')
            path.append((lat, lng))
        validated.append((route_id, path))
        ids.add(route_id)
    return validated


def score_routes(payload):
    started = time.monotonic()
    routes = validate_routes(payload)
    points = [point for _, path in routes for point in path]
    # A 1km buffer exceeds the meaningful range of the distance attenuation.
    bounds = {'north': max(p[0] for p in points) + 0.01,
              'south': min(p[0] for p in points) - 0.01,
              'east': max(p[1] for p in points) + 0.013,
              'west': min(p[1] for p in points) - 0.013}
    now = datetime.now(timezone.utc)
    if os.environ.get('DYNAMODB_TABLE_NAME') and os.environ.get('S3_BUCKET_NAME'):
        from safety_data_store import SafetyDataStore, filter_to_bounds
        snapshot = SafetyDataStore().load(now)
        crimes = filter_to_bounds(snapshot['crimes'], 'crime', bounds)
        hazards = filter_to_bounds(snapshot['hazards'], '311', bounds)
        fetched_at = snapshot['fetchedAt']
        data_mode = 'aws-snapshot'
    else:
        # Local development can exercise the same scorer without AWS credentials.
        token = os.environ.get('DATASF_API_KEY')
        with ThreadPoolExecutor(max_workers=2) as executor:
            crime_future = executor.submit(fetch_crime_data, bounds, token, now)
            hazard_future = executor.submit(fetch_311_data, bounds, token)
            crimes, hazards = crime_future.result(), hazard_future.result()
        fetched_at = now.isoformat()
        data_mode = 'live-datasf'
    # A populated but wholly unusable response must not appear to be zero risk.
    for records, kind in ((crimes, 'crime'), (hazards, '311')):
        if records and not any(incident_coordinates(record, kind) is not None for record in records):
            raise IncidentDataUnavailable('Incident data has no usable coordinates')
    results = []
    for route_id, path in routes:
        crime_risk = calculate_risk_score(path, crimes, 'crime', now)
        hazard_risk = calculate_risk_score(path, hazards, '311', now)
        total = crime_risk + hazard_risk
        results.append({'id': route_id, 'totalRisk': total, 'crimeRisk': crime_risk,
                        'hazardRisk': hazard_risk, 'safetyScore': round(100 / (1 + total), 1)})
    print(json.dumps({'event': 'routes_scored', 'routeCount': len(results),
                      'elapsedMs': round((time.monotonic() - started) * 1000), 'dataMode': data_mode}))
    return {'routes': results, 'assessedAt': now.isoformat(),
            'dataFetchedAt': fetched_at, 'dataMode': data_mode,
            'sources': {'policeCalls': len(crimes), 'open311Reports': len(hazards)},
            'model': 'incident-distance-time-v1'}
