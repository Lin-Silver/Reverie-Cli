import { useEffect, useState, type FormEvent } from "react";
import { useI18n } from "./i18n";
import { DailyTokenChart, TokenBreakdown, TokenModelRanking, TokenProvenance, tokenMoney } from "./TokenUsageCharts";
import type { TokenFilters, TokenPrice, TokenStatisticsData } from "./types";
import "./token-statistics.css";

function PriceForm({ price, save, busy }: { price?: TokenPrice; save: (price: TokenPrice) => void; busy: boolean }) {
  const { t } = useI18n();
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    save({
      currency: data.get("currency") === "CNY" ? "CNY" : "USD",
      input: Number(data.get("input")),
      cached_input: Number(data.get("cached_input")),
      output: Number(data.get("output")),
    });
  }
  return <form className="token-fields" aria-label={t("模型 Token 价格")} onSubmit={submit}>
    <label>{t("货币")}<select name="currency" defaultValue={price?.currency ?? "USD"}><option>USD</option><option>CNY</option></select></label>
    <label>{t("普通输入")}<input name="input" type="number" min="0" step="any" defaultValue={price?.input} required /></label>
    <label>{t("缓存输入")}<input name="cached_input" type="number" min="0" step="any" defaultValue={price?.cached_input} required /></label>
    <label>{t("输出")}<input name="output" type="number" min="0" step="any" defaultValue={price?.output} required /></label>
    <button className="primary-button" type="submit" disabled={busy}>{t("保存价格")}</button>
  </form>;
}

export default function TokenStatistics({ projectRoot }: { projectRoot: string }) {
  const { t } = useI18n();
  const [filters, setFilters] = useState<TokenFilters>({});
  const [report, setReport] = useState<TokenStatisticsData>();
  const [priceModel, setPriceModel] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [saved, setSaved] = useState(false);
  const invalidDates = Boolean(filters.start && filters.end && filters.start > filters.end);

  useEffect(() => {
    if (invalidDates) return;
    let current = true;
    setLoading(true);
    setLoadError("");
    window.reverie.request("getTokenStatistics", { projectRoot, filters }).then(
      response => { if (current) setReport(response.statistics); },
      error => { if (current) setLoadError(String(error)); },
    ).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [projectRoot, filters, refresh, invalidDates]);

  function changeFilter(key: keyof TokenFilters, value: string) {
    setFilters(previous => {
      const next = { ...previous };
      if (value) next[key] = value;
      else delete next[key];
      if (key === "project") delete next.session;
      return next;
    });
  }
  async function exportCsv() {
    setBusy(true);
    setActionError("");
    try {
      const { filename, content } = await window.reverie.request("exportTokenStatistics", { projectRoot, filters });
      const url = URL.createObjectURL(new Blob(["\uFEFF", content], { type: "text/csv;charset=utf-8" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      try { link.click(); } finally { setTimeout(() => URL.revokeObjectURL(url), 0); }
    } catch (error) { setActionError(String(error)); }
    finally { setBusy(false); }
  }
  async function savePrice(modelKey: string, price: TokenPrice) {
    setBusy(true);
    setActionError("");
    setSaved(false);
    try {
      await window.reverie.request("setTokenPrice", { modelKey, price });
      setSaved(true);
      setRefresh(value => value + 1);
    } catch (error) { setActionError(String(error)); }
    finally { setBusy(false); }
  }

  const options = report?.options;
  const selectedPriceModel = priceModel || filters.model || options?.models[0]?.id || "";
  const price = report?.prices[selectedPriceModel];
  const totals = report?.totals;
  return <section className="token-statistics" aria-label={t("Token 用量统计")}>
    <header className="token-statistics-head">
      <div><h1>{t("Token 用量统计")}</h1><p>{t("查看本机已记录的请求用量与预估费用。")}</p></div>
      <button type="button" className="secondary-button" onClick={() => void exportCsv()} disabled={!report || loading || busy || invalidDates || Boolean(loadError)}>{t("导出 CSV")}</button>
    </header>
    <div className="token-fields">
      <label>{t("开始日期（UTC）")}<input type="date" value={filters.start ?? ""} onChange={event => changeFilter("start", event.target.value)} /></label>
      <label>{t("结束日期（UTC）")}<input type="date" value={filters.end ?? ""} onChange={event => changeFilter("end", event.target.value)} /></label>
      <label>{t("统计项目")}<select value={filters.project ?? ""} onChange={event => changeFilter("project", event.target.value)}>
        <option value="">{t("所有项目")}</option>{options?.projects.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
      </select></label>
      <label>{t("统计会话")}<select value={filters.session ?? ""} onChange={event => changeFilter("session", event.target.value)}>
        <option value="">{t("所有会话")}</option>{options?.sessions.filter(item => !filters.project || item.project_id === filters.project).map(item => <option key={item.id} value={item.id}>{item.project_name} · {item.name}</option>)}
      </select></label>
      <label>{t("统计模型")}<select value={filters.model ?? ""} onChange={event => changeFilter("model", event.target.value)}>
        <option value="">{t("所有模型")}</option>{options?.models.map(item => <option key={item.id} value={item.id}>{item.name} · {item.provider}</option>)}
      </select></label>
    </div>
    {invalidDates ? <p role="alert">{t("结束日期不能早于开始日期。")}</p> : loadError ? <div role="alert" className="token-notice">
      <p>{t("无法加载 Token 统计。")} {loadError}</p><button type="button" className="secondary-button" onClick={() => setRefresh(value => value + 1)}>{t("重试")}</button>
    </div> : loading ? <p role="status">{t("正在加载 Token 统计…")}</p> : totals && report && <>
      <dl className="token-summary">
        <div><dt>{t("总 Tokens")}</dt><dd>{totals.total_tokens.toLocaleString()}</dd></div>
        <div><dt>{t("请求次数")}</dt><dd>{totals.calls.toLocaleString()}</dd></div>
        <div><dt>{t("预估费用")}</dt><dd>{Object.entries(totals.costs).map(([currency, cost]) => tokenMoney(cost, currency)).join(" · ") || "—"}</dd></div>
      </dl>
      {(!totals.calls || totals.unpriced_calls > 0 || totals.unknown_cache_calls > 0 || report.excluded_historical_calls > 0 || report.warnings.length > 0) && <div className="token-notice">
        {!totals.calls && <p>{t("没有符合筛选条件的用量记录。")}</p>}
        {totals.unpriced_calls > 0 && <p>{t("尚未设置价格，以下请求未计入费用：")}{totals.unpriced_calls.toLocaleString()}</p>}
        {totals.unknown_cache_calls > 0 && <p>{t("缓存用量未提供，按普通输入估算：")}{totals.unknown_cache_calls.toLocaleString()}</p>}
        {report.excluded_historical_calls > 0 && <p>{t("以下历史汇总缺少筛选所需的明细，未计入结果：")}{report.excluded_historical_calls.toLocaleString()}</p>}
        {report.warnings.map(warning => <p key={warning}>{warning}</p>)}
      </div>}
      {totals.calls > 0 && <div className="token-charts">
        <DailyTokenChart label={t("Token 用量趋势（UTC）")} points={report.daily.map(day => ({ date: day.date, value: day.total_tokens }))} />
        <TokenBreakdown totals={totals} />
        {Object.keys(totals.costs).map(currency => <DailyTokenChart key={currency} label={`${t("预估费用趋势（UTC）")} · ${currency}`} currency={currency}
          points={report.daily.flatMap(day => currency in day.costs ? [{ date: day.date, value: day.costs[currency] }] : [])} />)}
        <TokenModelRanking models={report.models} selectModel={model => changeFilter("model", model)} />
        <TokenProvenance totals={totals} />
      </div>}
    </>}
    {options?.models.length ? <section className="token-chart token-pricing">
      <h2>{t("模型 Token 价格")}</h2>
      <p>{t("按每 100 万 Tokens 输入价格。USD 和 CNY 分开统计，不换算。")}</p>
      <label className="token-price-model">{t("计价模型")}<select value={selectedPriceModel} onChange={event => { setPriceModel(event.target.value); setSaved(false); }}>
        {options.models.map(item => <option key={item.id} value={item.id}>{item.name} · {item.provider}</option>)}
      </select></label>
      <PriceForm key={`${selectedPriceModel}:${price?.updated_at ?? ""}`} price={price} busy={busy} save={next => void savePrice(selectedPriceModel, next)} />
      {saved && <p role="status">{t("价格已保存。")}</p>}
    </section> : null}
    {actionError && <p role="alert">{actionError}</p>}
  </section>;
}
