const {app, BrowserWindow} = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const options = JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
app.setName('Reverie Rust desktop verification');
fs.mkdirSync(path.join(options.runtimeRoot,'user-data'),{recursive:true});
app.setPath('userData',path.join(options.runtimeRoot,'user-data'));
process.env.REVERIE_DESKTOP_RUNTIME_ROOT = options.runtimeRoot;
process.argv = [process.execPath,options.uiRoot,'--gui','--project',options.projectRoot];
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
  await type('.composer textarea',text);
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
    await prompt('QUESTION');
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
    await prompt('WRITE');
    await wait('!!document.querySelector(".approval-panel:not(.user-question-panel)")','The write tool bypassed its approval');
    if(fs.existsSync(options.outputFile))throw new Error('Write occurred before approval.');
    await screenshot('approval.png');
    await evaluate(`Array.from(document.querySelectorAll('.approval-panel button')).find(button=>button.textContent.trim()==='同意').click()`);
    await wait('!document.querySelector(".approval-panel") && window.__reverieProbeEvents.filter(event=>event?.type==="run.finished" && event.state==="completed").length===2','The approved native tool did not finish');
    for(let i=0;i<100 && !fs.existsSync(options.outputFile);i++)await delay(25);
    if(fs.readFileSync(options.outputFile,'utf8')!==options.fileContent)throw new Error('The actual tool did not preserve complete file bytes.');
    checks.push('Actual strict approval and native complete file write');
    await prompt('COMMAND');
    await wait('!!document.querySelector(".approval-panel:not(.user-question-panel)")','The command bypassed its separate approval');
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
  } finally { app.quit(); }
});
