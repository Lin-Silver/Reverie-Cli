import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';

export async function verifyMotion({bridge, project, assets, appState, motionCalls, checks}) {
  let serial = 0;
  async function session(name, security) {
    const {session} = await bridge.request('createSession', {name});
    if (security) {
      const config = await bridge.request('getConversationConfig', {sessionId: session.id});
      const changed = await bridge.request('getConversationConfig', {sessionId: session.id, revision: config.revision,
        configuration: {...config.configuration, settings: {...config.configuration.settings, security}}});
      assert.notEqual(changed.type, 'error', JSON.stringify(changed));
    }
    return session.id;
  }
  function start(sessionId, name, args) {
    const runId = `motion-${++serial}`;
    const prompt = `Work on the page animation, step ${serial}.`;
    motionCalls.set(prompt, {name, args});
    const pending = bridge.request('runPrompt', {sessionId, runId, prompt, noIndex: true, stream: false}, 180000).then(reply => {
      assert.equal(reply.type, 'prompt.result');
      assert.equal(reply.result.success, true, JSON.stringify(reply.result).slice(0,1200));
      return JSON.parse(reply.result.output_text);
    });
    return {runId, pending};
  }
  function result(tool) {
    assert.equal(tool.success, true, JSON.stringify(tool).slice(-1800));
    assert.equal(tool.data.delivery, 'executed');
    const payload = JSON.parse(tool.data.stdout);
    assert.equal(payload.ok, true, JSON.stringify(payload));
    return payload.result;
  }
  const ordinary = await session('Bundled Motion');
  const lookup = async args => {
    const tool = await start(ordinary, 'skill_lookup', {skill_name:'reverie-motion', ...args}).pending;
    assert.equal(tool.success, true, JSON.stringify(tool));
    return JSON.parse(tool.output);
  };
  const body = await lookup({operation:'inspect', max_body_chars:20000});
  const pkg = path.join(assets, 'reverie-motion');
  assert.equal(body.scope, 'Built-in');
  assert.equal(body.complete, true);
  assert.equal(body.body, fs.readFileSync(path.join(pkg,'SKILL.md'),'utf8').replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/,'').trim());
  const guide = 'references/templates.md';
  const reference = await lookup({operation:'read_resource', resource_path:guide, max_body_chars:20000});
  assert.equal(reference.complete, true);
  assert.equal(reference.body, fs.readFileSync(path.join(pkg,guide),'utf8'));
  assert.equal(fs.realpathSync.native(body.runtime_entry),fs.realpathSync.native(path.join(pkg,'runtime/bin/reverie-motion.mjs')));
  assert(!fs.existsSync(path.join(project,'.agents/skills/reverie-motion/runtime')));
  checks.push('Model skill_lookup reads the original builtin Motion body and text reference with user and workspace shadows present');
  const command = suffix => `node "${body.runtime_entry}" ${suffix}`;
  const run = (id, suffix) => start(id,'command_exec',{command:command(suffix),timeout:150});
  for (const rejected of [
    `node "${path.join(pkg,'runtime/lib/cli.mjs')}" doctor`,
    `node --import "${body.runtime_entry}" version`,
    command('doctor --project ../outside'),
  ]) {
    const refusal = await start(ordinary,'command_exec',{command:rejected}).pending;
    assert.equal(refusal.success,false);
    assert.equal(refusal.data.delivery,'not_started');
  }
  fs.writeFileSync(path.join(project,'motion-input.json'),JSON.stringify({project:path.dirname(project),template:'spring-pop',id:'outside-attempt'}));
  const escaped = await run(ordinary,'design --input motion-input.json').pending;
  assert.equal(escaped.success,false);
  assert(!fs.existsSync(path.join(path.dirname(project),'.reverie-motion/specs/outside-attempt.json')));
  checks.push('Outside helper modules, Node options and traversal are blocked by native policy; JSON input retains workspace containment');
  const doctor = result(await run(ordinary, 'doctor --project . --launch').pending);
  assert(doctor.vendor.matchesProvenance && doctor.launch.ok && doctor.launch.version);
  fs.writeFileSync(path.join(project,'motion-input.json'),JSON.stringify({template:'stagger-list',id:'shop-products',params:{selector:'.product'}}));
  const design = result(await run(ordinary, 'design --project . --input motion-input.json').pending);
  assert.equal(design.revisionId, 'shop-products@1');
  const preview = result(await run(ordinary, 'preview --project . --spec shop-products@1 --viewport desktop').pending);
  assert(preview.passed, JSON.stringify(preview.findings));
  const evidence = JSON.parse(fs.readFileSync(path.join(project,preview.report),'utf8'));
  assert.equal(evidence.browser.version,preview.browser);
  if (process.env.REVERIE_MOTION_BROWSER) {
    assert.equal(fs.realpathSync.native(evidence.browser.executable),fs.realpathSync.native(process.env.REVERIE_MOTION_BROWSER));
  }
  const viewport = preview.viewports[0];
  assert(viewport.animations > 0 && viewport.frames.length > 1 && viewport.visual.motionEnergy > 0);
  assert.equal(viewport.reducedMotion.mediaMatched,true);
  const sheet = path.join(project,preview.evidenceDir,viewport.contactSheet);
  assert.deepEqual([...fs.readFileSync(sheet).subarray(0,8)],[137,80,78,71,13,10,26,10]);
  const exported = result(await run(ordinary, 'export --project . --spec shop-products@1 --targets css,waapi,dts').pending);
  assert.deepEqual(exported.written.map(w=>path.extname(w.file)).sort(),['.css','.js','.ts']);
  for (const {file,bytes} of exported.written) {assert(bytes>0);assert.equal(fs.statSync(path.join(project,file)).size,bytes);}
  checks.push('Actual command_exec doctor launch, design, real Chromium preview with motion frames and reduced motion, and CSS/WAAPI/types export');

  const strict = await session('Strict Motion',{permission_mode:'strict',permission_level:'workspace_write'});
  const strictDesign = 'design --project . --template spring-pop --id strict-pop';
  const strictSpec = path.join(project,'.reverie-motion/specs/strict-pop.json');
  const approvals = id => bridge.events.filter(item=>item.event?.run_id===id && item.event.type==='approval.request').map(item=>item.event);
  async function resolve(task, decision) {
    const deadline = Date.now()+15000;
    while (!approvals(task.runId).length && Date.now()<deadline) await delay(20);
    const [approval] = approvals(task.runId);
    assert.equal(approval?.tool,'command_exec');
    assert(!fs.existsSync(strictSpec));
    await bridge.request('resolveApproval',{runId:task.runId,approvalId:approval.approval_id,decision});
    return task.pending;
  }
  const denied = run(strict,strictDesign);
  assert.equal((await resolve(denied,'deny')).success,false);
  assert(!fs.existsSync(strictSpec));
  const allowed = run(strict,strictDesign);
  result(await resolve(allowed,'session'));
  assert(fs.existsSync(strictSpec));
  const reuse = run(strict,'export --project . --spec strict-pop --targets css');
  result(await reuse.pending);
  assert.equal(approvals(reuse.runId).length,0);
  assert(fs.statSync(path.join(project,'src/motion/strict-pop.motion.css')).size>0);
  const readonly = await session('Read-only Motion',{permission_mode:'default',permission_level:'read_only'});
  const blocked = run(readonly,'design --project . --template spring-pop --id readonly-pop');
  assert.equal((await blocked.pending).data.delivery,'not_started');
  assert(!fs.existsSync(path.join(project,'.reverie-motion/specs/readonly-pop.json')));
  checks.push('Strict refusal has no side effects, a session grant executes and covers a second command, and read_only denies before launch');
  const auditPath = path.join(appState.workspace.project_data_dir,'security/command_audit.jsonl');
  const audit = fs.readFileSync(auditPath,'utf8').trim().split('\n').map(line=>JSON.parse(line));
  for (const task of [denied,blocked]) assert(audit.some(row=>row.event==='command_blocked'&&row.run_id===task.runId&&row.delivery==='not_started'));
  for (const suffix of ['doctor','design','preview','export']) {
    assert(audit.some(row=>row.event==='command_attempt'&&row.executor==='builtin_motion'&&row.command.includes(`" ${suffix} `)));
    assert(audit.some(row=>row.event==='command_result'&&row.delivery==='executed'&&row.command.includes(`" ${suffix} `)));
  }
  checks.push('Command audit records all four actual operations and both pre-launch denials');
  return {browser:preview.browser, revision:design.revisionId, report:path.join(project,preview.report), contactSheet:sheet,
    exports:exported.written, audit:auditPath, frames:viewport.frames.length};
}
