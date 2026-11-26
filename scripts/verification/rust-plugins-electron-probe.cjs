const {app,BrowserWindow}=require('electron');
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const options=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
app.setName('Reverie native plugin verification');app.setPath('userData',path.join(options.runtimeRoot,'user-data'));
process.env.REVERIE_DESKTOP_RUNTIME_ROOT=options.runtimeRoot;process.argv=[process.execPath,options.uiRoot,'--gui','--project',options.projectRoot];
require(path.join(options.uiRoot,'dist-electron/main.js'));
const delay=milliseconds=>new Promise(resolve=>setTimeout(resolve,milliseconds));
const checks=[],errors=[];let win;
const evaluate=expression=>win.webContents.executeJavaScript(expression,true);
async function wait(expression,label){for(let index=0;index<400;index++){if(await evaluate(expression))return;await delay(40);}throw new Error(`${label}: ${await evaluate('document.body.innerText.slice(-1800)')}`);}
async function click(selector){await evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);}
async function input(selector,value){await evaluate(`(()=>{const input=document.querySelector(${JSON.stringify(selector)});Object.getOwnPropertyDescriptor(input.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype,'value').set.call(input,${JSON.stringify(value)});input.dispatchEvent(new Event(input.tagName==='SELECT'?'change':'input',{bubbles:true}));return true;})()`);await delay(40);}
async function capture(name,selector){if(selector)await evaluate(`document.querySelector(${JSON.stringify(selector)}).scrollIntoView({block:'start'})`);await delay(250);fs.writeFileSync(path.join(options.outputRoot,name),(await win.webContents.capturePage()).toPNG());}
async function navigate(label){
  const pinned=await evaluate(`Array.from(document.querySelectorAll('.main-nav button')).some(button=>button.textContent===${JSON.stringify(label)})`);
  if(!pinned){await click('.page-navigation-more>button');await wait("!!document.querySelector('.page-navigation-menu')",'The page menu did not open');await evaluate(`Array.from(document.querySelectorAll('.page-navigation-menu .page-navigation-row>button:first-child')).find(button=>button.textContent===${JSON.stringify(label)}).click()`);}
  else await evaluate(`Array.from(document.querySelectorAll('.main-nav button')).find(button=>button.textContent===${JSON.stringify(label)}).click()`);
}
async function addMarket(name,kind,location){
  await evaluate("document.querySelector('.market-add').open=true");await input('.market-fields label:nth-child(1) input',name);await input('.market-fields select',kind);await input('.market-fields label:nth-child(3) input',location);await click('.market-add button[type=submit]');
  await wait(`Array.from(document.querySelectorAll('.market-source-name')).some(button=>button.textContent===${JSON.stringify(name)})`,'The market was not added');
  return evaluate(`window.reverie.request('listMarkets',{}).then(response=>response.markets.sources.find(source=>source.name===${JSON.stringify(name)}).id)`);
}
async function refreshMarket(id){
  const revision=await evaluate("window.reverie.request('listMarkets',{}).then(response=>response.markets.revision)");await click(`[data-market-id="${id}"] button[aria-label^="刷新目录"]`);
  await wait(`window.reverie.request('listMarkets',{}).then(response=>response.markets.revision>${revision})`,'The actual catalog refresh did not commit');
  await wait("!document.querySelector('.market-notice button')&&document.querySelector('.market-entries')?.getAttribute('aria-busy')==='false'",'The actual catalog did not settle');
}
async function record(){return evaluate("window.reverie.request('listPlugins',{}).then(response=>response.plugins.records.find(record=>record.name==='Native plugin fixture😀'))");}
async function approve(expectedTitle){
  await wait(`document.querySelector('.plugin-review-dialog h2')?.textContent===${JSON.stringify(expectedTitle)}`,'The inspected confirmation did not open');
  if(!await evaluate("document.querySelector('.plugin-review-dialog button[type=submit]').disabled"))throw new Error('A newly opened review was implicitly approved.');
  if(await evaluate("document.querySelector('.plugin-review-dialog').innerText.includes('PLUGIN_FIXTURE_SECRET')"))throw new Error('The review exposed a fixture credential.');
  await evaluate("for(const input of document.querySelectorAll('.plugin-review-checks input'))input.click();true");
  await wait("!document.querySelector('.plugin-review-dialog button[type=submit]').disabled",'Explicit confirmations did not enable the operation');await click('.plugin-review-dialog button[type=submit]');
  await wait("!document.querySelector('.plugin-review-dialog')&&!document.querySelector('.plugins-page .market-notice[role=status]')",'The confirmed native operation did not finish');
}
app.whenReady().then(async()=>{
  try {
    for(let index=0;index<400;index++){win=BrowserWindow.getAllWindows().find(window=>window.getTitle()==='Reverie');if(win)break;await delay(25);}
    if(!win)throw new Error('The actual desktop window was not created.');win.webContents.on('console-message',event=>{if(/TypeError|ReferenceError|Error:/i.test(event.message||''))errors.push(event.message);});
    await wait("!!document.querySelector('.composer textarea')",'The actual desktop did not initialize');
    const state=await evaluate("window.reverie.request('getState',{}).then(response=>response.state)");if(state.core.implementation!=='rust'||!state.capabilities?.actions.includes('preparePlugin'))throw new Error('The desktop did not expose the coordinated Rust plugin API.');
    await navigate('扩展市场');await wait("!!document.querySelector('.market-add')",'The market page did not initialize');
    const local=await addMarket('Native install market','directory',options.marketRoot);await refreshMarket(local);
    await wait("!!document.querySelector('.market-entries button[aria-label=\"准备安装 native-plugin-fixture\"]')",'The native install entry did not render');
    await click('.market-entries button[aria-label="准备安装 native-plugin-fixture"]');
    await wait("!!document.querySelector('.plugins-page')&&document.querySelector('.plugin-detail h2')?.textContent==='Native plugin fixture😀'&&!document.querySelector('.plugins-page .market-notice[role=status]')",'The market preparation did not return an actual plugin candidate');
    let plugin=await record();const first=plugin.candidates.find(candidate=>candidate.version==='1.0.0');if(!first||plugin.active_sha256||plugin.trusted||plugin.enabled||plugin.hooks_enabled)throw new Error('Preparation unexpectedly activated or trusted content.');
    if(JSON.stringify(first).includes('PLUGIN_FIXTURE_SECRET'))throw new Error('The actual candidate leaked a fixture secret.');
    await capture('plugin-candidate.png','.plugin-detail');checks.push('Actual market-to-plugin preparation, native content/profile hashes, license, sanitized components and inactive/untrusted defaults');
    await click('.plugin-detail button.primary-button');await approve('激活这个版本');
    await wait("!document.querySelector('.plugin-detail input[aria-label=\"信任执行范围\"]').disabled",'Activation did not enable separate trust management');
    plugin=await record();if(plugin.active_sha256!==first.sha256||plugin.trusted||plugin.enabled)throw new Error('Activation implicitly granted trust or enabled the plugin.');
    await wait(`document.querySelector('.plugin-detail .plugin-candidate-details')?.innerText.includes(${JSON.stringify(first.sha256)})`,'The active version metadata disappeared when no inactive candidate remained');await capture('plugin-current-version.png','.plugin-detail');
    await click('.plugin-detail input[aria-label="信任执行范围"]');await wait("!!document.querySelector('.plugin-review-dialog')",'Trust did not require an inspected review');
    if(!await evaluate(`document.querySelector('.plugin-review-dialog').innerText.includes(${JSON.stringify(first.sha256)})&&document.querySelector('.plugin-review-dialog').innerText.includes(${JSON.stringify(first.approval_profile_sha256)})`))throw new Error('Trust review was not bound to inspected identity.');
    await capture('plugin-trust-review.png','.plugin-review-dialog');await approve('信任这个插件');
    await wait("document.querySelector('.plugin-detail input[aria-label=\"信任执行范围\"]').checked",'The native trust grant did not persist');
    await click('.plugin-detail input[aria-label="在当前项目启用"]');await wait("document.querySelector('.plugin-detail input[aria-label=\"在当前项目启用\"]').checked&&!document.querySelector('.plugins-page .market-notice[role=status]')",'The project enable did not commit');
    await click('.plugin-detail input[aria-label="Hooks"]');await wait("!!document.querySelector('.plugin-review-dialog')",'Hooks did not require an inspected review');
    if(!await evaluate("document.querySelector('.plugin-review-dialog').innerText.includes('PreToolUse')&&document.querySelector('.plugin-review-dialog').innerText.includes('forbidden-hook.mjs')&&document.querySelector('.plugin-review-dialog').innerText.includes('files.read')"))throw new Error('Hook event, entry or permissions were missing.');
    await capture('plugin-hooks-review.png','.plugin-review-dialog .plugin-components');
    await approve('启用这些 Hooks');await wait("document.querySelector('.plugin-detail input[aria-label=\"Hooks\"]').checked",'The explicit Hook grant did not commit');if(fs.existsSync(options.marker))throw new Error('Management executed a Hook.');
    await click('.plugin-detail input[aria-label="Hooks"]');await wait("!document.querySelector('.plugin-detail input[aria-label=\"Hooks\"]').checked&&!document.querySelector('.plugins-page .market-notice[role=status]')",'Hooks were not disabled');
    await click('.plugin-detail input[aria-label="自动更新"]');await wait("!document.querySelector('.plugin-detail input[aria-label=\"自动更新\"]').checked&&!document.querySelector('.plugins-page .market-notice[role=status]')",'Automatic update opt-out did not persist');checks.push('Separate version activation, exact-profile trust, project enable, inspected Hooks confirmation and explicit opt-out without business Hook execution');
    await fetch(options.base+'/version?value=2.0.0');await evaluate("Array.from(document.querySelectorAll('.plugin-version-actions button')).find(button=>button.textContent==='准备更新').click()");
    await wait("document.querySelector('.plugin-candidate-choice select')?.selectedOptions[0]?.textContent.startsWith('2.0.0')&&!document.querySelector('.plugins-page .market-notice[role=status]')",'The native update did not return the new candidate');
    plugin=await record();const second=plugin.candidates.find(candidate=>candidate.version==='2.0.0');if(!second||second.approval_profile_sha256===first.approval_profile_sha256||plugin.active_sha256!==first.sha256)throw new Error('The prepared update did not preserve activation or expose the profile change.');
    await click('.plugin-detail button.primary-button');await wait("document.querySelector('.plugin-review-dialog')?.innerText.includes('执行范围发生变化')",'The changed execution profile was not displayed');
    if(await evaluate("document.querySelectorAll('.plugin-review-checks input').length")!==3)throw new Error('Content/profile/operation confirmations were not separated.');
    await capture('plugin-profile-change.png','.plugin-profile-change');await capture('plugin-confirmations.png','.plugin-review-checks');await approve('激活这个版本');
    await evaluate("Array.from(document.querySelectorAll('.plugin-version-actions button')).find(button=>button.textContent==='回退').click()");await approve('回退到上一版本');
    plugin=await record();if(plugin.active_sha256!==first.sha256)throw new Error('The actual previous version was not restored.');checks.push('Actual update remains a candidate, explicit content/profile approvals switch it, and inspected rollback restores the previous version');
    await evaluate("document.querySelector('.plugin-prepare').open=true");await input('.plugin-source-fields select','archive');await input('.plugin-source-fields input',options.base+'/hold.zip');
    await click('.plugin-prepare button[type=submit]');await wait("!!document.querySelector('.plugins-page .market-notice button')",'The pending archive operation did not display cancellation');
    await navigate('对话');await navigate('插件');await wait("document.querySelector('.plugins-page .market-notice')?.innerText.includes('/hold.zip')",'Navigation lost the active plugin operation');
    if(await evaluate("document.querySelector('.plugin-source-fields input').value")!==options.base+'/hold.zip')throw new Error('Navigation lost the installation draft.');await click('.plugins-page .market-notice button');
    await wait("!document.querySelector('.plugins-page .market-notice[role=status]')",'The native plugin download did not stop');plugin=await record();if(plugin.active_sha256!==first.sha256)throw new Error('Cancellation replaced the active version.');checks.push('Actual archive download, retained cross-page draft/operation and targeted cancellation preserve activation');
    await navigate('扩展市场');const registry=await addMarket('Native registry fixture','mcp_registry',options.base+'/registry');await refreshMarket(registry);
    await wait("!!document.querySelector('.market-install-actions select')",'The actual Registry endpoints did not render');
    if(!await evaluate("document.querySelector('.market-install-actions button').disabled&&document.querySelector('.market-install-actions select').value===''") )throw new Error('A Registry endpoint was implicitly selected.');
    await input('.market-install-actions select',options.base+'/mcp-two');await click('.market-install-actions button');
    await wait("document.querySelector('.plugin-detail h2')?.textContent==='org.reverie/native-remote-fixture'&&!document.querySelector('.plugins-page .market-notice[role=status]')",'The selected endpoint was not prepared');
    const remote=await evaluate("window.reverie.request('listPlugins',{}).then(response=>response.plugins.records.find(record=>record.name==='org.reverie/native-remote-fixture'))");
    if(!JSON.stringify(remote.source).includes(options.base+'/mcp-two')||remote.active_sha256||remote.trusted||remote.enabled)throw new Error('Registry preparation chose the wrong endpoint or activated it.');checks.push('Actual Registry with two endpoints requires explicit URL selection and prepares only that inactive untrusted configuration');
    await navigate('插件');await evaluate(`Array.from(document.querySelectorAll('.plugin-selector')).find(button=>button.textContent.includes('Native plugin fixture😀')).click()`);await wait("document.querySelector('.plugin-detail h2')?.textContent==='Native plugin fixture😀'",'The fixture plugin could not be selected');
    await click('.plugin-detail header button');await approve('移除这个插件');if(await record())throw new Error('The actual plugin registration was not removed.');if(fs.existsSync(options.marker))throw new Error('The fixture Hook ran during management.');
    await capture('plugin-remaining-candidate.png','.plugin-detail');checks.push('Confirmed removal drops registration and preserves the unactivated Registry candidate with no Hook execution');
    await wait("!document.querySelector('.plugins-page p[role=status]')",'Final plugin inspection did not settle');
    if(errors.length)throw new Error('Renderer errors: '+errors.join('; '));const paths=await evaluate('window.reverie.paths()');
    const actual={executable:paths.kernelPath,sha256:crypto.createHash('sha256').update(fs.readFileSync(paths.kernelPath)).digest('hex'),size:fs.statSync(paths.kernelPath).size};if(actual.sha256!==options.kernel.sha256||actual.size!==options.kernel.size)throw new Error('The desktop used a different coordinated executable.');
    fs.writeFileSync(path.join(options.outputRoot,'report.json'),JSON.stringify({schema:'reverie.rust-plugins-electron-smoke.v1',passed:true,verified_at:new Date().toISOString(),checks,errors,kernel:actual,expected_kernel:options.kernel,paths,desktop_build:JSON.parse(fs.readFileSync(path.join(options.uiRoot,'dist-electron/reverie-build.json'),'utf8')),scope:'Actual production renderer/preload/Electron and Rust program with isolated local packages and HTTP catalogs; no public installation, user extension execution, real OAuth, DPI, platform packaging, performance or full product acceptance.'},null,2)+'\n');console.log(JSON.stringify({passed:true,checks:checks.length}));process.exitCode=0;
  }catch(error){fs.writeFileSync(path.join(options.outputRoot,'failure.json'),JSON.stringify({passed:false,error:String(error.stack||error),checks,errors},null,2));if(win&&!win.isDestroyed())await capture('failure.png').catch(()=>{});console.error(error);process.exitCode=1;}
  finally{app.quit();}
});
