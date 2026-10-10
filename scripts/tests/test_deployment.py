import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from aws_deployment import checksum, new_backup, AWSCommandError
from deploy_aws_backend import deploy

OLD=b'previous zip';NEW=b'new zip'

class FakeAWS:
    def __init__(self,failure=None):
        self.failure=failure;self.failed=False;self.sha=checksum(OLD);self.calls=[];self.changes={};self.executions=0
        self.template={'Resources':{key:{'Type':'fixture'} for key in ('ScoreRoutesRoute','SafetyDataRefreshRule','SafetyDataRefreshPermission','CrimeDataBackupBucket')},
                       'Parameters':{}}
        self.template['Resources']['ApiDataFetcherLambda']={'Type':'AWS::Lambda::Function',
            'Properties':{'FunctionName':'ApiDataFetcher','Code':{'S3Bucket':{'Ref':'LambdaDeploymentBucket'},'S3Key':{'Ref':'LambdaDeploymentKey'}}},
            'Metadata':{'SafePathCodeSha256':{'Ref':'LambdaDeploymentCodeSha256'}}}
        self.parameters=[{'ParameterKey':key,'ParameterValue':value} for key,value in
            [('LambdaDeploymentBucket','bucket'),('LambdaDeploymentKey','old.zip'),('LambdaDeploymentCodeSha256',checksum(OLD)),('ApiKey','****')]]

    def call(self,*args):
        self.calls.append(args);command=tuple(args[:2])
        def value(key):return args[args.index(key)+1]
        if (self.failure==command and not self.failed
            and (command!=('cloudformation','wait') or args[2]=='stack-update-complete')):
            self.failed=True
            if command==('cloudformation','execute-change-set'):
                self.sha=checksum(NEW) # Model an ambiguous accepted request.
            raise AWSCommandError('injected failure')
        if command==('sts','get-caller-identity'):return {'Account':'account'}
        if command==('cloudformation','describe-stacks'):return {'Stacks':[{'StackStatus':'UPDATE_COMPLETE','Parameters':self.parameters}]}
        if command==('cloudformation','get-template'):return {'TemplateBody':self.template}
        if command==('cloudformation','describe-stack-resource'):return {'StackResourceDetail':{'PhysicalResourceId':'api'}}
        if command==('lambda','get-function'):
            return {'Configuration':{'FunctionName':'ApiDataFetcher','CodeSha256':self.sha,'Environment':{'Variables':{'S3_BUCKET_NAME':'bucket'}}},'Code':{'Location':'fixture'}}
        if command==('cloudformation','create-change-set'):
            name=value('--change-set-name')
            params=json.loads(Path(value('--parameters')[7:]).read_text())
            self.changes[name]=next(p['ParameterValue'] for p in params if p['ParameterKey']=='LambdaDeploymentCodeSha256')
            return {'Id':name}
        if command==('cloudformation','describe-change-set'):
            return {'Changes':[{'ResourceChange':{'LogicalResourceId':'ApiDataFetcherLambda','Action':'Modify','Replacement':'False'}}]}
        if command==('cloudformation','execute-change-set'):
            self.sha=self.changes[value('--change-set-name')];self.executions+=1
        if command==('lambda','invoke'):
            Path(args[-1]).write_text(json.dumps({'refreshedAt':'2026-10-10T02:00:00Z','policeCalls':1,'open311Reports':1}))
            return {}
        return {}

class DeploymentTests(unittest.TestCase):
    def setUp(self):
        output=patch('builtins.print');output.start();self.addCleanup(output.stop)

    def options(self,folder,apply=True):
        code=Path(folder)/'new.zip';code.write_bytes(NEW)
        return SimpleNamespace(region='region',account='account',stack_name='stack',function='ApiDataFetcher',api_id='api',
                               lambda_zip=code,backup_dir=Path(folder)/'backups',apply=apply)

    def test_reusing_backup_root_never_overwrites_previous_artifacts(self):
        with tempfile.TemporaryDirectory() as folder:
            a=new_backup(folder);(a/'previous-lambda.zip').write_bytes(OLD)
            b=new_backup(folder)
            self.assertNotEqual(a,b)
            self.assertEqual((a/'previous-lambda.zip').read_bytes(),OLD)
            self.assertEqual(a.stat().st_mode & 0o777,0o700)

    def test_preview_does_not_write_or_modify_aws(self):
        with tempfile.TemporaryDirectory() as folder:
            aws=FakeAWS();options=self.options(folder,False)
            deploy(options,aws,lambda _:OLD)
            self.assertFalse(options.backup_dir.exists())
            self.assertFalse(any(call[:2] in [('s3api','put-object'),('cloudformation','create-change-set')] for call in aws.calls))

    def test_success_uses_cloudformation_and_private_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            aws=FakeAWS();backup=deploy(self.options(folder),aws,lambda _:OLD)
            self.assertEqual(aws.sha,checksum(NEW))
            self.assertEqual(json.loads((backup/'deployment-status.json').read_text())['status'],'complete')
            self.assertEqual((backup/'lambda-configuration.json').stat().st_mode & 0o777,0o600)
            self.assertFalse(any(call[:2]==('lambda','update-function-code') for call in aws.calls))

    def test_failure_before_stack_execution_keeps_live_code(self):
        for failure in [('s3api','put-object'),('cloudformation','create-change-set')]:
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as folder:
                aws=FakeAWS(failure)
                with self.assertRaises(RuntimeError):deploy(self.options(folder),aws,lambda _:OLD)
                self.assertEqual(aws.sha,checksum(OLD))
                self.assertEqual(aws.executions,0)

    def test_failures_across_execution_and_verification_restore_code(self):
        for failure in [('cloudformation','execute-change-set'),('cloudformation','wait'),('lambda','invoke')]:
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as folder:
                aws=FakeAWS(failure)
                with self.assertRaises(RuntimeError):deploy(self.options(folder),aws,lambda _:OLD)
                self.assertEqual(aws.sha,checksum(OLD))
                status=next((Path(folder)/'backups').glob('*/deployment-status.json'))
                # A failed change-set waiter has not touched live code.
                self.assertIn(json.loads(status.read_text())['status'],['rolled_back','failed'])

    def test_invalid_warmup_response_rolls_back(self):
        with tempfile.TemporaryDirectory() as folder:
            aws=FakeAWS()
            real=aws.call
            def call(*args):
                if args[:2]==('lambda','invoke'):
                    Path(args[-1]).write_text('{}')
                    return {}
                return real(*args)
            aws.call=call
            with self.assertRaises(RuntimeError):deploy(self.options(folder),aws,lambda _:OLD)
            self.assertEqual(aws.sha,checksum(OLD))
            self.assertEqual(aws.executions,2)

    def test_rollback_failure_is_reported_and_artifacts_retained(self):
        with tempfile.TemporaryDirectory() as folder:
            aws=FakeAWS(('lambda','invoke'))
            real=aws.call
            def call(*args):
                if args[:2]==('cloudformation','execute-change-set') and aws.executions==1:
                    raise AWSCommandError('rollback failed')
                return real(*args)
            aws.call=call
            with self.assertRaisesRegex(RuntimeError,'rollback needs attention'):
                deploy(self.options(folder),aws,lambda _:OLD)
            status=next((Path(folder)/'backups').glob('*/deployment-status.json'))
            self.assertEqual(json.loads(status.read_text())['status'],'rollback_failed')
            self.assertEqual((status.parent/'previous-lambda.zip').read_bytes(),OLD)

    def test_drift_and_missing_ownership_are_rejected_before_mutation(self):
        with tempfile.TemporaryDirectory() as folder:
            aws=FakeAWS();aws.sha='unexpected'
            with self.assertRaisesRegex(RuntimeError,'drift'):deploy(self.options(folder),aws,lambda _:OLD)
            aws=FakeAWS();del aws.template['Resources']['ScoreRoutesRoute']
            with self.assertRaisesRegex(RuntimeError,'Reconcile'):deploy(self.options(folder),aws,lambda _:OLD)

    def test_checksum_mismatch_prevents_updates(self):
        with tempfile.TemporaryDirectory() as folder:
            aws=FakeAWS()
            with self.assertRaisesRegex(RuntimeError,'checksum'):deploy(self.options(folder),aws,lambda _:b'wrong backup')
            self.assertEqual(aws.executions,0)

if __name__=='__main__':unittest.main()
