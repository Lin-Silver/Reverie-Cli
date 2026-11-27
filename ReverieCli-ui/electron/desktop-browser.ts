import { randomUUID } from "node:crypto";
import path from "node:path";
import { session, type BrowserWindow, type Rectangle } from "electron";
import { BrowserHost } from "./browser-host";
import type { HistoryAction } from "./browser-page";
import { BROWSER_PROTOCOL, browserActions } from "./browser-policy";
import type { CoreBridge } from "./core-bridge";
import type { BrowserHostRef, BrowserRequest } from "../src/generated/core-types";

type RecordData = Record<string,unknown>;
export interface PanelTab { id: string; title: string; url: string; canGoBack: boolean; canGoForward: boolean; busy: boolean }
export type BrowserPanelCommand = {operation:"list"|"hide"} | {operation:"show";tab:string;bounds:Rectangle} | {operation:"close"|HistoryAction;tab:string};

export function browserSession(profile: BrowserRequest["profile"]) {
  return session.fromPartition(profile.mode === "persistent" ? "persist:reverie-browser" : "reverie-browser-" + profile.profile_id);
}

export class DesktopBrowser {
  private host?: BrowserHost;
  private registering?: Promise<void>;
  private owners = new Map<string,string>();
  private running = new Set<string>();

  constructor(private parent: BrowserWindow, private core: CoreBridge, private log: (message:string) => void) {
    core.onBrowserDisconnect = () => {
      const host = this.host;
      this.host = undefined;
      core.onBrowserEvent = undefined;
      this.owners.clear();
      this.running.clear();
      void host?.dispose();
    };
  }

  async prepare(root: string, run: string) {
    await this.core.start();
    if (this.core.browserProtocol !== BROWSER_PROTOCOL) return;
    this.owners.set(run, path.resolve(root));
    this.running.add(run);
    if (!this.host) {
      this.registering ??= this.register().finally(() => { this.registering = undefined; });
      try { await this.registering; } catch (error) { this.finish(run,true); throw error; }
    }
  }

  private async register() {
    const core = this.core;
    const reply = await core.request("registerBrowserHost", {descriptor:{host_id:randomUUID(),engine:"Electron Chromium",engine_version:process.versions.chrome,actions:browserActions(core.browserActions),profile_modes:["persistent","ephemeral"]}});
    const ref = reply.host as BrowserHostRef, token = reply.token;
    const pid = core.getPid();
    const send = async (action:string, args:RecordData) => {
      if (this.host !== host || !pid || core.getPid() !== pid) return;
      await core.request(action, {...args,host:ref,token});
    };
    const host:BrowserHost = new BrowserHost({parent:this.parent,host:ref,resolveSession:(_scope,profile)=>browserSession(profile),
      onInvalidated: event => send("invalidateBrowserTab", {...event}),
      onChanged: () => { if (!this.parent.isDestroyed()) this.parent.webContents.send("core:event",{type:"browser.tabsChanged"}); },
    });
    this.host = host;
    core.onBrowserEvent = event => {
      if (event.type === "browser.cancel") { host.cancel(String(event.request_id)); return; }
      if (event.type !== "browser.request") return;
      const {type:_, ...request} = event;
      const input = request as unknown as BrowserRequest;
      if (!this.running.has(input.scope.run_id)) {
        const {action:_, ...identity} = input;
        void send("completeBrowserRequest",{completion:{...identity,outcome:{status:"failed",delivery:"not_started"}}}).catch(error => this.log(String(error)));
        return;
      }
      void host.receive(input)
        .then(completion => send("completeBrowserRequest",{completion})).catch(error => this.log(String(error)));
    };
  }

  finish(run:string, cancelled:boolean) {
    this.running.delete(run);
    const tabs = this.host?.state().tabs.filter(item => item.scope.run_id === run) ?? [];
    for (const item of tabs) if (cancelled || item.profile.mode === "ephemeral") this.host?.closeTab(item.tab.tab_id);
    if (!this.host?.state().tabs.some(item => item.scope.run_id === run)) this.owners.delete(run);
  }

  async panel(root:string, sessionId:string, command:BrowserPanelCommand):Promise<PanelTab[]> {
    const host = this.host;
    if (!host) return [];
    const owned = () => host.state().tabs.filter(item => item.scope.session_id === sessionId && this.owners.get(item.scope.run_id) === path.resolve(root));
    if (command.operation === "hide") host.setVisible(false);
    if ("tab" in command) {
      const tab = owned().find(item => item.tab.tab_id === command.tab);
      if (!tab) throw new Error("This tab belongs to another conversation or is already closed.");
      if (command.operation === "show") {
        const {x,y,width,height} = command.bounds;
        const [w,h] = this.parent.getContentSize();
        if (x + width > w || y + height > h) throw new Error("Browser panel is outside the window.");
        host.setBounds({x,y,width,height}); host.setVisible(true,command.tab);
      } else if (command.operation === "close") {
        host.closeTab(command.tab);
        if (!this.running.has(tab.scope.run_id) && !host.state().tabs.some(item => item.scope.run_id === tab.scope.run_id)) this.owners.delete(tab.scope.run_id);
      } else if (command.operation === "back" || command.operation === "forward" || command.operation === "reload") {
        await host.navigateTab(command.tab,command.operation);
      } else throw new Error("Unknown browser panel operation.");
    }
    return owned().map(({tab,canGoBack,canGoForward,busy,available,loading}) => ({id:tab.tab_id,title:tab.title,url:tab.url,canGoBack,canGoForward,busy:busy || !available || loading}));
  }
}
