import { app, BrowserWindow } from "electron";
import { mkdirSync } from "node:fs";
import { randomUUID } from "node:crypto";
import path from "node:path";
import { createInterface } from "node:readline";
import { connect } from "node:net";
import { once } from "node:events";
import { BrowserHost } from "./browser-host";
import { browserSession } from "./desktop-browser";
import { BROWSER_PROTOCOL, browserActions } from "./browser-policy";
import type { BrowserRequest } from "../src/generated/core-types";

const directory = process.env.REVERIE_BROWSER_DATA;
const port = Number(process.env.REVERIE_BROWSER_PORT), token = process.env.REVERIE_BROWSER_TOKEN;
const actions = browserActions(JSON.parse(process.env.REVERIE_BROWSER_ACTIONS ?? "null"));
delete process.env.REVERIE_BROWSER_TOKEN;
delete process.env.REVERIE_BROWSER_PORT;
delete process.env.REVERIE_BROWSER_ACTIONS;
if (!Number.isInteger(port) || port<1 || port>65535 || !token || !/^[a-f0-9]{32}$/.test(token)) throw new Error("Missing browser component channel.");
if (!directory || !path.isAbsolute(directory)) throw new Error("Browser component requires a profile directory.");
mkdirSync(directory,{recursive:true});
app.setPath("userData",directory);
const ownsProfile = app.requestSingleInstanceLock();
if (!ownsProfile) app.quit();

if (ownsProfile) void app.whenReady().then(async () => {
  const id = randomUUID();
  const channel = connect(port,"127.0.0.1");
  await once(channel,"connect");
  const send = (message:unknown) => new Promise<void>((resolve,reject) => {
    channel.write(JSON.stringify(message)+"\n",error => error ? reject(error) : resolve());
  });
  const lines = createInterface({input:channel,crlfDelay:Infinity});
  const records = lines[Symbol.asyncIterator]();
  channel.on("error",()=>lines.close());
  channel.write(token);
  const window = new BrowserWindow({title:"Chrome in Reverie",width:1000,height:740,show:false,autoHideMenuBar:true,webPreferences:{sandbox:true,contextIsolation:true,nodeIntegration:false}});
  let host:BrowserHost | undefined;
  window.on("resize",() => {
    const [width,height] = window.getContentSize();
    if (width>0 && height>0) host?.setBounds({x:0,y:0,width,height});
  });
  window.once("closed",() => lines.close());
  try {
    await send({protocol:BROWSER_PROTOCOL,descriptor:{host_id:id,engine:"Electron Chromium",engine_version:process.versions.chrome,actions,profile_modes:["persistent","ephemeral"]}});
    for await (const line of records) {
      const event = JSON.parse(line);
      if (event.type === "browser.attach" && !host && event.host?.host_id === id) {
        host = new BrowserHost({parent:window,host:event.host,resolveSession:(_scope,profile)=>browserSession(profile),
          onInvalidated:invalidation=>send({type:"invalidate",invalidation}),onChanged:()=>{}});
        host.setVisible(true);
      } else if (host && event.type === "browser.request") {
        const {type:_,...request} = event;
        if (request.action.action === "open") window.show();
        const active = host;
        void active.receive(request as BrowserRequest).then(completion => {
          if (completion.outcome.status === "completed" && completion.outcome.result.type === "opened") {
            active.setVisible(true,completion.outcome.result.tab.tab_id);
          }
          return send({type:"complete",completion});
        }).catch(()=>lines.close());
      } else if (host && event.type === "browser.cancel") {
        host.cancel(event.request_id);
      } else { throw new Error("Unsupported browser component message."); }
    }
  } finally {
    lines.close(); await host?.dispose(); channel.destroy();
    if (!window.isDestroyed()) window.destroy();
    app.quit();
  }
}).catch(()=>app.exit(1));
