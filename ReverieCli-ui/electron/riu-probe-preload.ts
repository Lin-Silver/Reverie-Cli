import { contextBridge, ipcRenderer } from "electron";

/**
 * Preload for the isolation-probe page only. It exposes a command/result pair and nothing
 * else: the probe window never receives the production `core:*` surface. Electron does not
 * run a preload in sub-frames unless `nodeIntegrationInSubFrames` is set, so a view frame
 * sees none of this — which the probe then verifies from inside the frame.
 */
contextBridge.exposeInMainWorld("riuProbe", {
  onCommand: (handler: (command: { id: string; name: string; args?: Record<string, unknown> }) => void) => {
    ipcRenderer.on("riu-probe:command", (_event, command) => handler(command));
  },
  reply: (id: string, value: unknown) => ipcRenderer.send("riu-probe:result", { id, value }),
  failed: (id: string, message: string) => ipcRenderer.send("riu-probe:result", { id, error: message }),
});
