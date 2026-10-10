"""CloudFormation deployment primitives with private, unique rollback artifacts."""
import base64
import hashlib
import json
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'infrastructure'))
from cloudformation_tools import load_template


class AWSCommandError(RuntimeError):
    pass


class AWSClient:
    def __init__(self, region):
        self.region = region

    def call(self, *args):
        result = subprocess.run(['aws', *map(str, args), '--region', self.region, '--output', 'json'],
                                capture_output=True, text=True)
        if result.returncode:
            raise AWSCommandError(result.stderr.strip())
        return json.loads(result.stdout) if result.stdout.strip() else {}


def private_json(path, value):
    # Create with private permissions before writing secrets, not afterwards.
    import os
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        json.dump(value, stream, indent=2)


def new_backup(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex)
    path.mkdir(mode=0o700, exist_ok=False)
    return path


def template_body(client, stack):
    response = client.call('cloudformation', 'get-template', '--stack-name', stack)
    body = response['TemplateBody']
    return load_template(body) if isinstance(body, str) else body


def checksum(data):
    return base64.b64encode(hashlib.sha256(data).digest()).decode()


def parameter_values(parameters, overrides=None):
    overrides = overrides or {}
    return [{'ParameterKey': parameter['ParameterKey'],
             **({'ParameterValue': overrides[parameter['ParameterKey']]}
                if parameter['ParameterKey'] in overrides else {'UsePreviousValue': True})}
            for parameter in parameters]


def guarded_update(client, stack, template_file, parameters_file, name):
    result = client.call('cloudformation', 'create-change-set', '--stack-name', stack,
                         '--change-set-name', name, '--change-set-type', 'UPDATE',
                         '--template-body', 'file://' + str(template_file),
                         '--parameters', 'file://' + str(parameters_file),
                         '--capabilities', 'CAPABILITY_NAMED_IAM')
    identifier = result['Id']
    try:
        client.call('cloudformation', 'wait', 'change-set-create-complete', '--change-set-name', identifier)
    except AWSCommandError:
        state = client.call('cloudformation', 'describe-change-set', '--change-set-name', identifier)
        if "didn't contain changes" in state.get('StatusReason', ''):
            return None
        raise
    changes = client.call('cloudformation', 'describe-change-set', '--change-set-name', identifier)['Changes']
    for change in changes:
        resource = change['ResourceChange']
        if resource['Action'] != 'Modify':
            raise RuntimeError('Deployment would add, delete, or import resources')
        logical = resource['LogicalResourceId']
        replacement = resource.get('Replacement', 'False')
        if logical == 'ApiDataFetcherLambda' and replacement == 'False':
            continue
        dependencies = {
            'LambdaIntegration': ('IntegrationUri', 'ApiDataFetcherLambda.Arn'),
            'SafetyDataRefreshRule': ('Targets', 'ApiDataFetcherLambda.Arn'),
            'ScheduledFetchRule': ('Targets', 'ApiDataFetcherLambda.Arn'),
            'SafetyDataRefreshPermission': ('SourceArn', 'SafetyDataRefreshRule.Arn'),
            'ScheduledFetchLambdaPermission': ('SourceArn', 'ScheduledFetchRule.Arn'),
        }
        expected = dependencies.get(logical)
        details = resource.get('Details', [])
        # CF reevaluates references when code changes, even though the named
        # function/rules keep their ARNs. Allow only these precise dependencies.
        if (not expected or replacement not in ('False', 'Conditional') or not details
                or any(detail.get('Evaluation') != 'Dynamic'
                       or detail.get('ChangeSource') != 'ResourceAttribute'
                       or detail.get('CausingEntity') != expected[1]
                       or detail.get('Target', {}).get('Name') != expected[0]
                       for detail in details)):
            raise RuntimeError('Deployment would modify or replace resources outside the Lambda update')
    return identifier


def settle_stack(client, stack, timeout_seconds=600):
    deadline = time.monotonic() + timeout_seconds
    while True:
        status = client.call('cloudformation', 'describe-stacks', '--stack-name', stack)['Stacks'][0]['StackStatus']
        if not status.endswith('_IN_PROGRESS'):
            return status
        if time.monotonic() >= deadline:
            raise RuntimeError('Stack did not reach a terminal state before rollback')
        time.sleep(2)
