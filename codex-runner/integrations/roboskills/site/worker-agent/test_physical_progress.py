import unittest
from physical_progress import lifecycle_events,admission_event,current_stage,task_outcome

class ProgressTests(unittest.TestCase):
    def test_preparing_is_not_assumed_admitted(self):
        key,_,detail=current_stage({'status':'preparing','session_id':'s'})
        self.assertEqual(key,'submitting')
        self.assertIn('not yet',detail)

    def test_real_lease_completes_queue_before_preparation(self):
        event={'id':2,'kind':'lifecycle','timestamp':20,'details':{'reason':'jetson_leased','episode_id':'e'}}
        state={'status':'preparing','interactions':{'events':[event]}}
        self.assertEqual(admission_event(lifecycle_events(state))['timestamp'],20)
        self.assertEqual(current_stage(state)[0],'preparing')

    def test_preparing_snapshot_without_lease_is_not_admission(self):
        self.assertEqual(current_stage({'status':'preparing','episode_id':'e'})[0],'submitting')
        self.assertEqual(current_stage({'status':'preparing','episode_id':'e','lease_id':'private'})[0],'preparing')

    def test_projection_excludes_capabilities_and_contact(self):
        state={'interactions':{'events':[{'id':1,'kind':'joined','timestamp':10,'details':{'session_id':'s','email':'private','session_capability':'secret'}},{'id':2,'kind':'model_request','details':{'prompt':'private'}}]}}
        self.assertEqual(lifecycle_events(state),[{'id':1,'kind':'joined','timestamp':10,'details':{'session_id':'s'}}])

    def test_queue_and_model_wait_are_distinct(self):
        self.assertIn('3',current_stage({'status':'queued','queue_position':3})[2])
        self.assertEqual(current_stage({'status':'running','provider':{'vision':{'state':'requesting'}}})[0],'planning')
        self.assertEqual(current_stage({'status':'running','provider':{'pending_packet':True}})[0],'moving')

    def test_stop_takes_priority(self):
        self.assertEqual(current_stage({'status':'queued'},True)[0],'stopping')

if __name__=='__main__':unittest.main()

class OutcomeTests(unittest.TestCase):
    def test_no_motion_is_not_presented_as_task_success(self):
        value=task_outcome({'status':'finished','packets_submitted':0,'provider':{'outcome':{'status':'done','reason':'No depth available.'}}})
        self.assertEqual(value['taskStatus'],'not_attempted')
        self.assertEqual(value['reason'],'No depth available.')
        self.assertFalse(value['nativeScore'])

    def test_visual_success_is_labelled_agent_report(self):
        value=task_outcome({'status':'finished','packets_submitted':8,'provider':{'outcome':{'status':'done','task_status':'reported_success','reason':'Stack remained stable after withdrawal.'}}})
        self.assertEqual(value['label'],'Agent reports task completed')
        self.assertEqual(value['assessmentSource'],'agent_report_unscored')

    def test_failure_overrides_a_success_report(self):
        value=task_outcome({'status':'safety_aborted','error':'Measured completion missing','provider':{'outcome':{'task_status':'reported_success'}}})
        self.assertEqual(value['status'],'failed')
        self.assertEqual(value['reason'],'Measured completion missing')
