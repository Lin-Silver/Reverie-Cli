export function parseFileLink(value: string): { path: string; line: number } | null {
  let decoded: string; try { decoded = decodeURIComponent(value.replace(/^file:\/\//, "")); } catch { return null; }
  if (/^https?:|^mailto:|^javascript:/i.test(decoded)) return null;
  const match = /^(.*?)(?::(\d+)(?::\d+)?|#L(\d+))?$/.exec(decoded);
  return match ? { path: match[1], line: Number(match[2] || match[3] || 1) } : null;
}
