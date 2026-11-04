"""Validate actual hosting broker/client compatibility without network or inference."""
import argparse
import base64
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from unittest.mock import patch
import uuid

ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'src'),str(ROOT)]


def check(broker_source,runner_name):
    started=time.perf_counter();broker_source=Path(broker_source).resolve()
    sys.path.insert(0,str(broker_source.parents[2]))
    broker=importlib.import_module('deploy.operator.personal_codex')
    if Path(broker.__file__).resolve()!=broker_source:raise ValueError('Wrong broker source imported')
    client_source=broker_source.parents[2]/'apps/blupe_web/codex_sponsor.py'
    spec=importlib.util.spec_from_file_location('roboharness_hosting_client',client_source)
    client=importlib.util.module_from_spec(spec);spec.loader.exec_module(client)
    from remote_yam.codex_policy import use_codex_executor
    from remote_yam.roboharness_contract import NAMES
    from remote_yam.roboharness_policy import RoboHarnessAdapter,INITIALIZATION_CARD_SHA256,INITIALIZATION_CARD_PNG_BASE64
    report=json.loads((ROOT/'tests/fixtures/roboharness-robohouse-calibration.json').read_text())
    receiver=object.__new__(broker.Broker);sender=client.BrokerSession('/nonexistent-offline-protocol-check')
    thread=str(uuid.uuid4());requests=[]
    def executor(**value):
        if not sender.accepts_model(value['model']) or not sender.accepts_effort(value['reasoning_effort']):raise ValueError('Actual client rejects selected model/effort')
        request=sender.request(value['schema'],value['prompt'],value['images'],value['model'],value['reasoning_effort'])
        if value['thread_id']!=(None if not requests else thread):raise ValueError('Model transport did not preserve the expected conversation')
        parsed=broker.Broker.prepare_request(receiver,request)
        count=len(parsed[2]);requests.append(count)
        if count not in (1,3):raise ValueError('Unexpected image role count')
        if any(hashlib.sha256(image).hexdigest()!=INITIALIZATION_CARD_SHA256 for image in value['images']):raise ValueError('Protocol probe must use synthetic cards only')
        for bad in ([],request['images']*4):
            try:broker.Broker.prepare_request(receiver,{**request,'images':bad})
            except broker.BrokerError:pass
            else:raise ValueError('Actual broker image-count guard changed')
        result=dict(action='give_up',targets={name:None for name in NAMES},note='',summary='',reason='non_actuating_session_ready',hindsight='')
        if count==3:
            result['action']='move_to'
            result['targets'].update(primitive=1,point_a=0,u=0,v=1000,
                                    point_b=1,x=500,y=250,point_c=2,rx=1000,ry=0)
            result['reason']='Offline three-point inspection parser check; no robot state or dispatch.'
        return [{'type':'thread.started','thread_id':thread},{'type':'item.completed','item':{'type':'agent_message','text':json.dumps(result)}},{'type':'turn.completed'}]
    with patch.object(socket,'socket',side_effect=AssertionError('Offline broker preflight attempted network')) as network:
        policy=RoboHarnessAdapter('https://yam-session-api.n5hthc3gj4cqy.us-east-1.cs.amazonlightsail.com','robot-ba8413962083809c',report,expected_calibration_id=report['calibration_id'],expected_model_calibration_id=report['model_joint_calibration']['calibration_id'],warm_model_session=True)
        policy.runner_name=runner_name;policy.execution_mode='offline_broker_protocol_validation'
        use_codex_executor(policy,executor)
        try:
            policy.start_preparation(lambda:False);policy._await_preparation()
            if policy._expected_camera_count!=3:raise ValueError('Physical policy image guard was not restored')
            image=dict(type='input_image',image_url='data:image/png;base64,'+INITIALIZATION_CARD_PNG_BASE64)
            probe=dict(model=policy.model,tools=[],store=False,input=[dict(role='user',content=[dict(type='input_text',text='Offline protocol test only; synthetic cards, no robot state or targets.'),image])])
            try:policy._post_json(probe)
            except RuntimeError as exc:
                if 'three fresh' not in str(exc):raise
            else:raise ValueError('Physical policy accepted fewer than three images')
            probe['input'][0]['content'] += [image,image]
            response=policy._post_json(probe)
            inspected=json.loads(response['output'][0]['arguments']).get('registrations',[])
            if len(inspected)!=3 or policy._pending is not None:raise ValueError('Read-only batch inspection parser contract changed')
            if requests!=[1,3]:raise ValueError('Initialization/policy protocol sequence changed')
            network.assert_not_called()
        finally:policy.close_transport()
    return dict(status='passed',scope='actual Codex parser, hosting client serializer and broker validator; synthetic executor only',runner_name=runner_name,execution_mode='offline_broker_protocol_validation',duration_s=time.perf_counter()-started,policy_source_sha256=hashlib.sha256(Path(sys.modules[RoboHarnessAdapter.__module__].__file__).read_bytes()).hexdigest(),broker_source_sha256=hashlib.sha256(broker_source.read_bytes()).hexdigest(),client_source_sha256=hashlib.sha256(client_source.read_bytes()).hexdigest(),initialization_images=1,initialization_robot_images=0,policy_images=3,card_sha256=INITIALIZATION_CARD_SHA256,zero_and_excess_images_rejected=True,policy_three_image_guard_preserved=True,batch_inspection_points=len(inspected),same_transport_resume=True,network_connections=0,actual_model_calls=0,robot_sessions=0,actuator_submissions=0)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--broker-source',type=Path,required=True);parser.add_argument('--runner-name',required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--allow-dirty',action='store_true');args=parser.parse_args()
    if not args.runner_name.strip():raise ValueError('Confirmed runner attribution is required')
    receipt=check(args.broker_source,args.runner_name.strip())
    receipt['source_revision']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    receipt['dirty_source']=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip())
    if receipt['dirty_source']:receipt['status']='draft_passed'
    args.output.write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt));return 0 if not receipt['dirty_source'] or args.allow_dirty else 1


if __name__=='__main__':raise SystemExit(main())
