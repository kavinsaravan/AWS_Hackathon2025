#!/usr/bin/env python3
"""Prepare an import and code baseline for the existing SafePath stack.

Preparation is read-only except private local files. Execute the reviewed import
change set first, then the reviewed baseline update. Existing resources are retained.
"""
import argparse
import copy
import hashlib
import json
import re
import textwrap
import yaml
from pathlib import Path
import requests
from aws_deployment import AWSClient, checksum, new_backup, private_json, template_body


def prepare(options, client=None):
    client = client or AWSClient(options.region)
    if client.call('sts', 'get-caller-identity')['Account'] != options.account:
        raise RuntimeError('Unexpected AWS account')
    original_body = client.call('cloudformation','get-template','--stack-name',options.stack_name)['TemplateBody']
    from cloudformation_tools import load_template
    current = load_template(original_body) if isinstance(original_body,str) else original_body
    function = client.call('lambda', 'get-function', '--function-name', options.function)
    config = function['Configuration']
    stack = client.call('cloudformation', 'describe-stacks', '--stack-name', options.stack_name)['Stacks'][0]
    routes = client.call('apigatewayv2', 'get-routes', '--api-id', options.api_id)['Items']
    route = next(r for r in routes if r['RouteKey'] == 'POST /score-routes')
    rule = client.call('events', 'describe-rule', '--name', 'SafePathSafetyDataRefresh')
    targets = client.call('events', 'list-targets-by-rule', '--rule', rule['Name'])['Targets']
    policy = json.loads(client.call('lambda', 'get-policy', '--function-name', options.function)['Policy'])
    statement = next(s for s in policy['Statement'] if s['Sid'] == 'SafePathSafetySnapshotRefresh')
    if statement['Condition']['ArnLike']['AWS:SourceArn'] != rule['Arn']:
        raise RuntimeError('Refresh permission does not match the schedule')
    bucket = config['Environment']['Variables']['S3_BUCKET_NAME']
    if bucket != 'safepath-crime-data-'+options.account:
        raise RuntimeError('Unexpected backup bucket name')
    definitions = {
        'ScoreRoutesRoute': {'Type':'AWS::ApiGatewayV2::Route', 'Properties':{
            'ApiId': {'Ref':'ApiGateway'}, 'RouteKey':route['RouteKey'], 'Target':{'Fn::Sub':'integrations/${LambdaIntegration}'}}},
        'SafetyDataRefreshRule': {'Type':'AWS::Events::Rule', 'Properties':{
            **{key:rule[key] for key in ('Name','Description','ScheduleExpression','State','EventBusName') if key in rule},
            'Targets':[{**target,'Arn':{'Fn::GetAtt':['ApiDataFetcherLambda','Arn']}} if target['Arn']==config['FunctionArn'] else target for target in targets]}},
        'SafetyDataRefreshPermission': {'Type':'AWS::Lambda::Permission','Properties':{
            'FunctionName': {'Ref':'ApiDataFetcherLambda'}, 'Action':'lambda:InvokeFunction',
            'Principal':'events.amazonaws.com', 'SourceArn':{'Fn::GetAtt':['SafetyDataRefreshRule','Arn']}}},
        'CrimeDataBackupBucket': {'Type':'AWS::S3::Bucket','Properties':{'BucketName':{'Fn::Sub':'safepath-crime-data-${AWS::AccountId}'}}},
    }
    identifiers = {
        'ScoreRoutesRoute': {'ApiId':options.api_id, 'RouteId':route['RouteId']},
        'SafetyDataRefreshRule': {'Arn':rule['Arn']},
        'SafetyDataRefreshPermission': {'FunctionName':options.function,'Id':statement['Sid']},
        'CrimeDataBackupBucket': {'BucketName':bucket},
    }
    candidate = copy.deepcopy(current)
    imports = []
    for logical, resource in definitions.items():
        if logical in current['Resources']:
            continue
        resource['DeletionPolicy'] = 'Retain'
        resource['UpdateReplacePolicy'] = 'Retain'
        candidate['Resources'][logical] = resource
        imports.append({'ResourceType':resource['Type'],'LogicalResourceId':logical,
                        'ResourceIdentifier':identifiers[logical]})
    folder = new_backup(options.output_dir)
    private_json(folder/'previous-template.json',current)
    private_json(folder/'import-template.json',candidate)
    if isinstance(original_body,str):
        # Import compares existing Outputs strictly. Preserve their YAML syntax.
        resources_start = re.search(r'^Resources:\s*$',original_body,re.M)
        if not resources_start:
            raise RuntimeError('Live template has no Resources section')
        next_section = re.search(r'^[A-Za-z][A-Za-z0-9]*:',original_body[resources_start.end():],re.M)
        end = resources_start.end()+next_section.start() if next_section else len(original_body)
        new_resources = {item['LogicalResourceId']:candidate['Resources'][item['LogicalResourceId']] for item in imports}
        addition = textwrap.indent(yaml.safe_dump(new_resources,sort_keys=False),'  ')
        (folder/'import-template.yaml').write_text(original_body[:end]+'\n'+addition+'\n'+original_body[end:])
    private_json(folder/'resources-to-import.json',imports)
    private_json(folder/'import-parameters.json',[{'ParameterKey':p['ParameterKey'],'UsePreviousValue':True} for p in stack['Parameters']])
    response = requests.get(function['Code']['Location'],timeout=30)
    response.raise_for_status()
    code = response.content
    if checksum(code) != config['CodeSha256']:
        raise RuntimeError('Current Lambda code checksum mismatch')
    (folder/'baseline-lambda.zip').write_bytes(code)
    key = 'lambda-releases/'+hashlib.sha256(code).hexdigest()+'.zip'
    baseline = copy.deepcopy(candidate)
    parameters = baseline.setdefault('Parameters',{})
    parameters.update({
        'LambdaDeploymentBucket': {'Type':'String','Description':'S3 bucket containing Lambda release ZIPs'},
        'LambdaDeploymentKey': {'Type':'String','Description':'Immutable S3 release key'},
        'LambdaDeploymentCodeSha256': {'Type':'String','Description':'Base64 SHA256 of the deployed Lambda ZIP'},
        'DataSfToken': {'Type':'String','Default':'','NoEcho':True,'Description':'Optional DataSF app token'},
    })
    resource = baseline['Resources']['ApiDataFetcherLambda']
    resource['Properties']['Code'] = {'S3Bucket':{'Ref':'LambdaDeploymentBucket'},'S3Key':{'Ref':'LambdaDeploymentKey'}}
    resource.setdefault('Metadata',{})['SafePathCodeSha256'] = {'Ref':'LambdaDeploymentCodeSha256'}
    resource['Properties']['Environment']['Variables'].update({
        'S3_BUCKET_NAME':{'Ref':'CrimeDataBackupBucket'}, 'SAFETY_CACHE_MAX_AGE_SECONDS':'300',
        'DATASF_API_KEY':{'Ref':'DataSfToken'}})
    role = baseline['Resources']['LambdaExecutionRole']['Properties']
    if not any(p['PolicyName']=='S3Access' for p in role.get('Policies',[])):
        # Match the already deployed inline policy, now declared by CloudFormation.
        s3_policy = client.call('iam','get-role-policy','--role-name',config['Role'].rsplit('/',1)[1],'--policy-name','S3Access')['PolicyDocument']
        for item in s3_policy['Statement']:
            item['Resource']=[{'Fn::GetAtt':['CrimeDataBackupBucket','Arn']}, {'Fn::Sub':'${CrimeDataBackupBucket.Arn}/*'}]
        role.setdefault('Policies',[]).append({'PolicyName':'S3Access','PolicyDocument':s3_policy})
    new_values = {'LambdaDeploymentBucket':bucket,'LambdaDeploymentKey':key,
                  'LambdaDeploymentCodeSha256':config['CodeSha256'],
                  'DataSfToken':config['Environment']['Variables'].get('DATASF_API_KEY','')}
    private_json(folder/'baseline-template.json',baseline)
    private_json(folder/'baseline-parameters.json',
                 [{'ParameterKey':p['ParameterKey'], **({'ParameterValue':new_values[p['ParameterKey']]} if p['ParameterKey'] in new_values else {'UsePreviousValue':True})} for p in stack['Parameters']]
                 + [{'ParameterKey':key,'ParameterValue':value} for key,value in new_values.items() if key not in {p['ParameterKey'] for p in stack['Parameters']}])
    private_json(folder/'reconciliation-summary.json',{'stack':options.stack_name,'imports':[r['LogicalResourceId'] for r in imports],
                 'bucket':bucket,'baselineKey':key,'codeSha256':config['CodeSha256']})
    print('Prepared reconciliation artifacts:',folder)
    print('Import resources:',', '.join(r['LogicalResourceId'] for r in imports))
    return folder


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--account',required=True)
    parser.add_argument('--api-id',required=True)
    parser.add_argument('--stack-name',default='safepath-backend')
    parser.add_argument('--function',default='ApiDataFetcher')
    parser.add_argument('--region',default='us-east-1')
    parser.add_argument('--output-dir',type=Path,required=True)
    prepare(parser.parse_args())
