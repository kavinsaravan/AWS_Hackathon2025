"""Reproducible SF location datasets with measured features and heuristic labels.

These are sampled locations, not evaluated walking routes or ground-truth safety.
"""
import argparse
import csv
import json
import math
import random
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

BOUNDS = {'north': 37.812, 'south': 37.708, 'west': -122.520, 'east': -122.357}
SF_TIMEZONE = ZoneInfo('America/Los_Angeles')
FIELDS = ['sample_id', 'latitude', 'longitude', 'crime_count', 'violent_crimes',
          'property_crimes', 'drug_crimes', 'priority_calls', 'hazard_count',
          'encampments', 'needles', 'lighting_issues', 'blocked_sidewalks',
          'hour', 'is_night', 'risk_score', 'label_threshold', 'is_unsafe', 'assessed_at']
WEIGHTS = {'violent_crimes': 30, 'property_crimes': 15, 'drug_crimes': 20,
           'priority_calls': 25, 'encampments': 20, 'needles': 15,
           'lighting_issues': 10, 'blocked_sidewalks': 10}


class DatasetSourceError(RuntimeError):
    pass


def coordinates(record):
    for field in ('intersection_point', 'point_geom', 'point'):
        point = record.get(field)
        if isinstance(point, dict):
            values = point.get('coordinates')
            if isinstance(values, (list, tuple)) and len(values) == 2:
                lng, lat = values
                break
            if 'latitude' in point and 'longitude' in point:
                lat, lng = point['latitude'], point['longitude']
                break
    else:
        lat = record.get('latitude', record.get('lat'))
        lng = record.get('longitude', record.get('long'))
    try:
        lat, lng = float(lat), float(lng)
        if math.isfinite(lat) and math.isfinite(lng) and -90 <= lat <= 90 and -180 <= lng <= 180:
            return lat, lng
    except (TypeError, ValueError):
        pass
    return None


def distance_meters(a, b):
    lat1, lng1, lat2, lng2 = map(math.radians, (*a, *b))
    value = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lng2-lng1)/2)**2
    return 6371000 * 2 * math.asin(math.sqrt(min(1, value)))


class SpatialIndex:
    def __init__(self, records):
        self.cells = defaultdict(list)
        self.valid_count = 0
        for record in records:
            point = coordinates(record)
            if point is not None:
                self.cells[self.cell(*point)].append((point, record))
                self.valid_count += 1
        if records and not self.valid_count:
            raise DatasetSourceError('A source has no usable coordinates')

    @staticmethod
    def cell(lat, lng):
        return math.floor(lat / .005), math.floor(lng / .005)

    def nearby(self, lat, lng, radius):
        lat_delta = radius / 111000
        lng_delta = lat_delta / math.cos(math.radians(lat))
        low = self.cell(lat-lat_delta, lng-lng_delta)
        high = self.cell(lat+lat_delta, lng+lng_delta)
        return [record for i in range(low[0], high[0]+1) for j in range(low[1], high[1]+1)
                for point, record in self.cells.get((i, j), [])
                if distance_meters((lat, lng), point) <= radius]


def fetch_records(url, params, max_records=100000):
    records = []
    for offset in range(0, max_records, 5000):
        try:
            response = requests.get(url, params={**params, '$limit': 5000, '$offset': offset}, timeout=(5, 30))
            response.raise_for_status()
            page = response.json()
            if not isinstance(page, list) or any(not isinstance(item, dict) for item in page):
                raise ValueError('Invalid API response')
        except (requests.RequestException, ValueError) as error:
            raise DatasetSourceError('A required DataSF source could not be read') from error
        records.extend(page)
        if len(page) < 5000:
            return records
    raise DatasetSourceError('Source exceeded the pagination limit; dataset was not generated')


class SafetyDatasetGenerator:
    def __init__(self, seed=42, now=None):
        self.seed = seed
        self.now = now or datetime.now(timezone.utc)
        if self.now.tzinfo is None:
            self.now = self.now.replace(tzinfo=SF_TIMEZONE)
        self.now = self.now.astimezone(timezone.utc)
        self.sf_bounds = BOUNDS.copy()
        self.sample_size = 385
        self.crime_data, self.calls_data, self.hazards_data = [], [], []
        self.source_counts = {}
        self.rows = []
        self._loaded = False

    def fetch_all_data(self):
        local = self.now.astimezone(SF_TIMEZONE).replace(tzinfo=None)
        spatial = lambda field: f"within_box({field}, {BOUNDS['north']}, {BOUNDS['west']}, {BOUNDS['south']}, {BOUNDS['east']})"
        jobs = {
            'crime_data': ('wg3w-h783', {'$where': f"incident_datetime >= '{(local-timedelta(days=90)).isoformat()}' AND incident_datetime <= '{local.isoformat()}' AND {spatial('point')}",
                                        '$select': 'incident_id,incident_datetime,incident_category,latitude,longitude', '$order': 'incident_id ASC'}),
            'calls_data': ('gnap-fj3t', {'$where': f"entry_datetime >= '{(local-timedelta(hours=72)).isoformat()}' AND entry_datetime <= '{local.isoformat()}' AND {spatial('intersection_point')}",
                                       '$select': 'cad_number,entry_datetime,priority_original,priority_final,intersection_point', '$order': 'cad_number ASC'}),
            'hazards_data': ('vw6y-z8j6', {'$where': f"status_description = 'Open' AND requested_datetime >= '{(local-timedelta(days=30)).isoformat()}' AND requested_datetime <= '{local.isoformat()}' AND {spatial('point_geom')}",
                                         '$select': 'service_request_id,requested_datetime,status_description,service_name,service_subtype,lat,long,point_geom', '$order': 'service_request_id ASC'}),
        }
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {name: executor.submit(fetch_records, 'https://data.sfgov.org/resource/'+dataset+'.json', params)
                       for name, (dataset, params) in jobs.items()}
            values = {name: future.result() for name, future in futures.items()}
        for name, records in values.items():
            setattr(self, name, records)
        self.source_counts = {name: len(records) for name, records in values.items()}
        self.build_indexes()

    def build_indexes(self):
        self.crime_index = SpatialIndex(self.crime_data)
        self.call_index = SpatialIndex(self.calls_data)
        self.hazard_index = SpatialIndex(self.hazards_data)
        self._loaded = True

    @staticmethod
    def is_land(lat, lng):
        # Approximate historical sampling mask, not an actual street/land polygon.
        return not (lng < -122.510 or (lat < 37.795 and lng > -122.390)
                    or (lat < 37.750 and lng > -122.380))

    def sample_points(self, count):
        if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            raise ValueError('Sample count must be a positive integer')
        rng = random.Random(self.seed)
        points = []
        for _ in range(count * 20):
            lat = rng.uniform(BOUNDS['south'], BOUNDS['north'])
            lng = rng.uniform(BOUNDS['west'], BOUNDS['east'])
            if self.is_land(lat, lng):
                points.append((lat, lng))
                if len(points) == count:
                    return points
        raise RuntimeError('Unable to obtain the requested number of land samples')

    def location_features(self, lat, lng):
        crimes = self.crime_index.nearby(lat, lng, 200)
        calls = self.call_index.nearby(lat, lng, 100)
        hazards = self.hazard_index.nearby(lat, lng, 100)
        categories = [record.get('incident_category', '') for record in crimes]
        services = [' '.join(str(record.get(field, '')) for field in ('service_name', 'service_subtype')).lower()
                    for record in hazards]
        hour = self.now.astimezone(SF_TIMEZONE).hour
        features = {'latitude': lat, 'longitude': lng, 'crime_count': len(crimes),
                    'violent_crimes': sum(c in ('Assault','Robbery','Homicide','Rape','Sex Offense','Weapons Offense','Human Trafficking') for c in categories),
                    'property_crimes': sum(c in ('Burglary','Larceny Theft','Stolen Property','Vandalism','Motor Vehicle Theft','Arson') for c in categories),
                    'drug_crimes': sum(c in ('Drug Offense','Drug Violation') for c in categories),
                    'priority_calls': sum(str(record.get('priority_final', record.get('priority_original', ''))).upper() in ('1','2','HIGH','PRIORITY 1') for record in calls),
                    'hazard_count': len(hazards), 'encampments': sum('encampment' in s or 'homeless' in s for s in services),
                    'needles': sum('needle' in s or 'syringe' in s for s in services),
                    'lighting_issues': sum('light' in s for s in services),
                    'blocked_sidewalks': sum('blocked' in s for s in services),
                    'hour': hour, 'is_night': int(hour < 6 or hour > 22),
                    'assessed_at': self.now.isoformat(), 'label_threshold': 50}
        features['risk_score'] = sum(features[key] * weight for key, weight in WEIGHTS.items()) + 15 * features['is_night']
        features['is_unsafe'] = int(features['risk_score'] > features['label_threshold'])
        return features

    def generate_dataset(self, num_samples=10000, fetch=True):
        points = self.sample_points(num_samples)
        if fetch:
            self.fetch_all_data()
        else:
            if not self._loaded:
                raise DatasetSourceError('Load all required sources before generating a dataset')
            self.build_indexes()
        self.rows = [{'sample_id': i, **self.location_features(lat, lng)}
                     for i, (lat, lng) in enumerate(points, 1)]
        return self.rows

    def save_dataset(self, rows, filename='sf_safety_dataset.csv', labels_only=False):
        return save_rows(rows, filename, seed=self.seed, now=self.now,
                         source_counts=self.source_counts, labels_only=labels_only)


def save_rows(rows, filename, seed=None, now=None, source_counts=None, labels_only=False):
    if not rows or any(not isinstance(row, dict) or any(field not in row for field in FIELDS) for row in rows):
        raise ValueError('Dataset must contain coordinates, measured features, and labels')
    path = Path(filename)
    if path.parent == Path('.'):
        path = Path('data') / path
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as stream:
        if labels_only:
            csv.writer(stream).writerows([row['is_unsafe']] for row in rows)
        else:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
    metadata = {'schema_version': 2, 'sample_count': len(rows), 'seed': seed,
                'assessed_at': now.isoformat() if now else rows[0]['assessed_at'],
                'source_counts': source_counts or {}, 'label_kind': 'heuristic_proxy',
                'label_rule': 'weighted incident counts + 15 if night; unsafe if risk_score > 50',
                'weights': WEIGHTS, 'crime_window_days': 90, 'dispatch_window_hours': 72,
                'crime_radius_m': 200, 'dispatch_radius_m': 100, 'hazard_radius_m': 100,
                'hazards': 'open 311 reports requested within the past 30 days', 'labels_only': labels_only,
                'sampling': 'seeded random locations with approximate land exclusion',
                'training_exclude': ['sample_id','risk_score','label_threshold','is_unsafe','assessed_at']}
    path.with_suffix('.metadata.json').write_text(json.dumps(metadata, indent=2))
    return str(path)


def main(filename='sf_safety_dataset.csv', default_samples=10000):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples', type=int, default=default_samples)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--output', default=filename)
    parser.add_argument('--labels-only', action='store_true', help='Explicit legacy export; discards training features')
    args = parser.parse_args()
    generator = SafetyDatasetGenerator(seed=args.seed)
    rows = generator.generate_dataset(args.samples)
    result = generator.save_dataset(rows, args.output, args.labels_only)
    print(f'Saved {len(rows)} sampled locations with measured features to {result}')


if __name__ == '__main__':
    main()
