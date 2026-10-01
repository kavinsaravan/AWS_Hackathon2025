#!/usr/bin/env python3
"""
Test script for hotspot detection algorithms
Run locally before deploying to AWS
"""

import sys
import os
import json
import requests

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from hotspot_detection import HotspotDetector


def fetch_sample_crime_data():
    """Fetch real crime data from SF Open Data for testing"""

    print("📞 Fetching crime data from SF Open Data...")

    api_url = "https://data.sfgov.org/resource/gnap-fj3t.json"

    query = {
        "$query": """SELECT
  entry_datetime,
  call_type_original_desc,
  call_type_final_desc,
  intersection_name,
  intersection_point
WHERE
  caseless_one_of(
    call_type_original_desc,
    "EXPLOSIVE FOUND",
    "SUSPICIOUS PERSON",
    "FIGHT W/WEAPONS",
    "FIGHT NO WEAPON",
    "ASSAULT / BATTERY DV",
    "PURSE SNATCH",
    "EXPLOSION",
    "ROBBERY",
    "THREATS / HARASSMENT",
    "STRONGARM ROBBERY",
    "INDECENT EXPOSURE",
    "PERSON BREAKING IN",
    "BURGLARY"
  )
ORDER BY entry_datetime DESC NULL LAST""",
        "$limit": 500
    }

    try:
        response = requests.get(api_url, params=query, timeout=10)
        response.raise_for_status()
        crimes = response.json()

        print(f"✅ Got {len(crimes)} crime incidents")
        return crimes

    except Exception as e:
        print(f"❌ Error fetching data: {e}")
        return []


def test_dbscan(crimes, eps_km=0.3, min_samples=5):
    """Test DBSCAN clustering"""

    print(f"\n{'='*60}")
    print(f"Testing DBSCAN (eps={eps_km}km, min_samples={min_samples})")
    print(f"{'='*60}")

    detector = HotspotDetector(eps_km=eps_km, min_samples=min_samples)
    result = detector.detect_hotspots_dbscan(crimes)

    print(f"\n📊 Results:")
    print(f"  Total clusters found: {result['total_clusters']}")
    print(f"  Noise points (isolated incidents): {result['noise_points']}")
    print(f"  Hotspots identified: {len(result['hotspots'])}")

    if result['hotspots']:
        print(f"\n🔥 Top 5 Hotspots:")
        for i, hotspot in enumerate(result['hotspots'][:5], 1):
            print(f"\n  {i}. Hotspot #{hotspot['id']}")
            print(f"     Location: {hotspot['center']['lat']:.4f}, {hotspot['center']['lng']:.4f}")
            print(f"     Incidents: {hotspot['incident_count']}")
            print(f"     Radius: {hotspot['radius_km']:.3f} km")
            print(f"     Risk Level: {hotspot['risk_level']} (severity: {hotspot['severity_score']:.2f})")
            print(f"     Top Crime: {hotspot['top_crimes'][0]['type']} ({hotspot['top_crimes'][0]['count']} incidents)")

    return result


def test_kmeans(crimes, n_clusters=10):
    """Test K-means clustering for comparison"""

    print(f"\n{'='*60}")
    print(f"Testing K-means (n_clusters={n_clusters})")
    print(f"{'='*60}")

    detector = HotspotDetector()
    result = detector.detect_hotspots_kmeans(crimes, n_clusters=n_clusters)

    print(f"\n📊 Results:")
    print(f"  Total clusters: {result['total_clusters']}")
    print(f"  Hotspots identified: {len(result['hotspots'])}")

    if result['hotspots']:
        print(f"\n🔥 Top 5 Clusters:")
        for i, hotspot in enumerate(result['hotspots'][:5], 1):
            print(f"\n  {i}. Cluster #{hotspot['id']}")
            print(f"     Incidents: {hotspot['incident_count']}")
            print(f"     Risk Level: {hotspot['risk_level']} (severity: {hotspot['severity_score']:.2f})")

    return result


def save_geojson(result, filename):
    """Save hotspots as GeoJSON for visualization"""

    detector = HotspotDetector()
    geojson = detector.to_geojson(result['hotspots'])

    output_path = os.path.join(os.path.dirname(__file__), '..', 'public', filename)

    with open(output_path, 'w') as f:
        json.dump(geojson, f, indent=2)

    print(f"\n💾 Saved GeoJSON to: {output_path}")
    print(f"   You can visualize this at: https://geojson.io")


def main():
    """Main test function"""

    print("🧪 SafePath Hotspot Detection Test Suite")
    print("=" * 60)

    # Fetch crime data
    crimes = fetch_sample_crime_data()

    if not crimes:
        print("❌ No crime data available. Exiting.")
        return

    # Test DBSCAN with different parameters
    print("\n" + "=" * 60)
    print("Test 1: DBSCAN with default parameters")
    print("=" * 60)
    result_dbscan = test_dbscan(crimes, eps_km=0.3, min_samples=5)

    # Save GeoJSON
    save_geojson(result_dbscan, 'hotspots-dbscan.geojson')

    # Test with stricter parameters (larger clusters)
    print("\n" + "=" * 60)
    print("Test 2: DBSCAN with stricter parameters (larger hotspots)")
    print("=" * 60)
    result_strict = test_dbscan(crimes, eps_km=0.5, min_samples=10)

    # Test K-means for comparison
    print("\n" + "=" * 60)
    print("Test 3: K-means for comparison")
    print("=" * 60)
    result_kmeans = test_kmeans(crimes, n_clusters=10)
    save_geojson(result_kmeans, 'hotspots-kmeans.geojson')

    # Comparison
    print("\n" + "=" * 60)
    print("Algorithm Comparison")
    print("=" * 60)
    print(f"DBSCAN (default):  {len(result_dbscan['hotspots'])} hotspots, {result_dbscan['noise_points']} noise points")
    print(f"DBSCAN (strict):   {len(result_strict['hotspots'])} hotspots, {result_strict['noise_points']} noise points")
    print(f"K-means:           {len(result_kmeans['hotspots'])} clusters")

    print("\n✅ Testing complete!")
    print("\n📝 Next steps:")
    print("   1. Review GeoJSON files in /public directory")
    print("   2. Visualize at https://geojson.io")
    print("   3. Adjust eps_km and min_samples if needed")
    print("   4. Deploy to AWS Lambda")


if __name__ == "__main__":
    main()
