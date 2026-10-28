import { useId, useState, type ReactNode } from "react";
import { ArrowUpRight, Globe, ImageOff } from "lucide-react";
import { answerExternalUrl, answerImageUrl, isAnswerNumericText, type AnswerBadge, type AnswerBlock, type AnswerCell, type AnswerLink } from "./answer-blocks";
import { useI18n } from "./i18n";

export function AnswerExternalLink({ url, children, className }: { url: string; children: ReactNode; className?: string }) {
  const href = answerExternalUrl(url);
  if (!href) return <span className={className}>{children}</span>;
  return <a href={href} className={className} rel="noreferrer noopener" onClick={event => {
    event.preventDefault();
    void window.reverie.openExternal(href);
  }}>{children}<ArrowUpRight size={13} aria-hidden="true" /></a>;
}

function Badge({ value }: { value: AnswerBadge }) {
  return <span className={`answer-badge answer-badge-${value.tone || "neutral"}`}>{value.text}</span>;
}

function Cell({ value }: { value: AnswerCell }) {
  const { t } = useI18n();
  if (isAnswerNumericText(value)) return <span className="answer-number">{value.text}</span>;
  if (typeof value === "object" && value !== null) return <Badge value={value} />;
  return value === null ? <span className="answer-empty">—</span> : typeof value === "boolean" ? t(value ? "是" : "否") : String(value);
}

export function AnswerImage({ url, alt, className = "" }: { url: string; alt: string; className?: string }) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const { t } = useI18n();
  const src = answerImageUrl(url);
  if (!src || failedUrl === src) return <span className={`answer-image-fallback ${className}`} role="img" aria-label={alt || t("图片无法显示")}><ImageOff size={22} aria-hidden="true" /><span>{alt || t("图片无法显示")}</span></span>;
  return <img className={className} src={src} alt={alt} loading="lazy" decoding="async" referrerPolicy="no-referrer" crossOrigin="anonymous" onError={() => setFailedUrl(src)} />;
}

function Sources({ items }: { items: AnswerLink[] }) {
  const { t } = useI18n();
  return <div className="answer-sources" role="group" aria-label={t("来源")}>
    {items.map((item, index) => <AnswerExternalLink className="answer-source" key={index} url={item.url}><Globe size={12} aria-hidden="true" /><span>{item.label}</span></AnswerExternalLink>)}
  </div>;
}

export function RichAnswer({ block }: { block: AnswerBlock }) {
  const { t } = useI18n();
  const titleId = useId();
  if (block.type === "metrics") return <dl className={`answer-metrics${block.items.some(item => String(item.value).length > 10) ? " answer-metrics-has-long-values" : ""}`}>
    {block.items.map((item, index) => {
      const longValue = String(item.value).length > 10;
      return <div className="answer-metric" key={index}><dt>{item.label}</dt><dd className={longValue ? "answer-metric-value-long" : undefined} tabIndex={longValue ? 0 : undefined}>{item.value}</dd>{item.detail && <small>{item.detail}</small>}</div>;
    })}
  </dl>;
  if (block.type === "sources") return <Sources items={block.items} />;
  if (block.type === "table") return <section className="answer-table-section">
    {block.title && <h3 id={titleId}>{block.title}</h3>}
    <div className="answer-table-scroll" role="region" aria-label={block.title ? undefined : t("表格")} aria-labelledby={block.title ? titleId : undefined} tabIndex={0}>
      <table className="answer-table">{block.caption && <caption>{block.caption}</caption>}<thead><tr>{block.columns.map((column, index) => <th scope="col" key={index}>{column}</th>)}</tr></thead>
        <tbody>{block.rows.map((row, index) => <tr key={index}>{row.map((value, column) => <td key={column}><Cell value={value} /></td>)}</tr>)}</tbody>
      </table>
      {!block.rows.length && <p className="answer-table-empty">{t("暂无数据")}</p>}
    </div>
  </section>;
  return <div className="answer-cards">{block.items.map((item, index) => <article className={`answer-card${item.image ? " answer-card-with-image" : ""}`} key={index}>
    {item.image && <AnswerImage className="answer-card-image" url={item.image.url} alt={item.image.alt} />}
    <div className="answer-card-content"><div className="answer-card-heading"><h3>{block.numbered ? `${index + 1}. ${item.title}` : item.title}</h3>{item.badge && <Badge value={item.badge} />}</div>
      <p>{item.description}</p>{item.details?.map((detail, detailIndex) => <p key={detailIndex}>{detail}</p>)}
      {Boolean(item.sources?.length) && <Sources items={item.sources!} />}
      {Boolean(item.links?.length) && <div className="answer-card-links">{item.links!.map((itemLink, linkIndex) => <AnswerExternalLink key={linkIndex} url={itemLink.url}>{itemLink.label}</AnswerExternalLink>)}</div>}
    </div>
  </article>)}</div>;
}
