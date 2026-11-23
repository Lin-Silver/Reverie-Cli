/** Score actual returned evidence under the maintainer's frozen retrieval contract. */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

export const TOKEN_BUDGET = 12000;
export const FRAGMENT_LINES = 72;
export const TOP_K = 10;
export const QUALITY_TRIALS = 30;
export const estimateTokens = text => Math.floor(Array.from(text).length / 4);
const sha256 = text => crypto.createHash('sha256').update(text, 'utf8').digest('hex');
const stripLegacyTrailingWhitespace = text => text.replace(
  /[\t\v\f\r \u001c-\u001f\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+$/u, '');
const lines = text => {
  const result = text.replace(/\r\n/g, '\n').split('\n');
  if (result.at(-1) === '') result.pop();
  return result;
};

function returnedLines(fragment, contextBytes) {
  const { context_start_byte: start, context_end_byte: end } = fragment;
  if (!Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start < 0 || end <= start || end > contextBytes.length) {
    throw new Error('Invalid returned text byte range');
  }
  const rendered = contextBytes.subarray(start, end).toString('utf8');
  if (rendered !== fragment.rendered_text || Buffer.byteLength(rendered, 'utf8') !== end - start) {
    throw new Error('Fragment is not the actual returned text');
  }
  const renderedLines = lines(rendered);
  if (fragment.render_format === 'raw_lines') return renderedLines;
  if (fragment.render_format !== 'numbered_lines') throw new Error('Unknown fragment rendering');
  return renderedLines.map((line, index) => {
    const match = /^\s*(\d+) \| (.*)$/.exec(line);
    if (!match || Number(match[1]) !== fragment.start_line + index) throw new Error('Non-contiguous returned evidence');
    return match[2];
  });
}

function validateFragment(fragment, contextBytes) {
  if (!Number.isSafeInteger(fragment.start_line) || !Number.isSafeInteger(fragment.end_line) ||
      fragment.start_line < 1 || fragment.end_line < fragment.start_line) throw new Error('Invalid fragment line bound');
  for (const [field, length] of [['source_commit', 40], ['blob_sha1', 40], ['file_sha256', 64]]) {
    if (!new RegExp(`^[a-f0-9]{${length}}$`).test(fragment[field] ?? '')) throw new Error(`Missing content identity: ${field}`);
  }
  if (typeof fragment.repo_relative_path !== 'string' || !fragment.repo_relative_path) throw new Error('Missing fragment path');
  const textLines = returnedLines(fragment, contextBytes);
  if (textLines.length !== fragment.end_line - fragment.start_line + 1) throw new Error('Omitted or extra source lines');
  return { ...fragment, textLines };
}

export function covers(evidence, fragment, sourceCommit) {
  if (fragment.repo_relative_path !== evidence.repo_relative_path || fragment.source_commit !== sourceCommit ||
      fragment.blob_sha1 !== evidence.blob_sha1 || fragment.file_sha256 !== evidence.file_sha256 ||
      fragment.start_line > evidence.start_line || fragment.end_line < evidence.end_line) return false;
  const expected = lines(evidence.raw_excerpt);
  const offset = evidence.start_line - fragment.start_line;
  // The legacy numbered renderer removes trailing whitespace only. Source
  // identity still binds the complete original bytes and no missing line is added.
  return expected.every((line, index) => stripLegacyTrailingWhitespace(line) ===
    stripLegacyTrailingWhitespace(fragment.textLines[offset + index]));
}

export function selectEvaluationFragments(response) {
  if (typeof response.context_string !== 'string' || !Array.isArray(response.fragments)) throw new Error('Missing actual context');
  const tokenEstimate = estimateTokens(response.context_string);
  if (tokenEstimate > TOKEN_BUDGET) throw new Error('Returned context exceeds historical token estimate budget');
  const contextBytes = Buffer.from(response.context_string, 'utf8');
  const unique = [];
  const seen = new Set();
  let previousEnd = 0;
  for (const item of response.fragments) {
    const fragment = validateFragment(item, contextBytes);
    if (fragment.context_start_byte < previousEnd) throw new Error('Invalid returned fragment order');
    previousEnd = fragment.context_end_byte;
    const key = JSON.stringify([fragment.repo_relative_path, fragment.source_commit, fragment.blob_sha1,
      fragment.file_sha256, fragment.start_line, fragment.end_line, fragment.textLines]);
    if (!seen.has(key)) { seen.add(key); unique.push(fragment); }
  }
  // The maintainer-approved cap applies to evaluation only. Deduplicate the
  // complete originals above; preserve their bytes, boundaries and ordering.
  const selected = unique.slice(0, TOP_K).map(fragment => ({ ...fragment,
    end_line: Math.min(fragment.end_line, fragment.start_line + FRAGMENT_LINES - 1),
    textLines: fragment.textLines.slice(0, FRAGMENT_LINES) }));
  const overlength = response.fragments.filter(fragment => fragment.end_line - fragment.start_line + 1 > FRAGMENT_LINES);
  return { selected, unique, overlength, tokenEstimate };
}

export function validateEvidence(evidence) {
  if (sha256(evidence.raw_excerpt) !== evidence.raw_utf8_sha256 ||
      Buffer.byteLength(evidence.raw_excerpt, 'utf8') !== evidence.byte_length ||
      lines(evidence.raw_excerpt).length !== evidence.end_line - evidence.start_line + 1) {
    throw new Error('Frozen evidence integrity mismatch');
  }
}

export function evaluateQuery(label, response, defaultSourceCommit) {
  if (response.query_id !== label.id) throw new Error('Query identity mismatch');
  const { selected, unique, overlength, tokenEstimate } = selectEvaluationFragments(response);
  const required = label.expected_evidence.filter(item => item.necessity === 'required');
  if (!required.length) throw new Error('A scored query needs required evidence');
  const hits = [];
  for (const [index, evidence] of required.entries()) {
    validateEvidence(evidence);
    const rank = selected.findIndex(fragment => covers(evidence, fragment, evidence.source_commit || defaultSourceCommit));
    if (rank >= 0) hits.push({ required_index: index, rank: rank + 1 });
  }
  return { query_id: label.id, domain: label.domain, family: label.family,
    query_language: label.query_language, required: required.length, hits: hits.length,
    recall_at_10: hits.length / required.length, hit_evidence: hits,
    returned_fragments: response.fragments.length, unique_fragments: unique.length,
    evaluated_fragments: selected.length, token_estimate: tokenEstimate,
    overlength_fragments: overlength.length, actual_fragment_bounds_passed: !overlength.length,
    overlength_originals: overlength.map(fragment => ({ path: fragment.repo_relative_path,
      start_line: fragment.start_line, end_line: fragment.end_line })),
    unicode_characters: Array.from(response.context_string).length };
}

const mean = values => values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
export function evaluateSet(labels, responses) {
  const byId = new Map();
  for (const response of responses) {
    if (byId.has(response.query_id)) throw new Error('Duplicate query response');
    byId.set(response.query_id, response);
  }
  if (byId.size !== labels.queries.length || new Set(labels.queries.map(query => query.id)).size !== labels.queries.length) {
    throw new Error('Incomplete or duplicate evaluation query set');
  }
  const results = labels.queries.map(query => {
    const response = byId.get(query.id);
    if (!response) throw new Error(`Missing actual response for ${query.id}`);
    return evaluateQuery(query, response, labels.source_commit);
  });
  const domains = Object.fromEntries([...new Set(results.map(result => result.domain))].map(domain => {
    const group = results.filter(result => result.domain === domain);
    return [domain, { queries: group.length,
      basic_recall_at_10_macro: mean(group.filter(result => result.family === 'basic').map(result => result.recall_at_10)),
      hard_recall_at_10_macro: mean(group.filter(result => result.family === 'hard').map(result => result.recall_at_10)) }];
  }));
  return { schema: 'reverie.context-evaluation.scores.v1', aggregation: 'equal-weight per-query macro average',
    budget: { max_lines: FRAGMENT_LINES, estimated_tokens: TOKEN_BUDGET, top_k_after_exact_deduplication: TOP_K,
      estimator: 'floor(unicode_character_count / 4)',
      fragment_cap: 'evaluate the first 72 lines; exact deduplication uses complete originals' },
    queries: results.length, domains,
    basic_recall_at_10_macro: mean(results.filter(result => result.family === 'basic').map(result => result.recall_at_10)),
    hard_recall_at_10_macro: mean(results.filter(result => result.family === 'hard').map(result => result.recall_at_10)),
    ndcg_at_10: null, ndcg_status: 'not computed by this evidence coverage evaluator', results };
}

export function evaluateRepeatedSet(labels, responses) {
  const queryIds = new Set(labels.queries.map(query => query.id));
  const trials = Array.from({ length: QUALITY_TRIALS }, () => []);
  const seen = new Set();
  for (const response of responses) {
    if (!queryIds.has(response.query_id)) throw new Error('Unknown repeated query identity');
    if (!Number.isSafeInteger(response.trial) || response.trial < 1 || response.trial > QUALITY_TRIALS) {
      throw new Error('Invalid repeated trial identity');
    }
    const key = JSON.stringify([response.query_id, response.trial]);
    if (seen.has(key)) throw new Error('Duplicate repeated query trial');
    seen.add(key);
    trials[response.trial - 1].push(response);
  }
  if (!queryIds.size || seen.size !== labels.queries.length * QUALITY_TRIALS) {
    throw new Error('Incomplete thirty-trial evaluation query set');
  }
  const scores = trials.map(items => evaluateSet(labels, items));
  const range = values => values.length ? [Math.min(...values), Math.max(...values)] : null;
  const results = labels.queries.map((query, index) => {
    const rows = scores.map((score, trial) => ({ trial: trial + 1, ...score.results[index] }));
    const values = rows.map(row => row.recall_at_10);
    const average = mean(values);
    return { query_id: query.id, domain: query.domain, family: query.family, query_language: query.query_language,
      required: rows[0].required, trials_per_query: rows.length,
      recall_at_10_mean: average, recall_at_10_range: range(values),
      recall_at_10_population_stddev: Math.sqrt(mean(values.map(value => (value - average) ** 2))),
      overlength_runs: rows.filter(row => !row.actual_fragment_bounds_passed).length, trials: rows };
  });
  const averageFamily = (group, family) => mean(group.filter(row => row.family === family).map(row => row.recall_at_10_mean));
  const domains = Object.fromEntries([...new Set(results.map(row => row.domain))].map(domain => {
    const group = results.filter(row => row.domain === domain);
    return [domain, { queries: group.length,
      basic_recall_at_10_macro: averageFamily(group, 'basic'), hard_recall_at_10_macro: averageFamily(group, 'hard'),
      basic_macro_range: range(scores.map(score => score.domains[domain].basic_recall_at_10_macro).filter(value => value !== null)),
      hard_macro_range: range(scores.map(score => score.domains[domain].hard_recall_at_10_macro).filter(value => value !== null)) }];
  }));
  return { schema: 'reverie.context-evaluation.repeated-scores.v1',
    aggregation: 'mean Recall per question over 30 trials, then equal-weight per-question macro average',
    queries: results.length, observations: responses.length, trials_per_query: QUALITY_TRIALS,
    budget: scores[0].budget, domains,
    basic_recall_at_10_macro: averageFamily(results, 'basic'), hard_recall_at_10_macro: averageFamily(results, 'hard'),
    basic_macro_range: range(scores.map(score => score.basic_recall_at_10_macro).filter(value => value !== null)),
    hard_macro_range: range(scores.map(score => score.hard_recall_at_10_macro).filter(value => value !== null)),
    actual_fragment_bounds_passed: results.every(result => result.overlength_runs === 0),
    ndcg_at_10: null, ndcg_status: scores[0].ndcg_status, results };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const [labelPath, responsePath, outputPath] = process.argv.slice(2);
  if (!labelPath || !responsePath || !outputPath) throw new Error('Usage: node context-evaluation.mjs labels.json responses.json scores.json');
  const labelBytes = fs.readFileSync(labelPath);
  const labels = JSON.parse(labelBytes);
  if (labels.status !== 'frozen_after_independent_cross_review') throw new Error('Freeze independently reviewed labels before scoring');
  const responseBytes = fs.readFileSync(responsePath);
  const responses = JSON.parse(responseBytes);
  const score = responses.some(response => 'trial' in response) ? evaluateRepeatedSet : evaluateSet;
  const result = { ...score(labels, responses),
    labels_sha256: sha256(labelBytes), responses_sha256: sha256(responseBytes) };
  fs.writeFileSync(outputPath, JSON.stringify(result, null, 2) + '\n');
  process.stdout.write(JSON.stringify({ queries: result.queries, basic_recall_at_10_macro: result.basic_recall_at_10_macro,
    hard_recall_at_10_macro: result.hard_recall_at_10_macro, output: path.resolve(outputPath) }) + '\n');
}
