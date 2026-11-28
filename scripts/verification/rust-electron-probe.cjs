const {app, BrowserWindow, ipcMain} = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const options = JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
app.setName('Reverie Rust desktop verification');
fs.mkdirSync(path.join(options.runtimeRoot,'user-data'),{recursive:true});
app.setPath('userData',path.join(options.runtimeRoot,'user-data'));
process.env.REVERIE_DESKTOP_RUNTIME_ROOT = options.runtimeRoot;
process.argv = [process.execPath,options.uiRoot,'--gui','--project',options.projectRoot];
const contextRequests=[];
const registerHandler=ipcMain.handle.bind(ipcMain);
ipcMain.handle=(channel,handler)=>registerHandler(channel,channel==='core:request'?async(event,...args)=>{
  const request={action:args[0],payload:args[1]};
  const tracked=/Semantic|Context|Settings|Setting|Skill/.test(String(request?.action||''));
  const record=tracked?{action:request.action,payload:request.payload,started:Date.now()}:null;
  if(record)contextRequests.push(record);
  try {
    const reply=await handler(event,...args);
    if(record)Object.assign(record,{finished:Date.now(),type:reply?.type,error:reply?.error});
    return reply;
  } catch(error) {
    if(record)Object.assign(record,{finished:Date.now(),error:String(error)});
    throw error;
  } finally {
    fs.writeFileSync(path.join(options.outputRoot,'context-requests.json'),JSON.stringify(contextRequests,null,2));
  }
}:handler);
require(path.join(options.uiRoot,'dist-electron/main.js'));
const delay = milliseconds => new Promise(resolve=>setTimeout(resolve,milliseconds));
const checks = [];
const errors = [];
let win;
async function evaluate(expression) { return win.webContents.executeJavaScript(expression,true); }
async function wait(expression,description) {
  for (let i=0;i<400;i++) { if (await evaluate(expression)) return; await delay(50); }
  throw new Error(description + ': ' + await evaluate('document.body.innerText.slice(-1800)'));
}
async function type(selector,text) {
  await evaluate(`document.querySelector(${JSON.stringify(selector)}).focus()`);
  await win.webContents.insertText(text);
}
async function prompt(text) {
  await wait(`!document.querySelector('.send-behavior') && !document.querySelector('.approval-panel') && document.querySelector('.composer textarea')?.value===''`,'The prior desktop turn did not finish delivery and restore its empty composer');
  await type('.composer textarea',text);
  await wait(`document.querySelector('.composer textarea')?.value===${JSON.stringify(text)}`,'The native keyboard prompt did not reach the editor');
  win.webContents.sendInputEvent({type:'keyDown',keyCode:'Enter'});
  win.webContents.sendInputEvent({type:'keyUp',keyCode:'Enter'});
}
async function screenshot(name) {
  await delay(350);
  fs.writeFileSync(path.join(options.outputRoot,name),(await win.webContents.capturePage()).toPNG());
}
app.whenReady().then(async()=>{
  try {
    for(let i=0;i<400;i++){win=BrowserWindow.getAllWindows().find(window=>window.getTitle()==='Reverie');if(win)break;await delay(25);}
    if(!win)throw new Error('The actual Reverie window was not created.');
    win.webContents.on('console-message',(_event,_level,message)=>{if(/Error|TypeError/i.test(message))errors.push(message);});
    await wait('!!window.reverie && !!document.querySelector(".composer textarea")','Native desktop did not become usable');
    await evaluate('window.__reverieProbeEvents=[]; window.reverie.onEvent(message=>window.__reverieProbeEvents.push(message.event)); true');
    const state = await evaluate('window.reverie.request("getState",{}).then(response=>response.state)');
    if(state.core.implementation!=='rust')throw new Error('The desktop is not using Rust.');
    const paths = await evaluate('window.reverie.paths()');
    fs.writeFileSync(path.join(options.outputRoot,'desktop-paths.json'),JSON.stringify(paths,null,2));
    checks.push('Real Electron window, renderer, preload and Rust initialization');
    await evaluate('document.querySelector(".footer-settings").click()');
    await wait('!!document.querySelector("select[aria-label=权限模式]")','The native permission settings did not appear');
    const modes=await evaluate('Array.from(document.querySelector("select[aria-label=权限模式]").options,o=>o.value)');
    if(JSON.stringify(modes)!==JSON.stringify(['strict','normal','auto','full_access']))throw new Error('The desktop did not expose four approval modes');
    for(const choice of ['deny','wait']){
      await evaluate(`(()=>{const field=document.querySelector('select[aria-label="Auto 审查拒绝或失败时"]');field.value=${JSON.stringify(choice)};field.dispatchEvent(new Event('change',{bubbles:true}));})()`);
      await wait(`document.querySelector('select[aria-label="Auto 审查拒绝或失败时"]').value===${JSON.stringify(choice)}`,'The selected Auto fallback did not reach the settings view');
    }
    await screenshot('permission-settings.png');
    const modelsTab=`Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()==='模型与提供商')`;
    await evaluate(`${modelsTab}.click()`);
    await wait("!!document.querySelector('.settings-model-card .edit-model')",'The standard model was missing from settings');
    const card=name=>`Array.from(document.querySelectorAll('.settings-model-card')).find(card=>card.querySelector('strong')?.textContent===${JSON.stringify(name)})`;
    await evaluate(`${card('Rust 本地验收模型')}.querySelector('.edit-model').click()`);
    await wait("!!document.querySelector('.api-key-environment-field button')",'The standard model edit dialog did not open');
    await evaluate("window.reverie.request('deleteStandardModel',{index:0,profileId:'before-edit'})");
    await evaluate("document.querySelector('.api-key-environment-field button').click()");
    await wait("!!document.querySelector('datalist option[value=REVERIE_DESKTOP_TEST_KEY]')",'The native environment suggestion did not reach the real model form');
    await evaluate(`(() => {
      const field=document.querySelector('.api-key-environment-field input');
      const suggestion=field.list.querySelector('option[value=REVERIE_DESKTOP_TEST_KEY]');
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(field,suggestion.value);
      field.dispatchEvent(new Event('input',{bubbles:true}));
    })()`);
    await evaluate("document.querySelector('.form-modal button[type=submit]').click()");
    await wait("!document.querySelector('.form-modal')",'The model reference was not saved');
    const savedModel=JSON.parse(fs.readFileSync(path.join(options.appRoot,'.reverie/config.json'),'utf8')).models[0];
    if(savedModel.api_key || savedModel.api_key_env!=='REVERIE_DESKTOP_TEST_KEY' || savedModel.max_context_tokens!==65536
        || savedModel.custom_headers?.['x-fixture-saved']!=='preserve')throw new Error('Saving the environment reference changed other model settings or retained the literal key');
    checks.push('Editing the named standard model lists actual native environment references, saves the selected name and preserves its context size and redacted headers');
    await evaluate(`${card('delete-target')}.querySelector('.delete-model').click()`);
    await wait("!!document.querySelector('.confirm-modal')",'The delete confirmation did not open');
    await evaluate("window.reverie.request('deleteStandardModel',{index:1,profileId:'before-delete'})");
    await evaluate("document.querySelector('.confirm-modal .danger-button').click()");
    await wait("document.querySelectorAll('.settings-model-card').length===2",'Deleting the original target after the index shifted failed');
    const inventory=JSON.parse(fs.readFileSync(path.join(options.appRoot,'.reverie/config.json'),'utf8'));
    if(inventory.models.map(m=>m.profile_id).join(',')!=='desktop-profile,alternate-profile'||inventory.active_model_index!==0)throw new Error('Stale dialog changed a neighboring profile or the workspace selection');
    for(const name of ['Alternate profile','Rust 本地验收模型']) {
      await evaluate(`${card(name)}.querySelector('.model-card-main').click()`);
      await wait(`document.querySelectorAll('.settings-model-card.active').length===1 && ${card(name)}.classList.contains('active')`,'Expected exactly the chosen profile to be active in settings');
    }
    checks.push('Real edit and deletion dialogs target their original profiles after a preceding row disappears, preserve the default, and select each same-name settings card independently');
    await evaluate('document.querySelector(".footer-settings").click()');
    checks.push('All four native permission modes and the two selectable Auto fallback choices are present in the actual settings window');
    await evaluate(`Array.from(document.querySelectorAll('.main-nav button')).find(button=>button.textContent.trim()==='技能').click()`);
    await wait('!!document.querySelector(".skills-page") && document.body.innerText.includes("desktop-native-skill") && document.body.innerText.includes("photo-to-3d")','The native skill catalog did not reach the actual Skills page');
    await type('.skills-page input','desktop-native-skill');
    await evaluate(`Array.from(document.querySelectorAll('.skills-page .plugin-card')).find(card=>card.innerText.includes('desktop-native-skill')).querySelector('.plugin-toggles button').click()`);
    await wait(`document.querySelector('.skills-page .skill-chip')?.innerText.includes('desktop-native-skill')`,'The native draft pin did not appear');
    await screenshot('native-skills.png');
    await evaluate(`Array.from(document.querySelectorAll('.main-nav button')).find(button=>button.textContent.trim()==='对话').click()`);
    await wait(`Array.from(document.querySelectorAll('.skill-chip')).some(chip=>chip.innerText.includes('desktop-native-skill'))`,'The same pin did not reach the composer');
    checks.push('Native built-in and workspace Skills page, filtering, draft pin and the same composer state');
    if(options.semantic) {
      const contextButton=`Array.from(document.querySelectorAll('.main-nav button')).find(button=>button.textContent.trim()==='上下文引擎')`;
      await evaluate(`${contextButton}.click()`);
      await wait('!!document.querySelector(".context-engine-page") && document.querySelectorAll(".context-fields input").length===3','The actual Context Engine page did not open');
      await type('.context-fields label:first-child input',options.semantic.directory);
      await type('.context-fields label:nth-child(2) input',options.semantic.digest);
      await evaluate(`Array.from(document.querySelectorAll('.context-engine-page button')).find(button=>button.textContent.trim()==='安装并启用').click()`);
      await wait(`window.__reverieProbeEvents.some(event=>event?.type==='context.progress' && event.action==='installSemanticResources')`,'The GUI did not start native resource validation');
      await evaluate(`Array.from(document.querySelectorAll('.main-nav button')).find(button=>button.textContent.trim()==='对话').click()`);
      await wait(`window.__reverieProbeEvents.some(event=>event?.type==='context.progress' && event.action==='installSemanticResources' && event.phase==='finished')`,'The native resource install did not finish while viewing the conversation');
      await evaluate(`${contextButton}.click()`);
      await wait(`document.querySelector('.context-fields label:first-child input')?.value===${JSON.stringify(options.semantic.directory)} && document.querySelector('.context-fields label:nth-child(2) input')?.value===${JSON.stringify(options.semantic.digest)}`,'Resource input drafts did not survive page navigation');
      await wait(`Array.from(document.querySelectorAll('.context-resources code')).some(code=>code.textContent===${JSON.stringify(options.semantic.digest)})`,'The installed native resource did not appear in the page');
      await screenshot('context-resources.png');
      checks.push('Actual context page, offline resource validation and activation with drafts preserved while navigating');
      await wait(`Array.from(document.querySelectorAll('.context-engine-page button')).find(button=>button.textContent.trim()==='更新语义索引')?.disabled===false`,'The semantic index control stayed disabled');
      await evaluate(`Array.from(document.querySelectorAll('.context-engine-page button')).find(button=>button.textContent.trim()==='更新语义索引').click()`);
      await wait(`window.__reverieProbeEvents.some(event=>event?.type==='context.progress' && event.action==='indexSemanticWorkspace' && event.phase==='finished')`,'The GUI did not finish the actual semantic index');
      const query='How can I restore player progress after closing the game?';
      await type('.context-query textarea',query);
      await wait(`document.querySelector('.context-query button[type=submit]')?.disabled===false`,'The actual retrieval control stayed disabled');
      await evaluate(`document.querySelector('.context-query button[type=submit]').click()`);
      await wait(`document.querySelector('.context-evidence pre')?.textContent.includes('恢复冒险进度')`,'Actual local vector and reranking evidence did not render');
      await evaluate(`document.querySelector('.context-evidence').scrollIntoView({block:'center'})`);
      await screenshot('context-evidence.png');
      await evaluate(`Array.from(document.querySelectorAll('.main-nav button')).find(button=>button.textContent.trim()==='对话').click()`);
      await evaluate(`${contextButton}.click()`);
      await wait(`document.querySelector('.context-query textarea')?.value===${JSON.stringify(query)} && document.querySelector('.context-evidence pre')?.textContent.includes('恢复冒险进度')`,'Query drafts or actual results were lost after page navigation');
      checks.push('Actual semantic index and neural evidence display with query drafts and results preserved');
      const beforeWatch = await evaluate("window.reverie.request('getContextStatus',{}).then(response=>response.context_engine.revision)");
      await wait("document.querySelector('.context-engine-page input[type=checkbox]')?.disabled===false",'The automatic index control did not become available');
      await evaluate("document.querySelector('.context-engine-page input[type=checkbox]').click()");
      await wait("window.reverie.request('getContextStatus',{}).then(response=>response.context_engine.watcher?.status==='watching')",'The actual GUI did not enable native file observation');
      fs.appendFileSync(path.join(options.projectRoot,'saving.md'),'新的进度字段记录已经收集的钥匙。\n');
      await wait(`window.reverie.request('getContextStatus',{}).then(response=>response.context_engine.revision>${Number(beforeWatch)} && response.context_engine.watcher?.semantic_revision===response.context_engine.revision && response.context_engine.watcher.status==='watching')`,'The GUI did not receive the automatically updated semantic generation');
      await wait("document.querySelector('.context-query button[type=submit]')?.disabled===false",'Retrieval stayed disabled after the automatic update');
      await evaluate("document.querySelector('.context-query button[type=submit]').click()");
      await wait("document.querySelector('.context-evidence pre')?.textContent.includes('已经收集的钥匙')",'The GUI query did not return automatically refreshed source evidence');
      if(!await evaluate("window.__reverieProbeEvents.some(event=>event?.automatic===true && event.phase==='embedding')"))throw new Error('No native automatic embedding event reached the renderer.');
      await evaluate("document.querySelector('.context-engine-page input[type=checkbox]').click()");
      await wait("window.reverie.request('getContextStatus',{}).then(response=>response.context_engine.watcher?.enabled===false && !response.context_engine.watcher.operation)",'The GUI did not pause native observation');
      await evaluate("document.querySelector('.context-section').scrollIntoView({block:'start'})");
      await screenshot('context-watcher.png');
      checks.push('Actual GUI pause/resume controls, automatic native embedding events and current neural evidence');
      await wait(`Array.from(document.querySelectorAll('.context-resources button')).some(button=>button.textContent.trim()==='删除' && !button.disabled)`,'The restored page did not load its managed resources');
      await evaluate(`Array.from(document.querySelectorAll('.context-resources button')).find(button=>button.textContent.trim()==='删除').click()`);
      await wait(`document.querySelector('dialog.context-remove')?.open===true`,'Resource removal did not require its explicit dialog');
      win.webContents.sendInputEvent({type:'keyDown',keyCode:'Escape'});win.webContents.sendInputEvent({type:'keyUp',keyCode:'Escape'});
      await wait(`!document.querySelector('dialog.context-remove')`,'Escape did not dismiss the native modal dialog');
      const unchanged=await evaluate(`window.reverie.request('getSemanticResources',{})`);
      if(unchanged.semantic.active.manifest_sha256!==options.semantic.digest)throw new Error('Cancelling the removal dialog changed the resource activation.');
      checks.push('Keyboard cancellation of explicit resource removal without altering the active bundle');
      await evaluate(`Array.from(document.querySelectorAll('.main-nav button')).find(button=>button.textContent.trim()==='对话').click()`);
    }
    await prompt('QUESTION');
    await wait('document.querySelector(".approval-tool")?.textContent.includes("userInput")','Strict did not ask before using the question tool');
    await evaluate(`Array.from(document.querySelectorAll('.approval-panel button')).find(button=>button.textContent.trim()==='同意').click()`);
    await wait('document.querySelectorAll(".user-question-panel input[type=radio]").length === 4','Four explicit answer choices did not appear');
    await wait('Array.from(document.querySelectorAll(".session-state")).some(item => item.textContent === "等待回答")','The user question was mislabeled as a permission approval');
    await screenshot('question.png');
    await evaluate('document.querySelector(".user-question-options label:last-child").click()');
    await wait('!!document.querySelector(".user-question-panel textarea")','Custom answer editor did not appear');
    await type('.user-question-panel textarea',options.answer);
    await evaluate('document.querySelector(".user-question-panel button[type=submit]").click()');
    await wait(`!document.querySelector('.user-question-panel') && document.body.innerText.includes(${JSON.stringify(options.answer)})`,'The explicit custom answer did not reach the native model and transcript');
    await screenshot('answer.png');
    await wait('window.__reverieProbeEvents.filter(event=>event?.type==="run.finished" && event.state==="completed").length===1','The answered conversation did not complete');
    checks.push('Keyboard prompt, three choices plus custom, explicit answer and visible newlines');
    const profileSession=(await evaluate('window.reverie.request("getState",{}).then(response=>response.state)')).sessions.current_session_id;
    await evaluate("document.querySelector('.model-trigger').click()");
    await wait("document.querySelectorAll('.model-option-list[data-source=standard] button').length===2",'The same-name profiles did not reach the picker');
    await evaluate("Array.from(document.querySelectorAll('.model-option-list button')).find(button=>button.innerText.includes('Alternate profile')).click()");
    await wait("!document.querySelector('.model-picker')",'The selected profile did not close the picker');
    const selection=await evaluate(`window.reverie.request('getConversationConfig',{sessionId:${JSON.stringify(profileSession)}})`);
    if(selection.configuration.model_ref.profile_id!=='alternate-profile')throw new Error('Clicked Alternate profile but session saved '+JSON.stringify(selection.configuration.model_ref));
    await evaluate("document.querySelector('.model-trigger').click()");
    await wait("document.querySelectorAll('.model-option-list button.active').length===1 && document.querySelector('.model-option-list button.active').innerText.includes('Alternate profile')",'The picker did not highlight only the selected profile');
    await evaluate("window.reverie.request('updateStandardModel',{index:0,profileId:'desktop-profile',model:{description:'Inventory changed while picker was open'}})");
    await evaluate("document.querySelector('.model-picker-sources button').click()");
    await wait("document.querySelector('.model-option-list')?.innerText.includes('Inventory changed while picker was open') && document.querySelector('.model-option-list button.active')?.innerText.includes('Alternate profile')",'Refreshing the real inventory lost the session selection or returned stale rows');
    await screenshot('selected-model-profile.png');
    win.webContents.sendInputEvent({type:'keyDown',keyCode:'Escape'});win.webContents.sendInputEvent({type:'keyUp',keyCode:'Escape'});
    await wait("!document.querySelector('.model-picker')",'The picker did not close');
    await evaluate("document.querySelector('.footer-settings').click()");
    await wait(`!!${modelsTab}`,'Settings did not reopen');
    await evaluate(`${modelsTab}.click()`);
    await wait(`!!${card('Rust 本地验收模型')}`,'The profiles did not return to settings');
    await evaluate(`${card('Rust 本地验收模型')}.querySelector('.edit-model').click()`);
    await wait("!!document.querySelector('.form-modal button[type=submit]:enabled')",'The existing model was not editable');
    await evaluate("document.querySelector('.form-modal button[type=submit]').click()");
    await wait(`!document.querySelector('.form-modal') && document.querySelectorAll('.settings-model-card.active').length===1 && ${card('Alternate profile')}.classList.contains('active')`,'Editing the workspace inventory lost the active conversation selection');
    await evaluate("document.querySelector('.footer-settings').click()");
    checks.push('Same-name picker selection, single active row and saved conversation profile; subsequent turns use its distinct loopback endpoint');
    await prompt('WRITE');
    await wait('!!document.querySelector(".approval-panel:not(.user-question-panel)")','The write tool bypassed its approval');
    if(fs.existsSync(options.outputFile))throw new Error('Write occurred before approval.');
    await screenshot('approval.png');
    await evaluate(`Array.from(document.querySelectorAll('.approval-panel button')).find(button=>button.textContent.trim()==='同意').click()`);
    await wait('!document.querySelector(".approval-panel") && window.__reverieProbeEvents.filter(event=>event?.type==="run.finished" && event.state==="completed").length===2','The approved native tool did not finish');
    await wait("!document.querySelector('.send-behavior') && document.querySelector('.composer textarea')?.value===''",'The approved write did not finish desktop integration and delivery');
    if(fs.readFileSync(options.outputFile,'utf8')!==options.fileContent)throw new Error('The actual tool did not preserve complete file bytes.');
    checks.push('Actual strict approval and native complete file write');
    await prompt('COMMAND');
    await wait('!!document.querySelector(".approval-panel:not(.user-question-panel)")','The command bypassed its separate approval');
    await wait(`document.querySelector('.approval-panel')?.innerText.includes('command_exec')`,'The displayed approval did not belong to the current command');
    await evaluate(`Array.from(document.querySelectorAll('.approval-panel button')).find(button=>button.textContent.trim()==='同意').click()`);
    await wait('Array.from(document.querySelectorAll(".activity-group")).some(group=>group.innerText.includes("command_exec"))','The command activity did not appear');
    await evaluate('Array.from(document.querySelectorAll(".activity-group")).filter(group=>group.innerText.includes("command_exec")).forEach(group=>{group.open=true})');
    await wait('Array.from(document.querySelectorAll(".activity-item")).some(item=>item.innerText.includes("command_exec"))','The command tool card did not appear');
    await evaluate('Array.from(document.querySelectorAll(".activity-item")).filter(item=>item.innerText.includes("command_exec")).forEach(item=>{item.open=true})');
    await wait('document.body.innerText.includes("COMMAND_LIVE😀")','The live command output did not reach the visible tool card');
    await wait('Array.from(document.querySelectorAll(".session-state")).some(item=>item.textContent==="运行中")','The approved command still appeared to be waiting for permission');
    if(await evaluate('Array.from(document.querySelectorAll(".activity-item")).filter(item=>item.querySelector("strong")?.textContent==="command_exec").length')!==1)throw new Error('Command chunks produced duplicate tool cards.');
    await screenshot('command-progress.png');
    await wait('window.__reverieProbeEvents.filter(event=>event?.type==="run.finished" && event.state==="completed").length===3 && document.body.innerText.includes("COMMAND_FINAL😀")','The command did not complete');
    await wait('!Array.from(document.querySelectorAll(".activity-item.working")).some(item=>item.innerText.includes("command_exec"))','The completed command retained a working tool card');
    checks.push('Visible native command output in one tool card, separate approval and completed state');
    await prompt('WAIT');
    await wait('document.body.innerText.includes("partial waiting output")','Live output did not arrive');
    const session = (await evaluate('window.reverie.request("getState",{}).then(response=>response.state)')).sessions.current_session_id;
    await evaluate(`window.reverie.request('stopPrompt',{projectRoot:${JSON.stringify(options.projectRoot)},sessionId:${JSON.stringify(session)}})`);
    await wait('window.__reverieProbeEvents.some(event=>event?.type==="run.finished" && event.state==="cancelled")','The stopped run did not finalize cancellation');
    const saved = await evaluate(`window.reverie.request('getSession',{sessionId:${JSON.stringify(session)},projectRoot:${JSON.stringify(options.projectRoot)},select:false})`);
    if(!saved.session.interrupted_streams.some(stream=>stream.content.includes('partial waiting output')))throw new Error('Cancelled native stream was lost.');
    const submitted=saved.session.messages.filter(message=>message.role==='user').map(message=>message.content);
    if(JSON.stringify(submitted)!==JSON.stringify(['QUESTION','WRITE','COMMAND','WAIT']))throw new Error('The native desktop submitted a duplicated or unexpected user turn: '+JSON.stringify(submitted));
    checks.push('Live output, targeted stop and persisted interrupted text');
    await screenshot('finished.png');
    fs.writeFileSync(path.join(options.outputRoot,'report.json'),JSON.stringify({passed:true,scope:'actual Electron and native Rust with a loopback model; no external service or full product acceptance',checks,errors,paths},null,2)+'\n');
    console.log(JSON.stringify({passed:true,checks:checks.length,report:path.join(options.outputRoot,'report.json')}));
    process.exitCode=0;
  } catch(error) {
    fs.writeFileSync(path.join(options.outputRoot,'failed.json'),JSON.stringify({passed:false,error:String(error.stack || error),checks,errors},null,2));
    if(win&&!win.isDestroyed())await screenshot('failed.png').catch(()=>{});
    console.error(error);
    process.exitCode=1;
  } finally {
    if(win&&!win.isDestroyed()) {
      const events=await evaluate('window.__reverieProbeEvents || []').catch(()=>[]);
      fs.writeFileSync(path.join(options.outputRoot,'core-events.json'),JSON.stringify(events,null,2)+'\n');
    }
    app.quit();
  }
});
