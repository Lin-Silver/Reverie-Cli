// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { SessionWorkbench } from "./SessionWorkbench";
import type { DesktopState } from "./types";

afterEach(()=>{cleanup();vi.unstubAllGlobals();});
const goal=(title:string)=>({title,conditions:"Actual tests pass",steps:[],validationCommands:"",revisions:[]});
const props={root:"C:/test",sessionId:"first",running:false,state:{workspace:{mode:"reverie"}} as DesktopState,onDraft:vi.fn(),onNavigate:vi.fn()};
function response(operation:string,title:string){return operation==="goal"?{goal:goal(title)}:operation==="terminals"?{terminals:[]}:operation==="actions"?{actions:[]}:operation==="runs"?{runs:[]}:{notifications:[],muted:false,supported:false};}

it("ignores a prior conversation refresh that resolves after the new owner",async()=>{
  let finish!:(value:unknown)=>void;
  const workbench=vi.fn((operation:string,payload:{sessionId:string})=>payload.sessionId==="first" && operation==="goal"?new Promise(resolve=>finish=resolve):Promise.resolve(response(operation,payload.sessionId)));
  Object.defineProperty(window,"reverie",{configurable:true,value:{workbench}});
  const mounted=render(<SessionWorkbench {...props}/>);
  fireEvent.click(screen.getByRole("button",{name:"目标与计划"}));
  await waitFor(()=>expect(workbench).toHaveBeenCalledTimes(5));
  mounted.rerender(<SessionWorkbench {...props} sessionId="second"/>);
  await waitFor(()=>expect((screen.getByRole("textbox",{name:"目标"}) as HTMLInputElement).value).toBe("second"));
  await act(async()=>finish({goal:goal("stale first")}));
  expect((screen.getByRole("textbox",{name:"目标"}) as HTMLInputElement).value).toBe("second");
});

it("does not overwrite an edited goal with a pending refresh",async()=>{
  let finish!:(value:unknown)=>void;let requests=0;
  const workbench=vi.fn((operation:string)=>operation==="goal" && requests++?new Promise(resolve=>finish=resolve):Promise.resolve(response(operation,"Saved")));
  Object.defineProperty(window,"reverie",{configurable:true,value:{workbench}});
  render(<SessionWorkbench {...props}/>);
  fireEvent.click(screen.getByRole("button",{name:"目标与计划"}));
  const field=await screen.findByRole("textbox",{name:"目标"});
  fireEvent.click(screen.getByRole("button",{name:"刷新"}));
  fireEvent.change(field,{target:{value:"Edited locally"}});
  await act(async()=>finish({goal:goal("Old server value")}));
  expect((field as HTMLInputElement).value).toBe("Edited locally");
});
