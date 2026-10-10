"""Shared incident snapshots: S3 payloads, DynamoDB freshness metadata.

S3 holds the potentially large datasets; DynamoDB items stay below its size limit.
Snapshots refresh on schedule and on demand. Stale data is never silently served.
"""

import gzip
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from path_risk_analysis import (fetch_crime_data, fetch_311_data,
                                incident_coordinates, IncidentDataUnavailable)

SF_BOUNDS = {'north': 37.84, 'south': 37.69, 'east': -122.337, 'west': -122.543}
SNAPSHOT_ID = 'safety-snapshot:sf:v1'


class SafetyDataStore:
    def __init__(self, table=None, s3=None, bucket=None, max_age_seconds=None):
        self.bucket = bucket or os.environ.get('S3_BUCKET_NAME')
        self.max_age = int(max_age_seconds or os.environ.get('SAFETY_CACHE_MAX_AGE_SECONDS', '300'))
        if not self.bucket or not 30 <= self.max_age <= 300:
            raise ValueError('Safety snapshot configuration is invalid')
        if table is None or s3 is None:
            import boto3
            from botocore.config import Config
            config = Config(connect_timeout=2, read_timeout=3, retries={'max_attempts': 1})
            table = table or boto3.resource('dynamodb', config=config).Table(
                os.environ.get('DYNAMODB_TABLE_NAME', 'ApiDataCache'))
            s3 = s3 or boto3.client('s3', config=config)
        self.table, self.s3 = table, s3

    def load(self, now=None, force_refresh=False):
        now = now or datetime.now(timezone.utc)
        if not force_refresh:
            try:
                item = self.table.get_item(Key={'data_id': SNAPSHOT_ID}, ConsistentRead=True).get('Item')
                if item and int(item['fresh_until']) > int(now.timestamp()):
                    response = self.s3.get_object(Bucket=self.bucket, Key=item['s3_key'])
                    raw = response['Body'].read()
                    if hashlib.sha256(raw).hexdigest() != item['sha256']:
                        raise ValueError('Snapshot checksum mismatch')
                    snapshot = json.loads(gzip.decompress(raw))
                    age = (now - datetime.fromisoformat(snapshot['fetchedAt'])).total_seconds()
                    if 0 <= age < self.max_age:
                        validate_snapshot(snapshot)
                        return snapshot
            except Exception as error:
                # A cache outage must not turn into a false zero-risk assessment.
                print(f'Safety cache read failed; refreshing live data: {type(error).__name__}')
        return self.refresh(now)

    def refresh(self, now=None):
        now = now or datetime.now(timezone.utc)
        token = os.environ.get('DATASF_API_KEY')
        with ThreadPoolExecutor(max_workers=2) as executor:
            crimes = executor.submit(fetch_crime_data, SF_BOUNDS, token, now)
            hazards = executor.submit(fetch_311_data, SF_BOUNDS, token)
            snapshot = {'crimes': crimes.result(), 'hazards': hazards.result(),
                        'fetchedAt': now.isoformat(), 'bounds': SF_BOUNDS}
        validate_snapshot(snapshot)
        raw = gzip.compress(json.dumps(snapshot, separators=(',', ':')).encode())
        digest = hashlib.sha256(raw).hexdigest()
        key = f"safety_incidents/{now.strftime('%Y/%m/%d')}/{digest}.json.gz"
        try:
            # Publish metadata only after the payload is successfully stored.
            self.s3.put_object(Bucket=self.bucket, Key=key, Body=raw,
                               ContentType='application/json', ContentEncoding='gzip',
                               ServerSideEncryption='AES256')
            self.table.put_item(Item={
                'data_id': SNAPSHOT_ID, 'record_type': 'safety_snapshot',
                's3_key': key, 'sha256': digest, 'fetched_at': now.isoformat(),
                'fresh_until': int(now.timestamp()) + self.max_age,
                'ttl': int(now.timestamp()) + 3 * 86400,
                'police_call_count': len(snapshot['crimes']),
                'open_311_count': len(snapshot['hazards']),
            })
        except Exception as error:
            raise IncidentDataUnavailable('Unable to publish the safety snapshot') from error
        print(json.dumps({'event': 'safety_snapshot_refreshed', 'policeCalls': len(snapshot['crimes']),
                          'open311Reports': len(snapshot['hazards']), 'fetchedAt': snapshot['fetchedAt']}))
        return snapshot


def validate_snapshot(snapshot):
    for field, kind in (('crimes', 'crime'), ('hazards', '311')):
        records = snapshot.get(field)
        if not isinstance(records, list) or any(not isinstance(record, dict) for record in records):
            raise IncidentDataUnavailable('Invalid safety snapshot')
        if records and not any(incident_coordinates(record, kind) is not None for record in records):
            raise IncidentDataUnavailable('Incident source has no usable coordinates')


def filter_to_bounds(records, kind, bounds):
    result = []
    for record in records:
        coords = incident_coordinates(record, kind)
        if coords is not None:
            lat, lng = coords
            if bounds['south'] <= lat <= bounds['north'] and bounds['west'] <= lng <= bounds['east']:
                result.append(record)
    return result
