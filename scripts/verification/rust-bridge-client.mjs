import {spawn} from 'node:child_process';
import {createInterface} from 'node:readline';

export function startBridge(executable, cwd, appRoot) {
  const child = spawn(executable, ['--sdk-bridge'], {cwd, windowsHide: true,
    env: {...process.env, REVERIE_APP_ROOT: appRoot}, stdio: ['pipe', 'pipe', 'pipe']});
  const pending = new Map();
  const events = [];
  let sequence = 0;
  let stderr = '';
  let readyResolve;
  let readyReject;
  const ready = new Promise((resolve, reject) => {readyResolve = resolve; readyReject = reject;});
  const lines = createInterface({input: child.stdout});
  lines.on('line', line => {
    let value;
    try {value = JSON.parse(line);} catch(error) {readyReject(error); for(const waiter of pending.values()) waiter.reject(error); return;}
    events.push(value);
    if(value.type === 'ready' && value.id === undefined) {readyResolve(value); return;}
    const waiter = pending.get(value.id);
    if(!waiter) return;
    if(value.type === 'event') {waiter.events.push(value); return;}
    pending.delete(value.id);
    clearTimeout(waiter.timer);
    waiter.resolve({...value, events: waiter.events});
  });
  child.stderr.on('data', bytes => {stderr += bytes.toString();});
  child.on('error', error => {readyReject(error); for(const waiter of pending.values()) {clearTimeout(waiter.timer); waiter.reject(error);}});
  const closed = new Promise(resolve => child.once('exit', (code, signal) => {
    const error = new Error(`Bridge exited ${code}/${signal}: ${stderr}`);
    readyReject(error);
    for(const waiter of pending.values()) {clearTimeout(waiter.timer); waiter.reject(error);}
    resolve({code,signal,stderr});
  }));
  const readyTimer = setTimeout(() => readyReject(new Error('Bridge ready timeout.')), 15000);
  ready.finally(() => clearTimeout(readyTimer)).catch(() => {});
  function request(action, payload = {}, timeout = 15000) {
    const id = ++sequence;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {pending.delete(id); reject(new Error(`Bridge ${action} timed out: ${stderr}`));}, timeout);
      pending.set(id, {resolve,reject,timer,events: []});
      child.stdin.write(JSON.stringify({id,action,payload}) + '\n');
    });
  }
  return {child, ready, request, closed, events};
}
