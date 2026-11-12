import { useI18n } from "./i18n";
import type { TokenModelTotals, TokenTotals } from "./types";

const compact = (value: number) => new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(value);
export const tokenMoney = (value: number, currency: string) => new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 6 }).format(value);

export function DailyTokenChart({ label, points, currency }: { label: string; points: Array<{ date: string; value: number }>; currency?: string }) {
  const { t } = useI18n();
  const max = Math.max(1, ...points.map(point => point.value));
  const start = Date.parse(points[0]?.date ?? "");
  const span = Date.parse(points.at(-1)?.date ?? "") - start;
  const coordinates = points.map(point => ({ ...point, x: span > 0 ? 50 + (Date.parse(point.date) - start) / span * 610 : 350, y: 150 - point.value / max * 120 }));
  const format = (value: number) => currency ? tokenMoney(value, currency) : compact(value);
  return <section className="token-chart">
    <h2>{label}</h2>
    {points.length ? <>
      <svg className="token-line-chart" viewBox="0 0 700 185" role="img" aria-label={label}>
        <title>{label}</title>
        {[0, 0.5, 1].map(ratio => <g key={ratio}><line className="token-chart-grid" x1="50" x2="670" y1={150 - ratio * 120} y2={150 - ratio * 120} /><text x="44" y={154 - ratio * 120} textAnchor="end">{format(max * ratio)}</text></g>)}
        <polyline className="token-chart-line" points={coordinates.map(point => `${point.x},${point.y}`).join(" ")} />
        {coordinates.map(point => <circle key={point.date} cx={point.x} cy={point.y} r="3.5" tabIndex={0}><title>{point.date}: {format(point.value)}</title></circle>)}
        <text x={coordinates[0].x} y="178" textAnchor={points.length === 1 ? "middle" : "start"}>{points[0].date}</text>
        {points.length > 1 && <text x={coordinates.at(-1)?.x} y="178" textAnchor="end">{points.at(-1)?.date}</text>}
      </svg>
      <details className="token-chart-data"><summary>{t("查看图表数据")}</summary><table><thead><tr><th>{t("日期（UTC）")}</th><th>{currency ? t("预估费用") : "Tokens"}</th></tr></thead><tbody>{points.map(point => <tr key={point.date}><td>{point.date}</td><td>{currency ? format(point.value) : point.value.toLocaleString()}</td></tr>)}</tbody></table></details>
    </> : <p className="token-chart-empty">{t("当前筛选没有可按日期展示的请求。")}</p>}
  </section>;
}

export function TokenBreakdown({ totals }: { totals: TokenTotals }) {
  const { t } = useI18n();
  const parts = [{ key: "input", label: t("普通输入"), value: totals.uncached_input_tokens }, { key: "cache", label: t("缓存输入"), value: totals.cached_input_tokens }, { key: "output", label: t("输出"), value: totals.output_tokens }];
  const sum = parts.reduce((total, part) => total + part.value, 0);
  return <section className="token-chart token-breakdown"><h2>{t("Token 构成")}</h2>
    <div className="token-stacked-bar" role="img" aria-label={parts.map(part => `${part.label}: ${part.value.toLocaleString()}`).join(" · ")}>{parts.map(part => <span key={part.key} className={`token-part-${part.key}`} style={{ width: `${sum ? part.value / sum * 100 : 0}%` }} />)}</div>
    <dl className="token-breakdown-values">{parts.map(part => <div key={part.key}><dt><span className={`token-swatch token-part-${part.key}`} />{part.label}</dt><dd>{part.value.toLocaleString()}</dd></div>)}</dl>
    <p>{t("输入包含缓存输入；输出包含 API 报告的思考 Tokens。未报告的缓存按普通输入估算费用。")}</p>
  </section>;
}

export function TokenModelRanking({ models, selectModel }: { models: TokenModelTotals[]; selectModel: (key: string) => void }) {
  const { t } = useI18n();
  const max = Math.max(1, ...models.map(model => model.total_tokens));
  return <section className="token-chart"><h2>{t("模型用量排行")}</h2><p>{t("选择模型可筛选全部统计和导出。")}</p>
    <div className="token-model-ranking">{models.map(model => <button type="button" key={model.model_key} onClick={() => selectModel(model.model_key)} aria-label={`${t("筛选模型")} ${model.name}`}>
      <span className="token-model-name"><strong>{model.name}</strong><small>{model.provider} · {model.calls.toLocaleString()} {t("次调用")}</small></span>
      <span className="token-ranking-bar"><span style={{ width: `${model.total_tokens / max * 100}%` }} /></span>
      <span className="token-model-value">{compact(model.total_tokens)}<small>{Object.entries(model.costs).map(([currency, cost]) => tokenMoney(cost, currency)).join(" · ") || t("尚未计价")}</small></span>
    </button>)}</div>
  </section>;
}

export function TokenProvenance({ totals }: { totals: TokenTotals }) {
  const { t } = useI18n();
  return <section className="token-chart"><h2>{t("计数来源")}</h2><dl className="token-provenance">{[
    [t("API 实测"), totals.api_calls], [t("混合计数"), totals.mixed_calls], [t("本地估算"), totals.local_calls], [t("历史汇总"), totals.historical_calls],
  ].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{Number(value).toLocaleString()} {t("次调用")}</dd></div>)}</dl>
    <p>{t("API 未返回的字段才使用本地估算；历史汇总的计数精度无法追溯。")}</p>
  </section>;
}
