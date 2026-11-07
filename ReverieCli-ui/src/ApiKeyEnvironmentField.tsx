import { type ReactNode, useEffect, useId, useState } from "react";
import { useI18n } from "./i18n";

export function ApiKeyEnvironmentField({ envName, update, validity, children, stored = false }: {
  envName: string;
  update: (name: string) => void;
  validity: (valid: boolean) => void;
  children: ReactNode;
  stored?: boolean;
}) {
  const { t } = useI18n();
  const listId = useId();
  const [environment, setEnvironment] = useState(Boolean(envName) && !stored);
  const [names, setNames] = useState<string[]>([]);
  useEffect(() => {
    validity(!environment || /^[A-Za-z_][A-Za-z0-9_]*$/.test(envName.trim()));
  }, [environment, envName, validity]);
  useEffect(() => {
    if (!environment) return;
    let active = true;
    void window.reverie.request("listApiKeyEnvironmentVariables", {}).then((response) => {
      if (active) setNames(Array.isArray(response.names) ? response.names : []);
    }).catch(() => { /* A variable name can still be entered manually. */ });
    return () => { active = false; };
  }, [environment]);
  return (
    <div className="api-key-environment-field">
      <button type="button" className="secondary-button small" onClick={() => {
        setEnvironment(!environment);
        update("");
      }}>{t(environment ? "手动输入密钥" : "使用环境变量")}</button>
      {environment ? <>
        <input aria-label={t("环境变量名称")} value={envName} onChange={(event) => update(event.target.value)}
          list={listId} placeholder="OPENAI_API_KEY" required pattern="[A-Za-z_][A-Za-z0-9_]*" autoComplete="off" spellCheck={false} />
        <datalist id={listId}>{names.map((name) => <option key={name} value={name} />)}</datalist>
        <small>{t("仅保存变量名，运行时读取密钥。新增环境变量后请重启 Reverie。")}</small>
      </> : children}
    </div>
  );
}
