// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { Workbench } from "./Workbench";
import { ViewPresentationProvider, useViewPresentation } from "./ViewPresentation";

afterEach(()=>cleanup());
const snapshot={root:"C:/project",version:"captured-version",indexVersion:"index",head:"head",branch:"main",scope:"working",base:"",conflicts:[],files:[{path:"src/bug.ts",status:"M",binary:false,additions:1,deletions:1}]};
const props={root:"C:/project",sessionId:"first",running:false,onDraft:vi.fn(),onReview:vi.fn(async()=>"not JSON")};
function reply(operation:string){return operation==="list-directory"?{directory:".",entries:[],truncated:false}:operation==="reviews"?{reviews:[]}:operation==="runs"?{runs:[]}:snapshot;}

function ViewModeButtons(){const view=useViewPresentation();return <><button onClick={()=>view.select("view","View","fullscreen")}>test-fullscreen</button><button onClick={()=>view.select("view","View","inline")}>test-inline</button></>;}
it("restores the prior panel on inline return and respects an explicit tab or close",async()=>{
  Object.defineProperty(window,"reverie",{configurable:true,value:{workbench:vi.fn(async(operation:string)=>reply(operation))}});
  const {container}=render(<ViewPresentationProvider><ViewModeButtons/><Workbench {...props}/></ViewPresentationProvider>);
  fireEvent.click(screen.getByRole("button",{name:"test-fullscreen"}));
  await waitFor(()=>expect(container.querySelector(".workbench-panel")?.getAttribute("aria-hidden")).toBeNull());
  fireEvent.click(screen.getByRole("button",{name:"test-inline"}));
  await waitFor(()=>expect(container.querySelector(".workbench-panel")?.getAttribute("aria-hidden")).toBe("true"));
  fireEvent.click(screen.getByRole("button",{name:"工作面板"}));
  fireEvent.click(screen.getByRole("button",{name:"文件"}));
  fireEvent.click(screen.getByRole("button",{name:"test-fullscreen"}));
  fireEvent.click(screen.getByRole("button",{name:"test-inline"}));
  await waitFor(()=>expect(screen.getByRole("button",{name:"文件"}).getAttribute("aria-pressed")).toBe("true"));
  fireEvent.click(screen.getByRole("button",{name:"test-fullscreen"}));
  fireEvent.click(screen.getByRole("button",{name:"Git 改动"}));
  await waitFor(()=>expect(screen.getByRole("button",{name:"Git 改动"}).getAttribute("aria-pressed")).toBe("true"));
  fireEvent.click(screen.getByRole("button",{name:"test-fullscreen"}));
  fireEvent.click(screen.getByRole("button",{name:"收起右侧栏"}));
  await waitFor(()=>expect(container.querySelector(".workbench-panel")?.getAttribute("aria-hidden")).toBe("true"));
});

it("does not replace the current checkout with a prior owner's Git response",async()=>{
  let finish!:(value:unknown)=>void;
  const workbench=vi.fn((operation:string,payload:{sessionId:string})=>operation==="snapshot" && payload.sessionId==="first"?new Promise(resolve=>finish=resolve):Promise.resolve(operation==="snapshot"?{...snapshot,files:[]}:reply(operation)));
  Object.defineProperty(window,"reverie",{configurable:true,value:{workbench}});
  const mounted=render(<Workbench {...props}/>);fireEvent.click(screen.getByRole("button",{name:"工作面板"}));
  await waitFor(()=>expect(finish).toBeTypeOf("function"));mounted.rerender(<Workbench {...props} sessionId="second"/>);
  await screen.findByText("没有改动");await act(async()=>finish(snapshot));expect(screen.queryByText("src/bug.ts")).toBeNull();expect(screen.queryByRole("alert")).toBeNull();
});

it("does not show a stale file preview after switching conversations",async()=>{
  let finish!:(value:unknown)=>void;
  const workbench=vi.fn((operation:string)=>operation==="preview"?new Promise(resolve=>finish=resolve):Promise.resolve(reply(operation)));
  Object.defineProperty(window,"reverie",{configurable:true,value:{workbench}});
  const mounted=render(<Workbench {...props}/>);
  act(()=>window.dispatchEvent(new CustomEvent("reverie:file-open",{detail:{path:"first.txt"}})));
  await waitFor(()=>expect(finish).toBeTypeOf("function"));mounted.rerender(<Workbench {...props} sessionId="second"/>);
  await act(async()=>finish({path:"C:/project/first.txt",relativePath:"first.txt",kind:"text",text:"Old owner content",version:"old",offset:0,next:null,size:17,totalLines:1,modifiedAt:"now"}));
  expect(screen.queryByText("Old owner content")).toBeNull();expect(screen.queryByRole("alert")).toBeNull();
});

it("shows invalid review output as an error and preserves it in the saved record",async()=>{
  const workbench=vi.fn(async(operation:string)=>operation==="patch"?{path:"src/bug.ts",version:snapshot.version,text:"@@ -10,1 +10,1 @@\n-old\n+new",offset:0,next:null,totalLines:3,hunks:[],binary:false}:reply(operation));
  Object.defineProperty(window,"reverie",{configurable:true,value:{workbench}});
  render(<Workbench {...props}/>);act(()=>window.dispatchEvent(new CustomEvent("reverie:workbench",{detail:{tab:"review"}})));
  await waitFor(()=>expect((screen.getByRole("button",{name:"开始只读审查"}) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole("button",{name:"开始只读审查"}));
  await screen.findByText("审查输出格式无效，请查看原文或重新审查");expect(screen.getByText("not JSON")).toBeTruthy();
  expect(workbench).toHaveBeenCalledWith("save-reviews",expect.objectContaining({reviews:[expect.objectContaining({output:"not JSON",formatError:expect.any(String),findings:[]})]}));
});
