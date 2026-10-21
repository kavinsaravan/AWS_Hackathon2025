import copy
import csv
import hashlib
import io
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
from analytics_snapshot import build_export
from export_tableau_data import download_snapshot, validate_snapshot

NOW = datetime(2026, 10, 20, 9, tzinfo=timezone.utc)


class DispatchDownloadTests(unittest.TestCase):
    def setUp(self):
        self.raw, self.summary, self.manifest = build_export([
            {'id': '0001', 'cad_number': '0002', 'entry_datetime': '2026-10-20T01:00:00',
             'intersection_point': {'coordinates': [-122.42, 37.77]},
             'call_type_original_desc': 'NOISE NUISANCE'}], NOW)
        self.summary = json.loads(json.dumps(self.summary))

    def test_valid_complete_snapshot(self):
        rows = validate_snapshot(self.raw, self.manifest, self.summary, now=NOW)
        self.assertEqual(rows[0]['ExternalId'], '0002')

    def test_stale_and_future_snapshots_rejected(self):
        for now in [NOW + timedelta(hours=49), NOW - timedelta(seconds=1)]:
            with self.subTest(now=now), self.assertRaises(ValueError):
                validate_snapshot(self.raw, self.manifest, self.summary, now=now)

    def test_coordinate_header_identity_time_and_count_validation(self):
        for field, value in [('Latitude', 'nan'), ('Longitude', '-120'), ('RecordKey', ''),
                             ('ExternalId', ''), ('RecordCount', '2'), ('SnapshotUTC', 'wrong'),
                             ('EventDate', '2026-10-18'), ('Hour', '9'),
                             ('LocalTimestamp', '2026-10-15 01:00:00')]:
            with self.subTest(field=field):
                reader = csv.DictReader(io.StringIO(self.raw.decode()))
                fields = reader.fieldnames
                row = next(reader); row[field] = value
                output = io.StringIO(); writer = csv.DictWriter(output, fieldnames=fields)
                writer.writeheader(); writer.writerow(row); raw = output.getvalue().encode()
                manifest = dict(self.manifest, csv_sha256=hashlib.sha256(raw).hexdigest())
                with self.assertRaises(ValueError): validate_snapshot(raw, manifest, now=NOW)
        with self.assertRaises(ValueError):
            validate_snapshot(self.raw.replace(b'RecordKey', b'WrongName'), self.manifest, now=NOW)

    def test_checksum_window_duplicates_and_summary_mismatch(self):
        for field, value in [('csv_sha256', 'bad'), ('window_hours', 168), ('rows', 2)]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_snapshot(self.raw, dict(self.manifest, **{field: value}), now=NOW)
        summary = copy.deepcopy(self.summary)
        summary['cells'][0]['count'] += 1
        with self.assertRaises(ValueError): validate_snapshot(self.raw, self.manifest, summary, now=NOW)
        raw = self.raw + self.raw.splitlines(keepends=True)[1]
        manifest = dict(self.manifest, rows=2, csv_sha256=hashlib.sha256(raw).hexdigest())
        with self.assertRaises(ValueError): validate_snapshot(raw, manifest, now=NOW)

    def test_failed_validation_preserves_all_previous_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ['sf-crime-incidents.csv', 'manifest.json', 'summary.json']:
                (root / name).write_text('previous published data')
            responses = [Mock(json=lambda: self.manifest), Mock(content=self.raw),
                         Mock(json=lambda: dict(self.summary, geocodedRecords=999))]
            with patch('export_tableau_data.requests.get', side_effect=responses):
                with self.assertRaises(ValueError): download_snapshot(root, summary_output=root / 'summary.json')
            self.assertTrue(all(p.read_text() == 'previous published data' for p in root.iterdir()))

    def test_success_downloads_the_verified_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            responses = [Mock(json=lambda: self.manifest), Mock(content=self.raw), Mock(json=lambda: self.summary)]
            with patch('export_tableau_data.requests.get', side_effect=responses), \
                 patch('export_tableau_data.datetime') as clock:
                clock.fromisoformat = datetime.fromisoformat
                clock.strptime = datetime.strptime
                clock.now.return_value = NOW
                download_snapshot(root, summary_output=root / 'summary.json')
            self.assertEqual((root / 'sf-crime-incidents.csv').read_bytes(), self.raw)
            self.assertEqual(json.loads((root / 'summary.json').read_text()), self.summary)


if __name__ == '__main__': unittest.main()
