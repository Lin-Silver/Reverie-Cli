"""Run the same four-stream workload in an isolated Windows package.

Synthetic persistence, renderer and lifecycle evidence is separate from real
model and native desktop task qualification. No user profile is modified.
"""
from pathlib import Path
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import argparse
import ctypes
import hashlib
import json
import os
import queue
import re
import socket
import subprocess
import sys
import threading
import time
import traceback
sys.stdout.reconfigure(encoding='utf-8')

import psutil
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'ReverieCli-py'))
from reverie.config import ConfigManager, ModelConfig
from reverie.session.manager import SessionManager as LegacySessionManager
from reverie.session.sqlite_manager import SQLiteSessionManager
from reverie.session.aio_store import AiOStore
from reverie.session.runtime_config import capture_runtime_config, resolve_runtime_config
from desktop_process import keep_windows_awake, launch_options, stop_process, wait_for_native_foreground, wait_for_packaged_page
from desktop_performance import measure, summary


class Fixture(BaseHTTPRequestHandler):
    requests=0
    active_streams=0
    request_routes=[]
    def log_message(self,*_args):
        pass
    def do_POST(self):
        payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        type(self).requests+=1
        ordinary=False
        for message in reversed(payload.get('messages',[])):
            if message.get('role')!='user':continue
            match=re.fullmatch(r'Preserve stream (\d+)-([0-3])\.',str(message.get('content','')).strip())
            if match:
                ordinary=True
                lane=int(match[2])
                type(self).request_routes.append({'iteration':int(match[1]),'lane':lane,'model':payload.get('model'),
                    'model_correct':payload.get('model')==f'package-fixture-{lane}',
                    'rule_correct':f'QUALIFICATION_RULE_{lane}' in str(payload.get('messages',[]))})
                break
        if not ordinary:
            answer=json.dumps({'speech':'','tasks':[],'memories':[]})
        else:
            answer='PACKAGE_STREAM_COMPLETE\n'+('完整保存的并行输出。 '*1000)
        self.send_response(200)
        self.send_header('Content-Type','text/event-stream' if payload.get('stream') else 'application/json')
        self.end_headers()
        try:
            if not payload.get('stream'):
                self.wfile.write(json.dumps({'choices':[{'message':{'role':'assistant','content':answer},'finish_reason':'stop'}]}).encode())
                return
            type(self).active_streams+=1
            for offset in range(0,len(answer),160):
                self.wfile.write(('data: '+json.dumps({'choices':[{'delta':{'content':answer[offset:offset+160]},'finish_reason':None}]},ensure_ascii=False)+'\n\n').encode())
                self.wfile.flush()
                time.sleep(.22)
            self.wfile.write(b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
            self.wfile.flush()
        except (BrokenPipeError,ConnectionResetError):
            pass
        finally:
            if payload.get('stream'):type(self).active_streams-=1


def seed(output,port,baseline):
    app_root=output/'app-root'
    home=output/'desktop-home'
    app_root.mkdir();home.mkdir()
    os.environ['REVERIE_APP_ROOT']=str(app_root)
    roots=[];owners=[]
    fixture_models=[ModelConfig(f'package-fixture-{lane}',f'Package fixture {lane}',f'http://127.0.0.1:{port}/v1') for lane in range(4)]
    for index in range(4):
        root=output/f'workspace-{index}';root.mkdir();roots.append(root)
        (root/'.gitignore').write_text('.reverie/\n',encoding='utf-8')
        subprocess.run(['git','init','-b','main',str(root)],check=True,capture_output=True)
        subprocess.run(['git','-C',str(root),'add','.gitignore'],check=True,capture_output=True)
        subprocess.run(['git','-C',str(root),'-c','user.name=Qualification','-c','user.email=qualification@example.invalid','commit','-m','Qualification fixture'],check=True,capture_output=True)
        manager=ConfigManager(root);manager.ensure_dirs();config=manager.load()
        config.models=fixture_models
        config.active_model_source='standard';config.active_model_index=0
        config.stream_responses=True;config.auto_index=False;config.api_proxy='';config.api_max_retries=0
        manager.save(config)
        owner_manager=ConfigManager(roots[0])
        store=(LegacySessionManager if baseline else SQLiteSessionManager)(owner_manager.project_data_dir,project_root=roots[0])
        session=store.create_session(f'Parallel {index}');owners.append(session.id)
        if index==0:
            for item in range(999):
                other=store.create_session(f'History {item:04}')
                other.messages=[{'role':'user','content':f'原文 {item}'},{'role':'assistant','content':f'回答 {item}'}]
                store.save_session(other)
            session=store.create_session('Qualification long 10000')
            session.messages=[{'role':'assistant' if row%2 else 'user','content':f'保留完整历史 {row} '+('message '*20)} for row in range(10000)]
            store.save_session(session);owners[0]=session.id
        owner_config=owner_manager.load()
        owner_config.active_model_index=index
        snapshot=capture_runtime_config(owner_config,rules=f'QUALIFICATION_RULE_{index}: Preserve exact task output and this conversation identity.')
        if baseline:
            session=store.load_session(owners[index])
            session.metadata['runtime_config']=snapshot
            store.save_session(session)
        else:
            page=store.get_page(owners[index],limit=1)
            store.update_metadata(owners[index],{'runtime_config':snapshot},expected_revision=page['revision'])
        store.flush_session_index()
    catalog=ConfigManager(roots[0]).load()
    for index,owner in enumerate(owners):
        metadata=store.load_session(owner).metadata if baseline else store.get_page(owner,limit=1)['metadata']
        resolved=resolve_runtime_config(catalog,metadata['runtime_config'])
        assert resolved.active_model.model==f'package-fixture-{index}','Seeded conversation references must resolve against the shared catalog'
    if baseline:
        store.load_session(owners[1])
    else:
        store.select_session(owners[1])
    if baseline:
        store=LegacySessionManager(app_root/'.reverie/computer-controller')
        session=store.create_session('Legacy assistant event dataset')
        session.messages=[{'role':'system','content':{'source':'synthetic-qualification','text':f'完整观察原文 {index}'}} for index in range(100000)]
        store.save_session(session)
    else:
        store=AiOStore(app_root/'.reverie/aio')
        # No enabled assistant or sampled history is loaded into model context.
        with store.connect() as db:
            for batch in range(100):
                db.execute('BEGIN IMMEDIATE')
                for index in range(batch*1000,(batch+1)*1000):
                    store._event(db,f'qualification-{index}','observation',{'source':'synthetic-qualification','text':f'完整观察原文 {index}'},store.mainline_id,f'2026-11-{1+batch%7:02}T12:00:00')
                db.commit()
    settings=home/'.reverie/desktop/desktop-settings.json';settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({'coreAppRoot':str(app_root),'projectRoot':str(roots[0]),'workspaceRoots':[str(root) for root in roots],'theme':'light','ui':{'language':'zh-CN','backgroundPreset':'none'}}),encoding='utf-8')
    return [roots[0]]*4,owners,app_root,home


def filter_process_rows(root_pid,rows):
    """Reject reused-parent PID edges whose child predates the observed parent."""
    by_pid={row['pid']:row for row in rows}
    excluded={row['pid'] for row in rows if row['pid']!=root_pid
              and row['parent'] in by_pid
              and row['created_at']<by_pid[row['parent']]['created_at']}
    while True:
        descendants={row['pid'] for row in rows
                     if row['pid']!=root_pid and row['parent'] in excluded}-excluded
        if not descendants:break
        excluded.update(descendants)
    return [row for row in rows if row['pid'] not in excluded]


def resources(pid,errors):
    parent=psutil.Process(pid);rows=[]
    for process in [parent,*parent.children(recursive=True)]:
        try:
            io=process.io_counters()
            rows.append({'pid':process.pid,'created_at':process.create_time(),'parent':process.ppid(),'name':process.name(),'rss':process.memory_info().rss,'write_bytes':io.write_bytes,'read_bytes':io.read_bytes})
        except psutil.NoSuchProcess:
            pass
        except psutil.AccessDenied:
            errors.append({'pid':process.pid,'error':'Owned process resource access denied'})
    return filter_process_rows(pid,rows)


def request(page,action,payload):
    return page.evaluate('([action,payload])=>window.reverie.request(action,payload)',[action,payload])


def foreground_state():
    """Identify the native foreground without changing it or reading window content."""
    from ctypes import wintypes
    user32=ctypes.windll.user32
    user32.GetForegroundWindow.restype=wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    handle=user32.GetForegroundWindow()
    pid=wintypes.DWORD()
    user32.GetWindowThreadProcessId(handle,ctypes.byref(pid))
    try:
        name=psutil.Process(pid.value).name()
    except psutil.NoSuchProcess:
        name='exited'
    return {'at':time.time(),'handle':int(handle or 0),'pid':pid.value,'process':name}


def native_main_visible(handle):
    from ctypes import wintypes
    user32=ctypes.windll.user32
    user32.IsWindowVisible.argtypes=[wintypes.HWND]
    return bool(user32.IsWindowVisible(wintypes.HWND(handle)))


def surviving_owned(tracked,exclude=None):
    result=[]
    for pid,created in tracked.items():
        if pid==exclude:
            continue
        try:
            if psutil.Process(pid).create_time()==created:
                result.append(pid)
        except psutil.NoSuchProcess:
            pass
    return result


def verify_committed_history(roots,owners,app_root,runs):
    store=SQLiteSessionManager(ConfigManager(roots[0]).project_data_dir,project_root=roots[0])
    expected_output='PACKAGE_STREAM_COMPLETE\n'+('完整保存的并行输出。 '*1000)
    evidence={'stream_conversations':[],'long_history':False,'aio_events':False}
    with store.connect() as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        for index,owner in enumerate(owners):
            completed=[];prompts=[];history_count=0
            for row in db.execute('SELECT sequence,payload,digest FROM messages WHERE session_id=? ORDER BY sequence',(owner,)):
                assert hashlib.sha256(row['payload'].encode('utf-8')).hexdigest()==row['digest']
                message=json.loads(row['payload'])
                content=message.get('content')
                if index==0 and row['sequence']<10000:
                    sequence=row['sequence']
                    assert message=={'role':'Reverie' if sequence%2 else 'user','content':f'保留完整历史 {sequence} '+('message '*20)}
                    history_count+=1
                if isinstance(content,str) and content.startswith('PACKAGE_STREAM_COMPLETE'):
                    assert message['role']=='Reverie' and content==expected_output
                    completed.append(row['sequence'])
                if message.get('role')=='user' and isinstance(content,str) and content.startswith('Preserve stream '):
                    prompts.append(content)
            expected=[f'Preserve stream {run["iteration"]}-{index}.' for run in runs]
            assert prompts==expected and len(completed)==len(expected),(index,len(prompts),len(completed),len(expected))
            if index==0:
                assert history_count==10000
                evidence['long_history']=True
            tasks=[dict(row) for row in db.execute('SELECT id,state,configuration_revision FROM task_runs WHERE session_id=?',(owner,))]
            assert len(tasks)==len(expected) and all(task['state']=='completed' for task in tasks),tasks
            assert db.execute('SELECT COUNT(*) FROM stream_chunks WHERE session_id=?',(owner,)).fetchone()[0]==0
            evidence['stream_conversations'].append({'session_id':owner,'complete_outputs':len(completed),'user_prompts':len(prompts),'completed_tasks':len(tasks)})
    aio=AiOStore(app_root/'.reverie/aio')
    with aio.connect() as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        count=0
        for row in db.execute("SELECT id,kind,payload FROM aio_events WHERE id LIKE 'qualification-%' ORDER BY sequence"):
            assert row['id']==f'qualification-{count}' and row['kind']=='observation'
            assert json.loads(row['payload'])=={'source':'synthetic-qualification','text':f'完整观察原文 {count}'}
            count+=1
        assert count==100000
        evidence['aio_events']=True
        evidence['aio_event_count']=count
    return evidence


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--duration-seconds',type=float,default=28800)
    parser.add_argument('--baseline',action='store_true')
    parser.add_argument('--baseline-report',type=Path)
    parser.add_argument('--interactive-exit',action='store_true',help='After measurements, wait for an actual tray-menu exit and check owned process cleanup.')
    args=parser.parse_args()
    output=args.output.resolve()
    if os.name!='nt' or args.duration_seconds<60 or output.exists() or not output.is_relative_to(ROOT/'.runtime'):
        parser.error('Use Windows, a fresh project .runtime folder and at least 60 seconds.')
    output.mkdir(parents=True)
    server=ThreadingHTTPServer(('127.0.0.1',0),Fixture)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    roots,owners,app_root,home=seed(output,server.server_port,args.baseline)
    os.environ['NO_PROXY']=os.environ['no_proxy']='127.0.0.1,localhost'
    env={**os.environ,'REVERIE_APP_ROOT':str(app_root),'HOME':str(home),'XDG_CONFIG_HOME':str(home/'.config'),'PORTABLE_EXECUTABLE_DIR':str(home),'NO_PROXY':'127.0.0.1,localhost','no_proxy':'127.0.0.1,localhost'}
    env.pop('ELECTRON_RUN_AS_NODE',None)
    git_entries=int(env.get('GIT_CONFIG_COUNT','0'))
    env.update({'GIT_CONFIG_COUNT':str(git_entries+1),f'GIT_CONFIG_KEY_{git_entries}':'safe.directory',f'GIT_CONFIG_VALUE_{git_entries}':str(ROOT).replace('\\','/')})
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    report={'scope':__doc__,'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'baseline':args.baseline,'exe':str(args.exe.resolve()),'exe_sha256':hashlib.sha256(args.exe.read_bytes()).hexdigest(),'requested_duration_seconds':args.duration_seconds,'passed':False,'browser_errors':[],'resource_access_errors':[],'runs':[],'popup_ready':[],'history_first_page':[],'uncached_switch':[],'cached_switch':[],'scenarios':{},'peak_tree_rss':0,'peak_kernel_tree_rss':0,'peak_process_count':0,'peak_renderer_heap':0,'dataset':{'ordinary_conversations':1004,'long_messages':10000,'aio_events':100000}}
    report['support_harness_sha256']={name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in ('desktop_process.py','desktop_performance.py')}
    if args.baseline_report:
        baseline=json.loads(args.baseline_report.read_text(encoding='utf-8'))
        report['process_tree_budget']=baseline['peak_tree_rss']+baseline['peak_kernel_tree_rss']+128*1024**2
        report['baseline_report']=str(args.baseline_report.resolve())
    process=browser=None;tracked={};started=None
    sampling_stop=threading.Event()
    sampling_thread=None
    resource_writer_thread=None
    resource_writer_stop=threading.Event()
    resource_queue=queue.Queue(maxsize=128)
    report.update(resource_writer_errors=[],resource_samples_collected=0,resource_samples_written=0)
    io_peaks={}
    sampling_gaps=[]
    last_resource_sample=[None]
    def data_sizes():
        files=[path for folder in [app_root,*set(roots)] for path in folder.rglob('*') if path.is_file()]
        sizes={}
        for path in files:
            try:sizes[path]=path.stat().st_size
            except FileNotFoundError:pass  # A WAL checkpoint or atomic temporary file can finish during sampling.
        return {'total_bytes':sum(sizes.values()),'databases':{str(path.relative_to(output)):size for path,size in sizes.items() if path.name.endswith(('.sqlite3','.sqlite3-wal','.sqlite3-shm'))}}
    initial_sizes=data_sizes()
    report['data_growth_samples']=[{'elapsed_seconds':0,**initial_sizes}]
    def write_resources():
        try:
            with (output/'resources.jsonl').open('a',encoding='utf-8') as stream:
                while not resource_writer_stop.is_set() or not resource_queue.empty():
                    try:record=resource_queue.get(timeout=.5)
                    except queue.Empty:continue
                    stream.write(json.dumps(record)+'\n')
                    stream.flush()
                    report['resource_samples_written']+=1
        except Exception as error:
            report['resource_writer_errors'].append({'error':type(error).__name__+': '+str(error),'traceback':traceback.format_exc()})
            sampling_stop.set()
    def sample_resources():
        previous_sample=None
        while not sampling_stop.is_set():
            sample_at=time.monotonic()
            if previous_sample is not None:sampling_gaps.append(sample_at-previous_sample)
            previous_sample=sample_at
            last_resource_sample[0]=sample_at
            try:
                rows=resources(process.pid,report['resource_access_errors'])
            except psutil.NoSuchProcess:
                break
            tracked.update({row['pid']:row['created_at'] for row in rows})
            report['peak_tree_rss']=max(report['peak_tree_rss'],sum(row['rss'] for row in rows))
            report['peak_process_count']=max(report['peak_process_count'],len(rows))
            def subtree_rss(parent):
                return parent['rss']+sum(subtree_rss(child) for child in rows if child['parent']==parent['pid'])
            for row in rows:
                identity=(row['pid'],row['created_at'])
                io_peaks[identity]=max(io_peaks.get(identity,0),row['write_bytes'])
                if row['name'].lower()=='reverie.exe':
                    report['peak_kernel_tree_rss']=max(report['peak_kernel_tree_rss'],subtree_rss(row))
            report['resource_samples_collected']+=1
            try:
                resource_queue.put_nowait({'at':time.time(),'elapsed_seconds':time.monotonic()-started if started else None,'processes':rows})
            except queue.Full:
                report['resource_writer_errors'].append({'error':'Resource log queue is full; observations cannot be retained.'})
                sampling_stop.set()
                break
            sampling_stop.wait(.5)
    try:
        with keep_windows_awake() as power_request,(output/'desktop.log').open('w',encoding='utf-8') as log,sync_playwright() as pw:
            report['power_request']=power_request
            process=subprocess.Popen([str(args.exe.resolve()),'--gui','--project',str(roots[0]),f'--remote-debugging-port={port}','--user-data-dir='+str(home/'electron-profile')],env=env,stdout=log,stderr=log,**launch_options(visible=True))
            resource_writer_thread=threading.Thread(target=write_resources,daemon=True)
            resource_writer_thread.start()
            sampling_thread=threading.Thread(target=sample_resources,daemon=True)
            sampling_thread.start()
            browser,page=wait_for_packaged_page(pw,process,port)
            page._qualification_process_id=process.pid
            page._qualification_output=output
            page.set_default_timeout(120000)
            page.on('pageerror',lambda error:report['browser_errors'].append(str(error)))
            page.wait_for_selector('.composer textarea',timeout=120000)
            page.wait_for_function("() => document.querySelector('.transcript')?.getAttribute('aria-busy')==='false'")
            page.bring_to_front()
            report['native_initial_window']=wait_for_native_foreground(page,process.pid,output,'initial')
            main_handle=max(report['native_initial_window']['windows'],key=lambda window:(window['bounds'][2]-window['bounds'][0])*(window['bounds'][3]-window['bounds'][1]))['handle']
            report['native_main_window_handle']=main_handle
            page.evaluate("()=>{window.__aioQualificationEvents=[];window.reverie.onEvent(event=>{if(event.type==='aio.popup-readable')window.__aioQualificationEvents.push(event);});}")
            asar=args.exe.parent/'resources/app.asar'
            if asar.exists():report['asar_sha256']=hashlib.sha256(asar.read_bytes()).hexdigest()
            for index in range(20):
                begin=time.perf_counter();response=request(page,'getSession',{'projectRoot':str(roots[0]),'sessionId':owners[0],'select':False})
                report['history_first_page'].append((time.perf_counter()-begin)*1000)
                count=len(response['session']['messages'])
                assert count==10000 if args.baseline else count==60 and response['session']['total']==10000
            page.evaluate("()=>document.addEventListener('click',event=>{if(event.target.closest('.session-item'))window.__switchStarted=performance.now();},true)")
            for number in range(998,978,-1):
                page.locator(f'.session-item[title="History {number:04}"]').click()
                page.wait_for_function("name=>document.querySelector('.conversation-header strong')?.textContent===name && document.querySelector('.transcript')?.textContent.includes('原文') && document.querySelector('.transcript').getAttribute('aria-busy')==='false'",arg=f'History {number:04}')
                report['uncached_switch'].append(page.evaluate('()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve(performance.now()-window.__switchStarted))))'))
            page.evaluate("()=>{const list=document.querySelector('.virtual-session-list');if(list){list.scrollTop=0;list.dispatchEvent(new Event('scroll'));}}")
            for index in range(22):
                number=998 if index%2 else 997
                page.locator(f'.session-item[title="History {number:04}"]').click()
                page.wait_for_function("name=>document.querySelector('.conversation-header strong')?.textContent===name && document.querySelector('.transcript')?.textContent.includes('原文') && document.querySelector('.transcript').getAttribute('aria-busy')==='false'",arg=f'History {number:04}')
                latency=page.evaluate('()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve(performance.now()-window.__switchStarted))))')
                if index>=2:report['cached_switch'].append(latency)
            page.locator('.session-item[title="Parallel 1"]').click()
            page.wait_for_function("() => document.querySelector('.conversation-header strong')?.textContent==='Parallel 1' && document.querySelector('.transcript')?.getAttribute('aria-busy')==='false'")
            report['foreground_stream_session_id']=owners[1]
            started=time.monotonic();iteration=0;next_ui_sample=3600
            report['renderer_lifecycle_samples']=[]
            report['aio_lifecycle_samples']=[]
            while time.monotonic()-started<args.duration_seconds:
                if process.poll() is not None:raise RuntimeError('Windows package exited during qualification.')
                native_visibility=[native_main_visible(main_handle)]
                payloads=[{'projectRoot':str(roots[0]),'sessionId':owner,'prompt':f'Preserve stream {iteration}-{index}.','noIndex':True,'freshSession':False,'stream':True,'runType':'review'} for index,owner in enumerate(owners)]
                page.evaluate('payloads=>{window.__qualificationDone=false;window.__qualificationRuns=[];Promise.allSettled(payloads.map(async(payload,index)=>{await new Promise(resolve=>setTimeout(resolve,index*1000));return window.reverie.request("runPrompt",payload);})).then(results=>{window.__qualificationRuns=results;window.__qualificationDone=true;});}',payloads)
                round_deadline=time.monotonic()+180
                elapsed=time.monotonic()-started
                sample_ui=iteration==0 or elapsed>=next_ui_sample
                if elapsed>=next_ui_sample:next_ui_sample=elapsed+3600
                visibility=page.evaluate('document.visibilityState')
                report['renderer_lifecycle_samples'].append({'elapsed_seconds':elapsed,'visibility':visibility,'native_main_visible':native_visibility[0]})
                if sample_ui and native_visibility[0] and visibility=='visible':
                    while Fixture.active_streams<4 and not page.evaluate('window.__qualificationDone'):
                        if time.monotonic()>round_deadline:raise TimeoutError('The fixed workload did not reach four overlapping streams.')
                        page.wait_for_timeout(100)
                    assert Fixture.active_streams==4,'Four streams must overlap before input measurement'
                    report['foreground_live_output_visible']=page.evaluate("document.querySelector('.transcript')?.textContent.includes('PACKAGE_STREAM_COMPLETE') || false")
                    if not args.baseline:
                        assert report['foreground_live_output_visible'],'The selected conversation must render its own stream while all four execute'
                    report['simultaneous_streams_at_measurement']=Fixture.active_streams
                    scenario='four_stream_typing' if iteration==0 else f'four_stream_typing_hour_{int(elapsed//3600)}'
                    report['scenarios'][scenario]=measure(page,8,typing=True)
                while not page.evaluate('window.__qualificationDone'):
                    if time.monotonic()>round_deadline:raise TimeoutError('Four local fixture tasks did not reach their terminal replies within three minutes.')
                    native_visibility.append(native_main_visible(main_handle))
                    page.wait_for_timeout(500)
                results=page.evaluate('window.__qualificationRuns')
                failures=[{'status':item['status'],'error':str(item.get('reason') or item.get('value',{}).get('result',{}).get('error') or '')[:1000]} for item in results if item['status']!='fulfilled' or not item['value']['result']['success'] or 'PACKAGE_STREAM_COMPLETE' not in item['value']['result']['output_text']]
                native_visibility.append(native_main_visible(main_handle))
                report['runs'].append({'iteration':iteration,'count':len(results),'failures':failures,'elapsed_seconds':time.monotonic()-started,'visibility_start':visibility,'visibility_end':page.evaluate('document.visibilityState'),'native_main_visibility_samples':native_visibility})
                if not args.baseline:
                    assert not failures,failures
                if not args.baseline and iteration==0:
                    request(page,'aioControl',{'assistantId':'aio','enable':True})
                    store=AiOStore(app_root/'.reverie/aio')
                    for index in range(10):
                        foreground=foreground_state()
                        store.append('proactive',{'text':f'完整发言 {index}\n'+('可滚动并复制的完整正文。\n'*80)},event_id=f'popup-{index}',visible=True,outbox=True)
                        request(page,'aioControl',{'assistantId':'aio','changes':{'proactive':True}})
                        popup=None
                        for _ in range(40):
                            popup=next((candidate for context in browser.contexts for candidate in context.pages if candidate!=page and not candidate.is_closed() and candidate.url.startswith('data:text/html')),None)
                            if popup:
                                try:
                                    if popup.locator('#body').inner_text(timeout=500):break
                                except Exception:pass
                            page.wait_for_timeout(100)
                        if not popup:raise RuntimeError('AiO popup did not become readable.')
                        popup.wait_for_function("() => document.querySelector('#body').textContent.length>100")
                        page.wait_for_function('id=>window.__aioQualificationEvents.some(event=>event.message_id===id)',arg=f'popup-{index}',timeout=5000)
                        after_foreground=foreground_state()
                        report.setdefault('popup_foreground_samples',[]).append({'message_id':f'popup-{index}','before':foreground,'after':after_foreground})
                        assert after_foreground['handle']==foreground['handle'],f'Native foreground changed during popup presentation: {foreground} -> {after_foreground}'
                        if index==0:
                            popup.screenshot(path=str(output/'aio-popup.png'))
                            popup.locator('#reply').fill('已确认，保持原任务归属。')
                            popup.locator('#send').click()
                        else:popup.locator('#close').click()
                        page.wait_for_timeout(150)
                    popup_events=page.evaluate('window.__aioQualificationEvents.filter(event=>/^popup-\\d+$/.test(event.message_id))')
                    report['popup_ready']=summary([event['latency_ms'] for event in popup_events])
                    assert len(popup_events)==10 and {event['message_id'] for event in popup_events}=={f'popup-{index}' for index in range(10)},'Every popup must acknowledge its saved message exactly once'
                    assert store.get_page(store.mainline_id)['messages'][-1]['content']=='已确认，保持原任务归属。' or any(message['content']=='已确认，保持原任务归属。' for message in store.get_page(store.mainline_id)['messages'])
                    request(page,'aioControl',{'assistantId':'aio','changes':{'proactive':args.interactive_exit}})
                if not args.baseline:
                    report['aio_lifecycle_samples'].append({'elapsed_seconds':time.monotonic()-started,**AiOStore(app_root/'.reverie/aio').state()})
                metrics=page.context.new_cdp_session(page)
                metrics.send('Performance.enable')
                heap=next((item['value'] for item in metrics.send('Performance.getMetrics')['metrics'] if item['name']=='JSHeapUsedSize'),0)
                metrics.detach();report['peak_renderer_heap']=max(report['peak_renderer_heap'],heap)
                if iteration==0:report['scenarios']['visible_idle']=measure(page,8)
                progress={**report,'elapsed_seconds':time.monotonic()-started,'iteration':iteration}
                report['data_growth_samples'].append({'elapsed_seconds':time.monotonic()-started,**data_sizes()})
                (output/'progress.json').write_text(json.dumps(progress,ensure_ascii=False,indent=2),encoding='utf-8')
                iteration+=1
                page.wait_for_timeout(min(30000,max(0,(args.duration_seconds-(time.monotonic()-started))*1000)))
            report['actual_duration_seconds']=time.monotonic()-started
            report['renderer_lifecycle_samples'].append({'elapsed_seconds':report['actual_duration_seconds'],'visibility':page.evaluate('document.visibilityState'),'native_main_visible':native_main_visible(main_handle)})
            report['cold_first_page_ms']=report['history_first_page'][0]
            report['hot_first_page']=summary(report['history_first_page'][1:])
            report['history_first_page']=summary(report['history_first_page'])
            report['cached_switch']=summary(report['cached_switch'])
            report['uncached_switch']=summary(report['uncached_switch'])
            for data in report['scenarios'].values():
                report['peak_renderer_heap']=max(report['peak_renderer_heap'],*(value for value in data.get('js_heap_bytes',{}).values() if value is not None))
            report['checks']={'duration':report['actual_duration_seconds']>=args.duration_seconds,'browser_errors':not report['browser_errors'],'renderer_heap':0<report['peak_renderer_heap']<=512*1024**2,'four_streams_completed':bool(report['runs']) and all(run['count']==4 and not run['failures'] for run in report['runs']),'local_first_page':report['history_first_page']['p95_ms']<=1500}
            report['checks']['foreground_live_output']=report['foreground_live_output_visible']
            report['request_routes']=Fixture.request_routes
            report['checks']['independent_models_and_rules']=bool(Fixture.request_routes) and {route['lane'] for route in Fixture.request_routes}==set(range(4)) and all(route['model_correct'] and route['rule_correct'] for route in Fixture.request_routes)
            if 'process_tree_budget' in report:report['checks']['process_tree_memory']=report['peak_tree_rss']<=report['process_tree_budget']
            report['checks']['cached_switch']=report['cached_switch']['p95_ms']<=300
            report['checks']['uncached_switch']=report['uncached_switch']['p95_ms']<=1500
            if not args.baseline:report['checks']['popup_ready']=report['popup_ready'].get('p95_ms',float('inf'))<=300
            if not args.baseline:
                report['committed_history']=verify_committed_history(roots,owners,app_root,report['runs'])
                report['checks']['committed_history_integrity']=True
            for label,data in report['scenarios'].items():
                report['checks'][label+'_native_window_visible']=all(state['visible'] for state in data['native_windows'].values())
                report['checks'][label+'_native_window_foreground']=all(state['foreground'] for state in data['native_windows'].values())
                report['checks'][label+'_visible']=all(value['visibility']=='visible' for value in data['environment'].values())
                report['checks'][label+'_raf']=data['raf_frames_per_second']>=50
                report['checks'][label+'_frame_p95']=data['frame_intervals']['p95_ms']<=34
                report['checks'][label+'_frame_max']=data['frame_intervals']['max_ms']<=200
                if data['input_to_two_frames']['n']:report['checks'][label+'_input']=data['input_to_two_frames']['p95_ms']<=100
            if args.interactive_exit:
                hidden_rounds=[run for run in report['runs'] if run['native_main_visibility_samples'] and not any(run['native_main_visibility_samples']) and not run['failures']]
                report['checks']['tray_continued_work']=bool(hidden_rounds)
                hidden_seen=False
                restored=False
                for sample in report['renderer_lifecycle_samples']:
                    if not sample['native_main_visible']:hidden_seen=True
                    elif hidden_seen and sample['native_main_visible']:restored=True
                if not native_main_visible(main_handle):
                    (output/'awaiting-tray-restore.json').write_text(json.dumps({'pid':process.pid,'main_window_handle':main_handle,'port':port}),encoding='utf-8')
                    print('READY FOR TRAY RESTORE '+str(output),flush=True)
                    deadline=time.monotonic()+600
                    while process.poll() is None and not native_main_visible(main_handle) and time.monotonic()<deadline:
                        time.sleep(.2)
                    restored=hidden_seen and native_main_visible(main_handle)
                report['checks']['native_tray_restore']=restored
                assert native_main_visible(main_handle),'The native main window was not restored from the tray.'
                page.screenshot(path=str(output/'desktop.png'))
                native_text='AiO 完整正文复制与回复验收\n'+''.join(f'正文第 {index:03} 行：完整文本保留。\n' for index in range(100))+'正文末尾标记：NATIVE_END'
                store.append('proactive',{'text':native_text},event_id='native-manual-first',visible=True,outbox=True)
                store.append('proactive',{'text':'AiO 第二条排队发言：输入期间不得覆盖第一条。'},event_id='native-manual-second',visible=True,outbox=True)
                request(page,'aioControl',{'assistantId':'aio','changes':{'proactive':True}})
                (output/'awaiting-tray-exit.json').write_text(json.dumps({'pid':process.pid,'port':port,'home':str(home),'report':str(output/'report.json')}),encoding='utf-8')
                print('READY FOR TRAY EXIT '+str(output),flush=True)
                deadline=time.monotonic()+600
                while process.poll() is None and time.monotonic()<deadline:
                    time.sleep(.2)
                report['checks']['native_tray_exit']=process.poll() is not None and process.returncode==0
                report['graceful_exit_code']=process.poll()
                time.sleep(1)
                report['checks']['graceful_owned_cleanup']=not surviving_owned(tracked,exclude=process.pid)
                report['native_saved_reply']=any(message.get('role')=='user' and message.get('content')=='已确认完整正文复制，回复保持主线归属。' for message in store.get_page(store.mainline_id)['messages'])
                report['checks']['native_saved_reply']=report['native_saved_reply']
            else:
                page.screenshot(path=str(output/'desktop.png'))
            report['passed']=all(report['checks'].values())
    except Exception as error:
        report['passed']=False
        report['error']=type(error).__name__+': '+str(error)
        report['error_traceback']=traceback.format_exc()
        if error.__cause__:report['cause']=str(error.__cause__)
    finally:
        report['resource_sampling_tail_gap_seconds']=time.monotonic()-last_resource_sample[0] if last_resource_sample[0] else None
        sampling_stop.set()
        if sampling_thread:sampling_thread.join(timeout=5)
        resource_writer_stop.set()
        if resource_writer_thread:resource_writer_thread.join(timeout=5)
        report['resource_sampling_max_gap_seconds']=max(sampling_gaps,default=0)
        report.setdefault('checks',{})['resource_sampling_continuity']=bool(sampling_gaps) and report['resource_sampling_max_gap_seconds']<=5 and report['resource_sampling_tail_gap_seconds'] is not None and report['resource_sampling_tail_gap_seconds']<=5
        report['checks']['resource_access']=not report['resource_access_errors']
        report['checks']['resource_log_complete']=not report['resource_writer_errors'] and report['resource_samples_collected']==report['resource_samples_written'] and resource_queue.empty() and not (sampling_thread and sampling_thread.is_alive()) and not (resource_writer_thread and resource_writer_thread.is_alive())
        if not report['checks']['resource_log_complete']:report['passed']=False
        if not report['checks']['resource_sampling_continuity']:report['passed']=False
        if not report['checks']['resource_access']:report['passed']=False
        if browser:
            try:browser.close()
            except Exception:pass
        stop_process(process)
        cleanup_deadline=time.monotonic()+5
        while surviving_owned(tracked) and time.monotonic()<cleanup_deadline:
            time.sleep(.1)
        report['surviving_owned_processes']=surviving_owned(tracked)
        if report['surviving_owned_processes']:report['passed']=False
        server.shutdown();server.server_close()
        report['fixture_requests']=Fixture.requests
        report['initial_data_bytes']=initial_sizes['total_bytes']
        final_sizes=data_sizes()
        report['final_data_bytes']=final_sizes['total_bytes']
        report['final_database_bytes']=final_sizes['databases']
        report['process_io_write_bytes']=sum(io_peaks.values())
        report['io_scope']='Windows per-process write transfer counters; includes non-disk I/O. Product database growth is reported separately.'
        report['final_disk_bytes']=sum(path.stat().st_size for path in output.rglob('*') if path.is_file())
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'error':report.get('error'),'report':str(output/'report.json')},ensure_ascii=False),flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
