import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from aws_deployment import guarded_update, settle_stack
from cloudformation_tools import load_template

class CloudFormationTests(unittest.TestCase):
    def test_intrinsic_output_shape_is_preserved(self):
        result=load_template('Resources: {}\nOutputs:\n  Arn:\n    Value: !GetAtt Function.Arn\n')
        self.assertEqual(result['Outputs']['Arn']['Value'],{'Fn::GetAtt':'Function.Arn'})

    def test_unsafe_yaml_constructors_are_rejected(self):
        with self.assertRaises(Exception):load_template('Resources: !!python/object/apply:os.system [echo unsafe]')

    def client(self,changes):
        client=Mock()
        def call(*args):
            if args[:2]==('cloudformation','create-change-set'):return {'Id':'change'}
            if args[:2]==('cloudformation','describe-change-set'):return {'Changes':changes}
            return {}
        client.call.side_effect=call
        return client

    def test_transitive_arn_dependency_is_allowed(self):
        change={'ResourceChange':{'LogicalResourceId':'SafetyDataRefreshPermission','Action':'Modify','Replacement':'Conditional',
                'Details':[{'Target':{'Name':'SourceArn'},'Evaluation':'Dynamic','ChangeSource':'ResourceAttribute',
                            'CausingEntity':'SafetyDataRefreshRule.Arn'}]}}
        self.assertEqual(guarded_update(self.client([change]),'stack',Path('/template'),Path('/params'),'name'),'change')

    def test_direct_changes_and_real_replacements_are_rejected(self):
        for replacement,source in [('True','ResourceAttribute'),('Conditional','DirectModification')]:
            change={'ResourceChange':{'LogicalResourceId':'SafetyDataRefreshPermission','Action':'Modify','Replacement':replacement,
                    'Details':[{'Target':{'Name':'SourceArn'},'Evaluation':'Dynamic','ChangeSource':source,
                                'CausingEntity':'SafetyDataRefreshRule.Arn'}]}}
            with self.assertRaises(RuntimeError):guarded_update(self.client([change]),'stack',Path('/template'),Path('/params'),'name')

    def test_automatic_rollback_terminal_state_is_accepted(self):
        client=Mock();client.call.return_value={'Stacks':[{'StackStatus':'UPDATE_ROLLBACK_COMPLETE'}]}
        self.assertEqual(settle_stack(client,'stack'),'UPDATE_ROLLBACK_COMPLETE')

if __name__=='__main__':unittest.main()
