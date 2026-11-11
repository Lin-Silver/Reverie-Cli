"""Qualify persisted AiO decisions and worker acceptance with the requested model."""
from pathlib import Path
from copy import deepcopy
import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'ReverieCli-py'))
from reverie.config import ConfigManager
from reverie.desktop_catalog import apply_model_selection
from reverie.sdk_bridge import ReverieSdkBridge


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe',type=Path,help='Qualify the rebuilt packaged kernel rather than source.')
    args=parser.parse_args()
    cfg = deepcopy(ConfigManager(ROOT).load())
    apply_model_selection(cfg,'sensenova','sensenova-6.8-flash')
    cfg.api_timeout,cfg.api_max_retries,cfg.stream_responses = 60,0,False
    cfg.security = {**cfg.security,'permission_level':'workspace_write','permission_mode':'default'}
    output = ROOT/'.runtime'/'aio-implementation'/('real-aio-'+time.strftime('%Y%m%d-%H%M%S'))
    output.mkdir(parents=True,exist_ok=False)
    workspace = output/'workspace'
    workspace.mkdir()
    os.environ['REVERIE_APP_ROOT'] = str(output/'app-root')
    manager = ConfigManager(workspace)
    manager.ensure_dirs()
    manager.save(cfg)
    events=[]
    approval_denials=[]
    bridge=process=None
    messages=queue.Queue()
    def receive_event(message):
        event=message.get('event',{})
        events.append(str(event.get('type','')))
        if event.get('type')=='approval.request':
            approval_denials.append({'tool':event.get('tool'),'reason':event.get('message')})
            refusal={'approvalId':event['approval_id'],'decision':'deny'}
            if bridge:
                bridge.dispatch({'id':'qualification-refusal','action':'resolveApproval','payload':refusal})
            else:
                process.stdin.write(json.dumps({'id':'qualification-refusal','action':'resolveApproval','payload':refusal})+'\n');process.stdin.flush()
    if args.exe:
        process=subprocess.Popen([str(args.exe.resolve()),'--sdk-bridge'],cwd=workspace,env=os.environ.copy(),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8',creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        def read_messages():
            for line in process.stdout:
                try:messages.put(json.loads(line))
                except json.JSONDecodeError:pass
        threading.Thread(target=read_messages,daemon=True).start()
    else:
        bridge=ReverieSdkBridge(receive_event)
        bridge.ensure_interface(workspace)
    sequence=0
    def request(action,payload):
        nonlocal sequence
        if bridge:return bridge.dispatch({'id':action,'action':action,'payload':payload})
        sequence+=1
        identity=f'qualification-{sequence}'
        process.stdin.write(json.dumps({'id':identity,'action':action,'payload':payload},ensure_ascii=False)+'\n');process.stdin.flush()
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            response=messages.get(timeout=max(.01,deadline-time.monotonic()))
            if response.get('type')=='prompt.event':
                receive_event(response)
                continue
            if response.get('id')==identity:
                if response.get('type')=='error':raise RuntimeError(response.get('error') or response.get('message'))
                return response
            if response.get('event'):events.append(str(response['event'].get('type','')))
        raise TimeoutError('Packaged kernel did not answer.')
    report={'model':cfg.active_model.model,'exe':str(args.exe.resolve()) if args.exe else None,'passed':False,'events':events,'approval_denials':approval_denials}
    try:
        if process:request('initialize',{'projectRoot':str(workspace),'deferPayloads':True})
        request('aioControl',{'assistantId':'aio','enable':True})
        from reverie.session.aio_store import AiOStore
        store=bridge._aio().store if bridge else AiOStore(output/'app-root'/'.reverie/aio')
        store.append('user',{'text':'This is an explicitly authorized qualification. Create exactly one Reverie worker task to write aio-proof.txt in the listed disposable workspace. Its full UTF-8 content must be AiO VERIFIED 中文 followed by one newline. Acceptance: read the saved file and match those exact bytes. Do not use desktop tools or shell commands. Do not create other tasks.'},event_id='qualification-user-message',visible=True)
        decision=request('aioDecision',{'assistantId':'aio','urgent':True,'workspaces':[str(workspace)],'observation':{'type':'user.reply','event_id':'qualification-request','message_id':'qualification-user-message','branch':'aio-mainline'}})['decision']
        report['decision']=decision
        report['judgment']=getattr(bridge._aio(),'last_decision',None) if bridge else None
        tasks=decision.get('tasks',[])
        if len(tasks)!=1:
            raise ValueError('Qualification expected exactly one concrete task.')
        task=tasks[0]
        root={'assistantId':'aio','projectRoot':str(workspace),'sessionId':task['branch'],'configuration':task['configuration'],'stream':False,'noIndex':True,'freshSession':False}
        revision=request('aioTaskState',{'assistantId':'aio','taskId':task['id'],'state':'running','revision':1})['revision']
        result=request('runPrompt',{**root,'prompt':task['prompt'],'promptAlreadySaved':True})['result']
        report['execution']=result
        if not result['success']:
            raise RuntimeError('Worker did not complete successfully: '+str(result.get('error')))
        revision=request('aioTaskState',{'assistantId':'aio','taskId':task['id'],'state':'verifying','revision':revision,'result':result})['revision']
        review=request('runPrompt',{**root,'runType':'review','prompt':'Independently read aio-proof.txt and check its exact bytes against AiO VERIFIED 中文 followed by one newline. Do not edit files or execute commands. Return only {"passed":true|false,"evidence":"what you actually read"}.'})['result']
        report['verification']=review
        text=str(review.get('output_text','')).strip()
        if text.startswith('```'):
            text=text.split('\n',1)[1].rsplit('```',1)[0].strip()
        evidence=json.loads(text)
        actual=(workspace/'aio-proof.txt').read_bytes()
        report['exact_artifact']=actual == 'AiO VERIFIED 中文\n'.encode('utf-8')
        report['passed']=result['success'] and review['success'] and evidence.get('passed') is True and report['exact_artifact']
        request('aioTaskState',{'assistantId':'aio','taskId':task['id'],'state':'completed' if report['passed'] else 'waiting_user','revision':revision,'result':{'execution':result,'verification':review,'exact_artifact':report['exact_artifact']}})
        report['persisted_tasks']=request('aioState',{'assistantId':'aio'})['aio']['tasks']
    except Exception as error:
        report['judgment']=getattr(bridge._aio(),'last_decision',None) if bridge else None
        report['error_type']=type(error).__name__
        report['error']=str(error).replace(cfg.active_model.resolve_api_key(),'[redacted]') if cfg.active_model.resolve_api_key() else str(error)
    finally:
        if bridge and bridge.interface:
            bridge.interface.close()
        if bridge:bridge.rats_runtime.shutdown()
        if process:
            try:request('shutdown',{});process.wait(timeout=30)
            except Exception:process.kill();process.wait(timeout=30)
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'artifact':str(output/'report.json'),'error':report.get('error')},ensure_ascii=False),flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
