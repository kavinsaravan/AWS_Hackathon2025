#!/usr/bin/env python3
"""Deploy code through the reconciled CloudFormation stack; preview by default.

Every run creates a unique private backup directory. CloudFormation owns route,
schedule, permissions, and code configuration. Any post-update failure triggers
a stack rollback to the previous code and parameters; rollback failures are reported.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

import requests
from aws_deployment import (AWSClient, AWSCommandError, checksum, new_backup,
                            parameter_values, private_json, template_body, guarded_update, settle_stack)

REQUIRED = {'ApiDataFetcherLambda', 'ScoreRoutesRoute', 'SafetyDataRefreshRule',
            'SafetyDataRefreshPermission', 'CrimeDataBackupBucket'}


def deploy(options, client=None, download=None):
    client = client or AWSClient(options.region)
    account = client.call('sts', 'get-caller-identity')['Account']
    if account != options.account:
        raise RuntimeError('AWS account does not match the intended deployment')
    stack = client.call('cloudformation', 'describe-stacks', '--stack-name', options.stack_name)['Stacks'][0]
    if stack['StackStatus'] not in ('CREATE_COMPLETE', 'UPDATE_COMPLETE', 'IMPORT_COMPLETE', 'UPDATE_ROLLBACK_COMPLETE'):
        raise RuntimeError('Stack is not ready for deployment')
    previous = template_body(client, options.stack_name)
    if not REQUIRED.issubset(previous['Resources']):
        raise RuntimeError('Reconcile the existing backend resources into CloudFormation before deploying')
    function = client.call('lambda', 'get-function', '--function-name', options.function)
    config = function['Configuration']
    resource = previous['Resources']['ApiDataFetcherLambda']
    baseline_sha = resource.get('Metadata', {}).get('SafePathCodeSha256')
    if isinstance(baseline_sha, dict) and 'Ref' in baseline_sha:
        baseline_sha = next((p['ParameterValue'] for p in stack['Parameters'] if p['ParameterKey'] == baseline_sha['Ref']), None)
    if baseline_sha != config['CodeSha256']:
        raise RuntimeError('Lambda code drift detected; reconcile its current code before deploying')
    properties = resource['Properties']
    if properties.get('FunctionName') != options.function:
        raise RuntimeError('Stack does not own the intended function')
    api_id = client.call('cloudformation', 'describe-stack-resource', '--stack-name', options.stack_name,
                         '--logical-resource-id', 'ApiGateway')['StackResourceDetail']['PhysicalResourceId']
    if api_id != options.api_id:
        raise RuntimeError('Stack does not own the intended API')
    code = Path(options.lambda_zip).read_bytes()
    digest = hashlib.sha256(code).hexdigest()
    bucket = config['Environment']['Variables']['S3_BUCKET_NAME']
    key = 'lambda-releases/' + digest + '.zip'
    print(json.dumps({'stack': options.stack_name, 'function': options.function,
                      'codeSha256': checksum(code), 'apply': options.apply}, indent=2))
    if not options.apply:
        return None
    backup = new_backup(options.backup_dir)
    private_json(backup / 'lambda-configuration.json', config)
    private_json(backup / 'previous-template.json', previous)
    private_json(backup / 'stack-parameters.json', stack['Parameters'])
    if download is None:
        response = requests.get(function['Code']['Location'], timeout=30)
        response.raise_for_status()
        old_code = response.content
    else:
        old_code = download(function['Code']['Location'])
    if checksum(old_code) != config['CodeSha256']:
        raise RuntimeError('Downloaded rollback code checksum mismatch')
    (backup / 'previous-lambda.zip').write_bytes(old_code)
    manifest = {'status': 'prepared', 'stack': options.stack_name,
                'previousCodeSha256': config['CodeSha256'], 'newCodeSha256': checksum(code)}
    def journal(status, **fields):
        manifest.update(status=status, **fields)
        target = backup / 'deployment-status.json'
        if not target.exists():
            private_json(target, manifest)
        else:
            target.write_text(json.dumps(manifest, indent=2))
    journal('prepared')
    candidate = copy.deepcopy(previous)
    candidate['Resources']['ApiDataFetcherLambda']['Properties']['Code'] = {
        'S3Bucket': {'Ref': 'LambdaDeploymentBucket'}, 'S3Key': {'Ref': 'LambdaDeploymentKey'}}
    candidate['Resources']['ApiDataFetcherLambda'].setdefault('Metadata', {})['SafePathCodeSha256'] = {'Ref': 'LambdaDeploymentCodeSha256'}
    private_json(backup / 'candidate-template.json', candidate)
    private_json(backup / 'candidate-parameters.json', parameter_values(stack['Parameters'], {
        'LambdaDeploymentBucket': bucket, 'LambdaDeploymentKey': key, 'LambdaDeploymentCodeSha256': checksum(code)}))
    previous_parameters = {item['ParameterKey']: item['ParameterValue'] for item in stack['Parameters']
                           if item['ParameterKey'] in ('LambdaDeploymentBucket', 'LambdaDeploymentKey', 'LambdaDeploymentCodeSha256')}
    private_json(backup / 'rollback-parameters.json', parameter_values(stack['Parameters'], previous_parameters))
    attempted = False
    try:
        client.call('s3api', 'put-object', '--bucket', bucket, '--key', key,
                    '--body', str(options.lambda_zip), '--server-side-encryption', 'AES256')
        change = guarded_update(client, options.stack_name, backup / 'candidate-template.json',
                                backup / 'candidate-parameters.json', 'safepath-code-' + backup.name)
        if change:
            journal('updating', changeSet=change)
            attempted = True
            client.call('cloudformation', 'execute-change-set', '--change-set-name', change)
            client.call('cloudformation', 'wait', 'stack-update-complete', '--stack-name', options.stack_name)
        event = backup / 'refresh-event.json'
        private_json(event, {'action': 'refresh-safety-data'})
        response_file = backup / 'refresh-response.json'
        invocation = client.call('lambda', 'invoke', '--function-name', options.function,
                                 '--payload', 'fileb://' + str(event), str(response_file))
        if invocation.get('FunctionError'):
            raise RuntimeError('Snapshot warm-up failed')
        result = json.loads(response_file.read_text())
        if not result.get('refreshedAt') or not all(isinstance(result.get(k), int) for k in ('policeCalls', 'open311Reports')):
            raise RuntimeError('Snapshot warm-up returned an invalid response')
        live = client.call('lambda', 'get-function', '--function-name', options.function)
        if live['Configuration']['CodeSha256'] != checksum(code):
            raise RuntimeError('Post-deployment code verification failed')
        journal('complete')
        print('Deployment complete. Private rollback artifacts:', backup)
        return backup
    except (Exception, KeyboardInterrupt) as error:
        journal('failed', failure=type(error).__name__)
        if attempted:
            try:
                state = settle_stack(client, options.stack_name)
                if state == 'UPDATE_ROLLBACK_FAILED':
                    raise RuntimeError('CloudFormation rollback needs manual recovery')
                if state != 'UPDATE_ROLLBACK_COMPLETE':
                    rollback = guarded_update(client, options.stack_name, backup / 'previous-template.json',
                                              backup / 'rollback-parameters.json', 'safepath-rollback-' + backup.name)
                    if rollback:
                        client.call('cloudformation', 'execute-change-set', '--change-set-name', rollback)
                        client.call('cloudformation', 'wait', 'stack-update-complete', '--stack-name', options.stack_name)
                restored = client.call('lambda', 'get-function', '--function-name', options.function)
                if restored['Configuration']['CodeSha256'] != config['CodeSha256']:
                    raise RuntimeError('Rollback code checksum mismatch')
                journal('rolled_back')
            except (Exception, KeyboardInterrupt) as rollback_error:
                journal('rollback_failed', rollbackFailure=type(rollback_error).__name__)
                raise RuntimeError(f'Deployment failed and rollback needs attention. Artifacts: {backup}') from rollback_error
        raise RuntimeError(f'Deployment failed; status and rollback artifacts: {backup}') from error


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--account', required=True)
    parser.add_argument('--api-id', required=True)
    parser.add_argument('--function', default='ApiDataFetcher')
    parser.add_argument('--stack-name', default='safepath-backend')
    parser.add_argument('--region', default='us-east-1')
    parser.add_argument('--lambda-zip', type=Path, required=True)
    parser.add_argument('--backup-dir', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    options = parser.parse_args()
    options.lambda_zip = options.lambda_zip.resolve()
    if not options.lambda_zip.is_file():
        parser.error('Lambda ZIP is missing')
    deploy(options)
