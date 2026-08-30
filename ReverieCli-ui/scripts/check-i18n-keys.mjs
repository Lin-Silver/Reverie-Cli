/**
 * Report translation keys the UI asks for but no map answers.
 *
 * `translate` falls back to the raw key for both languages, so a missing entry is
 * silent at runtime and at compile time: the page renders the Chinese source
 * string in English mode, or the literal dotted key in both. This walks the same
 * two directions the renderer does and fails the build instead.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const srcRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..", "src");

function sourceFiles(dir) {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.tsx?$/.test(entry) && !/\.test\.tsx?$/.test(entry) ? [path] : [];
  });
}

/** The literal keys of one `Record<string, string>` object literal in i18n.tsx. */
function mapKeys(text, name) {
  const start = text.indexOf(`const ${name}: Record<string, string> = {`);
  if (start < 0) throw new Error(`i18n.tsx has no map named ${name}`);
  const end = text.indexOf("\n};", start);
  const body = text.slice(start, end);
  return new Set([...body.matchAll(/^ {2}"((?:[^"\\]|\\.)*)":/gm)].map((match) => match[1]));
}

const i18nText = readFileSync(join(srcRoot, "i18n.tsx"), "utf8");
const english = mapKeys(i18nText, "ENGLISH_TRANSLATIONS");
const englishTemplates = mapKeys(i18nText, "ENGLISH_TEMPLATES");
const chineseTemplates = mapKeys(i18nText, "CHINESE_TEMPLATES");

const problems = [];
for (const file of sourceFiles(srcRoot)) {
  const text = readFileSync(file, "utf8");
  const lines = text.split("\n");
  lines.forEach((line, index) => {
    for (const match of line.matchAll(/\bt\(\s*"((?:[^"\\]|\\.)*)"/g)) {
      const key = match[1];
      const where = `${file.slice(srcRoot.length + 1)}:${index + 1}`;
      const dotted = /^[a-z][A-Za-z0-9]*(\.[A-Za-z0-9]+)+$/.test(key);
      if (dotted) {
        // A dotted key names a template. Neither language has a plain-text
        // fallback for one, so both maps must carry it.
        if (!englishTemplates.has(key)) problems.push(`${where}: ENGLISH_TEMPLATES is missing "${key}"`);
        if (!chineseTemplates.has(key)) problems.push(`${where}: CHINESE_TEMPLATES is missing "${key}"`);
      } else if (!english.has(key) && !englishTemplates.has(key)) {
        // A plain key is already Chinese, so zh-CN needs nothing; en-US would
        // render the Chinese source string.
        problems.push(`${where}: ENGLISH_TRANSLATIONS is missing "${key}"`);
      }
    }
  });
}

if (problems.length) {
  console.error(`${problems.length} untranslated key${problems.length === 1 ? "" : "s"}:`);
  for (const problem of problems) console.error(`  ${problem}`);
  process.exit(1);
}
console.log(`i18n keys resolved (${english.size} translations, ${englishTemplates.size} templates).`);
