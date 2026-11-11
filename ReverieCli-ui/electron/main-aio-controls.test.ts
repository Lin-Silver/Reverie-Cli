import { readFileSync } from 'node:fs';
import { expect,it,vi } from 'vitest';

// Exercise the actual host broadcast without starting an Electron application.
const source=readFileSync(new URL('./main.ts',import.meta.url),'utf8').replace(/\r\n/g,'\n');
const start=source.indexOf('if(changes &&');
const end=source.indexOf('\n  }\n  if (action === "initialize")',start);
if(start<0 || end<0)throw new Error('The AiO control broadcast could not be located.');
const broadcast=new Function('changes','executors','log',source.slice(start,end));

it.each([
  [{paused:true},'pausePrompt'],
  [{paused:false},'continuePrompt'],
  [{enabled:false},'stopPrompt'],
])('controls only explicit AiO owners for %j',(changes,control)=>{
  const ordinary=vi.fn().mockResolvedValue({});const assistant=vi.fn().mockResolvedValue({});
  const executors=new Map([
    ['ordinary',{sessionId:'aio-legacy-ordinary',root:'workspace',worker:{request:ordinary}}],
    ['assistant',{sessionId:'branch-without-a-prefix',assistantId:'aio',root:'workspace',worker:{request:assistant}}],
  ]);
  broadcast(changes,executors,vi.fn());
  expect(ordinary).not.toHaveBeenCalled();
  expect(assistant).toHaveBeenCalledWith(control,{projectRoot:'workspace',sessionId:'branch-without-a-prefix'});
});
