"""Incident-based route risk scoring for San Francisco.

Scores are a relative index of reported incidents, not a probability of safety.
DataSF timestamps without an offset are interpreted in America/Los_Angeles.
"""

import json
import math
import os
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

CRIME_API_URL = 'https://data.sfgov.org/resource/gnap-fj3t.json'
API_311_URL = 'https://data.sfgov.org/resource/vw6y-z8j6.json'
SF_TIMEZONE = ZoneInfo('America/Los_Angeles')
S3_BUCKET_NAME = os.environ.get('S3_BUCKET_NAME', 'my-path-risk-data')


class IncidentDataUnavailable(RuntimeError):
    """A source could not be completely read; do not report an invented score."""


def parse_incident_time(value):
    if isinstance(value, datetime):
        result = value
    else:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        result = result.replace(tzinfo=SF_TIMEZONE)
    return result.astimezone(timezone.utc)


def _fetch_records(url, bounds, where, coordinate_field, order, api_key=None, select='*'):
    if not bounds:
        raise ValueError('Geographic bounds are required')
    spatial = (f"within_box({coordinate_field}, {bounds['north']}, "
               f"{bounds['west']}, {bounds['south']}, {bounds['east']})")
    headers = {'X-App-Token': api_key} if api_key else {}
    records = []
    deadline = time.monotonic() + 20
    # Paginate rather than silently scoring a truncated source response.
    for offset in range(0, 15000, 5000):
        if time.monotonic() >= deadline:
            raise IncidentDataUnavailable('Incident query took too long')
        try:
            response = requests.get(url, params={
                '$where': f'({where}) AND {spatial}',
                '$limit': 5000, '$offset': offset, '$order': order, '$select': select,
            }, headers=headers, timeout=(3, min(6, max(1, deadline - time.monotonic()))))
            response.raise_for_status()
            page = response.json()
            if not isinstance(page, list) or any(not isinstance(item, dict) for item in page):
                raise ValueError('Invalid incident response')
        except (requests.RequestException, ValueError) as error:
            raise IncidentDataUnavailable('Unable to retrieve incident data') from error
        records.extend(page)
        if len(page) < 5000:
            return records
    raise IncidentDataUnavailable('Incident query exceeded the record limit')


def fetch_crime_data(area_bounds, api_key=None, current_time=None):
    now = parse_incident_time(current_time or datetime.now(timezone.utc))
    # SoQL floating timestamps are in local SF time, not UTC.
    start = (now - timedelta(hours=72)).astimezone(SF_TIMEZONE).replace(tzinfo=None).isoformat()
    end = now.astimezone(SF_TIMEZONE).replace(tzinfo=None).isoformat()
    return _fetch_records(CRIME_API_URL, area_bounds,
                         f"entry_datetime >= '{start}' AND entry_datetime <= '{end}'",
                         'intersection_point', 'entry_datetime DESC, cad_number ASC', api_key,
                         'entry_datetime,call_type_original_desc,intersection_point')


def fetch_311_data(area_bounds, api_key=None):
    return _fetch_records(API_311_URL, area_bounds,
                         "status_description = 'Open' AND caseless_one_of(service_name, "
                         "'Encampment', 'Encampments', 'Aggressive/Threatening')",
                         'point_geom', 'service_request_id ASC', api_key,
                         'requested_datetime,status_description,service_name,point_geom')


def save_to_s3(data, bucket_name, key):
    # Keep cloud clients out of the scoring module's import path.
    import boto3
    boto3.client('s3').put_object(Bucket=bucket_name, Key=key,
                                Body=json.dumps(data), ContentType='application/json')
    return True


def assign_risk(incident, incident_type):
    if incident_type == 'crime':
        description = incident.get('call_type_original_desc', '').upper()
        high = ('EXPLOSIVE', 'EXPLOSION', 'ROBBERY', 'ASSAULT', 'BATTERY',
                'PERSON W/GUN', 'PERSON W/KNIFE')
        medium = ('PURSE SNATCH', 'INDECENT EXPOSURE', 'FIGHT W/WEAPONS',
                  'FIGHT W/ WEAPONS', 'BREAKING IN', 'BURGLARY')
        if any(value in description for value in high):
            return 3
        if any(value in description for value in medium):
            return 2
        return 1
    description = incident.get('service_name', incident.get('Category', '')).upper()
    if 'ENCAMPMENT' in description:
        return 1
    if any(value in description for value in ('AGGRESSIVE', 'THREATENING', 'OBSTRUCTION',
                                             'HAZARD', 'DEBRIS', 'POTHOLE', 'SIDEWALK')):
        return 3
    if any(value in description for value in ('MAINTENANCE', 'REPAIR', 'CLEANUP')):
        return 2
    return 1


def incident_coordinates(incident, incident_type):
    fields = ('intersection_point', 'point') if incident_type == 'crime' else ('point_geom', 'point')
    for field in fields:
        point = incident.get(field)
        if isinstance(point, dict) and len(point.get('coordinates', [])) == 2:
            lng, lat = point['coordinates']
            break
    else:
        lat = incident.get('latitude', incident.get('lat', incident.get('Latitude')))
        lng = incident.get('longitude', incident.get('long', incident.get('Longitude')))
    try:
        lat, lng = float(lat), float(lng)
        if math.isfinite(lat) and math.isfinite(lng) and -90 <= lat <= 90 and -180 <= lng <= 180:
            return lat, lng
    except (TypeError, ValueError):
        pass
    return None


def min_distance_to_path(incident_coords, path):
    """Distance to line segments in km using a local projection appropriate for SF.

    Unlike vertex-only distance, a long segment cannot miss a nearby incident.
    """
    if len(path) < 2:
        return float('inf')
    lat, lng = incident_coords
    scale_x = 6371 * math.cos(math.radians(lat)) * math.pi / 180
    scale_y = 6371 * math.pi / 180
    points = [((p[1] - lng) * scale_x, (p[0] - lat) * scale_y) for p in path]
    distance = float('inf')
    for (ax, ay), (bx, by) in zip(points, points[1:]):
        dx, dy = bx - ax, by - ay
        length_squared = dx * dx + dy * dy
        fraction = max(0, min(1, -(ax * dx + ay * dy) / length_squared)) if length_squared else 0
        distance = min(distance, math.hypot(ax + fraction * dx, ay + fraction * dy))
    return distance


def calculate_risk_score(path, incidents, incident_type, current_time=None):
    now = parse_incident_time(current_time or datetime.now(timezone.utc))
    total_risk = 0.0
    for incident in incidents:
        coords = incident_coordinates(incident, incident_type)
        if coords is None:
            continue
        description = incident.get('call_type_original_desc', '') if incident_type == 'crime' else incident.get('service_name', '')
        encampment = 'ENCAMPMENT' in description.upper()
        status = incident.get('status_description', incident.get('status', '')).upper()
        if encampment and status == 'CLOSED':
            continue
        timestamp = incident.get('entry_datetime') if incident_type == 'crime' else incident.get('requested_datetime', incident.get('timestamp'))
        try:
            age_hours = max(0, (now - parse_incident_time(timestamp)).total_seconds() / 3600)
        except (TypeError, ValueError, AttributeError):
            # Unknown age retains its full weight rather than silently lowering risk.
            age_hours = 0
        weight = assign_risk(incident, incident_type)
        decay = 72 if weight == 3 else 24
        magnitude = weight if encampment else max(0, weight * (1 - age_hours / decay))
        distance = min_distance_to_path(coords, path)
        total_risk += magnitude ** 2 * math.exp(-(distance ** 2) / 0.02)
    return total_risk


def find_lowest_risk_paths(polypaths, area_bounds=None, crime_api_key=None, api_311_key=None):
    if not polypaths:
        return []
    if area_bounds is None:
        points = [point for path in polypaths for point in path]
        if not points:
            raise ValueError('Paths must contain coordinates')
        area_bounds = {'north': max(p[0] for p in points) + 0.01,
                       'south': min(p[0] for p in points) - 0.01,
                       'east': max(p[1] for p in points) + 0.013,
                       'west': min(p[1] for p in points) - 0.013}
    now = datetime.now(timezone.utc)
    crimes = fetch_crime_data(area_bounds, crime_api_key, now)
    hazards = fetch_311_data(area_bounds, api_311_key)
    return sorted(polypaths, key=lambda path: calculate_risk_score(path, crimes, 'crime', now)
                  + calculate_risk_score(path, hazards, '311', now))[:3]
