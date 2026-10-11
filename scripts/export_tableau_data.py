#!/usr/bin/env python3
"""Prepare Tableau-compatible dispatch snapshots, with explicit legacy police-incident export support."""
import argparse
import csv
import json
import math
import hashlib
import requests
from pathlib import Path

FIELDS = ['RecordKey', 'ExternalId', 'Category', 'Neighborhood', 'District', 'EventDate',
          'LocalTimestamp', 'Hour', 'Weekday', 'WeekdayNumber', 'Latitude', 'Longitude',
          'RecordCount', 'SnapshotUTC']


def export_tableau(source_dir, output_dir):
    source_dir, output_dir = Path(source_dir), Path(output_dir)
    manifest = json.loads((source_dir / 'manifest.json').read_text())
    rows, seen = [], set()
    with (source_dir / 'incidents.csv').open(encoding='utf-8', newline='') as stream:
        for source in csv.DictReader(stream):
            if source['Source'] != 'Police incidents' or source['IsGeocoded'] != '1':
                continue
            latitude, longitude = float(source['Latitude']), float(source['Longitude'])
            if not (math.isfinite(latitude) and math.isfinite(longitude) and
                    -90 <= latitude <= 90 and -180 <= longitude <= 180):
                raise ValueError('Invalid coordinates in mapped police data')
            if source['RecordKey'] in seen:
                raise ValueError('Duplicate police record key')
            seen.add(source['RecordKey'])
            row = {field: source[field] for field in FIELDS if field not in ('RecordCount', 'SnapshotUTC')}
            row.update(RecordCount=1, SnapshotUTC=manifest['refreshed_at_utc'])
            rows.append(row)
    if not rows:
        raise ValueError('No mapped police incident records available')
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / 'sf-crime-incidents.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)
    metadata = {
        'refreshed_at_utc': manifest['refreshed_at_utc'], 'rows': len(rows),
        'window_days': 90, 'timezone': 'America/Los_Angeles',
        'source': manifest['source_urls']['crime'],
        'scope': 'Police incident records with usable SF coordinates; excludes missing/outside coordinates',
        'count_measure': 'SUM(RecordCount) counts source report rows; COUNTD(ExternalId) counts unique incident IDs',
        'area_filter_fields': ['Latitude', 'Longitude'],
        'refresh': 'Snapshot only. Regenerate and republish the Tableau extract after refreshing analytics exports.',
    }
    (output_dir / 'manifest.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print(f'Tableau data: {len(rows):,} mapped police records')
    return metadata


def download_snapshot(output_dir, api_origin="https://scdwndv5z4.execute-api.us-east-1.amazonaws.com/prod", summary_output=None):
    response = requests.get(api_origin.rstrip('/') + '/analytics-manifest', timeout=30)
    response.raise_for_status(); manifest = response.json()
    response = requests.get(api_origin.rstrip('/') + '/analytics.csv', timeout=30)
    response.raise_for_status(); raw = response.content
    if manifest.get('source_type') != 'police_dispatch_calls' or manifest.get('fields') != FIELDS:
        raise ValueError('The AWS dispatch export schema is invalid')
    if hashlib.sha256(raw).hexdigest() != manifest.get('csv_sha256'):
        raise ValueError('The AWS snapshot changed during download; retry without replacing the old file')
    from io import StringIO
    rows = list(csv.DictReader(StringIO(raw.decode('utf-8'))))
    if not rows or len(rows) != manifest.get('rows') or len({row['RecordKey'] for row in rows}) != len(rows):
        raise ValueError('Incomplete or duplicate dispatch export')
    summary = None
    if summary_output is not None:
        response = requests.get(api_origin.rstrip('/') + '/analytics-summary', timeout=30)
        response.raise_for_status(); summary = response.json()
        if summary.get('refreshedUTC') != manifest.get('refreshed_at_utc') or summary.get('geocodedRecords') != len(rows):
            raise ValueError('CSV and area summary came from different snapshots; retry')
    output_dir = Path(output_dir); output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / 'sf-crime-incidents.csv').write_bytes(raw)
    (output_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    if summary is not None:
        Path(summary_output).write_text(json.dumps(summary, separators=(',', ':')) + '\n')
    print(f"Dispatch snapshot: {len(rows):,} mapped records")
    return manifest


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, help='Explicit legacy police-incident export directory; default downloads the AWS dispatch snapshot')
    parser.add_argument('--output-dir', type=Path, default=root / 'public/tableau')
    parser.add_argument('--api-origin', default='https://scdwndv5z4.execute-api.us-east-1.amazonaws.com/prod')
    parser.add_argument('--summary-output', type=Path, default=root / 'public/safety-analytics.json')
    args = parser.parse_args()
    if args.source_dir:export_tableau(args.source_dir, args.output_dir)
    else:download_snapshot(args.output_dir, args.api_origin, args.summary_output)
