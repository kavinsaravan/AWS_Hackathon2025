import csv
import json
import math
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analyze_sample_coverage import SampleAnalyzer
from safety_dataset import (SafetyDatasetGenerator, DatasetSourceError, FIELDS, SpatialIndex, fetch_records)
from generate_final_dataset import FinalSafetyDataset
from generate_production_dataset import OptimizedSafetyDatasetGenerator
from generate_statistical_dataset import StatisticalSafetyDataset

NOW = datetime(2026,10,9,19,tzinfo=timezone.utc)
CRIME = {'latitude':'37.77','longitude':'-122.42','incident_category':'Assault'}
CALL = {'intersection_point':{'coordinates':[-122.42,37.77]},'priority_final':'1'}
HAZARD = {'lat':'37.77','long':'-122.42','service_name':'Streetlight','status_description':'Open'}


def fixture(cls=SafetyDatasetGenerator):
    generator=cls(seed=42,now=NOW)
    generator.crime_data=[CRIME]*2
    generator.calls_data=[CALL]
    generator.hazards_data=[HAZARD]
    generator.build_indexes()
    return generator


class CoverageTests(unittest.TestCase):
    def test_real_incidents_are_counted_in_grid(self):
        analyzer=SampleAnalyzer()
        grid=analyzer.create_density_grid([CRIME,CRIME,{'latitude':37.80,'longitude':-122.45}])
        self.assertEqual(sum(map(sum,grid)),3)
        self.assertEqual(analyzer.calculate_coverage_metrics(grid)['active_cells'],2)

    def test_sample_coverage_uses_actual_coordinates(self):
        analyzer=SampleAnalyzer()
        second={'latitude':37.80,'longitude':-122.45}
        grid=analyzer.create_density_grid([CRIME,second])
        result=analyzer.calculate_coverage_metrics(grid,[(37.77,-122.42)])
        self.assertEqual(result['sampled_active_cells'],1)
        self.assertEqual(result['active_cell_sample_coverage_pct'],50)
        unknown=analyzer.calculate_coverage_metrics(grid)
        self.assertNotIn('active_cell_sample_coverage_pct',unknown)

    def test_invalid_and_outside_points_do_not_wrap_to_edge(self):
        analyzer=SampleAnalyzer()
        grid=analyzer.create_density_grid([{'latitude':37.7079,'longitude':-122.42},
              {'latitude':math.nan,'longitude':-122.42}, {'latitude':'bad','longitude':-122.42},
              {'latitude':37.812,'longitude':-122.42}])
        self.assertEqual(sum(map(sum,grid)),0)

    def test_partial_northern_edge_cell_is_kept(self):
        analyzer=SampleAnalyzer()
        grid=analyzer.create_density_grid([{'latitude':37.8119,'longitude':-122.42}])
        self.assertEqual(sum(map(sum,grid)),1)


class DatasetTests(unittest.TestCase):
    def test_features_keep_measured_counts_and_coordinates(self):
        row=fixture().location_features(37.77,-122.42)
        self.assertEqual(row['violent_crimes'],2)
        self.assertEqual(row['priority_calls'],1)
        self.assertEqual(row['lighting_issues'],1)
        self.assertEqual(row['risk_score'],95)
        self.assertEqual(row['is_unsafe'],1)
        self.assertEqual(row['latitude'],37.77)

    def test_spatial_distance_filters_square_corners(self):
        outside={**CRIME,'latitude':37.7717,'longitude':-122.4183}
        index=SpatialIndex([CRIME,outside])
        self.assertEqual(index.nearby(37.77,-122.42,200),[CRIME])

    def test_seeded_sampling_exact_small_or_non_multiple_count(self):
        a,b=fixture(),fixture()
        for count in [1,7,101]:
            points=a.sample_points(count)
            self.assertEqual(len(points),count)
            self.assertEqual(points,b.sample_points(count))
            self.assertTrue(all(a.is_land(*point) for point in points))
        with self.assertRaises(ValueError):a.sample_points(0)

    def test_all_export_wrappers_keep_features_and_metadata(self):
        for cls in [SafetyDatasetGenerator,FinalSafetyDataset,OptimizedSafetyDatasetGenerator,StatisticalSafetyDataset]:
            with self.subTest(cls=cls.__name__),tempfile.TemporaryDirectory() as folder:
                generator=fixture(cls)
                rows=generator.generate_dataset(7,fetch=False)
                path=Path(generator.save_dataset(rows,str(Path(folder)/'dataset.csv')))
                with path.open() as stream:
                    saved=list(csv.DictReader(stream))
                self.assertEqual(len(saved),7)
                self.assertEqual(list(saved[0]),FIELDS)
                self.assertTrue(all(-123<float(row['longitude'])<-122 for row in saved))
                metadata=json.loads(path.with_suffix('.metadata.json').read_text())
                self.assertEqual(metadata['label_kind'],'heuristic_proxy')
                self.assertFalse(metadata['labels_only'])

    def test_legacy_label_export_requires_explicit_flag(self):
        with tempfile.TemporaryDirectory() as folder:
            generator=fixture()
            rows=generator.generate_dataset(7,fetch=False)
            path=Path(generator.save_dataset(rows,str(Path(folder)/'labels.csv'),labels_only=True))
            self.assertTrue(all(line in ('0','1') for line in path.read_text().splitlines()))
            with self.assertRaises(ValueError):generator.save_dataset([0,1],str(path))

    def test_no_forced_unsafe_percentile_or_random_night_labels(self):
        generator=fixture(FinalSafetyDataset)
        generator.crime_data=[];generator.calls_data=[];generator.hazards_data=[]
        rows=generator.generate_dataset(20,fetch=False)
        self.assertTrue(all(row['is_unsafe']==0 for row in rows))
        self.assertEqual(rows,generator.generate_dataset(20,fetch=False))

    @patch('safety_dataset.requests.get')
    def test_fetch_paginates(self,get):
        page=Mock();page.json.return_value=[CRIME]*5000
        last=Mock();last.json.return_value=[CRIME]
        get.side_effect=[page,last]
        self.assertEqual(len(fetch_records('https://fixture.invalid',{})),5001)
        self.assertEqual(get.call_args.kwargs['params']['$offset'],5000)

    @patch('safety_dataset.requests.get')
    def test_fetch_errors_and_truncation_abort(self,get):
        from requests import ConnectionError
        get.side_effect=ConnectionError('offline')
        with self.assertRaises(DatasetSourceError):fetch_records('https://fixture.invalid',{})
        get.side_effect=None;get.return_value.json.return_value=[CRIME]*5000
        with self.assertRaises(DatasetSourceError):fetch_records('https://fixture.invalid',{},max_records=5000)

    def test_generation_without_loaded_sources_is_rejected(self):
        with self.assertRaises(DatasetSourceError):
            SafetyDatasetGenerator().generate_dataset(10, fetch=False)
        with self.assertRaises(ValueError):
            FinalSafetyDataset().generate_dataset(0, fetch=False)

    def test_unusable_coordinates_fail_instead_of_safe_labels(self):
        with self.assertRaises(DatasetSourceError):SpatialIndex([{'latitude':'bad','longitude':None}])


if __name__=='__main__':unittest.main()
