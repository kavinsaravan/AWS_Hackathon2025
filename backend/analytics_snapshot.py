"""Daily SF police-dispatch exports for Tableau and the web analytics summary."""
import csv
import gzip
import hashlib
import io
import json
import math
import os
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

SF = ZoneInfo('America/Los_Angeles')
BOUNDS = {'south': 37.70, 'north': 37.83, 'west': -122.53, 'east': -122.35}
FIELDS = ['RecordKey', 'ExternalId', 'Category', 'Neighborhood', 'District', 'EventDate',
          'LocalTimestamp', 'Hour', 'Weekday', 'WeekdayNumber', 'Latitude', 'Longitude',
          'RecordCount', 'SnapshotUTC']
SNAPSHOT_ID = 'analytics-history:sf:v1'
SOURCE = 'https://data.sf.gov/resource/gnap-fj3t.json'


def fetch_history(now, get=None):
    get = get or requests.get
    local = now.astimezone(SF).replace(tzinfo=None)
    start = local - timedelta(hours=72)
    where = (f"entry_datetime >= '{start.isoformat()}' AND entry_datetime <= '{local.isoformat()}' "
             f"AND within_box(intersection_point,{BOUNDS['north']},{BOUNDS['west']},{BOUNDS['south']},{BOUNDS['east']})")
    headers = {'User-Agent': 'SafePath-Daily-Analytics/1.0'}
    if os.environ.get('DATASF_API_KEY'):headers['X-App-Token'] = os.environ['DATASF_API_KEY']
    records = []; deadline = time.monotonic() + 200
    for page in range(20):
        params = {'$where': where, '$select': 'id,cad_number,entry_datetime,call_type_original_desc,intersection_point,analysis_neighborhood,police_district',
                  '$order': 'id ASC', '$limit': 5000, '$offset': page * 5000}
        for attempt in range(3):
            if time.monotonic() >= deadline:raise RuntimeError('History export exceeded its fetch deadline')
            try:
                response = get(SOURCE, params=params, headers=headers, timeout=(3, 15))
                response.raise_for_status()
                batch = response.json()
                if not isinstance(batch, list) or any(not isinstance(r, dict) for r in batch):
                    raise ValueError('Invalid DataSF history response')
                break
            except (requests.Timeout, requests.ConnectionError):
                if attempt == 2:raise
                time.sleep(attempt + 1)
            except requests.HTTPError as error:
                if error.response is None or error.response.status_code not in (429, 500, 502, 503, 504) or attempt == 2:raise
                time.sleep(attempt + 1)
        records.extend(batch)
        if len(batch) < 5000:return records
    raise RuntimeError('History export hit the pagination limit; refusing a truncated snapshot')


def build_export(records, now):
    rows = []; seen = set(); skipped = 0
    refreshed = now.astimezone(timezone.utc).isoformat()
    for raw in records:
        identity = raw.get('id')
        if identity is None:raise ValueError('Police record lacks its source row ID')
        key = 'calls:' + str(identity)
        if key in seen:raise ValueError('Duplicate source row during paginated history export')
        seen.add(key)
        try:
            lng, lat = map(float, raw['intersection_point']['coordinates'])
            if not (math.isfinite(lat) and math.isfinite(lng) and BOUNDS['south'] <= lat <= BOUNDS['north']
                    and BOUNDS['west'] <= lng <= BOUNDS['east']):raise ValueError('Invalid point')
            event = datetime.fromisoformat(str(raw['entry_datetime']).replace('Z', '+00:00'))
            event = event.replace(tzinfo=SF) if event.tzinfo is None else event.astimezone(SF)
            external = raw.get('cad_number')
            rows.append(dict(zip(FIELDS, [key, str(external) if external is not None else str(identity),
                raw.get('call_type_original_desc') or 'Unknown', raw.get('analysis_neighborhood') or 'Unknown',
                raw.get('police_district') or 'Unknown', event.date().isoformat(), event.strftime('%Y-%m-%d %H:%M:%S'),
                event.hour, event.strftime('%A'), event.weekday()+1, lat, lng, 1, refreshed])))
        except (ValueError, TypeError, KeyError):skipped += 1
    if not rows:raise ValueError('No usable police records; retaining the previous snapshot')
    stream = io.StringIO(newline=''); writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator='\n')
    writer.writeheader();writer.writerows(rows)
    cells = {}
    for row in rows:
        key = math.floor(row['Latitude']/.005), math.floor(row['Longitude']/.005)
        cell = cells.setdefault(key, {'count': 0, 'categories': Counter(), 'days': Counter()})
        cell['count'] += 1;cell['categories'][row['Category']] += 1;cell['days'][row['EventDate']] += 1
    day = now.astimezone(SF).date() - timedelta(days=3); dates = []
    while day <= now.astimezone(SF).date():dates.append(day.isoformat());day += timedelta(days=1)
    summary = {'version': 1, 'refreshedUTC': refreshed, 'windowDays': 3, 'geocodedRecords': len(rows),
        'dates': dates, 'cells': [{'south': round(i*.005, 6), 'north': round((i+1)*.005, 6),
            'west': round(j*.005, 6), 'east': round((j+1)*.005, 6), 'count': cell['count'],
            'categories': sorted(cell['categories'].items()), 'days': sorted(cell['days'].items())}
            for (i,j),cell in sorted(cells.items())]}
    manifest = {'version': 1, 'refreshed_at_utc': refreshed, 'rows': len(rows), 'window_days': 3, 'window_hours': 72, 'source_type': 'police_dispatch_calls',
        'skipped_rows': skipped, 'timezone': 'America/Los_Angeles', 'source': SOURCE,
        'fields': FIELDS, 'scope': 'Mapped SF police dispatch calls; calls for service are not confirmed crimes or safety probabilities'}
    csv_bytes = stream.getvalue().encode()
    manifest['csv_sha256'] = hashlib.sha256(csv_bytes).hexdigest()
    return csv_bytes, summary, manifest


class AnalyticsStore:
    def __init__(self, table=None, s3=None, bucket=None):
        self.bucket = bucket or os.environ['S3_BUCKET_NAME']
        if table is None or s3 is None:
            import boto3
            from botocore.config import Config
            config = Config(connect_timeout=3, read_timeout=10, retries={'max_attempts': 2})
            table = table or boto3.resource('dynamodb', config=config).Table(os.environ['DYNAMODB_TABLE_NAME'])
            s3 = s3 or boto3.client('s3', config=config)
        self.table, self.s3 = table, s3

    def publish(self, csv_bytes, summary, manifest):
        files = {'csv': gzip.compress(csv_bytes, mtime=0),
                 'summary': gzip.compress(json.dumps(summary, separators=(',', ':')).encode(), mtime=0),
                 'manifest': json.dumps(manifest, separators=(',', ':')).encode()}
        digest = hashlib.sha256(files['csv']).hexdigest()
        item = {'data_id': SNAPSHOT_ID, 'record_type': 'analytics_history', 'refreshed_at': manifest['refreshed_at_utc'], 'rows': manifest['rows']}
        for kind, payload in files.items():
            key = f'analytics-history/{digest}/{kind}'
            self.s3.put_object(Bucket=self.bucket, Key=key, Body=payload, ServerSideEncryption='AES256',
                              ContentType='application/octet-stream' if kind != 'manifest' else 'application/json')
            item[kind+'_key'] = key;item[kind+'_sha256'] = hashlib.sha256(payload).hexdigest()
        # Change the pointer only after every versioned object is safely stored.
        self.table.put_item(Item=item)
        return manifest

    def read(self, kind, now=None):
        now = now or datetime.now(timezone.utc)
        item = self.table.get_item(Key={'data_id': SNAPSHOT_ID}, ConsistentRead=True).get('Item')
        if not item:raise RuntimeError('The daily analytics snapshot is not available yet')
        age = (now - datetime.fromisoformat(item['refreshed_at'])).total_seconds()
        if not 0 <= age <= 72*3600:raise RuntimeError('The analytics snapshot is too old')
        key = item[kind+'_key']
        if not key.startswith('analytics-history/'):raise RuntimeError('Invalid analytics object key')
        raw = self.s3.get_object(Bucket=self.bucket, Key=key)['Body'].read()
        if hashlib.sha256(raw).hexdigest() != item[kind+'_sha256']:raise RuntimeError('Analytics checksum mismatch')
        return raw, item['refreshed_at']
