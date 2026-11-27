const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

// Served over loopback. Chromium supplies a genuine File input and GET/POST requests.
module.exports = function fileCases(project) {
  const original = Buffer.from([0, 255, ...Buffer.from('Reverie 文件\n'), 1]);
  const download = Buffer.concat([original, Buffer.alloc(160 * 1024, 85)]);
  const uploadPath = '作品.bin';
  const received = [];
  const digest = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
  fs.writeFileSync(path.join(project, uploadPath), original);
  let downloadCount = 0, held = false;
  async function serve(req, res) {
    if (req.url === '/files') {
      res.writeHead(200, {'Content-Type':'text/html; charset=utf-8', 'Set-Cookie':'browser_files=allowed; HttpOnly; SameSite=Lax'});
      res.end('<title>Files</title><body style="background:#bd682a"><label>Attachment<input id="attachment" type="file"></label><button onclick="fetch(\'/receive\',{method:\'POST\',body:attachment.files[0]}).then(()=>document.querySelector(\'p\').textContent=\'Sent\')">Send</button><a href="/asset">Download sample</a> <a href="/slow-file">Slow download</a> <a href="/bad-redirect">Blocked link</a><p>Ready</p>');
    } else if (req.url === '/receive') {
      const chunks=[]; for await (const chunk of req) chunks.push(chunk);
      received.push(Buffer.concat(chunks)); res.end('received');
    } else if (req.url === '/asset' || req.url === '/bad-redirect') {
      res.writeHead(302,{Location:req.url==='/asset'?'/asset-bytes':'file:///outside/fixture.bin'});res.end();
    } else if (req.url === '/asset-bytes' || req.url === '/slow-file') {
      if (!req.headers.cookie?.includes('browser_files=allowed')) { res.writeHead(403);res.end();return true; }
      if (req.url === '/slow-file') {
        held=true; res.writeHead(200); res.write(original); res.on('close',()=>{held=false;});
      } else {
        downloadCount++;
        res.writeHead(200,{'Content-Type':'application/octet-stream','Content-Disposition':'attachment; filename="server-choice.bin"','Cache-Control':'no-store'});
        res.end(download);
      }
    } else return false;
    return true;
  }
  function inspect(reply) {
    assert.equal(reply.success,true,JSON.stringify(reply));
    const png=path.join(project,'.reverie/browser/observations',reply.data.result.observation.screenshot.image_id+'.png');
    assert.equal(fs.readFileSync(png).subarray(1,4).toString(),'PNG');
    if (process.versions.electron) {
      const snapshot=require('electron').nativeImage.createFromPath(png);
      const {width,height}=snapshot.getSize(), bitmap=snapshot.toBitmap();
      const pixel=(Math.floor(height*.66)*width+Math.floor(width*.5))*4;
      const channels=Array.from(bitmap.subarray(pixel,pixel+3)).sort((a,b)=>a-b);
      assert(channels.length===3 && channels.every((v,i)=>Math.abs(v-[42,104,189][i])<=3),'File tab screenshot must contain its actual fixture background');
    }
    return {
      target:reply.data.target,
      element(name) {
        const item=reply.data.result.observation.elements.find(e=>e.name===name);
        assert(item,'Missing file fixture element '+name);return item.element_id;
      }
    };
  }
  async function* flow(base, mode, until) {
    const opened=yield {action:'open',url:base+'/files'};
    assert.equal(opened.success,true,JSON.stringify(opened));
    const tab_id=opened.data.result.tab.tab_id, observe={action:'observe',tab_id};
    let seen=inspect(yield observe);
    const attachment=() => ({action:'upload',target:seen.target,element_id:seen.element('Attachment'),path:uploadPath,origin:base});
    const asset=(file)=>({action:'download',target:seen.target,element_id:seen.element('Download sample'),path:file});
    if (mode==='strict' || mode==='full_access') {
      const before=downloadCount;
      const name=mode==='strict'?'download.bin':'download-full.bin';
      const saved=yield asset(name);
      assert.equal(saved.success,true,JSON.stringify(saved));
      assert.deepEqual(saved.data.file,{path:name,bytes:download.length,sha256:digest(download)});
      assert.deepEqual(fs.readFileSync(path.join(project,name)),download);assert.equal(downloadCount,before+1);
      assert(!fs.existsSync(path.join(project,'server-choice.bin')));
      seen=inspect(yield observe);
    }
    if (mode==='strict') {
      const before=downloadCount;
      for (const name of ['download.bin','../outside.bin','linked/outside.bin','.reverie/injected']) {
        const refused=yield asset(name);
        assert.equal(refused.success,false,JSON.stringify(refused));
      }
      assert.equal(downloadCount,before);
      const redirect=yield {...asset('unsafe.bin'),element_id:seen.element('Blocked link')};
      assert.equal(redirect.success,false);assert(!fs.existsSync(path.join(project,'unsafe.bin')));
      seen=inspect(yield observe);
      const denied=yield attachment();
      assert.equal(denied.success,false);assert.match(denied.error,/denied|declined/i);
      seen=inspect(yield observe);
    }
    const count=received.length;
    const attached=yield attachment();
    assert.equal(attached.success,true,JSON.stringify(attached));
    assert.deepEqual(attached.data.file,{path:uploadPath,bytes:original.length,sha256:digest(original)});
    if (mode==='strict') fs.writeFileSync(path.join(project,uploadPath),'changed after selection');
    seen=inspect(yield observe);
    const click=yield {action:'click',target:seen.target,element_id:seen.element('Send')};
    assert.equal(click.success,true,JSON.stringify(click));
    await until(()=>received.length===count+1,'real HTTP upload');
    assert.deepEqual(received.at(-1),original);
    if (mode==='strict') {
      fs.writeFileSync(path.join(project,uploadPath),original);
      seen=inspect(yield observe);
      for (const changed of [{origin:'https://other.invalid'}, {path:'../outside.bin'}, {path:'linked/private.bin'}]) {
        const blocked=yield {...attachment(),...changed};assert.equal(blocked.success,false);
      }
      const again=yield attachment();assert.equal(again.success,true,JSON.stringify(again));
    }
  }
  function* readOnly() {
    const target={tab_id:'unavailable',observation_id:'none',revision:1};
    for(const action of ['upload','download']) {
      const result=yield {action,target,element_id:'e1',path:'no-write.bin',...(action==='upload'?{origin:'http://localhost'}:{})};
      assert.equal(result.success,false);assert.match(result.error,/permission level/i);
    }
    assert(!fs.existsSync(path.join(project,'no-write.bin')));
  }
  function* slow(base) {
    const open=yield {action:'open',url:base+'/files'};assert.equal(open.success,true);
    const seen=inspect(yield {action:'observe',tab_id:open.data.result.tab.tab_id});
    yield {action:'download',target:seen.target,element_id:seen.element('Slow download'),path:'interrupted.bin'};
  }
  const outside=path.join(path.dirname(project),'outside-files');
  fs.mkdirSync(outside);fs.writeFileSync(path.join(outside,'private.bin'),'outside');
  fs.symlinkSync(outside,path.join(project,'linked'),process.platform==='win32'?'junction':'dir');
  return {serve,flow,readOnly,slow,held:()=>held,evidence:()=>({
    uploaded:received.map(bytes=>({bytes:bytes.length,sha256:digest(bytes)})),
    downloads:downloadCount,
    saved:['download.bin','download-full.bin'].filter(name=>fs.existsSync(path.join(project,name))).map(name=>{
      const bytes=fs.readFileSync(path.join(project,name));return {path:name,bytes:bytes.length,sha256:digest(bytes)};
    }),
  }),verifyCleanup() {
    assert(!fs.existsSync(path.join(outside,'outside.bin')));
    assert(!fs.existsSync(path.join(project,'interrupted.bin')));
    assert(!fs.readdirSync(project).some(file=>file.endsWith('.part')));
  }};
};
