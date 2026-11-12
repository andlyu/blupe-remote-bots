"""Real Kinex buffer -> canonical serializer tests. Wire spy sends no hardware."""
from copy import deepcopy
import io,json,math,time,unittest
from unittest.mock import patch
import numpy as np
from remote_yam.kinex_policy import KinexPackets,KinexAPI
from remote_yam.session import HttpSessionAPI,_trajectory_waypoints,MAX_COMMANDS


def observation():
    q=np.rad2deg([-.0311,.794,.6167,-.3748,-.0364,-.0246]).tolist()
    return dict(source='hardware',jetson_id='yam-1',settled=True,homed=True,safety={'ok':True},observed_at=time.time(),
        left_joints_deg=q,right_joints_deg=q.copy(),left_gripper=.9992793312193716,right_gripper=.9947321472782467)

class CommandContract(unittest.TestCase):
    def setUp(self):
        self.p=KinexPackets();self.obs=observation();self.sent=[]
        self.api=HttpSessionAPI('https://offline.invalid',supports_trajectories=True)
        self.api._session_capabilities['offline']='offline-only-capability'
        def wire(req,**kwargs):
            self.sent.append(json.loads(req.data));return io.BytesIO(b'{"accepted":true}')
        self.wire=patch('remote_yam.session.request.urlopen',side_effect=wire);self.wire.start();self.addCleanup(self.wire.stop)
    def submit(self,device,args,obs=None):
        points=self.p.build(device,args,obs or self.obs,7)
        self.api.submit_trajectory('offline','ep_offline','lease_offline','traj_offline',10.,points)
        return self.sent[-1]['waypoints']
    def test_both_gripper_endpoints_and_fractional_starts_exact_wire(self):
        for arm in ('left','right'):
            for target in (0.,1.,.37,1e-15,1-1e-15):
                with self.subTest(arm=arm,target=target):
                    points=self.submit(arm+'_gripper',{'actions':[target],'duration_s':1.})
                    self.assertEqual(points[-1][arm+'_gripper'],target)
                    self.assertEqual([p['step_id'] for p in points],list(range(7,17)))
                    before=self.obs[arm+'_gripper'];other='right' if arm=='left' else 'left'
                    for p in points:
                        self.assertTrue(0<=p[arm+'_gripper']<=1)
                        self.assertLessEqual(abs(p[arm+'_gripper']-before),.1+1e-12);before=p[arm+'_gripper']
                        self.assertEqual(p[other+'_gripper'],self.obs[other+'_gripper'])
                        for side in ('left','right'):self.assertEqual(p[side+'_joints_deg'],self.obs[side+'_joints_deg'])
                    self.assertEqual(_trajectory_waypoints(points),points)
    def test_both_joint_paths_and_preservation(self):
        for arm in ('left','right'):
            for delta in (-.03,.03):
                target=np.deg2rad(self.obs[arm+'_joints_deg']).tolist();target[-1]+=delta
                points=self.submit(arm+'_arm',dict(actions=[target],duration_s=.5))
                self.assertAlmostEqual(math.radians(points[-1][arm+'_joints_deg'][-1]),target[-1])
                other='right' if arm=='left' else 'left'
                previous=np.deg2rad(self.obs[arm+'_joints_deg'])
                for p in points:
                    current=np.deg2rad(p[arm+'_joints_deg']);self.assertLessEqual(np.max(np.abs(current-previous)),.035+1e-12);previous=current
                    self.assertEqual(p[other+'_joints_deg'],self.obs[other+'_joints_deg'])
                    for side in ('left','right'):self.assertEqual(p[side+'_gripper'],self.obs[side+'_gripper'])
    def test_invalid_gripper_targets_zero_dispatch(self):
        for arm in ('left','right'):
            for value in (-1e-16,1+1e-15,-1,2,float('nan'),float('inf'),True,None,'0'):
                before=len(self.sent)
                with self.assertRaises(ValueError):self.submit(arm+'_gripper',dict(actions=[value],duration_s=1.))
                self.assertEqual(before,len(self.sent))
    def test_invalid_joint_targets_and_sample_velocity_zero_dispatch(self):
        for arm in ('left','right'):
            for bad in (float('nan'),float('inf'),100,True,None):
                target=np.deg2rad(self.obs[arm+'_joints_deg']).tolist();target[-1]=bad
                with self.assertRaises(ValueError):self.submit(arm+'_arm',dict(actions=[target],duration_s=.5))
        target=np.deg2rad(self.obs['left_joints_deg']).tolist();target[-1]+=.1
        with self.assertRaises(ValueError):self.submit('left_arm',dict(actions=[target],duration_s=.1))
        self.assertEqual(self.sent,[])
    def test_stale_missing_safety_unsettled_or_wrong_robot_zero_dispatch(self):
        for changed in ({'observed_at':time.time()-3},{'source':'simulation'},{'settled':False},{'homed':False},{'safety':{}},{'jetson_id':'other'}):
            with self.assertRaises(ValueError):self.submit('left_gripper',dict(actions=[0],duration_s=1.),dict(self.obs,**changed))
        self.assertEqual(self.sent,[])
    def test_malformed_duration_budget_and_unadvertised_device(self):
        for args in ({'actions':[0],'duration_s':0},{'actions':[0],'duration_s':7},{'actions':[],'duration_s':1},{'actions':[0],'duration_s':1,'extra':1}):
            with self.assertRaises(ValueError):self.submit('left_gripper',args)
        with self.assertRaises(ValueError):self.submit('base',dict(actions=[0],duration_s=1))
        with self.assertRaises(ValueError):self.p.build('left_gripper',dict(actions=[0],duration_s=1),self.obs,MAX_COMMANDS-2)
        self.assertEqual(self.sent,[])
    def test_raw_serialized_negative_gripper_residual_rejected(self):
        bad={k:deepcopy(self.obs[k]) for k in ('left_joints_deg','right_joints_deg','left_gripper','right_gripper')}
        bad.update(step_id=0,left_gripper=-1.1102230246251565e-16)
        with self.assertRaises(ValueError):self.api.submit_trajectory('offline','ep_offline','lease_offline','traj_offline',10,[bad])
        self.assertEqual(self.sent,[])

if __name__=='__main__':unittest.main()

class BridgeRegression(unittest.TestCase):
    def test_gateway_final_without_source_requires_independent_fresh_hardware(self):
        p=self.adapter();fresh=observation();p._read=lambda:deepcopy(fresh)
        p._target={k:deepcopy(fresh[k]) for k in ('left_joints_deg','right_joints_deg','left_gripper','right_gripper')}
        gateway=deepcopy(fresh);gateway.pop('source');gateway['homed']=False
        self.assertEqual(p.validate_trajectory_final(gateway)['source'],'hardware')
        p._latest=dict(fresh,episode_id='episode');p.trajectory_completed(gateway,10)
        self.assertEqual(p._latest['episode_id'],'episode')
        for changed in ({'source':'simulation'},{'settled':False},{'observed_at':time.time()-3},{'left_gripper':0}):
            before=deepcopy(fresh);fresh.update(changed)
            with self.assertRaises(RuntimeError):p.validate_trajectory_final(gateway)
            fresh.clear();fresh.update(before)
        bad=deepcopy(gateway);bad['right_gripper']=0
        with self.assertRaises(RuntimeError):p.validate_trajectory_final(bad)

    def test_startup_home_attestation_is_required_and_bound_to_current_lease(self):
        p=self.adapter();obs=observation();obs['episode_id']='episode';p._latest=deepcopy(obs);p._lease='lease'
        session=dict(status='running',episode_id='episode',lease_id='lease')
        p.api.get_session=lambda *a:session;p.api.get_robot_observation=lambda *a:deepcopy(obs)
        obs['homed']=False
        with self.assertRaisesRegex(RuntimeError,'startup Home'):p._verify_startup_home()
        obs['homed']=True;p._verify_startup_home();obs['homed']=False
        obs['right_joints_deg'][-1]+=math.degrees(.08)
        item=self.item();p._pending=item;p._queue.put(item)
        self.assertEqual(len(p.build_trajectory('offline after Home',deepcopy(obs),0)),10)
        session['lease_id']='other'
        with self.assertRaisesRegex(RuntimeError,'lease changed'):p._read()

    def adapter(self):
        import tempfile
        from remote_yam.kinex_policy import KinexAdapter
        from types import SimpleNamespace
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        api=SimpleNamespace(session_id='offline',policy=None,stop_session=lambda *a,**k:{'status':'stopped'})
        policy=KinexAdapter('/tmp/offline-upstream',directory.name,api,None)
        policy._thread=object()  # Never launch an agent in these race tests.
        return policy
    def item(self):
        import threading
        return dict(device='left_gripper',args=dict(actions=[0.],duration_s=1.),event=threading.Event(),state={},result=None,error=None)
    def test_active_buffer_rejects_superseding_write_before_enqueue(self):
        p=self.adapter();p._active=True;p._read=observation
        with self.assertRaisesRegex(ValueError,'buffer owns the gateway'):
            p._device(dict(device='left_gripper',action='write',args=dict(actions=[0],duration_s=1)))
        self.assertTrue(p._queue.empty());self.assertIsNone(p._pending)

    def test_cancel_during_read_returns_no_buffer(self):
        import threading
        p=self.adapter();item=self.item();p._pending=item;p._queue.put(item)
        entered=threading.Event();release=threading.Event();result=[]
        def read():entered.set();release.wait(2);return observation()
        p._read=read
        def build():
            try:result.append(p.build_trajectory('offline',observation(),0))
            except RuntimeError:result.append('cancelled')
        thread=threading.Thread(target=build);thread.start();self.assertTrue(entered.wait(1))
        p.request_stop(terminate_agent=False);release.set();thread.join(2)
        self.assertEqual(result,['cancelled']);self.assertTrue(item['event'].is_set());self.assertIsNone(item['result'])
    def test_late_ack_after_stop_never_reports_success(self):
        from remote_yam.session import SessionAPIError
        p=self.adapter();p._pending=self.item();p._stop.set()
        with self.assertRaises(SessionAPIError):p.accepted({'trajectory_id':'offline'})
        self.assertIsNone(p._pending['result'])
    def test_stop_failure_is_not_success(self):
        p=self.adapter()
        def failure(*a,**k):raise OSError('offline synthetic stop failure')
        p.api.stop_session=failure
        with self.assertRaisesRegex(RuntimeError,'stop_failed'):p._device(dict(device='left_arm',action='stop'))
        self.assertIn('stop_failed',p.public_config()['stop_error'])
    def test_no_spawn_after_cancellation(self):
        p=self.adapter();p._stop.set()
        with patch('remote_yam.kinex_policy.subprocess.Popen') as spawn:
            with self.assertRaises(RuntimeError):p._spawn(['offline-never-executed'])
            spawn.assert_not_called()
    def test_final_gripper_mismatch_cannot_complete(self):
        p=self.adapter();p._target={k:deepcopy(observation()[k]) for k in ('left_joints_deg','right_joints_deg','left_gripper','right_gripper')}
        p._target['left_gripper']=0
        with self.assertRaisesRegex(RuntimeError,'gripper target'):p.trajectory_completed(observation(),10)
        self.assertFalse(p._finished_normally)
    def test_full_ack_validated_before_driver_success(self):
        from types import SimpleNamespace
        from remote_yam.session import SessionAPIError
        obs=observation();point={k:deepcopy(obs[k]) for k in ('left_joints_deg','right_joints_deg','left_gripper','right_gripper')};point['step_id']=7
        receipt=dict(schema_version=1,accepted=True,duplicate=False,session_id='s',episode_id='e',lease_id='l',trajectory_id='t',first_step_id=7,last_step_id=7,waypoint_count=1,dispatched_at=time.time())
        for patch_value in ({'waypoint_count':2},{'dispatched_at':float('nan')},{'duplicate':1},{'extra':1},{'schema_version':2},{'last_step_id':8}):
            seen=[];api=KinexAPI(SimpleNamespace(submit_trajectory=lambda *a,**k:dict(receipt,**patch_value)),'Offline fixture','fixture@example.test')
            import threading
            api.policy=SimpleNamespace(_stop=threading.Event(),cancelled=lambda:False,accepted=seen.append)
            with self.assertRaises(SessionAPIError):api.submit_trajectory('s','e','l','t',10,[point])
            self.assertEqual(seen,[])
