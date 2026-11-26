export type DesktopCommand =
  | { kind: "setting"; key: string; value: string }
  | { kind: "review"; file: string; scope?: "working" | "staged" | "commit" | "branch" | "round"; base?: string }
  | { kind: "provider"; name: string }
  | { kind: "wstyle"; args: string }
  | { kind: "unsupported" };

export function desktopCommand(text: string): DesktopCommand | null {
  const wstyle = /^\/wstyle(?:\s+([\s\S]*))?$/i.exec(text);
  if (wstyle) return {kind:"wstyle",args:wstyle[1] || ""};
  const mode = /^\/mode\s+(\S+)\s*$/i.exec(text);
  if (mode) return {kind:"setting",key:"mode",value:mode[1]};
  const permission = /^\/permission\s+mode\s+(normal|strict|auto|full_access|default|auto_check)\s*$/i.exec(text);
  if (permission) return {kind:"setting",key:"permission_mode",value:({default:"normal",auto_check:"auto"} as Record<string,string>)[permission[1].toLowerCase()] ?? permission[1].toLowerCase()};
  const fallback = /^\/permission\s+fallback\s+(wait|deny)\s*$/i.exec(text);
  if (fallback) return {kind:"setting",key:"auto_review_fallback",value:fallback[1].toLowerCase()};
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
  return /^\/wstyle(?:\s|$)/.test(command) || /^\/(?:mode|permission|provider|review|compact|skills?|markets?|model|settings?|tools|rats|tasks|operations|plugins|checkpoints|rollback)$/.test(command);
}
