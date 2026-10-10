#!/usr/bin/env python3
"""Prepare a single, geocoded police-incident table for Tableau Public web authoring."""
import argparse
import csv
import json
import math
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


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, default=root / 'public/analytics-data')
    parser.add_argument('--output-dir', type=Path, default=root / 'public/tableau')
    args = parser.parse_args()
    export_tableau(args.source_dir, args.output_dir)
