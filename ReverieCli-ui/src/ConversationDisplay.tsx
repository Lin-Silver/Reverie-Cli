import { useState } from "react";
import { Brain, Eye, Maximize2, MessageSquare, Minimize2, PictureInPicture2 } from "lucide-react";
import { FloatingMenu } from "./FloatingMenu";
import { useI18n } from "./i18n";
import type { UiPreferences } from "./preferences";
import type { ViewDisplayMode } from "./ViewPresentation";

/** Card and carousel are content layouts; only these three values cross the bridge. */
export function ViewDisplayControls({ mode, change }: { mode: ViewDisplayMode; change: (mode: ViewDisplayMode) => void }) {
  const { t } = useI18n();
  return <span className="view-display-controls" role="group" aria-label={t("视图展示位置")}>
    {([ ["inline", "返回对话内", Minimize2, "对话内"], ["fullscreen", "在工作面板中放大", Maximize2, "工作面板"], ["pip", "画中画", PictureInPicture2, "画中画"] ] as const).map(([value, label, Icon, currentLabel]) =>
      <button key={value} type="button" className="ghost-button" data-view-mode={value} aria-label={t(label)} title={t(label)} aria-pressed={mode === value} onClick={() => change(value)}><Icon size={14} aria-hidden="true" />{mode === value && <span aria-hidden="true">{t(currentLabel)}</span>}</button>)}
  </span>;
}

type Props = { preferences: UiPreferences; update: (patch: Partial<UiPreferences>) => void };
const presets = [
  { id: "all", label: "全部内容", description: "显示思考、回复、工具调用和结果", reasoning: true, tools: true },
  { id: "reasoning", label: "思考与回复", description: "保留思考和正文，隐藏工具调用与结果", reasoning: true, tools: false },
  { id: "reply", label: "仅模型回复", description: "只显示用户消息和模型正文", reasoning: false, tools: false },
] as const;
export function displayPreset(preferences: UiPreferences) {
  return presets.find(preset => preferences.showReasoning === preset.reasoning && preferences.showToolCalls === preset.tools && preferences.showToolResults === preset.tools)?.id || "custom";
}
export function DisplayPresets({ preferences, update }: Props) {
  const { t } = useI18n();
  return <div className="preset-grid display-presets">{presets.map(preset => <button type="button" key={preset.id} className={displayPreset(preferences) === preset.id ? "active" : ""} aria-pressed={displayPreset(preferences) === preset.id} onClick={() => update({ showReasoning: preset.reasoning, expandReasoning: preset.reasoning, showToolCalls: preset.tools, showToolResults: preset.tools, showLiveActivity: preset.tools })}>
    {preset.id === "reasoning" ? <Brain size={16} /> : preset.id === "reply" ? <MessageSquare size={16} /> : <Eye size={16} />}<strong>{t(preset.label)}</strong><span>{t(preset.description)}</span>
  </button>)}</div>;
}
export function DisplayOptions({ preferences, update }: Props) {
  const { t } = useI18n();
  return <div className="display-options">{([
    ["showReasoning", "推理记录"], ["showToolCalls", "工具调用"], ["showToolResults", "工具结果"], ["showLiveActivity", "实时活动"],
  ] as const).map(([key, label]) => <label key={key}><span>{t(label)}</span><button type="button" role="switch" aria-label={t(label)} aria-checked={preferences[key]} className={`toggle ${preferences[key] ? "on" : ""}`} onClick={() => update({ [key]: !preferences[key], ...(key === "showReasoning" && !preferences[key] ? { expandReasoning: true } : {}) })}><span /></button></label>)}</div>;
}
export function ConversationDisplay({ preferences, update }: Props) {
  const { t } = useI18n(); const [open, setOpen] = useState(false);
  const selected = presets.find(preset => preset.id === displayPreset(preferences));
  return <div className="conversation-display-control"><button type="button" className="conversation-display-button" aria-label={t("对话内容显示")} aria-expanded={open} onClick={() => setOpen(!open)}><Eye size={14} /><span>{t(selected?.label || "自定义显示")}</span></button>
    {open && <FloatingMenu label={t("对话内容显示")} className="conversation-display-menu" close={() => setOpen(false)}><strong>{t("对话内容显示")}</strong><DisplayPresets preferences={preferences} update={update} /><DisplayOptions preferences={preferences} update={update} /><p>{t("只改变页面显示，完整记录仍保存在会话中。")}</p></FloatingMenu>}
  </div>;
}
