"""Long-lived AiO identity, segmented events, task branches and transactional outbox."""

from datetime import datetime
from copy import deepcopy
from pathlib import Path
import json
import uuid

from .sqlite_manager import SQLiteSessionManager, _json, _digest
from .manager import Session
from .roles import to_stored_messages
from ..memory.models import MemoryItem, new_id, utc_now
from ..memory.store import MemoryStore


class AiOMemoryStore(MemoryStore):
    """All assistant extraction paths share durable correction tombstones."""

    def _connect(self):
        connection = super()._connect()
        connection.execute('PRAGMA synchronous=FULL')
        return connection

    def _initialize(self):
        super()._initialize()
        with self._connect() as connection:
            connection.executescript('''
                CREATE TABLE IF NOT EXISTS assistant_memory_suppressions (fingerprint TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS assistant_memory_sources (event_id TEXT NOT NULL,kind TEXT NOT NULL,PRIMARY KEY(event_id,kind));
            ''')

    def _write_item(self, connection, item):
        item.scope = 'assistant'
        if item.status in {'deleted','superseded'}:
            connection.execute('INSERT OR IGNORE INTO assistant_memory_suppressions VALUES (?)',(item.fingerprint(),))
            connection.executemany('INSERT OR IGNORE INTO assistant_memory_sources VALUES (?,?)',[(event_id,item.memory_type) for event_id in item.source_event_ids])
        elif item.status == 'active' and item.provenance != 'explicit_correction':
            suppressed = connection.execute('SELECT 1 FROM assistant_memory_suppressions WHERE fingerprint=?',(item.fingerprint(),)).fetchone()
            if not suppressed:
                suppressed = any(connection.execute('SELECT 1 FROM assistant_memory_sources WHERE event_id=? AND kind=?',(event_id,item.memory_type)).fetchone() for event_id in item.source_event_ids)
            if suppressed:
                item.status = 'suppressed'
        super()._write_item(connection,item)


class AiOStore(SQLiteSessionManager):
    mainline_id = 'aio-mainline'

    def __init__(self, base_dir):
        super().__init__(base_dir, navigation=False)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS aio_state (key TEXT PRIMARY KEY,payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS aio_segments (id INTEGER PRIMARY KEY AUTOINCREMENT,date TEXT NOT NULL,summary TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS aio_events (sequence INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT NOT NULL UNIQUE,segment INTEGER NOT NULL,kind TEXT NOT NULL,branch TEXT NOT NULL,created_at TEXT NOT NULL,payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS aio_tasks (id TEXT PRIMARY KEY,branch TEXT NOT NULL UNIQUE,workspace TEXT NOT NULL,configuration TEXT NOT NULL,state TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 1,acceptance TEXT NOT NULL,result TEXT NOT NULL DEFAULT '{}');
                CREATE TABLE IF NOT EXISTS aio_outbox (id TEXT PRIMARY KEY,branch TEXT NOT NULL,state TEXT NOT NULL,created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS aio_signals (id TEXT PRIMARY KEY,payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS aio_memory_suppressions (fingerprint TEXT PRIMARY KEY,reason TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS aio_events_segment ON aio_events(segment,sequence);
                CREATE INDEX IF NOT EXISTS aio_tasks_state ON aio_tasks(state);
            ''')
        self.memory = AiOMemoryStore(self.base_dir)
        with self.connect() as db, self.memory._connect() as memory_db:
            memory_db.executemany('INSERT OR IGNORE INTO assistant_memory_suppressions VALUES (?)',[(row[0],) for row in db.execute('SELECT fingerprint FROM aio_memory_suppressions')])

    def migrate_computer_history(self,legacy_dir):
        from .manager import Session
        imported = 0
        for path in (legacy_dir/'sessions').glob('*.json'):
            with self.connect() as db:
                if db.execute('SELECT 1 FROM conversations WHERE id=?',(path.stem,)).fetchone():
                    continue
            data = json.loads(path.read_text(encoding='utf-8'))
            session = Session.from_dict(data)
            session.metadata['legacy_mode']='computer-controller'
            session.metadata['legacy_source']=str(path)
            self._write_session(session,touch_updated_at=False)
            imported += 1
        return imported

    def _scope_metadata(self):
        return {'assistant_id':'aio'}

    def _record_appended_messages(self, db, entries):
        now = datetime.now().isoformat()
        for branch,sequence,message_id,payload,digest in entries:
            message = json.loads(payload)
            if message.get('role')=='assistant':
                db.execute('INSERT INTO conversation_read_states VALUES (?,1) ON CONFLICT(session_id) DO UPDATE SET unread=1',(branch,))
            kind = 'user' if message.get('role') == 'user' else 'conversation' if branch == self.mainline_id else 'execution_report'
            self._event(db,message_id,kind,{'message_sequence':sequence,'message_id':message_id},branch,now)

    def enable(self, snapshot):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM conversations WHERE id=?',(self.mainline_id,)).fetchone():
                now = datetime.now().isoformat()
                metadata = {'assistant_id':'aio','runtime_config':snapshot}
                db.execute('INSERT INTO conversations VALUES (?,?,?,?,?,1,0,0)',(self.mainline_id,'AiO',now,now,_json(metadata)))
                db.execute('INSERT INTO configuration_versions VALUES (?,1,?,?)',(self.mainline_id,_json(snapshot),now))
            db.execute("INSERT INTO aio_state VALUES ('control',?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload",(_json({'enabled':True,'proactive':True,'paused':False}),))
        return self.state()

    def state(self):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM aio_state WHERE key='control'").fetchone()
            active = [dict(item) for item in db.execute("SELECT t.id,t.branch,t.workspace,CASE WHEN t.state='running' THEN COALESCE((SELECT state FROM task_runs r WHERE r.session_id=t.branch ORDER BY created_at DESC LIMIT 1),t.state) ELSE t.state END AS state,t.revision,t.acceptance FROM aio_tasks t WHERE t.state NOT IN ('completed','cancelled','failed') ORDER BY t.rowid LIMIT 100")]
        return {'assistant_id':'aio','mainline_id':self.mainline_id, **(json.loads(row[0]) if row else {'enabled':False,'proactive':False,'paused':False}), 'tasks':active}

    def create_session(self,name=None):
        session = self.load_session(self.mainline_id)
        if session is None:
            raise ValueError('Enable AiO before opening its mainline.')
        return session

    def fork_current_session(self,message_count=None,name=None,*,workspace=None):
        current=self.get_current_session()
        if current is None:
            raise ValueError('No active AiO conversation to fork.')
        source=SQLiteSessionManager._read_session(self,current.id)
        root=workspace if source.id==self.mainline_id else source.metadata.get('workspace_path')
        if not root:
            raise ValueError('An AiO mainline fork requires its current workspace.')
        messages=deepcopy(source.messages)
        if message_count is not None:
            messages=messages[:max(0,min(int(message_count),len(messages)))]
        metadata={'assistant_id':'aio','workspace_path':str(Path(root).resolve()),'parent':self.mainline_id,
                  'forked_from':source.id,'forked_message_count':len(messages),
                  'runtime_config':deepcopy(source.metadata['runtime_config']),
                  'executor_role':source.metadata.get('executor_role','main')}
        if 'pinned_skills' in source.metadata:
            metadata['pinned_skills']=deepcopy(source.metadata['pinned_skills'])
        if 'task_id' in source.metadata:
            metadata['forked_task_id']=source.metadata['task_id']
        now=datetime.now().isoformat()
        forked=Session('aio-fork-'+uuid.uuid4().hex,name or f'{source.name} (fork)',now,now,messages,metadata)
        self._write_session(forked)
        self.set_current_session(forked)
        return forked

    def delete_session(self,session_id):
        if session_id==self.mainline_id:
            raise ValueError('The persistent AiO mainline cannot be deleted; archive it or start a new segment instead.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            task=db.execute('SELECT id,state FROM aio_tasks WHERE branch=?',(session_id,)).fetchone()
            if task and task['state'] in {'running','verifying','paused'}:
                raise ValueError('Stop the active AiO task before deleting its branch.')
            if task and task['state']=='queued':
                db.execute("UPDATE aio_tasks SET state='cancelled',revision=revision+1 WHERE id=?",(task['id'],))
        return super().delete_session(session_id)

    def export_assistant_records(self,session_id,output_path):
        from .runtime_config import _without_secrets
        mainline=session_id==self.mainline_id
        with self.connect() as db:
            tasks=[{**dict(row),'configuration':_without_secrets(json.loads(row['configuration'])),'result':json.loads(row['result'])} for row in db.execute('SELECT * FROM aio_tasks WHERE ? OR branch=? ORDER BY rowid',(mainline,session_id))]
            segments=[dict(row) for row in db.execute('SELECT * FROM aio_segments WHERE ? OR id IN (SELECT segment FROM aio_events WHERE branch=?) ORDER BY id',(mainline,session_id))]
            last_sequence=db.execute('SELECT COALESCE(MAX(sequence),0) FROM aio_events').fetchone()[0]
        target=Path(output_path).with_name(Path(output_path).name+'.aio-events.jsonl')
        target.parent.mkdir(parents=True,exist_ok=True)
        after=0
        with target.open('w',encoding='utf-8') as output:
            while True:
                with self.connect() as db:
                    rows=db.execute('SELECT e.*,o.state AS delivery_state FROM aio_events e LEFT JOIN aio_outbox o ON o.id=e.id WHERE e.sequence>? AND e.sequence<=? AND (? OR e.branch=?) ORDER BY e.sequence LIMIT 1000',(after,last_sequence,mainline,session_id)).fetchall()
                if not rows:
                    break
                for row in rows:
                    payload=json.loads(row['payload'])
                    if isinstance(payload.get('configuration'),dict):
                        payload['configuration']=_without_secrets(payload['configuration'])
                    output.write(_json({**dict(row),'payload':payload})+'\n')
                after=rows[-1]['sequence']
        return {'assistant_id':'aio','mainline_id':self.mainline_id,'segments':segments,'tasks':tasks,'events_file':target.name,'last_event_sequence':last_sequence}

    def _read_session(self,session_id,*,active_only=False):
        if session_id != self.mainline_id:
            return super()._read_session(session_id,active_only=active_only)
        try:
            page = self.get_page(session_id,limit=60)
        except ValueError:
            return None
        active_start = int(page['metadata'].get('active_context_start',0))
        first = page['total'] - len(page['messages'])
        messages = page['messages'][max(0,active_start-first):]
        session = Session(page['id'],page['name'],page['created_at'],page['updated_at'],messages,page['metadata'])
        self._remember_base(session,page['revision'],[_json(item) for item in to_stored_messages(messages)],max(active_start,first))
        return session

    def _write_session(self,session,*,touch_updated_at=True):
        base = getattr(session,'_storage_base',None)
        payloads = [_json(item) for item in to_stored_messages(session.messages)]
        prefix = base['messages'] if base else []
        replacement = base and (len(payloads)<len(prefix) or [_digest(item) for item in payloads[:len(prefix)]] != prefix)
        if session.id != self.mainline_id or not replacement:
            return super()._write_session(session,touch_updated_at=touch_updated_at)
        # A new context segment appends to the lossless mainline instead of deleting it.
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM conversations WHERE id=?',(session.id,)).fetchone()
            if row['revision'] != session._storage_revision:
                raise ValueError('AiO context revision conflict; reload before segmentation.')
            now = datetime.now().isoformat()
            session.metadata['active_context_start'] = row['message_count']
            db.executemany('INSERT INTO messages VALUES (?,?,?,?,?)',[(session.id,row['message_count']+index,uuid.uuid4().hex,item,_digest(item)) for index,item in enumerate(payloads)])
            db.execute('UPDATE conversations SET metadata=?,message_count=message_count+?,revision=revision+1,updated_at=? WHERE id=?',(_json(session.metadata),len(payloads),now,session.id))
        self._remember_base(session,row['revision']+1,payloads,row['message_count'])
        return session.to_dict()

    def restore_last_session(self):
        return self._current_session or self.load_session(self.mainline_id)

    def rotate_session(self,working_memory,reason='Context threshold reached',handoff_packet=None):
        session = self._current_session or self.restore_last_session()
        if session.id != self.mainline_id:
            return super().rotate_session(working_memory,reason,handoff_packet)
        self.segment_summary(working_memory)
        session.messages = [{'role':'system','content':working_memory,'segment_boundary':True}]
        self.save_session(session)
        return session

    def control(self, changes):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT payload FROM aio_state WHERE key='control'").fetchone()
            state = json.loads(row[0]) if row else {'enabled':False,'proactive':False,'paused':False}
            for key,value in changes.items():
                if key not in state or not isinstance(value,bool):
                    raise ValueError('Invalid AiO control setting.')
                state[key] = value
            if changes.get('enabled') is False:
                db.execute("UPDATE aio_tasks SET state='cancelled',revision=revision+1 WHERE state='queued'")
            db.execute("INSERT OR REPLACE INTO aio_state VALUES ('control',?)",(_json(state),))
        return self.state()

    def _segment(self, db, now):
        row = db.execute('SELECT id,date FROM aio_segments ORDER BY id DESC LIMIT 1').fetchone()
        if row is None or row['date'] != now[:10]:
            return db.execute('INSERT INTO aio_segments(date) VALUES (?)',(now[:10],)).lastrowid
        return row['id']

    def _event(self,db,event_id,kind,payload,branch,now):
        existing = db.execute('SELECT kind,branch,payload FROM aio_events WHERE id=?',(event_id,)).fetchone()
        if existing:
            if tuple(existing) != (kind,branch,_json(payload)):
                raise ValueError('AiO event identity was reused with different content.')
            return False
        db.execute('INSERT INTO aio_events(id,segment,kind,branch,created_at,payload) VALUES (?,?,?,?,?,?)',(event_id,self._segment(db,now),kind,branch,now,_json(payload)))
        return True

    def _message(self,db,event_id,branch,role,text,now):
        row = db.execute('SELECT message_count FROM conversations WHERE id=? AND deleted=0',(branch,)).fetchone()
        if not row:
            raise ValueError('AiO reply branch is unavailable.')
        payload = _json(to_stored_messages([{'role':role,'content':text,'event_id':event_id}])[0])
        db.execute('INSERT INTO messages VALUES (?,?,?,?,?)',(branch,row[0],event_id,payload,_digest(payload)))
        db.execute('UPDATE conversations SET message_count=message_count+1,revision=revision+1,updated_at=? WHERE id=?',(now,branch))
        if role=='assistant':
            db.execute('INSERT INTO conversation_read_states VALUES (?,1) ON CONFLICT(session_id) DO UPDATE SET unread=1',(branch,))

    def append(self,kind,payload,*,event_id=None,branch=None,visible=False,outbox=False):
        event_id = event_id or uuid.uuid4().hex
        branch = branch or self.mainline_id
        now = datetime.now().isoformat()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if self._event(db,event_id,kind,payload,branch,now):
                if visible:
                    self._message(db,event_id,branch,'user' if kind == 'user' else 'assistant',str(payload.get('text') or ''),now)
                if outbox:
                    db.execute("INSERT INTO aio_outbox VALUES (?,?,'queued',?)",(event_id,branch,now))
        return event_id

    def create_task(self,workspace,configuration,prompt,acceptance,*,task_id=None):
        task_id = task_id or uuid.uuid4().hex
        branch = f'aio-task-{task_id}'
        now = datetime.now().isoformat()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._create_task(db,task_id,workspace,configuration,prompt,acceptance,now)
        return {'id':task_id,'branch':branch}

    def _create_task(self,db,task_id,workspace,configuration,prompt,acceptance,now,run_type='prompt'):
        branch = f'aio-task-{task_id}'
        event = {'workspace':workspace,'prompt':prompt,'acceptance':acceptance,'configuration':configuration,'runType':run_type}
        if not self._event(db,task_id,'task.created',event,branch,now):
            return
        metadata = {'assistant_id':'aio','workspace_path':workspace,'runtime_config':configuration,'parent':self.mainline_id,'task_id':task_id,'executor_role':'main' if configuration.get('settings',{}).get('mode') == 'aio' else 'worker'}
        db.execute('INSERT INTO conversations VALUES (?,?,?,?,?,1,0,0)',(branch,prompt[:64] or 'AiO task',now,now,_json(metadata)))
        db.execute('INSERT INTO configuration_versions VALUES (?,1,?,?)',(branch,_json(configuration),now))
        db.execute("INSERT INTO aio_tasks VALUES (?,?,?,?,'queued',1,?,'{}')",(task_id,branch,workspace,_json(configuration),acceptance))
        self._message(db,f'{task_id}-request',branch,'user',prompt,now)

    def accept_decision(self,decision_id,decision,observation,tasks,*,show):
        now = datetime.now().isoformat()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not self._event(db,decision_id,'decision',decision,self.mainline_id,now):
                return False
            evidence = f'{decision_id}-observation'
            self._event(db,evidence,'observation',observation,self.mainline_id,now)
            speech = str(decision.get('speech') or '')
            if speech:
                branch = str(observation.get('branch') or self.mainline_id) if observation.get('type') in {'task.result','user.reply'} else self.mainline_id
                message_id = f'{decision_id}-speech'
                self._event(db,message_id,'proactive',{'text':speech,'evidence':evidence},branch,now)
                self._message(db,message_id,branch,'assistant',speech,now)
                if show:
                    db.execute("INSERT INTO aio_outbox VALUES (?,?,'queued',?)",(message_id,branch,now))
            for task in tasks:
                self._create_task(db,task['id'],task['workspace'],task['configuration'],task['prompt'],task['acceptance'],now,task.get('runType','prompt'))
        return True

    def task_state(self,task_id,state,*,revision,result=None):
        allowed = {'queued','running','waiting_user','paused','verifying','waiting_incorporation','completed','cancelled','failed','interrupted'}
        if state not in allowed:
            raise ValueError('Invalid AiO task state.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            previous = db.execute('SELECT state FROM aio_tasks WHERE id=?',(task_id,)).fetchone()
            if previous and previous['state'] in {'completed','cancelled','failed'}:
                raise ValueError('AiO task is finalized; create a new branch to continue.')
            changed = db.execute('UPDATE aio_tasks SET state=?,revision=revision+1,result=? WHERE id=? AND revision=?',(state,_json(result or {}),task_id,revision)).rowcount
            if not changed:
                raise ValueError('AiO task revision conflict.')
            self._event(db,f'{task_id}-state-{revision + 1}','task.state',{'task_id':task_id,'state':state,'result':result or {}},self.mainline_id,datetime.now().isoformat())
            if state in {'completed','cancelled','failed','interrupted','waiting_user','waiting_incorporation'}:
                branch = db.execute('SELECT branch FROM aio_tasks WHERE id=?',(task_id,)).fetchone()[0]
                signal_id = f'{task_id}-result-{revision + 1}'
                db.execute('INSERT INTO aio_signals VALUES (?,?)',(signal_id,_json({'event_id':signal_id,'type':'task.result','task_id':task_id,'branch':branch,'result':result or {},'state':state})))
        return revision + 1

    def recover_host(self):
        """Only the owning GUI host calls this once after acquiring the app lock."""
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            # Delivery may have happened before acknowledgement; never replay it blindly.
            db.execute("UPDATE aio_outbox SET state='delivery_uncertain' WHERE state='displaying'")
            tasks = db.execute("SELECT id,revision FROM aio_tasks WHERE state IN ('running','verifying','paused')").fetchall()
            for task in tasks:
                db.execute("UPDATE aio_tasks SET state='interrupted',revision=revision+1 WHERE id=?",(task['id'],))
                self._event(db,f"{task['id']}-state-{task['revision'] + 1}",'task.state',{'task_id':task['id'],'state':'interrupted','reason':'Application restarted; verify actual effects before resuming.'},self.mainline_id,datetime.now().isoformat())
        return self.state()

    def pending_tasks(self):
        with self.connect() as db:
            rows = db.execute("SELECT t.*,e.payload FROM aio_tasks t JOIN aio_events e ON e.id=t.id WHERE t.state='queued' ORDER BY t.rowid LIMIT 100").fetchall()
        return [{**dict(row),'configuration':json.loads(row['configuration']),'prompt':json.loads(row['payload'])['prompt'],'runType':json.loads(row['payload']).get('runType','prompt')} for row in rows]

    def pending_messages(self,limit=20):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT o.id,o.branch,e.payload,o.created_at,json_extract(c.metadata,'$.workspace_path') AS workspace FROM aio_outbox o JOIN aio_events e ON e.id=o.id JOIN conversations c ON c.id=o.branch WHERE o.state='queued' AND c.deleted=0 ORDER BY o.created_at LIMIT ?",(limit,))]

    def claim_message(self,event_id):
        with self.connect() as db:
            return bool(db.execute("UPDATE aio_outbox SET state='displaying' WHERE id=? AND state='queued'",(event_id,)).rowcount)

    def acknowledge_message(self,event_id):
        with self.connect() as db:
            db.execute("UPDATE aio_outbox SET state='presented' WHERE id=? AND state='displaying'",(event_id,))

    def release_message(self,event_id):
        with self.connect() as db:
            db.execute("UPDATE aio_outbox SET state='queued' WHERE id=? AND state='displaying'",(event_id,))

    def reply(self,event_id,text,reply_id):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT branch FROM aio_outbox WHERE id=?',(event_id,)).fetchone()
            if not row:
                raise ValueError('AiO message is unavailable.')
            now = datetime.now().isoformat()
            if self._event(db,reply_id,'user',{'text':text,'reply_to':event_id},row[0],now):
                self._message(db,reply_id,row[0],'user',text,now)
                db.execute('INSERT INTO aio_signals VALUES (?,?)',(reply_id,_json({'event_id':reply_id,'type':'user.reply','message_id':reply_id,'branch':row[0],'text':text})))
        return reply_id

    def pending_signals(self):
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute('SELECT payload FROM aio_signals ORDER BY rowid LIMIT 20')]

    def acknowledge_signal(self,event_id):
        with self.connect() as db:
            db.execute('DELETE FROM aio_signals WHERE id=?',(event_id,))

    def segment_summary(self,summary):
        now = datetime.now().isoformat()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current = self._segment(db,now)
            db.execute('UPDATE aio_segments SET summary=? WHERE id=?',(summary,current))
            db.execute('INSERT INTO aio_segments(date) VALUES (?)',(now[:10],))

    def context(self,query='',*,max_chars=48000):
        page = self.get_page(self.mainline_id)
        with self.connect() as db:
            summaries = [row[0] for row in db.execute("SELECT summary FROM aio_segments WHERE summary!='' ORDER BY id DESC LIMIT 4")]
            tasks = [dict(row) for row in db.execute("SELECT id,branch,workspace,state,substr(acceptance,1,512) AS acceptance FROM aio_tasks WHERE state NOT IN ('completed','cancelled','failed') ORDER BY rowid DESC LIMIT 16")]
        relevant = [self.memory.get(memory_id) for memory_id in self.memory.search_fts(query,limit=8)] if query else []
        memories = [item for item in relevant if item is not None] or self.memory.load_items(limit=8)
        context = {'recent':[],'summaries':[],'tasks':tasks,'memories':[], 'history_ref':{'session_id':self.mainline_id,'total':page['total']}}
        # These are explicitly labelled context excerpts. The authoritative bodies are unchanged.
        for item in memories:
            value = item.to_dict()
            if len(value['content']) > 1024:
                value['content'] = value['content'][:1024]
                value['context_excerpt'] = True
            context['memories'].append(value)
        for summary in summaries:
            context['summaries'].append(summary if len(summary)<=4096 else {'excerpt':summary[:4096],'context_excerpt':True})
        remaining = max(0,max_chars-len(_json(context)))
        first = page['total']-len(page['messages'])
        for index in range(len(page['messages'])-1,-1,-1):
            message = dict(page['messages'][index])
            body = message.get('content','')
            text = body if isinstance(body,str) else _json(body)
            if len(text)>min(4096,remaining):
                message['content'] = text[:min(4096,max(0,remaining-200))]
                message['context_excerpt'] = True
            message['history_ref'] = {'session_id':self.mainline_id,'sequence':first+index}
            size = len(_json(message))
            if size>remaining:
                break
            context['recent'].insert(0,message)
            remaining -= size
        return context

    def remember(self,content,*,kind='preference',provenance='inferred',confidence=0.5,event_ids=()):
        if provenance not in {'explicit_statement','observed','inferred'}:
            raise ValueError('Memory provenance must distinguish statement, observation and inference.')
        item = MemoryItem(id=new_id('mem'),scope='assistant',memory_type=kind,content=content,provenance=provenance,confidence=confidence,source='aio',source_event_ids=list(event_ids),evidence=[{'event_id':event_id} for event_id in event_ids])
        with self.connect() as db:
            if db.execute('SELECT 1 FROM aio_memory_suppressions WHERE fingerprint=?',(item.fingerprint(),)).fetchone():
                return None
        saved = self.memory.upsert(item)
        return saved if saved.status == 'active' else None

    def edit_memory(self,memory_id,content=None):
        existing = self.memory.get(memory_id)
        if existing is None:
            raise ValueError('Memory not found.')
        # Persist the suppression first: replay after a crash cannot resurrect old content.
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO aio_memory_suppressions VALUES (?,?)',(existing.fingerprint(),'deleted' if content is None else 'corrected'))
        return self.memory.delete(memory_id) if content is None else self.memory.correct(memory_id,content)
