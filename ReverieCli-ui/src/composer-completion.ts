import type { CommandRecord, SkillRecord } from "./types";
import { desktopCommandAvailable } from "./desktop-commands";

export type ComposerToken = { kind: "mention" | "command" | "skill"; query: string; start: number; end: number };
export type CompletionOption = { id: string; kind: "file" | "command" | "skill" | "skills"; label: string; description: string; value: string; disabled?: boolean; badge?: string };

export function composerToken(value: string, caret: number): ComposerToken | null {
  const before = value.slice(0, caret);
  const mention = /(?:^|\s)@([^\s@]*)$/.exec(before);
  if (mention) return { kind: "mention", query: mention[1], start: caret - mention[1].length - 1, end: caret };
  const skill = /^\s*\/skills?\s+(?:pin\s+|use\s+|add\s+)?([^\n]*)$/i.exec(before);
  if (skill) return { kind: "skill", query: skill[1].replace(/^\$/, ""), start: value.indexOf("/"), end: caret };
  const command = /^\s*\/([^\s/]*)$/.exec(before);
  return command ? { kind: "command", query: command[1], start: value.indexOf("/"), end: caret } : null;
}

export function slashOptions(token: ComposerToken, commands: CommandRecord[], skills: SkillRecord[], full: boolean, translate: (key: string) => string): CompletionOption[] {
  const query = token.query.trim().toLocaleLowerCase();
  const matches = (...values: string[]) => values.some(value => value.toLocaleLowerCase().includes(query));
  const skillOptions: CompletionOption[] = skills.filter(skill => !skill.shadowed && matches(skill.name, skill.description)).map(skill => ({
    id: `skill:${skill.key}`, kind: "skill", label: skill.name, description: skill.description, value: skill.name,
    disabled: skill.pinned || full, badge: translate(skill.pinned ? "已固定" : full ? "固定数量已满" : "必须使用"),
  }));
  if (token.kind === "skill") return skillOptions;
  const options: CompletionOption[] = [];
  if (matches("skill", "skills", translate("选择必须使用的 Skill"))) options.push({ id: "skills", kind: "skills", label: "/skill", description: translate("选择必须使用的 Skill"), value: "/skill " });
  options.push(...commands.filter(command => !/^\/skills?$/i.test(command.command) && matches(command.command, translate(command.summary), ...(command.aliases ?? []))).map(command => ({
    id: `command:${command.id}`, kind: "command" as const, label: command.command, description: translate(command.summary), value: command.command + " ", badge: desktopCommandAvailable(command.command) ? undefined : translate("终端参考"),
  })));
  if (query) options.push(...skillOptions);
  return options;
}
