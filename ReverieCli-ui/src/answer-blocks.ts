/** Declarative answer content only: no HTML, scripts, styles or host actions. */
export type AnswerTone = "neutral" | "info" | "success" | "warning" | "danger";
export type AnswerBadge = { text: string; tone?: AnswerTone };
export type AnswerLink = { label: string; url: string };
export type AnswerNumericText = { readonly kind: "answer-number"; readonly text: string };
export type AnswerCell = string | number | boolean | null | AnswerBadge | AnswerNumericText;
export type AnswerBlock =
  | { type: "metrics"; items: { label: string; value: string | number; detail?: string }[] }
  | { type: "table"; title?: string; columns: string[]; rows: AnswerCell[][]; caption?: string }
  | { type: "cards"; numbered?: boolean; items: {
    title: string; description: string; image?: { url: string; alt: string };
    badge?: AnswerBadge; details?: string[]; links?: AnswerLink[]; sources?: AnswerLink[];
  }[] }
  | { type: "sources"; items: AnswerLink[] };

const record = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === "object" && !Array.isArray(value);
const text = (value: unknown): value is string => typeof value === "string";
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const optional = (value: unknown, check: (value: unknown) => boolean) => value === undefined || check(value);
const fields = (value: unknown, allowed: readonly string[]): value is Record<string, unknown> =>
  record(value) && Object.keys(value).every(key => allowed.includes(key));

function hasDuplicateObjectKeys(source: string): boolean {
  let cursor = 0;
  const whitespace = () => { while (/\s/.test(source[cursor] ?? "")) cursor += 1; };
  const string = (): string => {
    const start = cursor++;
    while (cursor < source.length) {
      const character = source[cursor++];
      if (character === "\\") cursor += 1;
      else if (character === '"') return JSON.parse(source.slice(start, cursor)) as string;
    }
    throw new SyntaxError("Incomplete JSON string");
  };
  const value = (): boolean => {
    whitespace();
    if (source[cursor] === '"') { string(); return false; }
    if (source[cursor] === "[") {
      cursor += 1;
      whitespace();
      if (source[cursor] === "]") { cursor += 1; return false; }
      while (true) {
        if (value()) return true;
        whitespace();
        if (source[cursor] === "]") { cursor += 1; return false; }
        if (source[cursor++] !== ",") throw new SyntaxError("Invalid JSON array");
      }
    }
    if (source[cursor] === "{") {
      cursor += 1;
      whitespace();
      if (source[cursor] === "}") { cursor += 1; return false; }
      const keys = new Set<string>();
      while (true) {
        whitespace();
        if (source[cursor] !== '"') throw new SyntaxError("Invalid JSON object key");
        const key = string();
        if (keys.has(key)) return true;
        keys.add(key);
        whitespace();
        if (source[cursor++] !== ":") throw new SyntaxError("Invalid JSON object");
        if (value()) return true;
        whitespace();
        if (source[cursor] === "}") { cursor += 1; return false; }
        if (source[cursor++] !== ",") throw new SyntaxError("Invalid JSON object");
      }
    }
    const start = cursor;
    while (cursor < source.length && !/[\s,:}\]]/.test(source[cursor])) cursor += 1;
    if (cursor === start) throw new SyntaxError("Invalid JSON value");
    return false;
  };
  const duplicate = value();
  whitespace();
  if (cursor !== source.length) throw new SyntaxError("Unexpected JSON content");
  return duplicate;
}

const tones = new Set<unknown>(["neutral", "info", "success", "warning", "danger"]);
const badge = (value: unknown): value is AnswerBadge => fields(value, ["text", "tone"]) && text(value.text) && optional(value.tone, tone => tones.has(tone));
export const isAnswerNumericText = (value: unknown): value is AnswerNumericText => fields(value, ["kind", "text"]) && value.kind === "answer-number" && text(value.text);
const link = (value: unknown): value is AnswerLink => fields(value, ["label", "url"]) && text(value.label) && text(value.url);
const links = (value: unknown): value is AnswerLink[] => Array.isArray(value) && value.every(link);
const cell = (value: unknown): value is AnswerCell => value === null || text(value) || finite(value) || typeof value === "boolean" || badge(value);

/** Invalid or incomplete content stays visible as the original code, never a partial table. */
export function parseAnswerBlock(source: string): AnswerBlock | null {
  let value: unknown;
  // Numbers are display data, never calculation inputs. Retain the JSON token
  // before Number conversion can round identifiers, decimals or signed zero.
  // Keep their original types during shape validation: a numeric title or
  // column must not become a valid string through this preservation step.
  const numberSources = new WeakMap<object, Map<string, string>>();
  try {
    if (hasDuplicateObjectKeys(source)) return null;
    value = JSON.parse(source, function (this: object, key: string, item: unknown, context?: { source?: string }) {
      if (typeof item === "number" && Number.isFinite(item)) {
        if (context?.source) {
          let numbers = numberSources.get(this);
          if (!numbers) { numbers = new Map(); numberSources.set(this, numbers); }
          numbers.set(key, context.source);
        } else if (!Number.isSafeInteger(item)) {
          // Older JS engines without source-aware parsing must retain the raw
          // block instead of silently displaying a rounded value.
          throw new Error("Numeric source text is unavailable");
        }
      }
      return item;
    });
  } catch { return null; }
  const displayNumber = <T>(parent: object, key: string, item: T): T | string =>
    typeof item === "number" ? numberSources.get(parent)?.get(key) ?? item : item;
  if (!record(value)) return null;
  if (value.type === "metrics" && fields(value, ["type", "items"]) && Array.isArray(value.items) && value.items.length > 0 && value.items.every(item =>
    fields(item, ["label", "value", "detail"]) && text(item.label) && (text(item.value) || finite(item.value)) && optional(item.detail, text))) {
    const block = value as Extract<AnswerBlock, { type: "metrics" }>;
    return { ...block, items: block.items.map(item => ({ ...item, value: displayNumber(item, "value", item.value) })) };
  }
  if (value.type === "table" && fields(value, ["type", "title", "columns", "rows", "caption"]) && optional(value.title, text) && optional(value.caption, text) &&
    Array.isArray(value.columns) && value.columns.length > 0 && value.columns.every(text) &&
    Array.isArray(value.rows) && value.rows.every(row => Array.isArray(row) && row.length === (value.columns as string[]).length && row.every(cell))) {
    const block = value as Extract<AnswerBlock, { type: "table" }>;
    return { ...block, rows: block.rows.map(row => row.map((item, index) => {
      const source = typeof item === "number" ? numberSources.get(row)?.get(String(index)) : undefined;
      return source === undefined ? item : { kind: "answer-number", text: source };
    })) };
  }
  if (value.type === "cards" && fields(value, ["type", "numbered", "items"]) && optional(value.numbered, item => typeof item === "boolean") &&
    Array.isArray(value.items) && value.items.length > 0 && value.items.every(item => fields(item, ["title", "description", "image", "badge", "details", "links", "sources"]) && text(item.title) && text(item.description) &&
      optional(item.badge, badge) && optional(item.image, image => fields(image, ["url", "alt"]) && text(image.url) && text(image.alt)) &&
      optional(item.details, details => Array.isArray(details) && details.every(text)) && optional(item.links, links) && optional(item.sources, links))) return value as AnswerBlock;
  if (value.type === "sources" && fields(value, ["type", "items"]) && links(value.items) && value.items.length > 0) return value as AnswerBlock;
  return null;
}

export function answerExternalUrl(value: string): string | null {
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) && !url.username && !url.password ? url.href : null;
  } catch { return null; }
}

export function answerImageUrl(value: string): string | null {
  // Raster data and HTTPS images only. Never let answer content read local files.
  if (/^data:image\/(?:png|jpeg|gif|webp|avif);base64,[a-z\d+/=\s]+$/i.test(value)) return value;
  const url = answerExternalUrl(value);
  return url?.startsWith("https:") ? url : null;
}
