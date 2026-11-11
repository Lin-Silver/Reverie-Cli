"""Compare retained JSON storage and transactional storage on the approved local dataset.

This measures source persistence, paging and process resources. It does not
qualify renderer scheduling, model quality, popups or the final Windows package.
"""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
import argparse
import json
import math
import sys
import threading
import time

import psutil

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'ReverieCli-py'))


def distribution(values):
    ordered=sorted(values)
    return {'n':len(ordered),'p50_ms':ordered[math.ceil(len(ordered)*.5)-1],'p95_ms':ordered[math.ceil(len(ordered)*.95)-1],'max_ms':ordered[-1]}


def manager(kind,root):
    if kind=='sqlite':
        from reverie.session.sqlite_manager import SQLiteSessionManager
        return SQLiteSessionManager(root,project_root=root,navigation=False)
    from reverie.session.manager import SessionManager
    return SessionManager(root,project_root=root)


def writer(kind,root,session_id,worker):
    store=manager(kind,Path(root))
    session=store.load_session(session_id)
    timings=[]
    commits=[]
    for index in range(100):
        message={'role':'assistant','content':f'worker={worker} event={index} 中文 '+('stream fragment '*32)}
        start=time.perf_counter()
        if kind=='sqlite':
            store.append_messages(session_id,[message],event_id=f'worker-{worker}-{index}')
            commits.append((time.perf_counter()-start)*1000)
            stream_start=time.perf_counter()
            store.write_stream(session_id,f'run-{worker}','assistant',message['content'])
            commits.append((time.perf_counter()-stream_start)*1000)
        else:
            session.messages.append(message)
            store.save_session(session)
            commits.append((time.perf_counter()-start)*1000)
        timings.append((time.perf_counter()-start)*1000)
    store.flush_session_index()
    return {'cycles':timings,'commits':commits}


def fixture(kind,directory):
    store=manager(kind,directory)
    sessions=[]
    for index in range(1000):
        session=store.create_session(f'Conversation {index:04}')
        session.messages=[{'role':'user','content':'普通对话原文 '+str(index)},{'role':'assistant','content':'Preserved answer '+str(index)}]
        if index==0:
            session.messages=[{'role':'assistant' if row%2 else 'user','content':'长对话原文 '+str(row)+' '+('context '*24)} for row in range(10000)]
        store.save_session(session)
        sessions.append(session.id)
    aio=directory/'assistant'
    if kind=='sqlite':
        from reverie.session.aio_store import AiOStore
        events=AiOStore(aio)
        events.enable({'version':1,'model_ref':{'source':'standard','model':''},'settings':{'mode':'aio'}})
        with events.connect() as db:
            for batch in range(100):
                db.execute('BEGIN IMMEDIATE')
                for index in range(batch*1000,(batch+1)*1000):
                    events._event(db,f'event-{index}','observation',{'source':'qualification','text':'分段观察原文 '+str(index)},events.mainline_id,'2026-11-07T12:00:00')
                db.commit()
    else:
        events=manager(kind,aio)
        session=events.create_session('Computer history baseline')
        session.messages=[{'role':'system','content':{'source':'qualification','text':'分段观察原文 '+str(index)}} for index in range(100000)]
        events.save_session(session)
    return store,sessions


def measure(kind,directory):
    directory.mkdir(parents=True,exist_ok=False)
    store,sessions=fixture(kind,directory)
    resources=[]
    stop=threading.Event()
    process=psutil.Process()
    def sample():
        while not stop.is_set():
            entries=[]
            for child in [process,*process.children(recursive=True)]:
                try:
                    io=child.io_counters()
                    entries.append({'pid':child.pid,'rss':child.memory_info().rss,'write_bytes':io.write_bytes,'read_bytes':io.read_bytes})
                except (psutil.NoSuchProcess,psutil.AccessDenied):
                    pass
            resources.append({'at':time.monotonic(),'processes':entries})
            stop.wait(.1)
    monitor=threading.Thread(target=sample,daemon=True)
    monitor.start()
    initial_bytes=sum(file.stat().st_size for file in directory.rglob('*') if file.is_file())
    try:
        with ProcessPoolExecutor(max_workers=4,mp_context=get_context('spawn')) as pool:
            futures=[pool.submit(writer,kind,str(directory),session_id,index) for index,session_id in enumerate(sessions[1:5])]
            writes=[future.result(timeout=300) for future in futures]
            samples=[value for write in writes for value in write['cycles']]
            commit_samples=[value for write in writes for value in write['commits']]
        first_pages=[]
        for index in range(100):
            start=time.perf_counter()
            if kind=='sqlite':
                page=store.get_page(sessions[0])
                assert page['total']==10000 and len(page['messages'])==60
            else:
                assert len(store.load_session(sessions[0]).messages)==10000
            first_pages.append((time.perf_counter()-start)*1000)
        for session_id in sessions[1:5]:
            assert len(store.load_session(session_id).messages)==102
        assert len(store.list_sessions())==1000
        if kind=='sqlite':
            from reverie.session.aio_store import AiOStore
            with AiOStore(directory/'assistant').connect() as db:
                assert db.execute('SELECT count(*) FROM aio_events').fetchone()[0]==100000
    finally:
        stop.set();monitor.join(timeout=5)
    commits=distribution(samples)
    incremental_commits=distribution(commit_samples)
    pages=distribution(first_pages)
    result={'kind':kind,'method':__doc__,'dataset':{'conversations':1000,'long_messages':10000,'assistant_events':100000,'writers':4,'writes_per_writer':100},'save_with_stream':commits,'incremental_commit':incremental_commits,'first_page':pages,'initial_disk_bytes':initial_bytes,'final_disk_bytes':sum(file.stat().st_size for file in directory.rglob('*') if file.is_file()),'peak_process_tree_rss':max(sum(entry['rss'] for entry in row['processes']) for row in resources),'peak_process_count':max(len(row['processes']) for row in resources),'resources':resources,'saved_message_counts_verified':True}
    result['source_gates_passed']=kind=='sqlite' and incremental_commits['p95_ms']<=100 and pages['p95_ms']<=1500
    (directory/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    output=args.output.resolve()
    if output.exists() or not output.is_relative_to(ROOT/'.runtime'):
        parser.error('Use a fresh directory inside this project .runtime.')
    output.mkdir()
    comparisons=[]
    for repetition in range(1,4):
        for kind in ['legacy','sqlite']:
            result=measure(kind,output/f'{kind}-{repetition}')
            comparisons.append({key:value for key,value in result.items() if key!='resources'})
            (output/'comparison.json').write_text(json.dumps(comparisons,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({'repetition':repetition,'kind':kind,'save':result['save_with_stream'],'first_page':result['first_page'],'source_gates_passed':result['source_gates_passed']}),flush=True)
    return 0 if all(result['source_gates_passed'] for result in comparisons if result['kind']=='sqlite') else 1


if __name__=='__main__':
    raise SystemExit(main())
