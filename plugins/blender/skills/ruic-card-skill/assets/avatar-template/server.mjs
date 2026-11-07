import http from 'node:http';
import {readFile,stat} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root=path.dirname(fileURLToPath(import.meta.url));
const names=['lookX','lookY','breath','hairSway','blinkLeft','blinkRight','mouthOpen','smile'];
const signed=new Set(['lookX','lookY','hairSway']);
const types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.mjs':'text/javascript; charset=utf-8',
  '.css':'text/css; charset=utf-8','.json':'application/json; charset=utf-8','.png':'image/png'};
const receivers=new Set();
let pose={active:false},lastUpdate=0;
function broadcast(){for(const client of receivers)client.write('data: '+JSON.stringify(pose)+'\n\n');}

const server=http.createServer(async(req,res)=>{
  try {
    const url=new URL(req.url,'http://'+req.headers.host);
    if(url.pathname==='/avatar-events'&&req.method==='GET') {
      res.writeHead(200,{'Content-Type':'text/event-stream','Cache-Control':'no-cache','Connection':'keep-alive'});
      res.write('data: '+JSON.stringify(pose)+'\n\n');receivers.add(res);
      res.on('close',()=>receivers.delete(res));return;
    }
    if(url.pathname==='/avatar-state'&&req.method==='POST') {
      if(req.headers.origin&&req.headers.origin!==url.origin){res.writeHead(403);return res.end('Forbidden');}
      if(req.headers['content-type']!=='application/json'){res.writeHead(415);return res.end('Expected JSON');}
      let body='';
      for await(const chunk of req){body+=chunk;if(Buffer.byteLength(body)>4096){res.writeHead(413);return res.end('Too large');}}
      const input=JSON.parse(body);
      if(typeof input.active!=='boolean')throw new Error('Missing active state');
      const parameters={};
      if(input.active)for(const name of names) {
        const value=input.parameters?.[name];
        if(typeof value!=='number'||!Number.isFinite(value))throw new Error('Invalid parameter');
        parameters[name]=Math.min(1,Math.max(signed.has(name)?-1:0,value));
      }
      pose=input.active?{active:true,parameters}:{active:false};lastUpdate=Date.now();broadcast();
      res.writeHead(200,{'Content-Type':'application/json','Cache-Control':'no-store'});
      return res.end(JSON.stringify({receivers:receivers.size}));
    }
    if(req.method!=='GET'&&req.method!=='HEAD'){res.writeHead(405);return res.end('Method not allowed');}
    const filename=path.resolve(root,'.'+decodeURIComponent(url.pathname));
    if(filename!==root&&!filename.startsWith(root+path.sep)){res.writeHead(403);return res.end('Forbidden');}
    const target=(await stat(filename)).isDirectory()?path.join(filename,'index.html'):filename;
    const data=await readFile(target);
    res.writeHead(200,{'Content-Type':types[path.extname(target)]||'application/octet-stream','Cache-Control':'no-cache'});
    res.end(req.method==='HEAD'?undefined:data);
  } catch(error) {
    if(!res.headersSent){res.writeHead(error.code==='ENOENT'?404:400);res.end('Request failed');}
  }
});
// Restore independent motion when a controlling browser is closed or suspended.
setInterval(()=>{
  if(pose.active&&Date.now()-lastUpdate>3000){pose={active:false};broadcast();}
  for(const client of receivers)client.write(': keep-alive\n\n');
},1000).unref();
server.listen(Number(process.env.PORT||4174),'127.0.0.1',()=>console.log(`2D Avatar: http://127.0.0.1:${server.address().port}`));
