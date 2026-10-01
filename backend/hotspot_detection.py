"""
SafePath - Crime Hotspot Detection using DBSCAN Clustering
Identifies statistically significant clusters of unsafe areas
"""

import numpy as np
from sklearn.cluster import DBSCAN, KMeans
from sklearn.preprocessing import StandardScaler
from geopy.distance import geodesic
import json
from typing import List, Dict, Tuple
from collections import Counter


class HotspotDetector:
    """
    Detect crime hotspots using density-based clustering
    """

    def __init__(self, eps_km=0.3, min_samples=5):
        """
        Initialize hotspot detector

        Args:
            eps_km: Maximum distance between points in same cluster (kilometers)
            min_samples: Minimum incidents to form a hotspot
        """
        self.eps_km = eps_km
        self.min_samples = min_samples

        # Crime severity weights (same as path_risk_analysis.py)
        self.CRIME_SEVERITY = {
            # High risk (w=3)
            "EXPLOSIVE FOUND": 3, "EXPLOSION": 3,
            "ROBBERY": 3, "STRONGARM ROBBERY": 3,
            "ASSAULT": 3, "BATTERY": 3,
            "AGG ASSAULT / ADW": 3,
            "PERSON W/GUN": 3, "PERSON W/KNIFE": 3,

            # Medium risk (w=2)
            "PURSE SNATCH": 2, "INDECENT EXPOSURE": 2,
            "FIGHT W/WEAPONS": 2, "FIGHT W/ WEAPONS": 2,
            "PERSON BREAKING IN": 2, "BURGLARY": 2,

            # Low risk (w=1)
            "SUSPICIOUS PERSON": 1, "THREATS": 1, "HARASSMENT": 1,
            "THREATS / HARASSMENT": 1, "FIGHT NO WEAPON": 1,
            "AGGRESSIVE": 1, "THREATENING": 1, "ENCAMPMENT": 1
        }

    def detect_hotspots_dbscan(self, incidents: List[Dict]) -> Dict:
        """
        Use DBSCAN to find crime hotspots

        Args:
            incidents: List of crime incidents with coordinates

        Returns:
            Dictionary with cluster information and GeoJSON
        """

        if len(incidents) < self.min_samples:
            return {
                'hotspots': [],
                'total_clusters': 0,
                'noise_points': 0,
                'algorithm': 'DBSCAN',
                'params': {'eps_km': self.eps_km, 'min_samples': self.min_samples}
            }

        # Extract coordinates and keep track of incidents with valid coords
        coords = []
        incidents_with_coords = []
        for incident in incidents:
            if 'point' in incident and 'coordinates' in incident['point']:
                # DynamoDB cached format: {'type': 'Point', 'coordinates': [lng, lat]}
                lng, lat = incident['point']['coordinates']
                coords.append([lat, lng])
                incidents_with_coords.append(incident)
            elif 'intersection_point' in incident and 'coordinates' in incident['intersection_point']:
                # SF Open Data format: [longitude, latitude]
                lng, lat = incident['intersection_point']['coordinates']
                coords.append([lat, lng])
                incidents_with_coords.append(incident)
            elif 'point_geom' in incident:
                # 311 data format
                lng, lat = incident['point_geom']['coordinates']
                coords.append([lat, lng])
                incidents_with_coords.append(incident)

        if len(coords) < self.min_samples:
            return {
                'hotspots': [],
                'total_clusters': 0,
                'noise_points': 0,
                'algorithm': 'DBSCAN'
            }

        coords_array = np.array(coords)

        # Convert eps from kilometers to degrees (approximate)
        # At San Francisco latitude (37.7°), 1 degree ≈ 111 km
        eps_degrees = self.eps_km / 111.0

        # Run DBSCAN
        db = DBSCAN(eps=eps_degrees, min_samples=self.min_samples, metric='euclidean')
        labels = db.fit_predict(coords_array)

        # Process clusters
        unique_labels = set(labels)
        noise_points = list(labels).count(-1)
        total_clusters = len(unique_labels) - (1 if -1 in unique_labels else 0)

        hotspots = []

        for cluster_id in unique_labels:
            if cluster_id == -1:
                continue  # Skip noise points

            # Get all points in this cluster
            cluster_mask = labels == cluster_id
            cluster_coords = coords_array[cluster_mask]
            cluster_incidents = [incidents_with_coords[i] for i in range(len(incidents_with_coords)) if labels[i] == cluster_id]

            # Calculate cluster metadata
            hotspot = self._calculate_cluster_metadata(
                cluster_id,
                cluster_coords,
                cluster_incidents
            )

            hotspots.append(hotspot)

        # Sort by severity (highest first)
        hotspots.sort(key=lambda x: x['severity_score'], reverse=True)

        return {
            'hotspots': hotspots,
            'total_clusters': total_clusters,
            'noise_points': noise_points,
            'algorithm': 'DBSCAN',
            'params': {
                'eps_km': self.eps_km,
                'min_samples': self.min_samples
            }
        }

    def detect_hotspots_kmeans(self, incidents: List[Dict], n_clusters=10) -> Dict:
        """
        Use K-means for comparison (less suitable for crime data)

        Args:
            incidents: List of crime incidents
            n_clusters: Number of clusters to create

        Returns:
            Dictionary with cluster information
        """

        # Extract coordinates and keep track of incidents with valid coords
        coords = []
        incidents_with_coords = []
        for incident in incidents:
            if 'point' in incident and 'coordinates' in incident['point']:
                lng, lat = incident['point']['coordinates']
                coords.append([lat, lng])
                incidents_with_coords.append(incident)
            elif 'intersection_point' in incident:
                lng, lat = incident['intersection_point']['coordinates']
                coords.append([lat, lng])
                incidents_with_coords.append(incident)
            elif 'point_geom' in incident:
                lng, lat = incident['point_geom']['coordinates']
                coords.append([lat, lng])
                incidents_with_coords.append(incident)

        if len(coords) < n_clusters:
            return {'hotspots': [], 'total_clusters': 0, 'algorithm': 'K-means'}

        coords_array = np.array(coords)

        # Run K-means
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = kmeans.fit_predict(coords_array)

        hotspots = []

        for cluster_id in range(n_clusters):
            cluster_mask = labels == cluster_id
            cluster_coords = coords_array[cluster_mask]
            cluster_incidents = [incidents_with_coords[i] for i in range(len(incidents_with_coords)) if labels[i] == cluster_id]

            if len(cluster_incidents) < 3:
                continue  # Skip small clusters

            hotspot = self._calculate_cluster_metadata(
                cluster_id,
                cluster_coords,
                cluster_incidents
            )

            hotspots.append(hotspot)

        hotspots.sort(key=lambda x: x['severity_score'], reverse=True)

        return {
            'hotspots': hotspots,
            'total_clusters': len(hotspots),
            'algorithm': 'K-means',
            'params': {'n_clusters': n_clusters}
        }

    def _calculate_cluster_metadata(
        self,
        cluster_id: int,
        cluster_coords: np.ndarray,
        cluster_incidents: List[Dict]
    ) -> Dict:
        """
        Calculate metadata for a crime hotspot cluster

        Returns:
            Dictionary with cluster center, radius, crime stats, etc.
        """

        # Calculate centroid (center point)
        center_lat = float(np.mean(cluster_coords[:, 0]))
        center_lng = float(np.mean(cluster_coords[:, 1]))

        # Calculate radius (max distance from centroid)
        max_dist = 0
        for coord in cluster_coords:
            dist = geodesic((center_lat, center_lng), tuple(coord)).kilometers
            max_dist = max(max_dist, dist)

        # Count crime types
        crime_types = Counter()
        total_severity = 0

        for incident in cluster_incidents:
            # Get crime type
            crime_type = incident.get('call_type_final_desc',
                                     incident.get('call_type_original_desc',
                                                incident.get('service_name', 'Unknown')))
            crime_type = crime_type.upper()
            crime_types[crime_type] += 1

            # Calculate severity
            severity = self._get_severity(crime_type)
            total_severity += severity

        # Calculate average severity
        avg_severity = total_severity / len(cluster_incidents) if cluster_incidents else 0

        # Determine risk level
        if avg_severity >= 2.5:
            risk_level = "High"
            color = "#ef4444"  # Red
        elif avg_severity >= 1.5:
            risk_level = "Medium"
            color = "#f59e0b"  # Orange
        else:
            risk_level = "Low"
            color = "#eab308"  # Yellow

        # Get top 3 crime types
        top_crimes = crime_types.most_common(3)

        return {
            'id': cluster_id,
            'center': {
                'lat': center_lat,
                'lng': center_lng
            },
            'radius_km': round(max_dist, 3),
            'incident_count': len(cluster_incidents),
            'severity_score': round(avg_severity, 2),
            'risk_level': risk_level,
            'color': color,
            'top_crimes': [
                {'type': crime, 'count': count}
                for crime, count in top_crimes
            ],
            'crime_breakdown': dict(crime_types)
        }

    def _get_severity(self, crime_type: str) -> int:
        """Get severity weight for a crime type"""
        crime_type = crime_type.upper()

        for key, weight in self.CRIME_SEVERITY.items():
            if key in crime_type:
                return weight

        return 1  # Default low severity

    def to_geojson(self, hotspots: List[Dict]) -> Dict:
        """
        Convert hotspots to GeoJSON format for mapping

        Returns:
            GeoJSON FeatureCollection
        """

        features = []

        for hotspot in hotspots:
            feature = {
                'type': 'Feature',
                'geometry': {
                    'type': 'Point',
                    'coordinates': [hotspot['center']['lng'], hotspot['center']['lat']]
                },
                'properties': {
                    'id': hotspot['id'],
                    'radius_km': hotspot['radius_km'],
                    'incident_count': hotspot['incident_count'],
                    'severity_score': hotspot['severity_score'],
                    'risk_level': hotspot['risk_level'],
                    'color': hotspot['color'],
                    'top_crimes': hotspot['top_crimes'],
                    'description': self._generate_description(hotspot)
                }
            }
            features.append(feature)

        return {
            'type': 'FeatureCollection',
            'features': features
        }

    def _generate_description(self, hotspot: Dict) -> str:
        """Generate human-readable description for hotspot"""

        top_crime = hotspot['top_crimes'][0]['type'] if hotspot['top_crimes'] else 'incidents'

        return (
            f"{hotspot['risk_level']} risk area with {hotspot['incident_count']} "
            f"incidents. Most common: {top_crime}."
        )


# Example usage
if __name__ == "__main__":
    # Sample crime data
    sample_incidents = [
        {
            "call_type_final_desc": "ROBBERY",
            "intersection_point": {"coordinates": [-122.4194, 37.7749]}
        },
        {
            "call_type_final_desc": "ROBBERY",
            "intersection_point": {"coordinates": [-122.4195, 37.7750]}
        },
        {
            "call_type_final_desc": "ASSAULT",
            "intersection_point": {"coordinates": [-122.4193, 37.7748]}
        },
        # Add more test data...
    ]

    detector = HotspotDetector(eps_km=0.3, min_samples=3)

    # Run DBSCAN
    result = detector.detect_hotspots_dbscan(sample_incidents)

    print(f"Found {result['total_clusters']} hotspots")
    print(f"Noise points: {result['noise_points']}")

    # Convert to GeoJSON
    geojson = detector.to_geojson(result['hotspots'])
    print(json.dumps(geojson, indent=2))
