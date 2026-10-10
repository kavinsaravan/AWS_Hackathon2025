import gzip
import hashlib
import io
import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from safety_data_store import SafetyDataStore, SNAPSHOT_ID, filter_to_bounds
from path_risk_analysis import IncidentDataUnavailable
import route_scoring

NOW = datetime(2026, 10, 10, 2, tzinfo=timezone.utc)
CRIME = {'intersection_point': {'coordinates': [-122.41, 37.77]},
         'call_type_original_desc': 'ROBBERY', 'entry_datetime': NOW.isoformat()}
SNAPSHOT = {'crimes': [CRIME], 'hazards': [], 'fetchedAt': NOW.isoformat()}


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.table, self.s3 = Mock(), Mock()
        self.store = SafetyDataStore(self.table, self.s3, bucket='test-bucket', max_age_seconds=300)
        self.raw = gzip.compress(json.dumps(SNAPSHOT).encode())
        self.item = {'data_id': SNAPSHOT_ID, 'fresh_until': int(NOW.timestamp()) + 300,
                     's3_key': 'snapshot.json.gz', 'sha256': hashlib.sha256(self.raw).hexdigest()}
        self.table.get_item.return_value = {'Item': self.item}
        self.s3.get_object.return_value = {'Body': io.BytesIO(self.raw)}

    def test_fresh_snapshot_avoids_external_fetch(self):
        with patch('safety_data_store.fetch_crime_data') as fetch:
            result = self.store.load(NOW + timedelta(seconds=299))
        fetch.assert_not_called()
        self.assertEqual(result['crimes'], [CRIME])

    def test_expired_snapshot_refreshes_even_before_ttl_deletion(self):
        with patch.object(self.store, 'refresh', return_value=SNAPSHOT) as refresh:
            self.store.load(NOW + timedelta(seconds=301))
        refresh.assert_called_once()
        self.s3.get_object.assert_not_called()

    def test_payload_age_checked_independently_of_metadata(self):
        self.item['fresh_until'] += 1000
        with patch.object(self.store, 'refresh', return_value=SNAPSHOT) as refresh:
            self.store.load(NOW + timedelta(seconds=301))
        refresh.assert_called_once()

    def test_corrupt_payload_refreshes(self):
        self.item['sha256'] = 'invalid'
        with patch.object(self.store, 'refresh', return_value=SNAPSHOT) as refresh:
            self.store.load(NOW)
        refresh.assert_called_once()

    @patch('safety_data_store.fetch_311_data', return_value=[])
    @patch('safety_data_store.fetch_crime_data', return_value=[CRIME])
    def test_publish_s3_before_dynamodb_with_small_metadata(self, crime, hazard):
        operations = Mock()
        operations.attach_mock(self.s3.put_object, 's3_write')
        operations.attach_mock(self.table.put_item, 'metadata_write')
        self.store.refresh(NOW)
        self.assertEqual([call[0] for call in operations.mock_calls], ['s3_write', 'metadata_write'])
        item = self.table.put_item.call_args.kwargs['Item']
        self.assertNotIn('data', item)
        self.assertNotIn('crimes', item)
        self.assertEqual(item['fresh_until'], int(NOW.timestamp()) + 300)
        self.assertEqual(item['ttl'], int(NOW.timestamp()) + 3 * 86400)
        self.assertEqual(self.s3.put_object.call_args.kwargs['ServerSideEncryption'], 'AES256')

    @patch('safety_data_store.fetch_311_data', return_value=[])
    @patch('safety_data_store.fetch_crime_data', return_value=[CRIME])
    def test_failed_payload_publish_never_updates_metadata(self, crime, hazard):
        self.s3.put_object.side_effect = RuntimeError('S3 unavailable')
        with self.assertRaises(IncidentDataUnavailable):
            self.store.refresh(NOW)
        self.table.put_item.assert_not_called()

    def test_source_outage_never_falls_back_to_expired_snapshot(self):
        self.item['fresh_until'] = 0
        with patch('safety_data_store.fetch_crime_data', side_effect=IncidentDataUnavailable('offline')):
            with patch('safety_data_store.fetch_311_data', return_value=[]):
                with self.assertRaises(IncidentDataUnavailable):
                    self.store.load(NOW)

    def test_force_refresh_bypasses_cache(self):
        with patch.object(self.store, 'refresh', return_value=SNAPSHOT) as refresh:
            self.store.load(NOW, force_refresh=True)
        refresh.assert_called_once()
        self.table.get_item.assert_not_called()

    def test_route_bounds_filter(self):
        bounds = {'north': 37.8, 'south': 37.7, 'east': -122.4, 'west': -122.5}
        outside = {**CRIME, 'intersection_point': {'coordinates': [-122.6, 37.77]}}
        self.assertEqual(filter_to_bounds([CRIME, outside, {}], 'crime', bounds), [CRIME])

    def test_aws_route_scoring_uses_snapshot_and_current_time(self):
        route = {'routes': [{'id': 1, 'coordinates': [{'lat': 37.77, 'lng': -122.42},
                                                     {'lat': 37.77, 'lng': -122.40}]}]}
        with patch.dict(os.environ, {'DYNAMODB_TABLE_NAME': 'test-table', 'S3_BUCKET_NAME': 'test-bucket'}):
            with patch('safety_data_store.SafetyDataStore') as store, patch('route_scoring.datetime') as clock:
                store.return_value.load.return_value = SNAPSHOT
                clock.now.return_value = NOW + timedelta(seconds=120)
                result = route_scoring.score_routes(route)
        self.assertEqual(result['dataFetchedAt'], NOW.isoformat())
        self.assertEqual(result['dataMode'], 'aws-snapshot')
        self.assertLess(result['routes'][0]['crimeRisk'], 9)
        self.assertGreater(result['routes'][0]['crimeRisk'], 8)


if __name__ == '__main__':
    unittest.main()
