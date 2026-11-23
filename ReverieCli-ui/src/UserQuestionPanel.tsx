import { useEffect, useState } from "react";
import { useI18n } from "./i18n";
import type { UserQuestion } from "./generated/core-types";
import "./user-question.css";

export type UserInputRequest = UserQuestion & {
  project_root: string;
  session_id: string;
  run_id: string;
};
export type UserQuestionDraft = { selected: number[]; custom: boolean; text: string };

export function UserQuestionPanel({ question, resolve, drafts }: {
  question: UserInputRequest;
  resolve: (answer: string | undefined, cancelled: boolean) => Promise<void>;
  drafts?: Map<string, UserQuestionDraft>;
}) {
  const { t } = useI18n();
  const saved = drafts?.get(question.question_id);
  const [selected, setSelected] = useState<number[]>(saved?.selected ?? []);
  const [custom, setCustom] = useState(saved?.custom ?? question.options.length === 0);
  const [text, setText] = useState(saved?.text ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { drafts?.set(question.question_id,{selected,custom,text}); }, [drafts,question.question_id,selected,custom,text]);
  const answer = custom ? text : selected.map(index => question.options[index]).join("\n");
  const submit = async (cancelled = false) => {
    if (submitting || !cancelled && !answer.trim()) return;
    setSubmitting(true);
    setError("");
    try { await resolve(cancelled ? undefined : answer, cancelled); drafts?.delete(question.question_id); }
    catch (error) { setError(error instanceof Error ? error.message : String(error)); }
    finally { setSubmitting(false); }
  };
  return <form className="approval-panel user-question-panel" aria-label={t("Reverie 需要回答")} onSubmit={event => { event.preventDefault(); void submit(); }}>
    <h3>{question.question}</h3>
    <div className="user-question-options" role={question.multiple ? "group" : "radiogroup"} aria-label={question.question}>
      {question.options.map((option, index) => <label key={index}>
        <input type={question.multiple ? "checkbox" : "radio"} name={`question-${question.question_id}`} checked={!custom && selected.includes(index)} disabled={submitting} onChange={() => {
          setCustom(false);
          setSelected(current => question.multiple ? current.includes(index) ? current.filter(item => item !== index) : [...current, index].sort((a,b) => a-b) : [index]);
        }} />
        <span>{index + 1}. {option}</span>
      </label>)}
      <label>
        <input type="radio" name={`question-${question.question_id}`} checked={custom} disabled={submitting} onChange={() => { setCustom(true); setSelected([]); }} />
        <span>{question.options.length + 1}. {t("自定义回答")}</span>
      </label>
    </div>
    {custom && <textarea aria-label={t("自定义回答")} rows={3} value={text} disabled={submitting} onChange={event => setText(event.target.value)} autoFocus />}
    {error && <div className="composer-error" role="alert">{error}</div>}
    <div className="approval-actions">
      <button type="button" className="secondary-button" disabled={submitting} onClick={() => void submit(true)}>{t("取消询问")}</button>
      <button type="submit" className="primary-button" disabled={submitting || !answer.trim()}>{t(submitting ? "正在提交回答…" : "提交回答")}</button>
    </div>
  </form>;
}
