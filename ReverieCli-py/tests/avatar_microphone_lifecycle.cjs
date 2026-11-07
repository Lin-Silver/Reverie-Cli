const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

// Execute the maintained viewer's state/handlers; real graphics and audio are
// covered by browser integration checks. Bootstrap fetch/RAF is not started.
let source = fs.readFileSync(process.argv[2], 'utf8');
const bootstrap = source.lastIndexOf('\nload().catch');
assert(bootstrap > 0);
source = source.slice(0, bootstrap);
if (process.argv.includes('--mutate')) source = source.replace('  audioRequest++;\n', '');
const elements = new Map();
const element = id => {
  if (!elements.has(id)) elements.set(id, {setAttribute(){}, classList:{add(){}}, value:0});
  return elements.get(id);
};
let grant, resume, stopCount = 0, closeCount = 0, deferResume = false;
const stream = {getTracks:()=>[{stop(){stopCount++;}}]};
class AudioContext {
  resume(){return deferResume ? new Promise(resolve=>{resume=resolve;}) : Promise.resolve();}
  createAnalyser(){return {fftSize:512,getFloatTimeDomainData(){}};}
  createMediaStreamSource(){return {connect(){}};}
  close(){closeCount++;return Promise.resolve();}
}
const environment = {document:{querySelector:element,getElementById:element,body:element('body')},
  matchMedia:()=>({matches:false}),URLSearchParams,location:{search:''},AudioContext,
  navigator:{mediaDevices:{getUserMedia:()=>new Promise(resolve=>{grant=resolve;})}},
  console,performance:{now:()=>0}};
vm.createContext(environment);
vm.runInContext(source+'\nglobalThis.tests={microphone,reset,stopMicrophone,active:()=>Boolean(audio)};',environment);

(async()=>{
  const pending = environment.tests.microphone();
  environment.tests.reset(true);
  grant(stream);
  await pending;
  assert.equal(environment.tests.active(),false,'reset must cancel pending microphone activation');
  assert.equal(stopCount,1,'the stale granted stream must be stopped');

  deferResume=true;
  environment.navigator.mediaDevices.getUserMedia=()=>Promise.resolve(stream);
  const resuming=environment.tests.microphone();
  // Let the VM assimilate the host Promise before checking the deferred resume.
  await new Promise(setImmediate);
  assert.equal(typeof resume,'function');
  environment.tests.stopMicrophone();
  assert.equal(stopCount,2,'stop must release the stream without waiting for AudioContext resume');
  assert.equal(closeCount,1,'stop must close the pending AudioContext immediately');
  resume();
  await resuming;
  assert.equal(environment.tests.active(),false,'stop must cancel pending AudioContext resume');
  assert.equal(stopCount,2);
  assert.equal(closeCount,1);

  deferResume=false;
  await environment.tests.microphone();
  assert.equal(environment.tests.active(),true);
  environment.tests.stopMicrophone();
  assert.equal(environment.tests.active(),false);
  assert.equal(stopCount,3);
  assert.equal(closeCount,2);
  console.log('Three microphone lifecycle checks passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
