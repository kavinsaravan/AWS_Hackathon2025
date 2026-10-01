"""
AWS Lambda Handler Extension for Hotspot Detection
Adds GET /hotspots endpoint to existing API
"""

import json
import boto3
from datetime import datetime, timedelta
from decimal import Decimal
from hotspot_detection import HotspotDetector


# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
s3_client = boto3.client('s3')

# Configuration
crime_table_name = 'ApiDataCache'  # Reuse existing crime data table
hotspot_table_name = 'HotspotCache'  # New table for hotspot cache

crime_table = dynamodb.Table(crime_table_name)


def decimal_default(obj):
    """Helper to serialize Decimal objects"""
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError


def get_cached_crime_data():
    """Retrieve crime data from existing DynamoDB cache"""
    try:
        response = crime_table.scan()
        items = response.get('Items', [])

        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = crime_table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            items.extend(response.get('Items', []))

        # Extract just the crime data
        crimes = [item['data'] for item in items if 'data' in item]

        print(f"Retrieved {len(crimes)} crime incidents from cache")
        return crimes

    except Exception as e:
        print(f"Error retrieving crime data: {e}")
        return []


def calculate_hotspots(eps_km=0.3, min_samples=5, algorithm='dbscan'):
    """
    Calculate crime hotspots using clustering

    Args:
        eps_km: DBSCAN epsilon (km)
        min_samples: Minimum incidents for hotspot
        algorithm: 'dbscan' or 'kmeans'

    Returns:
        Dictionary with hotspot data and GeoJSON
    """

    # Get crime data from cache
    crimes = get_cached_crime_data()

    if not crimes:
        return {
            'hotspots': [],
            'geojson': {'type': 'FeatureCollection', 'features': []},
            'metadata': {
                'total_clusters': 0,
                'crime_count': 0,
                'algorithm': algorithm,
                'timestamp': datetime.now().isoformat()
            }
        }

    # Initialize detector
    detector = HotspotDetector(eps_km=eps_km, min_samples=min_samples)

    # Run clustering
    if algorithm == 'dbscan':
        result = detector.detect_hotspots_dbscan(crimes)
    elif algorithm == 'kmeans':
        n_clusters = min(10, len(crimes) // 20)  # Auto-determine clusters
        result = detector.detect_hotspots_kmeans(crimes, n_clusters=n_clusters)
    else:
        raise ValueError(f"Unknown algorithm: {algorithm}")

    # Convert to GeoJSON
    geojson = detector.to_geojson(result['hotspots'])

    return {
        'hotspots': result['hotspots'],
        'geojson': geojson,
        'metadata': {
            'total_clusters': result.get('total_clusters', 0),
            'noise_points': result.get('noise_points', 0),
            'crime_count': len(crimes),
            'algorithm': algorithm,
            'params': result.get('params', {}),
            'timestamp': datetime.now().isoformat()
        }
    }


def lambda_handler(event, context):
    """
    Lambda handler for GET /hotspots endpoint

    Query Parameters:
        - eps: DBSCAN epsilon in km (default: 0.3)
        - min_samples: Minimum incidents (default: 5)
        - algorithm: 'dbscan' or 'kmeans' (default: 'dbscan')
        - format: 'json' or 'geojson' (default: 'geojson')
    """

    # Parse query parameters
    query_params = event.get('queryStringParameters', {}) or {}

    eps_km = float(query_params.get('eps', 0.3))
    min_samples = int(query_params.get('min_samples', 5))
    algorithm = query_params.get('algorithm', 'dbscan')
    output_format = query_params.get('format', 'geojson')

    try:
        # Calculate hotspots
        result = calculate_hotspots(
            eps_km=eps_km,
            min_samples=min_samples,
            algorithm=algorithm
        )

        # Choose output format
        if output_format == 'json':
            # Return full data structure
            body = json.dumps(result, default=decimal_default)
        else:
            # Return GeoJSON only (for map display)
            body = json.dumps(result['geojson'], default=decimal_default)

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': '*',
                'Access-Control-Allow-Methods': 'GET, OPTIONS'
            },
            'body': body
        }

    except Exception as e:
        print(f"Error processing hotspots: {e}")
        import traceback
        traceback.print_exc()

        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'error': 'Internal server error',
                'message': str(e)
            })
        }


# Test locally
if __name__ == "__main__":
    # Simulate API Gateway event
    test_event = {
        'queryStringParameters': {
            'eps': '0.3',
            'min_samples': '5',
            'algorithm': 'dbscan',
            'format': 'geojson'
        }
    }

    response = lambda_handler(test_event, None)
    print(json.dumps(json.loads(response['body']), indent=2))
