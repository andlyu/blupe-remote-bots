"""Private text-only ChatGPT transport. No robot schema, images or tools.

Run as the existing credential owner; web requests cross a UID-checked Unix
socket. Authentication stays in that owner's CODEX_HOME. No credentials travel
through the socket, browser, source tree or another account's home.
"""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import socket
import socketserver
import struct
import subprocess
import tempfile
import threading
import time

from .run_data_chat import SYSTEM, MODEL, DataChatUnavailable
MAX_FRAME = 500_000
MAX_OUTPUT = 1_000_000


def send_frame(sock, data):
    raw = json.dumps(data).encode()
    if not 0 < len(raw) <= MAX_FRAME:
        raise ValueError('Discussion request is too large')
    sock.sendall(struct.pack('!I',len(raw))+raw)


def receive_frame(sock):
    def exact(n):
        data=bytearray()
        while len(data)<n:
            chunk=sock.recv(min(n-len(data),65536))
            if not chunk:raise EOFError()
            data.extend(chunk)
        return data
    size=struct.unpack('!I',exact(4))[0]
    if not 0<size<=MAX_FRAME:raise ValueError('Invalid discussion frame')
    return json.loads(exact(size))


def validate_request(data, model):
    if not isinstance(data,dict) or set(data) != {'model','input','schema'} or data['model'] != model:
        raise ValueError('Invalid discussion request')
    messages,schema=data['input'],data['schema']
    if not isinstance(messages,list) or not 1<=len(messages)<=13:
        raise ValueError('Invalid discussion history')
    for i,m in enumerate(messages):
        if (not isinstance(m,dict) or set(m)!={'role','content'} or m['role'] not in ('user','assistant')
                or not isinstance(m['content'],str) or len(m['content'])>(400000 if i==len(messages)-1 else 6000)):
            raise ValueError('Invalid discussion history')
    if messages[-1]['role']!='user':raise ValueError('Missing question')
    try:
        ids=schema['properties']['citations']['items']['properties']['episode_id']['enum']
        if not isinstance(ids,list) or not 1<=len(ids)<=32 or any(not isinstance(e,str) or not re.fullmatch(r'ep_[A-Za-z0-9_-]{1,100}',e) for e in ids):
            raise ValueError()
        expected={'type':'object','properties':{'answer':{'type':'string'},'citations':{'type':'array',
            'items':{'type':'object','properties':{'episode_id':{'type':'string','enum':ids},
                'note':{'type':'string'}},'required':['episode_id','note'],'additionalProperties':False}}},
            'required':['answer','citations'],'additionalProperties':False}
        if schema!=expected:raise ValueError()
    except (KeyError,TypeError):
        raise ValueError('Invalid discussion schema') from None
    return messages,schema


def request_discussion(path, body):
    try:
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
            sock.settimeout(65);sock.connect(path)
            send_frame(sock,dict(model=body['model'],input=body['input'],schema=body['text']['format']['schema']))
            result=receive_frame(sock)
        if not isinstance(result,dict) or 'text' not in result:
            raise ValueError()
        return dict(model=body['model'],status='completed',subscription=True,
            output=[dict(type='message',content=[dict(type='output_text',text=result['text'])])])
    except (OSError,ValueError,EOFError,KeyError,TypeError):
        raise DataChatUnavailable('ChatGPT could not complete this answer. Your question is kept; try again. No API billing or other model was used.') from None


def execute(binary, home, model, messages, schema, timeout=55):
    env={k:os.environ[k] for k in ['PATH','LANG','LC_ALL','TMPDIR'] if k in os.environ}
    env.update(HOME=str(home),CODEX_HOME=str(home/'.codex'),USER=home.name,LOGNAME=home.name)
    with tempfile.TemporaryDirectory(prefix='data-discussion-',dir=home/'workspace') as directory:
        root=Path(directory);schema_path=root/'answer-schema.json';schema_path.write_text(json.dumps(schema))
        command=[str(binary),'exec','--ignore-user-config','--skip-git-repo-check','--json','--ephemeral',
            '--model',model,'--output-schema',str(schema_path)]
        for config in ['forced_login_method="chatgpt"','model_provider="openai"','model_reasoning_effort="low"',
                'service_tier="default"','sandbox_mode="read-only"','approval_policy="never"','web_search="disabled"',
                'features.shell_tool=false','features.multi_agent=false','features.apps=false','features.hooks=false',
                'model_reasoning_summary="none"']:
            command+=['-c',config]
        command+=['-']
        with tempfile.TemporaryFile() as stdin,tempfile.TemporaryFile() as stdout,tempfile.TemporaryFile() as stderr:
            stdin.write((SYSTEM+'\nCONVERSATION_MESSAGES (JSON data):\n'+json.dumps(messages)).encode());stdin.seek(0)
            process=subprocess.Popen(command,stdin=stdin,stdout=stdout,stderr=stderr,cwd=root,env=env,start_new_session=True)
            deadline=time.monotonic()+timeout
            try:
                while process.poll() is None:
                    if time.monotonic()>deadline or os.fstat(stdout.fileno()).st_size>MAX_OUTPUT or os.fstat(stderr.fileno()).st_size>MAX_OUTPUT:
                        raise ValueError('Discussion timed out or exceeded output limit')
                    time.sleep(.05)
                if process.returncode:raise ValueError('Discussion did not complete')
                stdout.seek(0);raw=stdout.read(MAX_OUTPUT+1)
                if len(raw)>MAX_OUTPUT:raise ValueError('Discussion output too large')
                texts=[]
                for line in raw.splitlines():
                    event=json.loads(line)
                    if event.get('model') and event['model']!=model:
                        raise ValueError('Unexpected model override')
                    item=event.get('item',{})
                    # Treat any attempted tool use as a failed read-only discussion.
                    if item.get('type') and item['type'] not in ('agent_message','reasoning'):
                        raise ValueError('Discussion attempted a tool')
                    if event.get('type')=='item.completed' and item.get('type')=='agent_message':texts.append(item['text'])
                if len(texts)!=1:raise ValueError('Missing discussion answer')
                return texts[0]
            finally:
                if process.poll() is None:
                    os.killpg(process.pid,signal.SIGTERM)
                    try:process.wait(timeout=2)
                    except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=2)


class Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads=True
    def __init__(self,path,*,binary,home,model,client_uid):
        self.binary,self.home,self.model,self.client_uid=binary,home,model,client_uid
        self.gate=threading.BoundedSemaphore(2)
        super().__init__(str(path),Handler)
        os.chmod(path,0o660)


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(65)
        if not hasattr(socket,'SO_PEERCRED'):return
        _,uid,_=struct.unpack('3i',self.request.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
        if uid!=self.server.client_uid:return
        acquired=False
        try:
            data=receive_frame(self.request);messages,schema=validate_request(data,self.server.model)
            acquired=self.server.gate.acquire(blocking=False)
            if not acquired:raise ValueError('Busy')
            text=execute(self.server.binary,self.server.home,self.server.model,messages,schema)
            send_frame(self.request,{'text':text})
        except Exception:
            try:send_frame(self.request,{'error':'Discussion unavailable; no API fallback used'})
            except (OSError,ValueError):pass
        finally:
            if acquired:self.server.gate.release()


def main():
    p=argparse.ArgumentParser();p.add_argument('--socket',type=Path,required=True)
    p.add_argument('--binary',type=Path,required=True);p.add_argument('--home',type=Path,required=True)
    p.add_argument('--model',default=MODEL);p.add_argument('--client-uid',type=int,required=True)
    args=p.parse_args()
    if not args.socket.is_absolute() or not args.home.is_absolute() or not args.binary.is_absolute():p.error('Absolute paths required')
    if args.socket.exists():
        if not args.socket.is_socket() or args.socket.stat().st_uid!=os.getuid():p.error('Refusing to replace an unrelated path')
        args.socket.unlink()
    with Server(args.socket,binary=args.binary,home=args.home,model=args.model,client_uid=args.client_uid) as server:
        server.serve_forever()


if __name__=='__main__':main()
