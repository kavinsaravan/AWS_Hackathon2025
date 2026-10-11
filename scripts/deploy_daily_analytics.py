#!/usr/bin/env python3
"""Deploy the isolated daily-analytics stack; preview unless --apply is supplied."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'infrastructure'))
from cloudformation_tools import load_template
from aws_deployment import AWSClient, AWSCommandError, new_backup, private_json


def check_changes(changes, expected):
    for change in changes:
        resource = change['ResourceChange']
        if resource['LogicalResourceId'] not in expected or resource['Action'] not in ('Add', 'Modify'):
            raise RuntimeError('Daily deployment would affect unexpected resources')
        if resource['Action'] != 'Modify' or resource.get('Replacement', 'False') == 'False':
            continue
        details = resource.get('Details', [])
        if (resource['LogicalResourceId'] == 'DailyRefreshPermission' and resource.get('Replacement') == 'Conditional'
                and details and all(d.get('Evaluation') == 'Dynamic' and d.get('ChangeSource') == 'ResourceAttribute'
                and d.get('CausingEntity') == 'DailyRefreshRule.Arn' and d.get('Target', {}).get('Name') == 'SourceArn' for d in details)):
            continue
        raise RuntimeError('Daily deployment would replace a resource')


def deploy(options):
    aws = AWSClient(options.region)
    if aws.call('sts', 'get-caller-identity')['Account'] != options.account:
        raise RuntimeError('AWS account does not match the intended deployment')
    def physical(logical):
        return aws.call('cloudformation','describe-stack-resource','--stack-name','safepath-backend',
                        '--logical-resource-id',logical)['StackResourceDetail']['PhysicalResourceId']
    api, bucket, table = physical('ApiGateway'), physical('CrimeDataBackupBucket'), physical('ApiDataCacheTable')
    if api != options.api_id:raise RuntimeError('Unexpected parent API')
    code = options.lambda_zip.read_bytes();digest = hashlib.sha256(code).hexdigest()
    key = 'lambda-releases/daily-analytics/' + digest + '.zip'
    template = load_template(options.template.read_text())
    expected = {'AnalyticsRole','AnalyticsLambda','DailyRefreshRule','DailyRefreshPermission','AnalyticsIntegration',
                'AnalyticsCsvRoute','AnalyticsSummaryRoute','AnalyticsManifestRoute','ApiPermission'}
    if set(template['Resources']) != expected:raise RuntimeError('Unexpected daily-analytics resources')
    print(json.dumps({'stack':options.stack_name,'parentApi':api,'dailyFunction':'SafePathDailyAnalytics','sha256':digest,'apply':options.apply}))
    if not options.apply:return
    backup=new_backup(options.backup_dir)
    private_json(backup/'candidate-template.json',template)
    params=[{'ParameterKey':k,'ParameterValue':v} for k,v in {
        'ExistingApiId':api,'ExistingDataBucket':bucket,'ExistingCacheTable':table,'DeploymentKey':key}.items()]
    private_json(backup/'candidate-parameters.json',params)
    mode='CREATE'
    try:
        prior=aws.call('cloudformation','describe-stacks','--stack-name',options.stack_name)['Stacks'][0]
        if prior['StackStatus'] not in ('CREATE_COMPLETE','UPDATE_COMPLETE','UPDATE_ROLLBACK_COMPLETE'):
            raise RuntimeError('Daily stack is not ready for update')
        mode='UPDATE'
        previous=aws.call('cloudformation','get-template','--stack-name',options.stack_name)['TemplateBody']
        private_json(backup/'previous-template.json',previous)
        private_json(backup/'previous-stack.json',prior)
    except AWSCommandError as error:
        if 'does not exist' not in str(error):raise
    aws.call('s3api','put-object','--bucket',bucket,'--key',key,'--body',str(options.lambda_zip),'--server-side-encryption','AES256')
    result=aws.call('cloudformation','create-change-set','--stack-name',options.stack_name,'--change-set-name','daily-'+backup.name,
                   '--change-set-type',mode,'--template-body','file://'+str(backup/'candidate-template.json'),
                   '--parameters','file://'+str(backup/'candidate-parameters.json'),'--capabilities','CAPABILITY_IAM')
    identifier=result['Id']
    aws.call('cloudformation','wait','change-set-create-complete','--change-set-name',identifier)
    changes=aws.call('cloudformation','describe-change-set','--change-set-name',identifier)['Changes']
    private_json(backup/'change-set.json',changes)
    check_changes(changes, expected)
    aws.call('cloudformation','execute-change-set','--change-set-name',identifier)
    aws.call('cloudformation','wait','stack-create-complete' if mode=='CREATE' else 'stack-update-complete','--stack-name',options.stack_name)
    private_json(backup/'refresh-event.json',{'action':'refresh-analytics'})
    response=backup/'refresh-response.json'
    invoked=aws.call('lambda','invoke','--function-name','SafePathDailyAnalytics','--cli-read-timeout','300',
                     '--payload','fileb://'+str(backup/'refresh-event.json'),str(response))
    if invoked.get('FunctionError'):raise RuntimeError('Initial daily export failed; inspect private deployment artifacts: '+str(backup))
    manifest=json.loads(response.read_text())
    if not isinstance(manifest.get('rows'),int) or manifest['rows']<1 or not manifest.get('refreshed_at_utc'):
        raise RuntimeError('Initial daily export returned invalid metadata')
    private_json(backup/'deployment-status.json',{'status':'complete','rows':manifest['rows'],'refreshed_at_utc':manifest['refreshed_at_utc']})
    print('Daily analytics deployed:',manifest['rows'],'rows; private artifacts:',backup)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--account',required=True);parser.add_argument('--api-id',required=True)
    parser.add_argument('--region',default='us-east-1');parser.add_argument('--stack-name',default='safepath-daily-analytics')
    parser.add_argument('--lambda-zip',type=Path,required=True);parser.add_argument('--backup-dir',type=Path,required=True)
    parser.add_argument('--template',type=Path,default=Path(__file__).resolve().parents[1]/'infrastructure/daily-analytics-template.yaml')
    parser.add_argument('--apply',action='store_true');options=parser.parse_args()
    options.lambda_zip=options.lambda_zip.resolve();options.template=options.template.resolve()
    deploy(options)
