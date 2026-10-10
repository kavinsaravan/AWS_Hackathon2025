#!/usr/bin/env python3
"""Deploy tested scoring code to existing SafePath resources; keep rollback files.

Requires AWS CLI credentials. Preview is the default; --apply publishes changes.
Does not replace unrelated routes, IAM policies, or the legacy hourly schedule.
"""
import argparse
import json
import os
import subprocess
from pathlib import Path
import requests


def aws(*args):
    result = subprocess.run(['aws', *args, '--region', OPTIONS.region, '--output', 'json'],
                            text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return json.loads(result.stdout) if result.stdout.strip() else {}


def deploy():
    account = aws('sts', 'get-caller-identity')['Account']
    if account != OPTIONS.account:
        raise RuntimeError('AWS account does not match the intended deployment')
    function = aws('lambda', 'get-function', '--function-name', OPTIONS.function)
    config = function['Configuration']
    variables = config.get('Environment', {}).get('Variables', {})
    if not variables.get('S3_BUCKET_NAME') or not variables.get('DYNAMODB_TABLE_NAME'):
        raise RuntimeError('Lambda must already have S3_BUCKET_NAME and DYNAMODB_TABLE_NAME')
    routes = aws('apigatewayv2', 'get-routes', '--api-id', OPTIONS.api_id)['Items']
    integration = next(route['Target'] for route in routes if route['RouteKey'] == 'POST /fetch-new')
    existing = next((route for route in routes if route['RouteKey'] == 'POST /score-routes'), None)
    if existing and existing['Target'] != integration:
        raise RuntimeError('Existing scoring route targets a different integration')
    print(json.dumps({'account': account, 'function': OPTIONS.function, 'apiId': OPTIONS.api_id,
                      'zip': str(OPTIONS.lambda_zip), 'scoringRoute': 'POST /score-routes',
                      'snapshotRefresh': 'rate(5 minutes)', 'apply': OPTIONS.apply}, indent=2))
    if not OPTIONS.apply:
        return
    backup = OPTIONS.backup_dir
    backup.mkdir(parents=True, exist_ok=True)
    saved_config = backup / 'lambda-configuration.json'
    saved_config.write_text(json.dumps(config, indent=2))
    saved_config.chmod(0o600)
    response = requests.get(function['Code']['Location'], timeout=30)
    response.raise_for_status()
    previous_code = response.content
    (backup / 'previous-lambda.zip').write_bytes(previous_code)
    aws('lambda', 'update-function-code', '--function-name', OPTIONS.function,
        '--revision-id', config['RevisionId'], '--zip-file', 'fileb://' + str(OPTIONS.lambda_zip))
    aws('lambda', 'wait', 'function-updated', '--function-name', OPTIONS.function)
    # Warm the snapshot before exposing the new API route.
    event_file = backup / 'refresh-event.json'
    event_file.write_text(json.dumps({'action': 'refresh-safety-data'}))
    response_file = backup / 'refresh-response.json'
    invocation = aws('lambda', 'invoke', '--function-name', OPTIONS.function,
                     '--payload', 'fileb://' + str(event_file), str(response_file))
    if invocation.get('FunctionError'):
        # Roll back the code if live data cannot be read/persisted.
        aws('lambda', 'update-function-code', '--function-name', OPTIONS.function,
            '--zip-file', 'fileb://' + str(backup / 'previous-lambda.zip'))
        aws('lambda', 'wait', 'function-updated', '--function-name', OPTIONS.function)
        raise RuntimeError('Snapshot warm-up failed; previous Lambda code restored: ' + response_file.read_text())
    if not existing:
        aws('apigatewayv2', 'create-route', '--api-id', OPTIONS.api_id,
            '--route-key', 'POST /score-routes', '--target', integration)
    rule_name = 'SafePathSafetyDataRefresh'
    rule = aws('events', 'put-rule', '--name', rule_name,
               '--schedule-expression', 'rate(5 minutes)', '--state', 'ENABLED',
               '--description', 'Refresh SafePath incident snapshots every five minutes')
    statement = 'SafePathSafetySnapshotRefresh'
    try:
        policy = json.loads(aws('lambda', 'get-policy', '--function-name', OPTIONS.function)['Policy'])
        permission_exists = any(item['Sid'] == statement for item in policy['Statement'])
    except RuntimeError as error:
        if 'ResourceNotFoundException' not in str(error):
            raise
        permission_exists = False
    if not permission_exists:
        aws('lambda', 'add-permission', '--function-name', OPTIONS.function,
            '--statement-id', statement, '--action', 'lambda:InvokeFunction',
            '--principal', 'events.amazonaws.com', '--source-arn', rule['RuleArn'])
    targets_file = backup / 'refresh-targets.json'
    targets_file.write_text(json.dumps([{'Id': 'SafetySnapshotRefresh', 'Arn': config['FunctionArn'],
                                       'Input': json.dumps({'action': 'refresh-safety-data'})}]))
    result = aws('events', 'put-targets', '--rule', rule_name,
                 '--targets', 'file://' + str(targets_file))
    if result.get('FailedEntryCount'):
        raise RuntimeError('Unable to connect the snapshot refresh schedule')
    print('Snapshot warm-up:', response_file.read_text())
    print('AWS backend deployed. Rollback code and configuration:', backup)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--account', required=True)
    parser.add_argument('--api-id', required=True)
    parser.add_argument('--function', default='ApiDataFetcher')
    parser.add_argument('--region', default='us-east-1')
    parser.add_argument('--lambda-zip', type=Path, required=True)
    parser.add_argument('--backup-dir', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    OPTIONS = parser.parse_args()
    OPTIONS.lambda_zip = OPTIONS.lambda_zip.resolve()
    if not OPTIONS.lambda_zip.is_file():
        parser.error('Lambda ZIP is missing')
    deploy()
