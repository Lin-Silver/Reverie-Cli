const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

let source=fs.readFileSync(process.argv[2],'utf8');
source=source.slice(0,source.lastIndexOf('\nload().catch'));
const elements=new Map();
const element=id=>{
  if(!elements.has(id))elements.set(id,{setAttribute(){},classList:{add(){}},value:0});
  return elements.get(id);
};
const requests=[];let now=0;
const environment={document:{querySelector:element,getElementById:element,body:element('body')},
  matchMedia:()=>({matches:false}),URLSearchParams,location:{search:''},console,performance:{now:()=>now},
  fetch:(_url,options)=>new Promise(resolve=>requests.push({value:JSON.parse(options.body),
    finish:()=>resolve({ok:true,json:async()=>({receivers:1})})}))};
vm.createContext(environment);
vm.runInContext(source+'\nglobalThis.tests={startSync,stopSync,sendPose,advance,clock:()=>clock};',environment);
const settle=()=>new Promise(setImmediate);
(async()=>{
  environment.tests.startSync();environment.tests.sendPose(true);await settle();
  assert.equal(requests.length,1);
  environment.tests.stopSync();environment.tests.startSync();
  requests[0].finish();await settle();
  assert.equal(requests.length,1,'an outdated stop must not release a restarted controller');
  environment.tests.sendPose(true);await settle();
  assert.equal(requests.length,2);assert.equal(requests[1].value.active,true);
  environment.tests.stopSync();await settle();
  assert.equal(requests.length,2,'release must wait for the active request');
  requests[1].finish();await settle();
  assert.equal(requests.length,3);assert.equal(requests[2].value.active,false);
  requests[2].finish();await settle();

  environment.tests.startSync();
  for(let second=1;second<=10;second++)environment.tests.advance(second*1000);
  assert.equal(environment.tests.clock(),10,'synchronized animation must use actual elapsed time');
  now=60000;environment.tests.stopSync();environment.tests.startSync();
  environment.tests.advance(60100);
  assert(Math.abs(environment.tests.clock()-10.1)<1e-7,'restarting must not count idle wall time');
  console.log('Sync cancellation, serialized release, and wall-clock checks passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
