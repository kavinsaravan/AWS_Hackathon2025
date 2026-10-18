import base64
import json
import math
import sys
import subprocess
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import path_risk_analysis as risk
import route_scoring

NOW = datetime(2026, 10, 10, 2, tzinfo=timezone.utc)
PATH = [(37.77, -122.42), (37.77, -122.40)]
CRIME = {'intersection_point': {'coordinates': [-122.41, 37.77]},
         'call_type_original_desc': 'ROBBERY', 'entry_datetime': NOW.isoformat()}
HAZARD = {'point_geom': {'coordinates': [-122.41, 37.77]},
          'service_name': 'Encampment', 'requested_datetime': NOW.isoformat(),
          'status_description': 'Open'}
PAYLOAD = {'routes': [{'id': 1, 'coordinates': [{'lat': lat, 'lng': lng} for lat, lng in PATH]},
                      {'id': 2, 'coordinates': [{'lat': lat + 0.01, 'lng': lng} for lat, lng in PATH]}]}


class RiskTests(unittest.TestCase):
    def test_segment_distance_and_sampling_invariance(self):
        self.assertAlmostEqual(risk.min_distance_to_path((37.77, -122.41), PATH), 0)
        dense = [PATH[0], (37.77, -122.41), PATH[1]]
        self.assertAlmostEqual(risk.calculate_risk_score(PATH, [CRIME], 'crime', NOW),
                               risk.calculate_risk_score(dense, [CRIME], 'crime', NOW))

    def test_severity_and_time_decay(self):
        self.assertAlmostEqual(risk.calculate_risk_score(PATH, [CRIME], 'crime', NOW), 9)
        self.assertAlmostEqual(risk.calculate_risk_score(PATH, [CRIME], 'crime', NOW + timedelta(hours=36)), 2.25)
        self.assertEqual(risk.calculate_risk_score(PATH, [CRIME], 'crime', NOW + timedelta(hours=72)), 0)
        low = {**CRIME, 'call_type_original_desc': 'SUSPICIOUS PERSON'}
        self.assertEqual(risk.calculate_risk_score(PATH, [low], 'crime', NOW + timedelta(hours=24)), 0)

    def test_local_sf_time_and_future_age(self):
        local = {**CRIME, 'entry_datetime': '2026-10-09T19:00:00'}
        self.assertEqual(risk.calculate_risk_score(PATH, [local], 'crime', NOW), 9)
        future = {**CRIME, 'entry_datetime': (NOW + timedelta(hours=1)).isoformat()}
        self.assertEqual(risk.calculate_risk_score(PATH, [future], 'crime', NOW), 9)

    def test_persistent_open_and_closed_hazards(self):
        self.assertEqual(risk.calculate_risk_score(PATH, [HAZARD], '311', NOW + timedelta(days=30)), 1)
        closed = {**HAZARD, 'status_description': 'Closed'}
        self.assertEqual(risk.calculate_risk_score(PATH, [closed], '311', NOW), 0)

    def test_index_matches_exact_distance_for_nearby_incidents(self):
        import random
        rng=random.Random(42)
        path=[(37.77+i*.00001,-122.46+i*.0001) for i in range(500)]
        index=risk.RouteSegmentIndex(path)
        for _ in range(100):
            point=(rng.uniform(37.765,37.78),rng.uniform(-122.465,-122.405))
            exact=risk.min_distance_to_path(point,path)
            result=index.distance(point)
            if exact<1:
                self.assertAlmostEqual(result,exact,places=10)
            else:
                self.assertTrue(math.isinf(result))

    def test_distance_attenuation(self):
        far = [(lat + 0.01, lng) for lat, lng in PATH]
        self.assertLess(risk.calculate_risk_score(far, [CRIME], 'crime', NOW), 0.001)

    @patch('path_risk_analysis.requests.get')
    def test_query_bounds_local_time_and_pagination(self, get):
        page = Mock(); page.json.return_value = [{}] * 5000
        last = Mock(); last.json.return_value = [CRIME]
        get.side_effect = [page, last]
        bounds = {'north': 37.8, 'south': 37.7, 'east': -122.4, 'west': -122.5}
        records = risk.fetch_crime_data(bounds, 'test-token', NOW)
        self.assertEqual(len(records), 5001)
        params = get.call_args_list[0].kwargs['params']
        self.assertIn('within_box(intersection_point', params['$where'])
        self.assertIn('2026-10-06T19:00:00', params['$where'])
        self.assertEqual(get.call_args_list[1].kwargs['params']['$offset'], 5000)
        self.assertEqual(get.call_args.kwargs['headers']['X-App-Token'], 'test-token')

    @patch('path_risk_analysis.requests.get')
    def test_failures_and_truncation_are_not_zero_risk(self, get):
        get.side_effect = risk.requests.ConnectionError('offline')
        bounds = {'north': 37.8, 'south': 37.7, 'east': -122.4, 'west': -122.5}
        with self.assertRaises(risk.IncidentDataUnavailable):
            risk.fetch_crime_data(bounds, current_time=NOW)
        get.side_effect = None
        get.return_value.json.return_value = [{}] * 5000
        with self.assertRaises(risk.IncidentDataUnavailable):
            risk.fetch_311_data(bounds)


class ScoringTests(unittest.TestCase):
    def test_proxy_output_and_scorer_share_the_coordinate_boundary(self):
        # Exercise the actual JS handler and Python validator together, offline.
        script = """
            import { handler } from './backend/graphhopper-proxy/index.mjs';
            process.env.GRAPHHOPPER_API_KEY = 'offline-fixture';
            const results = [];
            for (const count of [2000, 2001]) {
                const coordinates = Array.from({length: count}, (_, i) => [-122.42 + i / 1000000, 37.77]);
                globalThis.fetch = async () => ({ok: true, json: async () => ({paths: [{distance: 200, time: 120000, points: {coordinates}}]})});
                const result = await handler({routeKey: 'POST /routing/route', requestContext: {http: {method: 'POST'}}, body: JSON.stringify({origin: {lat: 37.77, lng: -122.42}, destination: {lat: 37.77, lng: -122.418}})});
                results.push({status: result.statusCode, data: JSON.parse(result.body)});
            }
            console.log(JSON.stringify(results));
        """
        result = subprocess.run(['node', '--input-type=module', '-e', script],
                                cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, check=True)
        accepted, rejected = json.loads(result.stdout)
        self.assertEqual(accepted['status'], 200)
        coordinates = [{'lat': lat, 'lng': lng} for lng, lat in accepted['data']['paths'][0]['points']['coordinates']]
        self.assertEqual(len(route_scoring.validate_routes({'routes': [{'id': 1, 'coordinates': coordinates}]})[0][1]), 2000)
        coordinates.append(coordinates[-1])
        with self.assertRaises(ValueError):
            route_scoring.validate_routes({'routes': [{'id': 1, 'coordinates': coordinates}]})
        self.assertEqual(rejected['status'], 422)
        self.assertNotIn('paths', rejected['data'])

    def test_bad_input(self):
        for payload in [None, {}, {'routes': []}, {'routes': [PAYLOAD['routes'][0]] * 2},
                        {'routes': [{'id': 1, 'coordinates': [{'lat': math.nan, 'lng': -122.4}] * 2}]},
                        {'routes': [{'id': 1, 'coordinates': [{'lat': 0, 'lng': 0}] * 2}]}]:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                route_scoring.validate_routes(payload)

    @patch('route_scoring.fetch_311_data', return_value=[HAZARD])
    @patch('route_scoring.fetch_crime_data', return_value=[CRIME])
    def test_actual_incidents_change_route_ranking(self, crime, hazard):
        with patch('route_scoring.datetime') as clock:
            clock.now.return_value = NOW
            result = route_scoring.score_routes(PAYLOAD)
        first, second = result['routes']
        self.assertAlmostEqual(first['totalRisk'], 10)
        self.assertLess(second['totalRisk'], first['totalRisk'])
        self.assertGreater(second['safetyScore'], first['safetyScore'])
        self.assertEqual(result['sources'], {'policeCalls': 1, 'open311Reports': 1})

    @patch('route_scoring.fetch_311_data', return_value=[])
    @patch('route_scoring.fetch_crime_data', return_value=[{'unusable': True}])
    def test_unusable_source_fails(self, crime, hazard):
        with self.assertRaises(risk.IncidentDataUnavailable):
            route_scoring.score_routes(PAYLOAD)

    @patch('route_scoring.fetch_311_data', return_value=[])
    @patch('route_scoring.fetch_crime_data', return_value=[])
    def test_successful_empty_queries(self, crime, hazard):
        result = route_scoring.score_routes(PAYLOAD)
        self.assertEqual(result['routes'][0]['totalRisk'], 0)
        self.assertEqual(result['sources']['policeCalls'], 0)


class HandlerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # AWS calls are stubbed; these tests never use credentials or network.
        with patch.dict(sys.modules, {'boto3': types.SimpleNamespace(resource=Mock(), client=Mock())}):
            import lambda_fetch_api
            cls.handler = staticmethod(lambda_fetch_api.lambda_handler)

    def test_v1_v2_and_base64(self):
        for event in [
            {'httpMethod': 'POST', 'path': '/score-routes', 'body': json.dumps(PAYLOAD)},
            {'requestContext': {'http': {'method': 'POST'}, 'stage': 'prod'},
             'rawPath': '/prod/score-routes', 'isBase64Encoded': True,
             'body': base64.b64encode(json.dumps(PAYLOAD).encode()).decode()},
        ]:
            with patch('route_scoring.score_routes', return_value={'routes': []}) as scorer:
                result = self.handler(event, None)
            self.assertEqual(result['statusCode'], 200)
            scorer.assert_called_once_with(PAYLOAD)

    def test_malformed_request(self):
        result = self.handler({'httpMethod': 'POST', 'path': '/score-routes', 'body': '{'}, None)
        self.assertEqual(result['statusCode'], 400)

    def test_legacy_data_excludes_snapshots_and_expired_records(self):
        table = Mock()
        future = int(datetime.now(timezone.utc).timestamp()) + 100
        table.scan.return_value = {'Items': [
            {'data': {'incident': 'valid'}, 'ttl': future},
            {'data': {'incident': 'expired'}, 'ttl': 1},
            {'record_type': 'safety_snapshot', 'ttl': future},
        ]}
        with patch.dict(self.handler.__globals__, {'table': table}):
            self.assertEqual(self.handler.__globals__['get_cached_data'](),
                             [{'data': {'incident': 'valid'}, 'ttl': future}])

    def test_scheduled_refresh_failure_propagates_for_retry(self):
        with patch('safety_data_store.SafetyDataStore') as store:
            store.return_value.load.side_effect = risk.IncidentDataUnavailable('offline')
            with self.assertRaises(risk.IncidentDataUnavailable):
                self.handler({'action': 'refresh-safety-data'}, None)

    def test_source_failure_returns_503(self):
        with patch('route_scoring.score_routes', side_effect=risk.IncidentDataUnavailable('offline')):
            result = self.handler({'httpMethod': 'POST', 'path': '/score-routes', 'body': '{}'}, None)
        self.assertEqual(result['statusCode'], 503)
        self.assertNotIn('routes', json.loads(result['body']))


if __name__ == '__main__':
    unittest.main()
