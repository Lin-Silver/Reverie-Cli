export type DesktopCommand =
  | { kind: "setting"; key: string; value: string }
  | { kind: "review"; file: string; scope?: "working" | "staged" | "commit" | "branch" | "round"; base?: string }
  | { kind: "provider"; name: string }
  | { kind: "unsupported" };

export function desktopCommand(text: string): DesktopCommand | null {
  const mode = /^\/mode\s+(\S+)\s*$/i.exec(text);
  if (mode) return {kind:"setting",key:"mode",value:mode[1]};
  const permission = /^\/permission\s+mode\s+(default|auto_check|strict)\s*$/i.exec(text);
  if (permission) return {kind:"setting",key:"permission_mode",value:permission[1].toLowerCase()};
  const provider = /^\/provider(?:\s+(list|status))?\s*$/i.exec(text);
  if (provider) return {kind:"provider",name:provider[1] || ""};
  const review = /^\/review(?:\s+([\s\S]+))?$/i.exec(text);
  if (review) {
    const args = (review[1] || "").match(/"[^"]*"|'[^']*'|\S+/g) || [];
    const result:Extract<DesktopCommand,{kind:"review"}> = {kind:"review",file:""};
    for (let i=0;i<args.length;i++) {
      const value=args[i].replace(/^["']|["']$/g, "");
      if (value === "--scope") {
        const scope=args[++i];
        if (!["working","staged","commit","branch","round"].includes(scope)) return {kind:"unsupported"};
        result.scope=scope as typeof result.scope;
      } else if (value === "--base") {
        if (!args[i+1]) return {kind:"unsupported"};
        result.base=args[++i].replace(/^["']|["']$/g, "");
      } else if (!result.file && !value.startsWith("--")) result.file=value;
      else return {kind:"unsupported"};
    }
    return result;
  }
  return null;
}

export function desktopCommandAvailable(command:string):boolean {
  return /^\/(?:mode|permission|provider|review|compact|skills?|model|settings?|tools|rats|tasks|operations|plugins|checkpoints|rollback)$/.test(command);
}
