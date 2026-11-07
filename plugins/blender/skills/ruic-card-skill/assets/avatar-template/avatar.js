const names = ["lookX", "lookY", "breath", "hairSway", "blinkLeft", "blinkRight", "mouthOpen", "smile"];
const zero = () => Object.fromEntries(names.map(name => [name, 0]));
const clamp = (value, low, high) => Math.min(high, Math.max(low, value));
const canvas = document.querySelector("#avatar");
const status = document.querySelector("#status");
const reduced = matchMedia("(prefers-reduced-motion: reduce)");
const query = new URLSearchParams(location.search);
if (query.get("obs") === "1") {
  document.body.classList.add("obs");
  document.documentElement.classList.add("obs");
}
const state = {parameters: zero(), effective: zero(), playing: !reduced.matches, autoBlink: !reduced.matches,
  autoBreath: !reduced.matches, followPointer: !reduced.matches, talking: false, closeup: false, fit: .94, syncOBS:false};
let config, images, renderer, audio, pendingAudio, audioRequest = 0, lastTime = 0, clock = 0, blinkUntil = 0;
let remotePose, poseRequest, syncTimer, poseEvents, syncGeneration=0;

function smoothstep(low, high, value) {
  const t=clamp((value-low)/(high-low),0,1);
  return t*t*(3-2*t);
}

function deform(point, parameters, rig) {
  const [x,y]=point,[px,py]=rig.headPivot;
  const head=1-smoothstep(...rig.headBand,y);
  const body=smoothstep(...rig.bodyBand,y)*(1-smoothstep(...rig.feetBand,y));
  const hair=smoothstep(...rig.hairSides,Math.abs(x-px))*smoothstep(...rig.hairStart,y)*(1-smoothstep(...rig.hairEnd,y));
  return [x+head*(24+.055*(y-py))*parameters.lookX+(x-px)*.008*body*parameters.breath+8*hair*parameters.hairSway,
    y-head*.055*(x-px)*parameters.lookX+head*18*parameters.lookY-3*body*parameters.breath];
}

class PortraitRenderer {
  constructor(target, manifest, textures) {
    this.canvas = target;
    this.config = manifest;
    this.images = textures;
    this.gl = target.getContext("webgl", {alpha: true, premultipliedAlpha: false, antialias: true, preserveDrawingBuffer: true});
    if (!this.gl) {
      this.context = target.getContext("2d");
      if (!this.context) throw new Error("浏览器无法创建绘图画布");
      this.type = "canvas2d";
      this.softwareMeshes={};
      for(const key of ["source",...Object.keys(manifest.expressions)]) {
        const box=key==="source"?[0,0,manifest.width,manifest.height]:manifest.expressions[key].box;
        const [x,y,w,h]=box,columns=key==="source"?12:1,rows=key==="source"?18:1;
        const points=[],triangles=[];
        for(let row=0;row<=rows;row++)for(let column=0;column<=columns;column++)points.push([x+w*column/columns,y+h*row/rows]);
        for(let row=0;row<rows;row++)for(let column=0;column<columns;column++) {
          const a=row*(columns+1)+column,b=a+1,c=a+columns+1,d=c+1;triangles.push([a,b,d],[a,d,c]);
        }
        this.softwareMeshes[key]={box,points,triangles};
      }
      return;
    }
    this.type = "webgl";
    const gl = this.gl;
    const shader = (type, source) => {
      const value = gl.createShader(type);
      gl.shaderSource(value, source);
      gl.compileShader(value);
      if (!gl.getShaderParameter(value, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(value));
      return value;
    };
    const vertex = shader(gl.VERTEX_SHADER, `
      attribute vec2 position; attribute vec2 uv; varying vec2 texCoord;
      uniform vec2 size; uniform vec2 viewport; uniform vec2 center; uniform float fit;
      uniform vec2 pivot; uniform vec2 headBand; uniform vec2 bodyBand; uniform vec2 feetBand;
      uniform vec2 hairSides; uniform vec2 hairStart; uniform vec2 hairEnd;
      uniform float lookX; uniform float lookY; uniform float breath; uniform float hairSway;
      void main(){
        vec2 p=position;
        float head=1.0-smoothstep(headBand.x,headBand.y,p.y);
        float body=smoothstep(bodyBand.x,bodyBand.y,p.y)*(1.0-smoothstep(feetBand.x,feetBand.y,p.y));
        float hair=smoothstep(hairSides.x,hairSides.y,abs(p.x-pivot.x));
        hair*=smoothstep(hairStart.x,hairStart.y,p.y)*(1.0-smoothstep(hairEnd.x,hairEnd.y,p.y));
        p+=vec2(head*(24.0+.055*(p.y-pivot.y))*lookX,-head*.055*(p.x-pivot.x)*lookX+head*18.0*lookY);
        p+=vec2((position.x-pivot.x)*.008*body*breath,-3.0*body*breath);
        p.x+=8.0*hair*hairSway;
        gl_Position=vec4((p.x-center.x)*fit*2.0/viewport.x,(center.y-p.y)*fit*2.0/viewport.y,0.,1.);
        texCoord=uv;
      }`);
    const fragment = shader(gl.FRAGMENT_SHADER, `
      precision highp float; varying vec2 texCoord;
      uniform sampler2D portrait; uniform sampler2D leftEye; uniform sampler2D rightEye;
      uniform sampler2D mouth; uniform sampler2D smileImage;
      uniform vec4 leftBox; uniform vec4 rightBox; uniform vec4 mouthBox;
      uniform float blinkLeft; uniform float blinkRight; uniform float mouthOpen; uniform float smile;
      vec4 applyPatch(vec4 base,sampler2D image,vec4 box,float amount){
        vec2 local=(texCoord-box.xy)/box.zw;
        if(local.x<0.||local.x>1.||local.y<0.||local.y>1.) return base;
        vec4 patch=texture2D(image,local);
        return vec4(mix(base.rgb,patch.rgb,clamp(patch.a*amount,0.,1.)),base.a);
      }
      void main(){
        vec4 color=texture2D(portrait,texCoord);
        color=applyPatch(color,leftEye,leftBox,blinkLeft);
        color=applyPatch(color,rightEye,rightBox,blinkRight);
        color=applyPatch(color,smileImage,mouthBox,smile*(1.-mouthOpen));
        color=applyPatch(color,mouth,mouthBox,mouthOpen);
        gl_FragColor=color;
      }`);
    this.program = gl.createProgram();
    gl.attachShader(this.program, vertex); gl.attachShader(this.program, fragment); gl.linkProgram(this.program);
    if (!gl.getProgramParameter(this.program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(this.program));
    gl.useProgram(this.program);
    this.uniforms = {};
    for (const name of ["size", "viewport", "center", "fit", "pivot", "headBand", "bodyBand", "feetBand", "hairSides", "hairStart", "hairEnd", ...names,
      "portrait", "leftEye", "rightEye", "mouth", "smileImage", "leftBox", "rightBox", "mouthBox"]) this.uniforms[name] = gl.getUniformLocation(this.program, name);
    const [columns, rows] = manifest.grid;
    const vertices = [], indices = [];
    for (let y=0; y<=rows; y++) for (let x=0; x<=columns; x++) vertices.push(x/columns*manifest.width,y/rows*manifest.height,x/columns,y/rows);
    for (let y=0; y<rows; y++) for (let x=0; x<columns; x++) {
      const a=y*(columns+1)+x,b=a+1,c=a+columns+1,d=c+1;
      indices.push(a,b,d,a,d,c);
    }
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer()); gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(vertices),gl.STATIC_DRAW);
    for (const [name, offset] of [["position",0],["uv",8]]) {
      const attribute=gl.getAttribLocation(this.program,name); gl.enableVertexAttribArray(attribute); gl.vertexAttribPointer(attribute,2,gl.FLOAT,false,16,offset);
    }
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,gl.createBuffer()); gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,new Uint16Array(indices),gl.STATIC_DRAW);
    this.count=indices.length;
    for (const [index, [name, key]] of [["portrait","source"],["leftEye","blinkLeft"],["rightEye","blinkRight"],["mouth","mouthOpen"],["smileImage","smile"]].entries()) {
      gl.activeTexture(gl.TEXTURE0+index); gl.bindTexture(gl.TEXTURE_2D,gl.createTexture());
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR); gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
      gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,textures[key]); gl.uniform1i(this.uniforms[name],index);
    }
    for (const [uniform,key] of [["leftBox","blinkLeft"],["rightBox","blinkRight"],["mouthBox","mouthOpen"]]) {
      const [x,y,w,h]=manifest.expressions[key].box; gl.uniform4f(this.uniforms[uniform],x/manifest.width,y/manifest.height,w/manifest.width,h/manifest.height);
    }
    const rig=manifest.rig;
    gl.uniform2f(this.uniforms.pivot,...rig.headPivot);
    for (const name of ["headBand","bodyBand","feetBand","hairSides","hairStart","hairEnd"]) gl.uniform2f(this.uniforms[name],...rig[name]);
    gl.disable(gl.BLEND); gl.disable(gl.DITHER);
  }
  drawSoftwareImage(key,parameters) {
    const ctx=this.context,mesh=this.softwareMeshes[key],image=this.images[key];
    const [x,y]=mesh.box;
    if(!["lookX","lookY","breath","hairSway"].some(name=>Math.abs(parameters[name])>.00001)) {
      ctx.drawImage(image,...mesh.box);return;
    }
    const destination=mesh.points.map(point=>deform(point,parameters,this.config.rig));
    for(const triangle of mesh.triangles) {
      const source=triangle.map(index=>[mesh.points[index][0]-x,mesh.points[index][1]-y]);
      const target=triangle.map(index=>destination[index]);
      const [[u0,v0],[u1,v1],[u2,v2]]=source,[[x0,y0],[x1,y1],[x2,y2]]=target;
      const determinant=u0*(v1-v2)+u1*(v2-v0)+u2*(v0-v1);
      const a=(x0*(v1-v2)+x1*(v2-v0)+x2*(v0-v1))/determinant;
      const c=(x0*(u2-u1)+x1*(u0-u2)+x2*(u1-u0))/determinant;
      const e=(x0*(u1*v2-u2*v1)+x1*(u2*v0-u0*v2)+x2*(u0*v1-u1*v0))/determinant;
      const b=(y0*(v1-v2)+y1*(v2-v0)+y2*(v0-v1))/determinant;
      const d=(y0*(u2-u1)+y1*(u0-u2)+y2*(u1-u0))/determinant;
      const f=(y0*(u1*v2-u2*v1)+y1*(u2*v0-u0*v2)+y2*(u0*v1-u1*v0))/determinant;
      ctx.save();ctx.beginPath();ctx.moveTo(x0,y0);ctx.lineTo(x1,y1);ctx.lineTo(x2,y2);ctx.closePath();ctx.clip();
      ctx.transform(a,b,c,d,e,f);ctx.drawImage(image,0,0);ctx.restore();
    }
  }
  draw(parameters, native=false) {
    const bounds=this.canvas.getBoundingClientRect();
    const ratio=Math.min(devicePixelRatio||1,2);
    const width=native?this.config.width:Math.round(bounds.width*ratio);
    const height=native?this.config.height:Math.round(bounds.height*ratio);
    if (this.canvas.width!==width||this.canvas.height!==height) {this.canvas.width=width;this.canvas.height=height;}
    const zoom=state.closeup&&!native?2.7:1;
    const fit=Math.min(width/this.config.width,height/this.config.height)*state.fit*zoom;
    const center=state.closeup&&!native?this.config.rig.faceCenter:[this.config.width/2,this.config.height/2];
    if (this.gl) {
      const gl=this.gl;gl.viewport(0,0,width,height);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);
      gl.uniform2f(this.uniforms.viewport,width,height);gl.uniform2f(this.uniforms.center,...center);gl.uniform1f(this.uniforms.fit,fit);
      for (const name of names) gl.uniform1f(this.uniforms[name],parameters[name]);
      gl.drawElements(gl.TRIANGLES,this.count,gl.UNSIGNED_SHORT,0);
    } else {
      const ctx=this.context;ctx.setTransform(1,0,0,1,0,0);ctx.clearRect(0,0,width,height);
      ctx.translate(width/2,height/2);ctx.scale(fit,fit);ctx.translate(-center[0],-center[1]);
      ctx.globalCompositeOperation="source-over";this.drawSoftwareImage("source",parameters);
      ctx.globalCompositeOperation="source-atop";
      for (const key of ["blinkLeft","blinkRight","smile","mouthOpen"]) {
        ctx.globalAlpha=key==="smile"?parameters.smile*(1-parameters.mouthOpen):parameters[key];
        if(ctx.globalAlpha>0)this.drawSoftwareImage(key,parameters);
      }
      ctx.globalAlpha=1;ctx.globalCompositeOperation="source-over";
    }
  }
}

function updateControls() {
  for (const name of names) {
    const input=document.getElementById(name), output=document.getElementById(name+"Value");
    if (input) input.value=state.parameters[name];
    if (output) output.value=state.parameters[name].toFixed(2);
  }
  for (const name of ["autoBlink","autoBreath","followPointer"]) document.getElementById(name).checked=state[name];
  document.querySelector("#pause").setAttribute("aria-pressed",String(!state.playing));
  document.querySelector("#pause").textContent=state.playing?"暂停动作":"继续动作";
  document.querySelector("#talk").setAttribute("aria-pressed",String(state.talking));
  document.querySelector("#talk").innerHTML=state.talking?'停止说话 <kbd>T</kbd>':'说话演示 <kbd>T</kbd>';
  document.querySelector("#smile").setAttribute("aria-pressed",String(state.parameters.smile>0));
  document.querySelector("#closeup").setAttribute("aria-pressed",String(state.closeup));
  document.querySelector("#obsSync").setAttribute("aria-pressed",String(state.syncOBS));
  document.querySelector("#obsSync").textContent=state.syncOBS?"停止同步到 OBS":"同步到 OBS";
}

function setParameters(values) {
  for (const name of names) if (name in values) {
    const value=Number(values[name]);if(!Number.isFinite(value)) continue;
    state.parameters[name]=clamp(value,["lookX","lookY","hairSway"].includes(name)?-1:0,1);
  }
  updateControls();
}

function reset(staticPose=false) {
  state.parameters=zero();state.talking=false;state.playing=!staticPose&&!reduced.matches;
  state.autoBlink=state.autoBreath=state.followPointer=!staticPose&&!reduced.matches;
  state.fit=staticPose?1:.94;state.closeup=false;clock=0;blinkUntil=0;lastTime=performance.now();
  stopMicrophone();updateControls();
}

function effective() {
  if(remotePose)return {...remotePose};
  const result={...state.parameters};
  if (state.playing&&state.autoBlink) {
    const phase=clock%4.8;
    const blink=phase>4.48?Math.sin((phase-4.48)/.32*Math.PI):0;
    result.blinkLeft=Math.max(result.blinkLeft,blink);result.blinkRight=Math.max(result.blinkRight,blink);
  }
  if (performance.now()<blinkUntil) result.blinkLeft=result.blinkRight=1;
  if (state.playing&&state.autoBreath) {result.breath=Math.max(result.breath,.45+.35*Math.sin(clock*1.7));result.hairSway+=.35*Math.sin(clock*.95);}
  if (state.talking&&state.playing) result.mouthOpen=.12+.83*Math.abs(Math.sin(clock*8.1));
  if (audio) {
    audio.analyser.getFloatTimeDomainData(audio.buffer);
    const rms=Math.sqrt(audio.buffer.reduce((sum,value)=>sum+value*value,0)/audio.buffer.length);
    audio.level+=(clamp((rms-.008)*12,0,1)-audio.level)*.28;
    result.mouthOpen=audio.level;document.querySelector("#level").value=audio.level;
  }
  for (const name of names) result[name]=clamp(result[name],["lookX","lookY","hairSway"].includes(name)?-1:0,1);
  return result;
}

function advance(time) {
  const elapsed=Math.max(0,(time-lastTime)/1000);lastTime=time;
  if(state.playing)clock+=state.syncOBS?elapsed:Math.min(elapsed,.1);
  state.effective=effective();
}

async function publishPose(active,generation) {
  try {
    const response=await fetch('/avatar-state',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(active?{active:true,parameters:state.effective}:{active:false}),keepalive:!active});
    if(!response.ok)throw new Error('Sync unavailable');
    const result=await response.json();
    if(state.syncOBS&&generation===syncGeneration)document.querySelector('#syncStatus').textContent=result.receivers?
      `正在同步到 ${result.receivers} 个透明输出窗口。`:'已开启同步；请在 OBS 添加本地透明模式地址。';
  } catch(error) {
    if(state.syncOBS&&generation===syncGeneration)document.querySelector('#syncStatus').textContent='同步服务未连接。请用 start-avatar.cmd 启动本地角色服务。';
  }
}

function sendPose(active,generation=syncGeneration) {
  const request=Promise.resolve(poseRequest).then(()=>{
    if(generation!==syncGeneration||active!==state.syncOBS)return;
    return publishPose(active,generation);
  });
  poseRequest=request;request.finally(()=>{if(poseRequest===request)poseRequest=null;});
}

function startSync() {
  if(state.syncOBS)return;
  syncGeneration++;state.syncOBS=true;lastTime=performance.now();updateControls();
}

function stopSync() {
  const wasSyncing=state.syncOBS;state.syncOBS=false;
  if(wasSyncing)sendPose(false,++syncGeneration);
  document.querySelector('#syncStatus').textContent='同步已停止；透明输出恢复独立动作。';updateControls();
}

function stopMicrophone() {
  audioRequest++;
  if (pendingAudio) {pendingAudio.stream.getTracks().forEach(track=>track.stop());pendingAudio.context?.close();pendingAudio=null;}
  if (audio) {audio.stream.getTracks().forEach(track=>track.stop());audio.context.close();audio=null;}
  document.querySelector("#microphone").disabled=false;
  document.querySelector("#microphone").setAttribute("aria-pressed","false");
  document.querySelector("#microphone").textContent="启用麦克风嘴型";
  document.querySelector("#level").value=0;
  document.querySelector("#micStatus").textContent="声音只在本地驱动嘴型。";
}

async function microphone() {
  if (audio) {stopMicrophone();return;}
  const button=document.querySelector("#microphone");button.disabled=true;
  const request=++audioRequest;
  let stream, context;
  try {
    stream=await navigator.mediaDevices.getUserMedia({audio:true});
    if(request!==audioRequest){stream.getTracks().forEach(track=>track.stop());return;}
    pendingAudio={stream,context:null};
    context=new AudioContext();pendingAudio.context=context;await context.resume();
    if(request!==audioRequest)return;
    const analyser=context.createAnalyser();analyser.fftSize=512;
    context.createMediaStreamSource(stream).connect(analyser);
    pendingAudio=null;
    audio={stream,context,analyser,buffer:new Float32Array(analyser.fftSize),level:0};state.talking=false;
    button.setAttribute("aria-pressed","true");button.textContent="关闭麦克风嘴型";
    document.querySelector("#micStatus").textContent="麦克风已启用，声音不会上传。";updateControls();
  } catch (error) {
    if(request===audioRequest) {
      if(stream)stream.getTracks().forEach(track=>track.stop());if(context)context.close();pendingAudio=null;
      document.querySelector("#micStatus").textContent="麦克风未启用。请允许本地页面使用麦克风，或使用嘴型滑块。";
    }
  } finally {if(request===audioRequest)button.disabled=false;}
}

async function download() {
  const button=document.querySelector("#download");button.disabled=true;
  renderer.draw(state.effective,true);
  const blob=await new Promise(resolve=>canvas.toBlob(resolve,"image/png"));
  renderer.draw(state.effective);
  if(blob){const link=document.createElement("a");link.download=config.name+".png";link.href=URL.createObjectURL(blob);link.click();setTimeout(()=>URL.revokeObjectURL(link.href),3000);}
  button.disabled=false;
}

async function load() {
  const response=await fetch("avatar.json");if(!response.ok)throw new Error("角色配置无法读取");config=await response.json();
  if(config.schema!=="reverie.2d-avatar.v1")throw new Error("角色包格式不受支持");
  document.querySelector("#name").textContent=config.name;document.title=config.name+" · 2D 虚拟形象";
  images={};
  const files={source:config.image,...Object.fromEntries(Object.entries(config.expressions).map(([key,value])=>[key,value.image]))};
  await Promise.all(Object.entries(files).map(async([key,path])=>{const image=new Image();image.src=path;await image.decode();images[key]=image;}));
  renderer=new PortraitRenderer(canvas,config,images);
  document.querySelector("#blink").onclick=()=>{blinkUntil=performance.now()+220;};
  document.querySelector("#smile").onclick=()=>setParameters({smile:state.parameters.smile>0?0:1});
  document.querySelector("#talk").onclick=()=>{stopMicrophone();state.talking=!state.talking;state.playing=true;lastTime=performance.now();updateControls();};
  document.querySelector("#pause").onclick=()=>{state.playing=!state.playing;lastTime=performance.now();updateControls();};
  document.querySelector("#neutral").onclick=()=>reset(true);document.querySelector("#reset").onclick=()=>reset();
  document.querySelector("#closeup").onclick=()=>{state.closeup=!state.closeup;updateControls();};
  document.querySelector("#microphone").onclick=microphone;document.querySelector("#download").onclick=download;
  document.querySelector('#obsSync').onclick=()=>{
    if(state.syncOBS){stopSync();return;}
    startSync();
  };
  for (const name of names) {
    const input=document.getElementById(name);if(!input)continue;
    input.oninput=()=>{
      if(name.startsWith("blink"))state.autoBlink=false;
      if(name==="breath"||name==="hairSway")state.autoBreath=false;
      if(name.startsWith("look"))state.followPointer=false;
      if(name==="mouthOpen"){state.talking=false;stopMicrophone();}
      setParameters({[name]:input.value});
    };
  }
  for(const name of ["autoBlink","autoBreath","followPointer"])document.getElementById(name).onchange=event=>{state[name]=event.target.checked;};
  canvas.addEventListener("pointermove",event=>{
    if(!state.followPointer)return;const bounds=canvas.getBoundingClientRect();
    setParameters({lookX:(event.clientX-bounds.left)/bounds.width*2-1,lookY:(event.clientY-bounds.top)/bounds.height*2-1});
  });
  canvas.addEventListener("pointerleave",()=>{if(state.followPointer)setParameters({lookX:0,lookY:0});});
  addEventListener("keydown",event=>{
    if(event.target.closest("input,button,textarea,select"))return;
    const key=event.key.toLowerCase();
    const actions={b:"blink",s:"smile",t:"talk",r:"reset",m:"microphone"," ":"pause"};
    if(actions[key]){event.preventDefault();document.getElementById(actions[key]).click();}
    if(key==="h")document.body.classList.toggle("controls-hidden");
  });
  reduced.addEventListener("change",()=>{if(reduced.matches){state.playing=state.autoBlink=state.autoBreath=state.followPointer=false;updateControls();}});
  addEventListener("pagehide",stopMicrophone);
  function connectRelay() {
    if(query.get('obs')==='1') {
      if(poseEvents)return;
      poseEvents=new EventSource('/avatar-events');
      poseEvents.onmessage=event=>{
        const pose=JSON.parse(event.data);remotePose=pose.active?pose.parameters:null;
      };
      poseEvents.onerror=()=>{remotePose=null;};
    } else if(!syncTimer) {
      syncTimer=setInterval(()=>{
        if(!state.syncOBS)return;
        advance(performance.now());
        if(!poseRequest)sendPose(true);
      },50);
    }
  }
  addEventListener('pagehide',()=>{
    stopSync();clearInterval(syncTimer);syncTimer=null;poseEvents?.close();poseEvents=null;remotePose=null;
  });
  addEventListener('pageshow',connectRelay);connectRelay();
  updateControls();status.textContent="角色已加载 · 原画纹理与透明背景";
  window.avatar={ready:true,config,rendererType:renderer.type,setParameters,reset,
    getState:()=>({ready:true,rendererType:renderer.type,...structuredClone(state),microphoneActive:Boolean(audio),syncedFromBrowser:Boolean(remotePose)}),
    renderNative:()=>{state.effective=effective();renderer.draw(state.effective,true);return canvas.toDataURL("image/png");}};
  function frame(time){
    if(!state.syncOBS)advance(time);
    renderer.draw(state.effective);requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

load().catch(error=>{status.textContent="角色加载失败："+error.message;window.avatar={ready:false,error:error.message};console.error(error);});
