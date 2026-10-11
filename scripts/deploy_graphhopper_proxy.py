"""Deploy the existing console-created routing Lambda; never print its credentials."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import ssl
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--function', default='SafePathGraphHopperProxy')
    parser.add_argument('--api', default='scdwndv5z4')
    parser.add_argument('--region', default='us-east-1')
    args = parser.parse_args()
    os.umask(0o077)
    backup = Path(tempfile.mkdtemp(prefix='safepath-routing-backup-'))

    def aws(service, action, *options):
        result = subprocess.run(['aws', service, action, '--region', args.region, *options, '--output', 'json'], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(f'AWS {service} {action} failed; credentials and raw configuration omitted.')
        return json.loads(result.stdout) if result.stdout.strip() else {}

    function = aws('lambda', 'get-function', '--function-name', args.function)
    config = function['Configuration']
    (backup / 'function.json').write_text(json.dumps(config))
    context = ssl.create_default_context(cafile='/etc/ssl/cert.pem') if Path('/etc/ssl/cert.pem').exists() else ssl.create_default_context()
    with urllib.request.urlopen(function['Code']['Location'], timeout=30, context=context) as download:
        (backup / 'previous-code.zip').write_bytes(download.read())
    variables = dict(config.get('Environment', {}).get('Variables', {}))
    key = variables.pop('REACT_APP_GRAPHHOPPER_API_KEY', None)
    if not variables.get('GRAPHHOPPER_API_KEY') and key:
        variables['GRAPHHOPPER_API_KEY'] = key
    if not variables.get('GRAPHHOPPER_API_KEY'):
        raise RuntimeError('Add GRAPHHOPPER_API_KEY to the Lambda before deployment.')
    envfile = backup / 'environment.json'
    envfile.write_text(json.dumps({'Variables': variables}))
    package = backup / 'proxy.zip'
    with zipfile.ZipFile(package, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.write(ROOT / 'backend/graphhopper-proxy/index.mjs', 'index.mjs')
    aws('lambda', 'update-function-configuration', '--function-name', args.function,
        '--handler', 'index.handler', '--timeout', '25', '--memory-size', '256',
        '--revision-id', config['RevisionId'], '--environment', f'file://{envfile}')
    aws('lambda', 'wait', 'function-updated-v2', '--function-name', args.function)
    aws('lambda', 'update-function-code', '--function-name', args.function, '--zip-file', f'fileb://{package}')
    aws('lambda', 'wait', 'function-updated-v2', '--function-name', args.function)
    arn = config['FunctionArn']
    integrations = aws('apigatewayv2', 'get-integrations', '--api-id', args.api)['Items']
    existing = next((i for i in integrations if i.get('IntegrationUri') == arn), None)
    integration = existing or aws('apigatewayv2', 'create-integration', '--api-id', args.api,
        '--integration-type', 'AWS_PROXY', '--integration-uri', arn, '--payload-format-version', '2.0', '--timeout-in-millis', '28000')
    policy_result = subprocess.run(['aws', 'lambda', 'get-policy', '--region', args.region, '--function-name', args.function], capture_output=True, text=True)
    policy = json.loads(json.loads(policy_result.stdout)['Policy']) if policy_result.returncode == 0 else {'Statement': []}
    sid = 'SafePathRoutingApiGateway'
    if not any(s.get('Sid') == sid for s in policy['Statement']):
        aws('lambda', 'add-permission', '--function-name', args.function, '--statement-id', sid,
            '--action', 'lambda:InvokeFunction', '--principal', 'apigateway.amazonaws.com',
            '--source-arn', f'arn:aws:execute-api:{args.region}:{arn.split(":")[4]}:{args.api}/*/POST/routing/*')
    routes = aws('apigatewayv2', 'get-routes', '--api-id', args.api)['Items']
    (backup / 'routes.json').write_text(json.dumps(routes))
    for route in ['POST /routing/geocode', 'POST /routing/route']:
        existing_route = next((r for r in routes if r['RouteKey'] == route), None)
        target = f'integrations/{integration["IntegrationId"]}'
        if existing_route:
            aws('apigatewayv2', 'update-route', '--api-id', args.api, '--route-id', existing_route['RouteId'], '--target', target)
        else:
            aws('apigatewayv2', 'create-route', '--api-id', args.api, '--route-key', route, '--target', target)
    stage = aws('apigatewayv2', 'get-stage', '--api-id', args.api, '--stage-name', 'prod')
    (backup / 'stage.json').write_text(json.dumps(stage))
    settings = stage.get('RouteSettings', {})
    for route in ['POST /routing/geocode', 'POST /routing/route']:
        settings[route] = {**settings.get(route, {}), 'ThrottlingBurstLimit': 10, 'ThrottlingRateLimit': 2.0}
    settingsfile = backup / 'route-settings.json'
    settingsfile.write_text(json.dumps(settings))
    aws('apigatewayv2', 'update-stage', '--api-id', args.api, '--stage-name', 'prod', '--route-settings', f'file://{settingsfile}')
    print(json.dumps({'function': args.function, 'api': args.api, 'routes': ['POST /routing/geocode', 'POST /routing/route'], 'private_backup': str(backup)}))

if __name__ == '__main__':
    main()
