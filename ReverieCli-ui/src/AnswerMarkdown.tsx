import { Children, isValidElement, memo, createContext, useContext, type ReactNode } from "react";
import ReactMarkdown, { defaultUrlTransform, type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { parseFileLink } from "./file-links";
import { parseAnswerBlock, answerExternalUrl } from "./answer-blocks";
import { AnswerExternalLink, AnswerImage, RichAnswer } from "./RichAnswer";
import { useI18n } from "./i18n";
import "./answer-markdown.css";

const isFile = (href: string) => !/^[a-z][a-z\d+.-]*:/i.test(href) || /^(?:file:\/\/|[a-z]:[\\/])/i.test(href);

const AnswerStreamingContext = createContext(false);

const components: Components = {
      a: ({ href, children: linkChildren }) => {
        if (href && answerExternalUrl(href)) return <AnswerExternalLink url={href}>{linkChildren}</AnswerExternalLink>;
        const file = href && isFile(href) ? parseFileLink(href) : null;
        if (!file) return <span>{linkChildren}</span>;
        return <a href={href} onClick={event => { event.preventDefault(); window.dispatchEvent(new CustomEvent("reverie:file-open", { detail: file })); }}>{linkChildren}</a>;
      },
      img: ({ src, alt }) => <AnswerImage url={src || ""} alt={alt || ""} />,
      table: function AnswerTable({ children: tableChildren }) {
        const { t } = useI18n();
        return <div className="answer-table-scroll" role="region" aria-label={t("表格")} tabIndex={0}><table>{tableChildren}</table></div>;
      },
      th: ({ children: heading, ...props }) => <th style={props.style} scope="col">{heading}</th>,
      pre: function AnswerPre({ children: codeChildren }) {
        const streaming = useContext(AnswerStreamingContext);
        const { t } = useI18n();
        const elements = Children.toArray(codeChildren);
        const code = elements.length === 1 && isValidElement<{ className?: string; children?: ReactNode }>(elements[0]) ? elements[0] : null;
        if (code?.props.className === "language-reverie-ui" && typeof code.props.children === "string") {
          const block = parseAnswerBlock(code.props.children);
          if (block) return <RichAnswer block={block} />;
          if (streaming) return <p className="answer-block-pending" role="status">{t("正在整理内容…")}</p>;
          return <div className="answer-block-fallback"><p>{t("此内容暂时无法排版，原始内容已保留。")}</p><pre>{codeChildren}</pre></div>;
        }
        return <pre>{codeChildren}</pre>;
      },
};

export const AnswerMarkdown = memo(function AnswerMarkdown({ children, streaming = false }: { children: string; streaming?: boolean }) {
  return <AnswerStreamingContext.Provider value={streaming}><div className="markdown answer-markdown"><ReactMarkdown remarkPlugins={[remarkGfm]}
    urlTransform={value => isFile(value) ? value : defaultUrlTransform(value)}
    components={components}>{children}</ReactMarkdown></div></AnswerStreamingContext.Provider>;
});
