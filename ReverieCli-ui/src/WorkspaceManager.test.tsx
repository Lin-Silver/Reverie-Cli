// @vitest-environment jsdom
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { WorkspaceManager } from "./WorkspaceManager";

afterEach(()=>cleanup());
it("ignores stale worktree and executor responses after switching the owner",async()=>{
  let finish!:(value:unknown)=>void;
  const workbench=vi.fn((operation:string,payload:{sessionId:string})=>operation==="worktrees" && payload.sessionId==="first"?new Promise(resolve=>finish=resolve):Promise.resolve(operation==="worktrees"?{worktrees:[]}:{entries:[]}));
  Object.defineProperty(window,"reverie",{configurable:true,value:{workbench}});
  const props={root:"C:/project",sessionId:"first",onNavigate:vi.fn()};const mounted=render(<WorkspaceManager {...props}/>);
  await waitFor(()=>expect(workbench).toHaveBeenCalledTimes(2));mounted.rerender(<WorkspaceManager {...props} sessionId="second"/>);
  await waitFor(()=>expect(workbench).toHaveBeenCalledTimes(4));
  await act(async()=>finish({worktrees:[{id:"stale",name:"Old owner workspace",state:"archived",path:"C:/old"}]}));
  expect(screen.queryByText(/Old owner workspace/)).toBeNull();
});
