import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import http from 'node:http';
import {startBridge} from './rust-bridge-client.mjs';

const executable = path.resolve(process.argv[2] || `ReverieCli-rs/target/release/reverie${process.platform === 'win32' ? '.exe' : ''}`);
const directory = path.resolve(process.argv[3] || '.runtime/rust-3.0/modes-smoke');
fs.mkdirSync(directory, {recursive: true});
const root = fs.mkdtempSync(path.join(directory, 'case-'));
const project = path.join(root, '工作区');
const appRoot = path.join(root, 'application');
fs.mkdirSync(path.join(appRoot, '.reverie'), {recursive: true});
fs.mkdirSync(path.join(project, 'artifacts'), {recursive: true});
fs.writeFileSync(path.join(project, 'artifacts/Master Document.md'), '# Design\n\nConcrete fixture requirements and implementation design.\n');
fs.writeFileSync(path.join(project, 'artifacts/proof.json'), '{"fixture":true}\n');
const checks = [];
let bridge;
let serverFailure;
let call = 0;
let modelPhase = 'tools';
let modelCalls = 0;
let pendingModel;
const extractionBody = '# 可调原则\n\n选择与场景目标有关的细节，用角色主动做出的决定推动变化。保留项目确定的事实、视角和限制。根据叙述任务调整长短句，不用固定句式模拟某位作者的独特语言。示例须重新创作，不复制样本角色、地名或可识别的语句。为行动建立原因和结果，并用具体的感知与反应体现情绪。安静的场景可以保留停顿，不强行加上悬念。复核每处重复是否改变意义；删去没有新信息的解释，允许有意识的回收。局限：少量片段不能代表完整作品、普遍规律或任何作者的全部风格。';
process.env.NO_PROXY = [process.env.NO_PROXY, '127.0.0.1', 'localhost'].filter(Boolean).join(',');
const server = http.createServer(async (request, response) => {
  try {
    assert.equal(request.url, '/v1/chat/completions');
    let bytes = '';
    for await (const chunk of request) bytes += chunk;
    const body = JSON.parse(bytes);
    modelCalls++;
    assert.equal(body.stream, false);
    const last = body.messages.at(-1);
    let message;
    if (modelPhase.startsWith('wstyle-')) {
      assert(!body.tools?.length, 'WStyle model requests must have no execution tools');
      assert(body.messages[0].content.includes('No tools are available'));
      const input = JSON.parse(last.content);
      if (modelPhase === 'wstyle-cancel') {pendingModel = {input, response}; return;}
      let content;
      if (modelPhase.startsWith('wstyle-review')) {
        assert(input.active_wstyles.includes('delicate-prose'));
        content = {summary: '结合已确认事实检查动作的作用。', issues: [{line_start: input.prose[0].line,
          line_end: input.prose[0].line, quote: input.prose[0].text, category: 'character',
          impact: '局部原文未说明全部前因。', suggestion: '结合已确认的情节检查角色的行动目标。', wstyle_ids: ['delicate-prose']}],
          limitations: ['仅检查所给片段及摘要，没有评价整部作品。']};
        if (modelPhase === 'wstyle-review-invalid') content.issues[0].quote = '这段伪造的引文不在原文内';
      } else {
        assert(input.samples.length === 1);
        content = {name: '可调机制', description: '从有限样本提取的可调叙事机制。', layer: 'prose',
          body: modelPhase === 'wstyle-extract-copy' ? input.samples[0].text.repeat(4) : extractionBody,
          observations: [{sample: 1, quote: 'observed motion', mechanism: '将感知与具体的主动选择关联。'}],
          limitations: ['有限样本无法证明完整作品或任何作者的全部风格。']};
      }
      message = modelPhase === 'wstyle-review-tool' ? {role: 'assistant', content: null,
        tool_calls: [{id: 'forbidden-wstyle-tool', type: 'function', function: {name: 'create_file', arguments: JSON.stringify({path: 'forbidden-wstyle.txt', content: 'must not execute'})}}]} : {role: 'assistant', content: JSON.stringify(content)};
    } else if (modelPhase.startsWith('aio')) {
      assert(!body.tools?.length, 'AiO judgments must have no execution tools');
      assert(body.messages[0].content.includes('No tools are available'));
      const input = JSON.parse(last.content);
      assert.deepEqual(input.workspaces, [project]);
      assert(input.context.history_ref.session_id === 'aio-mainline');
      const decision = {speech: modelPhase === 'aio-recovery' ? '恢复验证的完整发言\n保留第二行😀' : '原生 AiO 的完整发言\n保留第二行😀',
        tasks: [{workspace: project, mode: 'reverie-atlas', actor: 'worker', prompt: 'ATLAS:{"action":"assess_completion"}',
          acceptance: 'Read the native Atlas ledger and report its actual state without editing.', role: 'verify'}],
        memories: [{content: '用户要求保留小说完整原文和原始版本', kind: 'preference', provenance: 'explicit_statement', confidence: 1.0}]};
      if (['aio-cancel', 'aio-hold'].includes(modelPhase)) {pendingModel = {input, response, decision}; return;}
      if (modelPhase === 'aio-retired') decision.tasks[0].mode = 'ant';
      message = {role: 'assistant', content: JSON.stringify(decision)};
    } else if (last.role === 'tool') message = {role: 'assistant', content: last.content};
    else {
      const prompt = body.messages.findLast(item => item.role === 'user').content;
      const args = JSON.parse(prompt.slice(prompt.indexOf(':') + 1));
      const name = prompt.startsWith('WRITER:') ? 'serial_novel' : 'atlas_delivery_orchestrator';
      assert(body.tools.some(tool => tool.function.name === name));
      assert(body.messages[0].content.includes(name));
      message = {role: 'assistant', content: null, tool_calls: [{id: `mode-${++call}`, type: 'function', function: {name, arguments: JSON.stringify(args)}}]};
    }
    response.writeHead(200, {'content-type': 'application/json'});
    response.end(JSON.stringify({choices: [{message, finish_reason: message.tool_calls ? 'tool_calls' : 'stop'}]}));
  } catch (error) {serverFailure = error; response.destroy(error);}
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
fs.writeFileSync(path.join(appRoot, '.reverie/config.json'), JSON.stringify({mode: 'reverie', models: [{
  model: 'fixture-model', profile_id: 'fixture-model', provider: 'openai-chat',
  base_url: `http://127.0.0.1:${server.address().port}/v1`, api_key: 'FIXTURE_SECRET',
}], active_model_source: 'standard', active_model_index: 0, auto_index: false, stream_responses: false,
security: {permission_level: 'full_control', permission_mode: 'default'}}));
async function request(action, payload, expected) {
  const reply = await bridge.request(action, payload, 20000);
  if (expected) assert.equal(reply.type, expected, JSON.stringify(reply));
  return reply;
}
async function start() {
  bridge = startBridge(executable, project, appRoot);
  await bridge.ready;
  await request('initialize', {projectRoot: project}, 'state');
}
async function session(mode, security) {
  const item = (await request('createSession', {name: `${mode} fixture`}, 'session.created')).session;
  const saved = await request('getConversationConfig', {sessionId: item.id}, 'conversation.config');
  await request('getConversationConfig', {sessionId: item.id, revision: saved.revision,
    configuration: {...saved.configuration, settings: {...saved.configuration.settings, mode,
      ...(security ? {security} : {})}}}, 'conversation.config');
  return item.id;
}
async function tool(sessionId, mode, args) {
  const result = await request('runPrompt', {projectRoot: project, sessionId, mode, noIndex: true,
    prompt: `${mode === 'writer' ? 'WRITER' : 'ATLAS'}:${JSON.stringify(args)}`}, 'prompt.result');
  assert.equal(result.result.success, true, JSON.stringify(result));
  const output = JSON.parse(result.result.output_text);
  assert(!JSON.stringify(result).includes('FIXTURE_SECRET'));
  return output;
}
async function close() {
  if (!bridge) return;
  await request('shutdown', {}, 'shutdown');
  assert.equal((await bridge.closed).code, 0);
  bridge = undefined;
}
function passed(name) {checks.push(name);}
async function until(predicate, label) {
  const deadline = Date.now() + 10000;
  while (Date.now() < deadline) {
    if (serverFailure) throw serverFailure;
    const result = predicate();
    if (result) return result;
    await new Promise(resolve => setTimeout(resolve, 20));
  }
  throw new Error(`Timed out waiting for ${label}`);
}
async function wstyle(sessionId, args, phase = 'tools', success = true) {
  modelPhase = phase;
  try {
    const result = await request('wstyleCommand', {projectRoot: project, sessionId, args}, 'wstyle.result');
    assert.equal(result.success, success, JSON.stringify(result));
    assert(!JSON.stringify(result).includes('FIXTURE_SECRET'));
    return result;
  } finally {modelPhase = 'tools';}
}
async function aio(action, payload = {}, expected) {
  const result = await request(action, {assistantId: 'aio', ...payload}, expected);
  assert(!JSON.stringify(result).includes('FIXTURE_SECRET'));
  return result;
}
async function judgment(event, phase = 'aio') {
  modelPhase = phase;
  try {return await aio('aioDecision', {observation: {event_id: event, type: 'fixture'}, workspaces: [project], urgent: true});}
  finally {modelPhase = 'tools';}
}
try {
  await start();
  const atlas = await session('reverie-atlas');
  const catalog = await request('listTools', {sessionId: atlas}, 'tools');
  assert.equal(catalog.mode, 'reverie-atlas');
  assert(catalog.tools.some(item => item.name === 'atlas_delivery_orchestrator'));
  assert(!(await request('listTools', {mode: 'reverie'}, 'tools')).tools.some(item => item.name === 'atlas_delivery_orchestrator'));
  let result = await tool(atlas, 'atlas', {action: 'bootstrap_delivery', objective: 'Native Atlas fixture',
    success_criteria: ['Inspect retained evidence'], contract_confirmed: true});
  assert.equal(result.success, true);
  result = await tool(atlas, 'atlas', {action: 'plan_slices', slice_titles: ['Real persisted fixture']});
  const slice = result.data.state.slices[0].slice_id;
  assert.equal((await tool(atlas, 'atlas', {action: 'assess_completion'})).data.ready, false);
  await tool(atlas, 'atlas', {action: 'record_slice', slice_id: slice, status: 'completed', delivered_changes: ['Fixture file exists']});
  await tool(atlas, 'atlas', {action: 'record_verification', slice_id: slice, summary: 'The fixture evidence exists',
    command: 'fixture evidence read', passed: true, evidence_paths: ['artifacts/proof.json']});
  assert.equal((await tool(atlas, 'atlas', {action: 'assess_completion'})).data.ready, true);
  passed('Session mode, alias, tool catalog, native Atlas ledger and completion evidence');
  const readOnly = await session('reverie-atlas', {permission_level: 'read_only', permission_mode: 'default'});
  assert.equal((await tool(readOnly, 'atlas', {action: 'assess_completion'})).success, true);
  assert.equal((await tool(readOnly, 'atlas', {action: 'plan_slices', slice_titles: ['Forbidden write']})).success, false);
  passed('Mode reads and writes respect the active conversation permission level');
  const writer = await session('writer');
  const writerTools = await request('listTools', {sessionId: writer}, 'tools');
  assert(writerTools.tools.some(item => item.name === 'serial_novel'));
  assert(!writerTools.tools.some(item => ['create_file', 'file_ops', 'command_exec'].includes(item.name)));
  result = await tool(writer, 'writer', {action: 'bootstrap', novel_id: 'native-story', title: 'Native fixture',
    brief: 'Explicit 1000 characters short story', target_chars: 1000, chapter_target_chars: 1000});
  assert.equal(result.success, true);
  assert.equal((await tool(writer, 'writer', {action: 'prepare_chapter', novel_id: 'native-story', title: 'Start', data: {outline: 'Original causal plan'}})).success, false);
  const documents = Object.fromEntries(['world_bible', 'cast_bible', 'story_architecture', 'style_guide', 'roadmap'].map(key => [key, `Concrete original ${key} facts.`]));
  await tool(writer, 'writer', {action: 'configure', novel_id: 'native-story', data: documents});
  await tool(writer, 'writer', {action: 'prepare_chapter', novel_id: 'native-story', title: 'Start', data: {outline: 'Original causal plan'}});
  const original = Array.from({length: 12}, (_,n) => `${n} 她拿着行李走向河岸，并且作出自己的选择。`).join('\n');
  assert.equal((await tool(writer, 'writer', {action: 'commit_chapter', novel_id: 'native-story', data: {content: original}})).success, false);
  const draft = JSON.parse(fs.readFileSync(path.join(project, 'novels/native-story/drafts/chapter-0001.json'), 'utf8'));
  assert.equal(draft.data.content, original);
  assert.equal(draft.recovery_mode, 'append_only');
  const append = Array.from({length: 100}, (_,n) => `${n + 12} 她把票据交给站长，随后乘上新的列车。`).join('\n');
  result = await tool(writer, 'writer', {action: 'commit_chapter', novel_id: 'native-story', data: {append_content: append, summary: 'Retained source fixture', opened_threads: ['A'], timeline_updates: ['Day one']}});
  assert.equal(result.success, true, JSON.stringify(result));
  assert(fs.readFileSync(path.join(project, 'novel/native-story/manuscript.txt'), 'utf8').includes(original));
  assert.equal((await tool(writer, 'writer', {action: 'audit', novel_id: 'native-story'})).data.completion_ready, true);
  const writerSession = await request('getSession', {sessionId: writer}, 'session');
  assert.equal(writerSession.session.metadata.writer_project.novel_id, 'native-story');
  passed('Native Writer five-bible gate, original rejected prose, append recovery, reader export, audit and conversation binding');
  await close();
  await start();
  assert.equal((await tool(writer, 'writer', {action: 'audit', novel_id: 'native-story'})).data.completion_ready, true);
  assert.equal((await tool(writer, 'writer', {action: 'complete', novel_id: 'native-story'})).data.status, 'complete');
  passed('Native Writer restart and disk-backed completion');
  assert.equal((await tool(atlas, 'atlas', {action: 'assess_completion'})).data.ready, true);
  fs.writeFileSync(path.join(project, 'artifacts/proof.json'), '{"fixture":"changed"}\n');
  assert.equal((await tool(atlas, 'atlas', {action: 'assess_completion'})).data.ready, false);
  passed('Native process restart retains state and detects changed verification evidence');
  const chapterPath = path.join(project, 'novels/native-story/chapters/chapter-0001.md');
  const readerPath = path.join(project, 'novel/native-story/manuscript.txt');
  const chapterBytes = fs.readFileSync(chapterPath);
  const readerBytes = fs.readFileSync(readerPath);
  const modelCallsBeforeOffline = modelCalls;
  let selected = (await wstyle(writer, 'use delicate-prose --global')).data.state;
  assert.deepEqual(selected.saved_ids, ['delicate-prose']);
  selected = (await wstyle(writer, 'current')).data.state;
  assert.equal(selected.scope, 'novel:native-story');
  assert.equal(selected.inherited, true);
  assert.equal(selected.cards[0].id, 'delicate-prose');
  assert.equal((await wstyle(writer, 'off')).data.state.cards.length, 0);
  assert.equal((await wstyle(writer, 'inherit')).data.state.inherited, true);
  assert.equal((await wstyle(writer, 'list')).data.items.length, 6);
  const stockCard = path.join(appRoot, '.reverie/wstyles/delicate-prose.md');
  const stockBytes = fs.readFileSync(stockCard);
  assert.equal((await wstyle(writer, 'new custom --from delicate-prose')).data.card.id, 'custom');
  assert.deepEqual(fs.readFileSync(stockCard), stockBytes);
  assert.equal(modelCalls, modelCallsBeforeOffline);
  passed('WStyle offline list/copy, global selection, novel override and inheritance use no Provider calls');
  const review = await wstyle(writer, 'review --chapter 1', 'wstyle-review');
  assert.equal(review.data.report.model_review.issues[0].quote, original.split('\n')[0]);
  assert.equal(review.data.report.source.kind, 'committed_chapter');
  assert(fs.existsSync(review.data.path));
  const invalidReview = await wstyle(writer, 'review --chapter 1', 'wstyle-review-invalid', false);
  assert(invalidReview.error.includes('verbatim'));
  await wstyle(writer, 'review --chapter 1', 'wstyle-review-tool', false);
  assert(!fs.existsSync(path.join(project, 'forbidden-wstyle.txt')));
  passed('WStyle real SDK review validates exact prose quotes and rejects model-requested execution tools');
  const sample = 'First original sample sentence about observed motion and specific choices. Second original sample sentence.';
  const samplePath = path.join(project, 'sample.txt');
  fs.writeFileSync(samplePath, sample);
  const extracted = await wstyle(writer, 'extract mechanism --sample sample.txt --layer prose', 'wstyle-extract');
  assert.equal(extracted.data.card.id, 'mechanism');
  assert.equal(extracted.data.enabled, false);
  assert(fs.existsSync(extracted.data.path));
  const copied = await wstyle(writer, 'extract copied --sample sample.txt --layer prose', 'wstyle-extract-copy', false);
  assert(copied.error.includes('48 contiguous'));
  assert(!fs.existsSync(path.join(appRoot, '.reverie/wstyles/copied.md')));
  assert.equal(fs.readFileSync(samplePath, 'utf8'), sample);
  passed('WStyle real SDK extraction keeps sample provenance, defaults disabled and rejects copied sample passages');
  pendingModel = undefined;
  const eventStart = bridge.events.length;
  const cancelled = wstyle(writer, 'review --chapter 1', 'wstyle-cancel', false);
  cancelled.catch(() => {});
  await until(() => pendingModel, 'a WStyle model request');
  const started = await until(() => bridge.events.slice(eventStart).map(item => item.event).find(item => item?.type === 'wstyle.started'), 'WStyle run identity');
  const busy = await request('wstyleCommand', {projectRoot: project, sessionId: writer, args: 'current'}, 'wstyle.result');
  assert.equal(busy.success, false);
  assert(busy.error.includes('active conversation run'));
  const stopping = await request('stopPrompt', {projectRoot: project, sessionId: writer, runId: started.run_id}, 'run.control');
  assert.equal(stopping.run_id, started.run_id);
  assert((await cancelled).error.includes('cancel'));
  assert(fs.existsSync(path.join(started.diagnostics_path, 'failure.json')));
  await until(() => pendingModel.response.destroyed, 'the cancelled WStyle HTTP connection');
  assert.deepEqual(fs.readFileSync(chapterPath), chapterBytes);
  assert.deepEqual(fs.readFileSync(readerPath), readerBytes);
  assert.deepEqual(fs.readFileSync(stockCard), stockBytes);
  assert.equal((await wstyle(writer, 'current')).success, true);
  passed('WStyle actual cancellation and active-run isolation release the Provider connection and preserve full source bytes');
  assert.equal((await aio('aioState', {}, 'aio.state')).aio.enabled, false);
  assert.equal((await aio('aioControl', {enable: true}, 'aio.state')).aio.enabled, true);
  assert.equal((await aio('getSession', {sessionId: 'aio-mainline'}, 'session')).session.metadata.assistant_id, 'aio');
  assert.equal((await request('getSession', {sessionId: 'aio-mainline'})).type, 'error');
  const observation = await aio('aioObserve', {}, 'aio.observation');
  assert.equal(observation.available, false);
  assert.equal(observation.status, 'native_observation_not_migrated');
  pendingModel = undefined;
  const stale = judgment('stale-control', 'aio-hold');
  stale.catch(() => {});
  await until(() => pendingModel, 'an AiO judgment before changing controls');
  await aio('aioControl', {changes: {proactive: false}}, 'aio.state');
  pendingModel.response.writeHead(200, {'content-type': 'application/json'});
  pendingModel.response.end(JSON.stringify({choices: [{message: {role: 'assistant', content: JSON.stringify(pendingModel.decision)}, finish_reason: 'stop'}]}));
  const staleResult = await stale;
  assert.equal(staleResult.type, 'aio.decision');
  assert.equal(staleResult.decision.control_changed, true);
  assert.equal((await aio('aioPendingTasks', {}, 'aio.tasks')).tasks.length, 0);
  assert.equal((await aio('aioMessages', {}, 'aio.messages')).messages.length, 0);
  assert.equal((await aio('aioMemory', {}, 'aio.memory')).memories.length, 0);
  await aio('aioControl', {changes: {proactive: true}}, 'aio.state');
  pendingModel = undefined;
  const aioEventStart = bridge.events.length;
  const cancelledJudgment = judgment('cancelled-decision', 'aio-cancel');
  cancelledJudgment.catch(() => {});
  await until(() => pendingModel, 'a cancellable AiO Provider judgment');
  await until(() => bridge.events.slice(aioEventStart).some(item => item.event?.type === 'aio.decision.started'), 'an AiO judgment event');
  await aio('aioControl', {changes: {paused: true}}, 'aio.state');
  assert.equal((await cancelledJudgment).type, 'error');
  await until(() => pendingModel.response.destroyed, 'the cancelled AiO HTTP connection');
  assert.equal((await aio('aioPendingTasks', {}, 'aio.tasks')).tasks.length, 0);
  assert.equal((await aio('getSession', {sessionId: 'aio-mainline'}, 'session')).session.messages.length, 0);
  await aio('aioControl', {changes: {paused: false}}, 'aio.state');
  assert.equal((await judgment('retired-proposal', 'aio-retired')).type, 'error');
  assert.equal((await aio('aioPendingTasks', {}, 'aio.tasks')).tasks.length, 0);
  passed('AiO actual decisions use application scope, report unavailable observation, reject retired task modes and commit no stale or cancelled effects');
  const accepted = await judgment('decision-one');
  assert.equal(accepted.type, 'aio.decision');
  assert.equal(accepted.decision.tasks.length, 1);
  const task = accepted.decision.tasks[0];
  const messageId = accepted.decision.message_id;
  assert.equal(task.configuration.settings.mode, 'reverie-atlas');
  assert.equal((await aio('aioPendingTasks', {}, 'aio.tasks')).tasks[0].id, task.id);
  const originalModelCalls = modelCalls;
  const duplicate = await judgment('decision-one');
  assert.equal(duplicate.decision.skipped, 'already_accepted');
  assert.equal(modelCalls, originalModelCalls);
  assert.equal((await aio('getSession', {sessionId: 'aio-mainline'}, 'session')).session.messages[0].content, '原生 AiO 的完整发言\n保留第二行😀');
  const taskPage = (await aio('getSession', {sessionId: task.branch}, 'session')).session;
  assert.equal(taskPage.metadata.assistant_id, 'aio');
  assert.equal(taskPage.messages[0].content, task.prompt);
  assert.equal((await request('getSession', {sessionId: task.branch})).type, 'error');
  assert.equal((await aio('aioTaskState', {taskId: task.id, state: 'running', revision: 1}, 'aio.task-state')).revision, 2);
  const taskExecution = await aio('runPrompt', {projectRoot: project, sessionId: task.branch,
    prompt: task.prompt, promptAlreadySaved: true, configuration: task.configuration, acceptance: task.acceptance,
    runType: task.runType, noIndex: true}, 'prompt.result');
  assert.equal(taskExecution.result.success, true, JSON.stringify(taskExecution));
  assert.equal(JSON.parse(taskExecution.result.output_text).data.ready, false);
  const afterRun = (await aio('getSession', {sessionId: task.branch}, 'session')).session;
  assert.equal(afterRun.messages.filter(item => item.role === 'user' && item.content === task.prompt).length, 1);
  assert.equal((await aio('aioTaskState', {taskId: task.id, state: 'waiting_incorporation', revision: 2,
    result: {source: 'actual loopback Rust run', output: taskExecution.result.output_text}}, 'aio.task-state')).revision, 3);
  assert.equal((await aio('aioTaskState', {taskId: task.id, state: 'completed', revision: 2})).type, 'error');
  await aio('aioTaskState', {taskId: task.id, state: 'completed', revision: 3, result: {checked: true}}, 'aio.task-state');
  assert.equal((await aio('aioMessageState', {messageId, state: 'displaying'}, 'aio.message-state')).claimed, true);
  assert.equal((await aio('aioMessageState', {messageId, state: 'displaying'}, 'aio.message-state')).claimed, false);
  await aio('aioMessageState', {messageId, state: 'presented'}, 'aio.message-state');
  const reply = {messageId, replyId: 'user-reply-one', text: '用户完整回复\n原文😀'};
  await aio('aioReply', reply, 'aio.state');
  await aio('aioReply', reply, 'aio.state');
  assert.equal((await aio('getSession', {sessionId: 'aio-mainline'}, 'session')).session.messages.filter(item => item.content === reply.text).length, 1);
  const signals = (await aio('aioPendingSignals', {}, 'aio.signals')).signals;
  assert(signals.length >= 2);
  for (const signal of signals) await aio('aioAcknowledgeSignal', {eventId: signal.event_id}, 'aio.signal-state');
  assert.equal((await aio('aioPendingSignals', {}, 'aio.signals')).signals.length, 0);
  let memories = (await aio('aioMemory', {}, 'aio.memory')).memories;
  assert.equal(memories.length, 1);
  memories = (await aio('aioMemory', {memoryId: memories[0].id, content: '用户要求保留全部完整原文、原始版本及精确来源。'}, 'aio.memory')).memories;
  assert.equal(memories.length, 1);
  await aio('aioMemory', {memoryId: memories[0].id, content: null}, 'aio.memory');
  assert.equal((await aio('aioMemory', {}, 'aio.memory')).memories.length, 0);
  passed('AiO actual native worker run, task revision conflicts, delivery claims, reply deduplication, signals and memory correction/deletion');
  const pausedCalls = modelCalls;
  await aio('aioControl', {changes: {paused: true}}, 'aio.state');
  const pausedDecision = await judgment('paused-decision');
  assert.equal(pausedDecision.decision.tasks.length, 0);
  assert.equal(modelCalls, pausedCalls);
  await aio('aioControl', {changes: {paused: false}}, 'aio.state');
  const recovery = (await judgment('recovery-decision', 'aio-recovery')).decision;
  await aio('aioTaskState', {taskId: recovery.tasks[0].id, state: 'running', revision: 1}, 'aio.task-state');
  await aio('aioMessageState', {messageId: recovery.message_id, state: 'displaying'}, 'aio.message-state');
  assert.equal((await aio('aioMemory', {}, 'aio.memory')).memories.length, 0);
  await close();
  await start();
  const recovered = (await aio('aioRecoverHost', {}, 'aio.state')).aio;
  assert.equal(recovered.uncertain_messages, 1);
  assert.equal(recovered.tasks.find(item => item.id === recovery.tasks[0].id).state, 'interrupted');
  assert.equal((await aio('aioMessages', {}, 'aio.messages')).messages.length, 0);
  assert.equal((await aio('aioPendingTasks', {}, 'aio.tasks')).tasks.length, 0);
  assert.equal((await aio('getSession', {sessionId: recovery.tasks[0].branch}, 'session')).session.messages[0].content, recovery.tasks[0].prompt);
  assert.equal((await aio('getSession', {sessionId: 'aio-mainline'}, 'session')).session.messages.at(-1).content, '恢复验证的完整发言\n保留第二行😀');
  assert.equal((await aio('aioMemory', {}, 'aio.memory')).memories.length, 0);
  await aio('aioControl', {changes: {enabled: false}}, 'aio.state');
  passed('AiO restart preserves full text and memory tombstones, marks interrupted work and uncertain delivery, and avoids automatic replay');
  assert.equal((await request('runPrompt', {sessionId: atlas, mode: 'ant', prompt: 'retired', noIndex: true})).type, 'error');
  passed('Retired mode fails explicitly');
  if (serverFailure) throw serverFailure;
  const report = {status: 'passed', executable, sha256: crypto.createHash('sha256').update(fs.readFileSync(executable)).digest('hex'),
    root, checks, model_calls: modelCalls, model: 'loopback protocol fixture', limitations: ['Fixture model verifies native tool execution and persistence; real model workflow quality is unverified.', 'Native desktop observation/execution, foreground actions and prolonged AiO endurance are unverified.']};
  fs.writeFileSync(path.join(root, 'report.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify(report));
} catch (error) {
  fs.writeFileSync(path.join(root, 'report.json'), JSON.stringify({status: 'failed', checks, error: String(error)}, null, 2) + '\n');
  throw error;
} finally {
  await close();
  server.closeAllConnections();
  await new Promise(resolve => server.close(resolve));
}
