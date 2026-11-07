const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {once}=require('node:events');

const child=spawn(process.execPath,[process.argv[2]],{env:{...process.env,PORT:'0'},stdio:['ignore','pipe','pipe']});
let reader;
(async()=>{
  const output=await once(child.stdout,'data');
  const url=/http:\/\/127\.0\.0\.1:\d+/.exec(output[0].toString())[0];
  const response=await fetch(url+'/avatar-events');reader=response.body.getReader();
  let pending='';const poses=[],waiting=[];
  const receive=(async()=>{
    while(true){
      const {value,done}=await reader.read();if(done)return;
      pending+=Buffer.from(value).toString();let end;
      while((end=pending.indexOf('\n\n'))>=0){
        const packet=pending.slice(0,end);pending=pending.slice(end+2);
        if(!packet.startsWith('data: '))continue;
        const pose=JSON.parse(packet.slice(6));poses.push(pose);
        const resolve=waiting.shift();if(resolve)resolve(pose);
      }
    }
  })();
  let index=0;
  const next=()=>index<poses.length?Promise.resolve(poses[index++]):Promise.race([
    new Promise(resolve=>waiting.push(pose=>{index++;resolve(pose);})),
    new Promise((_,reject)=>setTimeout(()=>reject(new Error('No relayed pose')),6000).unref())]);
  assert.deepEqual(await next(),{active:false});
  const parameters={lookX:2,lookY:-2,breath:-1,hairSway:.8,blinkLeft:1,blinkRight:.4,mouthOpen:.7,smile:.5};
  const post=(value,headers={})=>fetch(url+'/avatar-state',{method:'POST',headers:{'Content-Type':'application/json',...headers},body:JSON.stringify(value)});
  const sent=await post({active:true,parameters,audio:'must never be relayed'});
  assert.equal(sent.status,200);assert.equal((await sent.json()).receivers,1);
  const pose=await next();assert.equal(pose.parameters.lookX,1);assert.equal(pose.parameters.lookY,-1);
  assert.equal(pose.parameters.breath,0);assert.equal(pose.parameters.mouthOpen,.7);
  assert.equal(Object.keys(pose.parameters).length,8);assert.equal('audio' in pose,false);
  assert.equal((await post({active:true,parameters:{...parameters,mouthOpen:null}})).status,400);
  assert.equal((await post({active:false},{Origin:'https://example.org'})).status,403);
  assert.equal((await fetch(url+'/%2e%2e%2ftest-secret.txt')).status,403);
  assert.equal((await fetch(url+'/avatar-state',{method:'POST',headers:{'Content-Type':'application/json'},body:'x'.repeat(4097)})).status,413);
  assert.equal((await post({active:false})).status,200);assert.deepEqual(await next(),{active:false});
  await post({active:true,parameters});assert.equal((await next()).active,true);
  assert.deepEqual(await next(),{active:false},'a disconnected controller must release the output');
  await reader.cancel();await receive;
  console.log('Pose relay, release, timeout, validation, origin, and containment checks passed');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{
  if(reader)await reader.cancel().catch(()=>{});child.kill();
});
