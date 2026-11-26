const {app,BrowserWindow}=require('electron');
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const options=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
app.setName('Reverie native market verification');app.setPath('userData',path.join(options.runtimeRoot,'user-data'));
process.env.REVERIE_DESKTOP_RUNTIME_ROOT=options.runtimeRoot;process.argv=[process.execPath,options.uiRoot,'--gui','--project',options.projectRoot];
require(path.join(options.uiRoot,'dist-electron/main.js'));
const delay=milliseconds=>new Promise(resolve=>setTimeout(resolve,milliseconds));
const checks=[],errors=[],visuals={};let win;
const evaluate=expression=>win.webContents.executeJavaScript(expression,true);
async function wait(expression,label){for(let index=0;index<300;index++){if(await evaluate(expression))return;await delay(50);}throw new Error(`${label}: ${await evaluate('document.body.innerText.slice(-1200)')}`);}
async function type(selector,text){await evaluate(`document.querySelector(${JSON.stringify(selector)}).focus()`);await win.webContents.insertText(text);}
async function click(selector){await evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);}
async function capture(name){await delay(250);fs.writeFileSync(path.join(options.outputRoot,name),(await win.webContents.capturePage()).toPNG());}
async function add(name,kind,location){
  await evaluate("document.querySelector('.market-add').open=true");
  await type('.market-fields label:nth-child(1) input',name);
  await evaluate(`(()=>{const select=document.querySelector('.market-fields select');const setter=Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set;setter.call(select,${JSON.stringify(kind)});select.dispatchEvent(new Event('change',{bubbles:true}));return true;})()`);
  await type('.market-fields label:nth-child(3) input',location);await click('.market-add button[type=submit]');
  await wait(`Array.from(document.querySelectorAll('.market-source-name')).some(button=>button.textContent===${JSON.stringify(name)})`,'The native source was not added');
  return await evaluate(`window.reverie.request('listMarkets',{}).then(response=>response.markets.sources.find(source=>source.name===${JSON.stringify(name)}).id)`);
}
async function refresh(id){
  const revision=await evaluate("window.reverie.request('listMarkets',{}).then(response=>response.markets.revision)");
  await click(`[data-market-id="${id}"] button[aria-label^="刷新目录"]`);
  await wait(`window.reverie.request('listMarkets',{}).then(response=>response.markets.revision>${revision})`,'The native catalog refresh did not complete');
  await wait("!document.querySelector('.market-notice button')",'The catalog refresh control did not clear');
}
app.whenReady().then(async()=>{
  try {
    for(let index=0;index<400;index++){win=BrowserWindow.getAllWindows().find(window=>window.getTitle()==='Reverie');if(win)break;await delay(25);}
    if(!win)throw new Error('The actual Reverie window was not created.');
    win.webContents.on('console-message',event=>{const text=event.message;if(/TypeError|ReferenceError|Error:/i.test(text||''))errors.push(text);});
    await wait("!!document.querySelector('.composer textarea')",'The native desktop did not initialize');
    const state=await evaluate("window.reverie.request('getState',{}).then(response=>response.state)");if(state.core.implementation!=='rust')throw new Error('The window did not use Rust.');
    await evaluate("document.querySelector('.composer textarea').focus();document.querySelector('.page-navigation-more>button').dispatchEvent(new PointerEvent('pointerover',{pointerType:'mouse',bubbles:true}));true");
    await wait("!!document.querySelector('.page-navigation-menu')",'Hover did not open all pages');
    if(!await evaluate("document.activeElement===document.querySelector('.composer textarea')"))throw new Error('Hovering over navigation took input focus.');
    await click('.page-navigation-more>button');
    await wait("document.activeElement===document.querySelector('.page-navigation-menu button')",'Clicking did not establish keyboard menu focus');
    await wait("document.querySelector('.page-navigation-menu')?.matches(':popover-open')",'The native menu did not enter the browser top layer');
    await wait("Number(getComputedStyle(document.querySelector('.page-navigation-menu')).opacity)>=0.99",'The native menu did not finish entering');
    visuals.navigation=await evaluate("(()=>{const menu=document.querySelector('.page-navigation-menu');const style=getComputedStyle(menu);const rect=menu.getBoundingClientRect();return{background:style.backgroundColor,opacity:style.opacity,visibility:style.visibility,display:style.display,bounds:{x:rect.x,y:rect.y,width:rect.width,height:rect.height},viewport:{width:innerWidth,height:innerHeight}};})()");
    await capture('page-navigation.png');
    await click('.page-navigation-menu button[aria-label="固定到侧栏 扩展市场"]');await click('.page-navigation-menu button[aria-label="上移 扩展市场"]');
    await wait("(()=>{const menu=document.querySelector('.page-navigation-menu')?.getBoundingClientRect();const anchor=document.querySelector('.page-navigation-more>button').getBoundingClientRect();return menu&&(Math.abs(menu.top-anchor.bottom-8)<1||Math.abs(anchor.top-menu.bottom-8)<1);})()",'The menu did not follow its anchor after pinning a page');
    await evaluate("Array.from(document.querySelectorAll('.page-navigation-menu .page-navigation-row>button:first-child')).find(button=>button.textContent==='扩展市场').click()");
    await wait("!!document.querySelector('.markets-page') && document.querySelectorAll('.market-sources article').length===4",'The four lazy sources did not render');
    const stored=JSON.parse(fs.readFileSync(path.join(options.runtimeRoot,'desktop-settings.json'),'utf8')).ui;
    if(!stored.navigationPinned.includes('markets')||stored.navigationOrder.indexOf('markets')>=stored.navigationOrder.indexOf('recovery'))throw new Error('Page pin/order was not stored by Electron.');
    checks.push('Real native window, four lazy sources, hover/click/keyboard focus and persistent page pins/order');
    const local=await add('GUI 目录😀','directory',options.sourceRoot);await refresh(local);
    await wait("document.querySelectorAll('.market-entries article').length===30",'The native first catalog page did not render');
    await wait("Array.from(document.querySelectorAll('.market-pagination button')).some(button=>button.textContent==='下一页'&&!button.disabled)",'The first catalog page did not become ready for pagination');
    await evaluate("Array.from(document.querySelectorAll('.market-pagination button')).find(button=>button.textContent==='下一页').click()");
    await wait("document.querySelector('.market-entries h3')?.textContent==='fixture-30'",'The next actual cache page did not render');
    await type('.market-search input','fixture-39');await wait("document.querySelectorAll('.market-entries article').length===1 && document.querySelector('.market-entries h3')?.textContent==='fixture-39'",'Native cached search did not filter');
    const catalog=await evaluate(`window.reverie.request('queryMarket',{market_id:${JSON.stringify(local)}})`);
    const hash=crypto.createHash('sha256').update(fs.readFileSync(path.join(options.sourceRoot,'.claude-plugin/marketplace.json'))).digest('hex');if(catalog.total!==50||catalog.source.content_sha256!==hash)throw new Error('The actual directory identity drifted.');
    await type('.market-fields label:nth-child(1) input','未提交草稿😀');await type('.market-fields label:nth-child(3) input','retained/source');
    await evaluate("Array.from(document.querySelectorAll('.main-nav button')).find(button=>button.textContent==='对话').click()");
    await evaluate("Array.from(document.querySelectorAll('.main-nav button')).find(button=>button.textContent==='扩展市场').click()");
    await wait("document.querySelector('.market-fields label:nth-child(1) input')?.value==='未提交草稿😀' && document.querySelector('.market-search input')?.value==='fixture-39'",'Market drafts were lost after navigation');
    await evaluate("document.querySelector('#market-catalog-title').scrollIntoView({block:'start'})");await capture('market-catalog.png');checks.push('Actual local source, explicit add, native hash, cache pagination/search and retained navigation drafts');
    await evaluate("for(const input of document.querySelectorAll('.market-add input')){const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;setter.call(input,'');input.dispatchEvent(new Event('input',{bubbles:true}));}true");
    const remote=await add('GUI HTTP source','manifest',options.base+'/catalog');await refresh(remote);
    await fetch(options.base+'/control?broken=1');await refresh(remote);
    await wait("document.querySelector('.market-sources').innerText.includes('更新失败，保留缓存') && document.querySelectorAll('.market-entries article').length===30",'The malformed refresh lost valid native cache');
    await fetch(options.base+'/control?broken=0');checks.push('Actual HTTP catalog and malformed refresh with previous cached entries retained');
    const slow=await add('GUI slow source','manifest',options.base+'/hold');await click(`[data-market-id="${slow}"] button[aria-label^="刷新目录"]`);
    await wait("document.querySelector('.market-notice button')?.textContent==='停止'",'The cancel control did not appear');
    await evaluate("Array.from(document.querySelectorAll('.main-nav button')).find(button=>button.textContent==='对话').click()");
    await evaluate("Array.from(document.querySelectorAll('.main-nav button')).find(button=>button.textContent==='扩展市场').click()");
    await wait("document.querySelector('.market-notice')?.innerText.includes('GUI slow source')",'The running download was lost on navigation');await click('.market-notice button');
    await wait("!document.querySelector('.market-notice button')",'Explicit source cancellation did not finish');checks.push('Actual pending HTTP refresh, page navigation and targeted cancellation');
    await click(`[data-market-id="${remote}"] input[type=checkbox]`);
    await wait(`(()=>{const input=document.querySelector('[data-market-id="${remote}"] input[type=checkbox]');return input?.checked===false&&!input.disabled&&document.querySelector('[data-market-id="${remote}"] button[aria-label^="刷新目录"]')?.disabled===true;})()`,'Disabling a source did not commit its final state');
    await click(`[data-market-id="${remote}"] input[type=checkbox]`);await wait(`document.querySelector('[data-market-id="${remote}"] button[aria-label^="刷新目录"]')?.disabled===false`,'Re-enabling a source did not restore refresh');
    await click(`[data-market-id="${remote}"] button[aria-label^="移除来源"]`);await wait(`!document.querySelector('[data-market-id="${remote}"]')`,'Removal did not affect native state');checks.push('Native source disable/enable and removal through the shared GUI contract');
    await evaluate("document.querySelector('#market-sources-title').scrollIntoView({block:'start'})");await capture('market-sources.png');win.webContents.reload();await wait("!!document.querySelector('.composer textarea')",'The reloaded window did not initialize');
    await wait("Array.from(document.querySelectorAll('.main-nav button')).some(button=>button.textContent==='扩展市场')",'Pinned market navigation was lost after reload');
    await evaluate("Array.from(document.querySelectorAll('.main-nav button')).find(button=>button.textContent==='扩展市场').click()");await wait("Array.from(document.querySelectorAll('.market-source-name')).some(button=>button.textContent==='GUI 目录😀')",'Native sources were lost after reload');checks.push('Renderer reload restores persisted Electron navigation and native source catalogs');
    await wait("document.querySelector('.market-entries')?.getAttribute('aria-busy')==='false'",'The reloaded native cache query did not settle');
    if(errors.length)throw new Error('Renderer errors: '+errors.join('; '));
    const paths=await evaluate('window.reverie.paths()');
    const kernel={executable:paths.kernelPath,sha256:crypto.createHash('sha256').update(fs.readFileSync(paths.kernelPath)).digest('hex'),size:fs.statSync(paths.kernelPath).size,staged:options.kernelEvidence};
    if(kernel.sha256!==options.kernelEvidence.sha256||kernel.size!==options.kernelEvidence.size)throw new Error('The actual desktop kernel identity changed from the coordinated build.');
    fs.writeFileSync(path.join(options.outputRoot,'report.json'),JSON.stringify({schema:'reverie.rust-markets-electron-smoke.v1',passed:true,verified_at:new Date().toISOString(),scope:'Actual Electron and native Rust market management with isolated local/HTTP catalogs; no public source installation, OAuth, full platform or DPI acceptance.',checks,errors,paths,kernel,visuals},null,2)+'\n');console.log(JSON.stringify({passed:true,checks:checks.length}));process.exitCode=0;
  }catch(error){fs.writeFileSync(path.join(options.outputRoot,'failed.json'),JSON.stringify({passed:false,error:String(error.stack||error),checks,errors},null,2));if(win&&!win.isDestroyed())await capture('failed.png').catch(()=>{});console.error(error);process.exitCode=1;}
  finally{app.quit();}
});
