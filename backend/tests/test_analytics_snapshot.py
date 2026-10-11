import base64
import csv
import gzip
import io
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import analytics_snapshot as analytics
import lambda_daily_analytics as handler

NOW = datetime(2026, 10, 10, 20, tzinfo=timezone.utc)
ROW = {'id': 'one', 'cad_number': 'call-one', 'entry_datetime': '2026-10-09T15:00:00',
       'call_type_original_desc': 'ASSAULT', 'intersection_point': {'coordinates': [-122.42,37.77]}, 'analysis_neighborhood': 'Mission'}

class Store:
    def __init__(self):self.objects = {};self.item = None;self.fail_key = None
    def put_object(self, **args):
        if args['Key'].endswith(self.fail_key or '__never__'):raise RuntimeError('Storage failure')
        self.objects[args['Key']] = args['Body']
    def get_object(self, **args):return {'Body': io.BytesIO(self.objects[args['Key']])}
    def put_item(self, Item):self.item = dict(Item)
    def get_item(self, **args):return {'Item': self.item} if self.item else {}

class AnalyticsTests(unittest.TestCase):
    def test_export_retains_ids_local_dates_and_matches_summary_totals(self):
        raw, summary, manifest = analytics.build_export([ROW, {**ROW, 'id': 'two', 'call_type_original_desc': 'Theft', 'entry_datetime':'2026-10-10T02:00:00Z'}], NOW)
        rows=list(csv.DictReader(io.StringIO(raw.decode())))
        self.assertEqual(rows[1]['EventDate'],'2026-10-09')
        self.assertEqual(rows[1]['Hour'],'19');self.assertEqual(rows[0]['RecordKey'],'calls:one')
        self.assertEqual(manifest['rows'],2);self.assertEqual(summary['geocodedRecords'],2)
        self.assertEqual(sum(c['count'] for c in summary['cells']),2)
        self.assertEqual(len(summary['dates']),4)

    def test_duplicate_empty_and_unusable_records_do_not_publish_false_zero(self):
        for rows in [[],[ROW,ROW],[{**ROW,'intersection_point':{'coordinates':[-122.42,'nan']}}],[{**ROW,'id':None}]]:
            with self.subTest(rows=rows),self.assertRaises(ValueError):analytics.build_export(rows,NOW)

    def test_bad_coordinates_are_omitted_with_quality_count(self):
        raw, summary, manifest=analytics.build_export([ROW,{**ROW,'id':'two','intersection_point':{'coordinates':[-110,37.77]}}],NOW)
        self.assertEqual(manifest['skipped_rows'],1);self.assertEqual(summary['geocodedRecords'],1)

    def test_pagination_uses_bounded_window_and_stable_order(self):
        response=Mock();response.json.return_value=[ROW];get=Mock(return_value=response)
        self.assertEqual(analytics.fetch_history(NOW,get),[ROW])
        args=get.call_args.kwargs
        self.assertIn('entry_datetime <=',args['params']['$where']);self.assertEqual(args['params']['$order'],'id ASC')
        self.assertEqual(args['params']['$limit'],5000)

    def test_truncation_and_invalid_source_responses_raise(self):
        response=Mock();response.json.return_value=[ROW]*5000
        with self.assertRaises(RuntimeError):analytics.fetch_history(NOW,Mock(return_value=response))
        response.json.return_value={}
        with self.assertRaises(ValueError):analytics.fetch_history(NOW,Mock(return_value=response))

    def test_failed_publish_preserves_old_pointer(self):
        storage=Store();store=analytics.AnalyticsStore(storage,storage,'bucket')
        raw,summary,manifest=analytics.build_export([ROW],NOW)
        store.publish(raw,summary,manifest);old=storage.item.copy()
        storage.fail_key='summary'
        fresh=analytics.build_export([ROW],NOW+timedelta(hours=1))
        with self.assertRaises(RuntimeError):store.publish(*fresh)
        self.assertEqual(storage.item,old)

    def test_checksum_and_staleness_are_enforced(self):
        storage=Store();store=analytics.AnalyticsStore(storage,storage,'bucket')
        raw,summary,manifest=analytics.build_export([ROW],NOW);store.publish(raw,summary,manifest)
        csv_bytes,_=store.read('csv',NOW+timedelta(hours=24));self.assertEqual(gzip.decompress(csv_bytes),raw)
        with self.assertRaises(RuntimeError):store.read('csv',NOW+timedelta(hours=73))
        storage.objects[storage.item['csv_key']]=b'corrupt'
        with self.assertRaises(RuntimeError):store.read('csv',NOW)

    def test_api_serves_compressed_csv_and_fails_cleanly(self):
        with patch.object(handler,'AnalyticsStore') as cls:
            cls.return_value.read.return_value=(gzip.compress(b'a,b\n1,2\n'),NOW.isoformat())
            result=handler.lambda_handler({'routeKey':'GET /analytics.csv','requestContext':{'http':{'method':'GET'}}},None)
            self.assertEqual(result['statusCode'],200);self.assertTrue(result['isBase64Encoded'])
            self.assertEqual(gzip.decompress(base64.b64decode(result['body'])),b'a,b\n1,2\n')
            cls.return_value.read.side_effect=RuntimeError('Unavailable')
            self.assertEqual(handler.lambda_handler({'routeKey':'GET /analytics-summary','requestContext':{'http':{'method':'GET'}}},None)['statusCode'],503)
        self.assertEqual(handler.lambda_handler({'routeKey':'POST /analytics.csv','requestContext':{'http':{'method':'POST'}}},None)['statusCode'],404)

if __name__=='__main__':unittest.main()
