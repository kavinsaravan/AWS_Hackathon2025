#!/usr/bin/env python3
"""Measure incident density and actual sample overlap; no accuracy guarantees."""
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from safety_dataset import BOUNDS, SF_TIMEZONE, coordinates, fetch_records


class SampleAnalyzer:
    def __init__(self):
        self.police_api_url = 'https://data.sfgov.org/resource/wg3w-h783.json'
        self.sf_bounds = BOUNDS.copy()
        self.grid_size = .004

    def fetch_all_incidents(self):
        now = datetime.now(timezone.utc).astimezone(SF_TIMEZONE).replace(tzinfo=None)
        bounds = self.sf_bounds
        where = (f"incident_datetime >= '{(now-timedelta(days=90)).isoformat()}' "
                 f"AND incident_datetime <= '{now.isoformat()}' AND within_box(point, "
                 f"{bounds['north']}, {bounds['west']}, {bounds['south']}, {bounds['east']})")
        return fetch_records(self.police_api_url, {
            '$where': where, '$order': 'incident_id ASC',
            '$select': 'incident_id,latitude,longitude,analysis_neighborhood'})

    def grid_cell(self, lat, lng):
        bounds = self.sf_bounds
        if (not math.isfinite(lat) or not math.isfinite(lng)
            or not bounds['south'] <= lat < bounds['north']
            or not bounds['west'] <= lng < bounds['east']):
            return None
        return (math.floor((lat-bounds['south'])/self.grid_size),
                math.floor((lng-bounds['west'])/self.grid_size))

    def create_density_grid(self, incidents):
        lat_steps = math.ceil((self.sf_bounds['north']-self.sf_bounds['south'])/self.grid_size)
        lng_steps = math.ceil((self.sf_bounds['east']-self.sf_bounds['west'])/self.grid_size)
        grid = [[0 for _ in range(lng_steps)] for _ in range(lat_steps)]
        for incident in incidents:
            point = coordinates(incident)
            cell = self.grid_cell(*point) if point else None
            if cell is not None:
                grid[cell[0]][cell[1]] += 1
        return grid

    def analyze_neighborhoods(self, incidents):
        counts = defaultdict(int)
        for incident in incidents:
            counts[incident.get('analysis_neighborhood') or 'Unknown'] += 1
        return sorted(counts.items(), key=lambda pair: pair[1], reverse=True)

    def calculate_coverage_metrics(self, density_grid, sample_points=None):
        flat = [value for row in density_grid for value in row]
        active = {(i,j) for i,row in enumerate(density_grid) for j,value in enumerate(row) if value}
        values = sorted(value for value in flat if value)
        mean = sum(values)/len(values) if values else 0
        result = {'total_cells':len(flat), 'active_cells':len(active),
                  'coverage_pct':len(active)/len(flat)*100 if flat else 0,
                  'incident_count':sum(flat), 'mean_density':mean,
                  'median_density':values[len(values)//2] if values else 0,
                  'std_density':math.sqrt(sum((value-mean)**2 for value in values)/len(values)) if values else 0,
                  'max_density':max(values,default=0),
                  'high_risk_cells':sum(value>values[int(len(values)*.75)] for value in values) if values else 0}
        if sample_points is not None:
            sampled = set()
            for point in sample_points:
                try:
                    pair = coordinates(point) if isinstance(point,dict) else tuple(map(float,point))
                    cell = self.grid_cell(*pair) if pair and len(pair)==2 else None
                    if cell is not None:
                        sampled.add(cell)
                except (TypeError, ValueError):
                    continue
            result.update(sampled_cells=len(sampled), sampled_active_cells=len(active & sampled),
                          active_cell_sample_coverage_pct=len(active & sampled)/len(active)*100 if active else 0)
        return result

    def validate_sample_strategy(self, sample_points=None):
        incidents = self.fetch_all_incidents()
        grid = self.create_density_grid(incidents)
        result = self.calculate_coverage_metrics(grid, sample_points)
        print(f"Incidents in the rolling 90-day window: {result['incident_count']}")
        print(f"Active grid cells: {result['active_cells']} of {result['total_cells']}")
        if sample_points is None:
            print('Supply actual sample coordinates to measure spatial sample coverage.')
        else:
            print(f"Active cells covered by samples: {result['active_cell_sample_coverage_pct']:.1f}%")
        print('Spatial coverage and sample size do not establish safety-label or model accuracy.')
        return result


if __name__ == '__main__':
    SampleAnalyzer().validate_sample_strategy()
