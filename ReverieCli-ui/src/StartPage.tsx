import { ArrowUpRight, Code2, FileText, Folder, ShieldCheck, Wrench } from "lucide-react";
import { useI18n } from "./i18n";

const REVERIE_MARK_URL = new URL("reverie-mark.png", document.baseURI).href;
const STARTERS = [
  { icon: Code2, title: "理解代码库", description: "从架构到关键细节", prompt: "分析这个项目的架构、入口和关键模块，并指出最值得关注的技术风险。" },
  { icon: Wrench, title: "实现功能", description: "让想法成为可用的功能", prompt: "检查当前工作区，提出并实现一个最有价值且范围明确的改进，完成后运行验证。" },
  { icon: ShieldCheck, title: "审查变更", description: "发现问题，放心交付", prompt: "审查当前未提交的改动，重点找出正确性、安全性和回归风险。" },
  { icon: FileText, title: "整理文档", description: "把知识整理得更清楚", prompt: "检查项目文档与实现是否一致，并修复最重要的文档缺口。" },
] as const;

export function WelcomeHeader({ workspace }: { workspace: string }) {
  const { t } = useI18n();
  return (
    <section className="welcome-header" aria-labelledby="welcome-title">
      <div className="welcome-copy">
        <div className="welcome-workspace"><Folder size={14} /><span>{workspace || t("工作区")}</span></div>
        <h1 id="welcome-title">{t("从一个想法开始。")}</h1>
        <p>{t("与 Reverie 一起，把想法变成下一步。")}</p>
      </div>
      <div className="welcome-art" aria-hidden="true">
        <img src={REVERIE_MARK_URL} alt="" />
        <span>Reverie</span>
      </div>
    </section>
  );
}

export function StarterActions({ choose }: { choose: (prompt: string) => void }) {
  const { t } = useI18n();
  return (
    <nav className="starter-actions" aria-label={t("从这里开始")}>
      {STARTERS.map(({ icon: Icon, title, description, prompt }) => (
        <button type="button" key={title} onClick={() => choose(t(prompt))}>
          <div className="starter-heading"><Icon size={17} /><strong>{t(title)}</strong><ArrowUpRight size={13} /></div>
          <span>{t(description)}</span>
        </button>
      ))}
    </nav>
  );
}
