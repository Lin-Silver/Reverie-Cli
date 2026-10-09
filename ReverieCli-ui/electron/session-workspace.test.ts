import { mkdtemp, readFile, rm, appendFile, writeFile, stat } from "node:fs/promises";
import path from "node:path";
import { tmpdir } from "node:os";
import { afterEach, expect, it } from "vitest";
import { RunJournal, saveActions, actions, saveGoal, loadGoal, goalInstructions, appendLog, readLogTail, LOG_FILE_BYTES, LOG_REPLAY_BYTES } from "./session-workspace";
const roots:string[]=[];
async function fixture(){const root=await mkdtemp(path.join(tmpdir(),"reverie-journal-"));roots.push(root);return root;}
afterEach(async()=>{for(const root of roots.splice(0)){if(!path.resolve(root).startsWith(path.resolve(tmpdir())+path.sep))throw new Error("Unsafe cleanup");await rm(root,{recursive:true,force:true});}});
it("recovers unfinished runs conservatively and exports ordered evidence without credentials",async()=>{const root=await fixture();const journal=new RunJournal();const record=await journal.start(root,"session",{prompt:"api_key=hidden-secret",authorization:"Bearer hidden-token"},"actual model");await journal.update(record.id,{state:"running"});journal.event(record.id,{type:"tool.start",command:"https://user:pass@example.invalid",args:{password:"private"}});journal.event(record.id,{type:"tool.end",exit_code:7});await journal.update(record.id,{});await appendFile(path.join(root,".reverie/desktop/runs",`${record.id}.json.jsonl`),'{"partial":');const rebooted=new RunJournal();const recovered=await rebooted.detail(root,record.id);expect(recovered.state).toBe("interrupted");expect(recovered.unknownEffects).toContain("never replays");expect(recovered.events?.map(value=>value.type)).toEqual(["tool.start","tool.end"]);const exported=await readFile(await rebooted.export(root,record.id),"utf8");expect(exported).not.toContain("hidden-secret");expect(exported).not.toContain("hidden-token");expect(exported).not.toContain("user:pass");expect(exported).not.toContain('"private"');expect(exported).toContain("[redacted]");});
it("persists explicit action configuration and user verification without executing commands",async()=>{const root=await fixture();const action={id:"initialize",name:"Initialize",command:"exit 7",cwd:".",envRefs:["TEST_TOKEN"],kind:"initialize" as const};await saveActions(root,[action]);expect(await actions(root)).toEqual([action]);await expect(saveActions(root,[{...action,cwd:"../outside"}])).rejects.toThrow("relative");await expect(saveActions(root,[{...action,envRefs:["TOKEN=value"]}])).rejects.toThrow("names");const goal={title:"Goal",conditions:"Real tests pass",steps:[{id:"step",text:"Test",state:"verified" as const,source:"user"}],validationCommands:"exit 0",revisions:[]};await saveGoal(root,"first",goal);expect(await loadGoal(root,"first")).toEqual(goal);expect(await loadGoal(root,"second")).toBeNull();});
it("loads the saved goal for its owner with explicit manual verification states",async()=>{
  const root=await fixture();const goal={title:"Fix actual bug",conditions:"Runtime must pass",steps:[{id:"one",text:"Run tests",state:"implemented" as const,source:"user"}],validationCommands:"npm test",revisions:[]};
  await saveGoal(root,"owner",goal);const text=goalInstructions(await loadGoal(root,"owner"));expect(text).toContain(goal.conditions);expect(text).toContain("[implemented] Run tests");expect(text).toContain("user-reported, not proof");expect(goalInstructions(await loadGoal(root,"other"))).toBe("");
});
it("rotates long and legacy logs and replays a bounded UTF-8 tail",async()=>{
  const root=await fixture();const log=path.join(root,"output.log");await writeFile(log,"旧记录 😀\n".repeat(1000000));
  await appendLog(log,"最新记录 😀\n".repeat(10000));expect((await stat(`${log}.previous`)).size).toBeLessThanOrEqual(LOG_FILE_BYTES);
  const tail=await readLogTail(log);expect(tail.truncated).toBe(true);expect(Buffer.byteLength(tail.text)).toBeLessThanOrEqual(LOG_REPLAY_BYTES);expect(tail.text).not.toContain("�");expect(tail.text).toContain("最新记录");
  await appendLog(log,"a".repeat(LOG_FILE_BYTES));await appendLog(log,"end\n");expect((await stat(log)).size).toBeLessThanOrEqual(LOG_FILE_BYTES);expect((await stat(`${log}.previous`)).size).toBeLessThanOrEqual(LOG_FILE_BYTES);
});
it("retains bounded complete journal events and marks oversized evidence explicitly",async()=>{
  const root=await fixture();const journal=new RunJournal();const record=await journal.start(root,"owner",{prompt:"test"},"model");
  for(let index=0;index<12;index++){journal.event(record.id,{type:"tool.end",index,content:"x".repeat(800000)});await journal.update(record.id,{});}
  journal.event(record.id,{type:"tool.end",content:"y".repeat(2*LOG_REPLAY_BYTES)});await journal.finish(record.id,{success:true},"completed");
  const detail=await journal.detail(root,record.id);expect(detail.logTruncated).toBe(true);expect(detail.events?.at(-1)?.type).toBe("run.event-truncated");expect(detail.events?.some(event=>event.type==="tool.end")).toBe(true);expect(Buffer.byteLength(JSON.stringify(detail.events))).toBeLessThanOrEqual(LOG_REPLAY_BYTES);
});
it("records burst loss explicitly without growing the pending disk queue",async()=>{
  const root=await fixture();const journal=new RunJournal();const record=await journal.start(root,"owner",{},"model");
  for(let index=0;index<50;index++)journal.event(record.id,{type:"tool.end",index,content:"x".repeat(800000)});
  await journal.finish(record.id,{success:true},"completed");const detail=await journal.detail(root,record.id);
  expect(detail.events?.at(-1)?.type).toBe("run.events-dropped");expect(detail.events?.at(-1)?.events).toBe(48);
  expect((await stat(path.join(root,".reverie/desktop/runs",`${record.id}.json.jsonl`))).size).toBeLessThan(2*LOG_REPLAY_BYTES);
});
it("keeps the first complete current event when only the previous log is omitted",async()=>{
  const root=await fixture();const file=path.join(root,"events.jsonl");const event=JSON.stringify({type:"first",body:"x".repeat(LOG_REPLAY_BYTES-Buffer.byteLength(JSON.stringify({type:"first",body:""})+"\n"))})+"\n";
  await writeFile(`${file}.previous`,"old\n");await writeFile(file,event);
  expect((await readLogTail(file,true)).text.startsWith('{"type":"first"')).toBe(true);
});
