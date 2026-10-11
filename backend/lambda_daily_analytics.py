"""Daily police-dispatch ingestion and public, read-only Tableau/Sheets exports."""
import base64
import json
from datetime import datetime, timezone
from analytics_snapshot import AnalyticsStore, fetch_history, build_export


def lambda_handler(event, context):
    if event.get('action') == 'refresh-analytics':
        now = datetime.now(timezone.utc)
        records = fetch_history(now)
        csv_bytes, summary, manifest = build_export(records, now)
        AnalyticsStore().publish(csv_bytes, summary, manifest)
        print(json.dumps({'event': 'daily_analytics_refreshed', 'rows': manifest['rows'], 'updatedAt': manifest['refreshed_at_utc']}))
        return manifest
    method = event.get('requestContext', {}).get('http', {}).get('method')
    route = event.get('routeKey', '')
    kind = {'GET /analytics.csv': 'csv', 'GET /analytics-summary': 'summary', 'GET /analytics-manifest': 'manifest'}.get(route)
    if method != 'GET' or kind is None:return {'statusCode': 404, 'body': 'Not found'}
    try:
        raw, updated = AnalyticsStore().read(kind)
        headers = {'Content-Type': 'text/csv; charset=utf-8' if kind == 'csv' else 'application/json',
                   'Cache-Control': 'public, max-age=300', 'Access-Control-Allow-Origin': '*', 'X-Data-Updated': updated}
        if kind != 'manifest':headers['Content-Encoding'] = 'gzip'
        return {'statusCode': 200, 'headers': headers, 'isBase64Encoded': True, 'body': base64.b64encode(raw).decode()}
    except Exception as error:
        print(json.dumps({'event': 'analytics_read_failed', 'kind': kind, 'errorType': type(error).__name__}))
        return {'statusCode': 503, 'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*', 'Cache-Control': 'no-store'},
                'body': json.dumps({'error': 'Daily analytics are temporarily unavailable'})}
