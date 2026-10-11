import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from deploy_daily_analytics import check_changes

class DailyDeploymentTests(unittest.TestCase):
    def test_own_additions_and_non_replacing_updates_are_allowed(self):
        check_changes([{'ResourceChange':{'LogicalResourceId':'AnalyticsLambda','Action':'Add'}},
                       {'ResourceChange':{'LogicalResourceId':'AnalyticsLambda','Action':'Modify','Replacement':'False'}}],{'AnalyticsLambda'})

    def test_only_known_dynamic_permission_reference_is_allowed(self):
        resource={'LogicalResourceId':'DailyRefreshPermission','Action':'Modify','Replacement':'Conditional','Details':[
            {'Evaluation':'Dynamic','ChangeSource':'ResourceAttribute','CausingEntity':'DailyRefreshRule.Arn','Target':{'Name':'SourceArn'}}]}
        check_changes([{'ResourceChange':resource}],{'DailyRefreshPermission'})
        resource['Details'][0]['CausingEntity']='OtherRule.Arn'
        with self.assertRaises(RuntimeError):check_changes([{'ResourceChange':resource}],{'DailyRefreshPermission'})

    def test_deletion_foreign_resources_and_lambda_replacement_are_rejected(self):
        for r in [{'LogicalResourceId':'AnalyticsLambda','Action':'Remove'},
                  {'LogicalResourceId':'ApiDataFetcherLambda','Action':'Modify','Replacement':'False'},
                  {'LogicalResourceId':'AnalyticsLambda','Action':'Modify','Replacement':'True'}]:
            with self.subTest(resource=r),self.assertRaises(RuntimeError):check_changes([{'ResourceChange':r}],{'AnalyticsLambda'})

if __name__=='__main__':unittest.main()
