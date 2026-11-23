import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import test from 'node:test';
import { evaluateQuery } from './context-evaluation.mjs';
import { evaluateNdcgQuery, evaluateRepeatedNdcg } from './context-ndcg.mjs';

const source = 'a'.repeat(40), blob = 'b'.repeat(40), fileHash = 'c'.repeat(64);
function evidence(start, text, necessity = 'required') {
  return { necessity, repo_relative_path: 'evidence.txt', blob_sha1: blob, file_sha256: fileHash,
    start_line: start, end_line: start + text.split('\n').length - 1, raw_excerpt: text,
    raw_utf8_sha256: crypto.createHash('sha256').update(text).digest('hex'), byte_length: Buffer.byteLength(text) };
}
function response(parts, queryId = 'Q') {
  let text = '';
  const fragments = parts.map(({ start, body }) => {
    const offset = Buffer.byteLength(text);
    text += body + '\n';
    return { source_commit: source, blob_sha1: blob, file_sha256: fileHash, repo_relative_path: 'evidence.txt',
      start_line: start, end_line: start + body.split('\n').length - 1, render_format: 'raw_lines',
      rendered_text: body, context_start_byte: offset, context_end_byte: offset + Buffer.byteLength(body) };
  });
  return { query_id: queryId, context_string: text, fragments };
}
const label = expected => ({ id: 'Q', domain: 'code', family: 'hard', query_language: 'en', expected_evidence: expected });

test('grades use the approved gain, discount and ideal frozen order', () => {
  const query = label([evidence(1, 'required'), evidence(2, 'supplementary', 'supplementary')]);
  const perfect = evaluateNdcgQuery(query, response([{ start: 1, body: 'required' }, { start: 2, body: 'supplementary' }]), source);
  assert.equal(perfect.ndcg_at_10, 1);
  assert.equal(perfect.ideal_dcg_at_10, 3 + 1 / Math.log2(3));
  const reversed = evaluateNdcgQuery(query, response([{ start: 2, body: 'supplementary' }, { start: 1, body: 'required' }]), source);
  assert.equal(reversed.dcg_at_10, 1 + 3 / Math.log2(3));
  assert.ok(reversed.ndcg_at_10 < 1);
});

test('overlapping distinct fragments cannot score the same evidence twice', () => {
  const query = label([evidence(2, 'fact\nend')]);
  const value = response([{ start: 1, body: 'start\nfact\nend' }, { start: 2, body: 'fact\nend' }]);
  const result = evaluateNdcgQuery(query, value, source);
  assert.deepEqual(result.ranked_grades, [2, 0]);
  assert.equal(result.one_to_one_assignments.length, 1);
  assert.equal(result.ndcg_at_10, 1);
});

test('one fragment receives one grade while Recall still covers all required spans', () => {
  const query = label([evidence(1, 'first'), evidence(2, 'second')]);
  const value = response([{ start: 1, body: 'first\nsecond' }]);
  assert.equal(evaluateQuery(query, value, source).recall_at_10, 1);
  const result = evaluateNdcgQuery(query, value, source);
  assert.equal(result.dcg_at_10, 3);
  assert.equal(result.ndcg_at_10, 3 / (3 + 3 / Math.log2(3)));
});

test('equal-grade ambiguous coverage is reassigned without losing an earlier rank', () => {
  const query = label([evidence(1, 'first'), evidence(2, 'second')]);
  const value = response([{ start: 1, body: 'first\nsecond' }, { start: 1, body: 'first' }]);
  const before = JSON.stringify(value);
  const result = evaluateNdcgQuery(query, value, source);
  assert.deepEqual(result.ranked_grades, [2, 2]);
  assert.equal(result.ndcg_at_10, 1);
  assert.equal(JSON.stringify(value), before);
});

test('required evidence takes priority when a fragment covers both grades', () => {
  const query = label([evidence(1, 'required'), evidence(2, 'optional', 'supplementary')]);
  const result = evaluateNdcgQuery(query, response([{ start: 1, body: 'required\noptional' }]), source);
  assert.deepEqual(result.ranked_grades, [2]);
  assert.equal(result.one_to_one_assignments[0].necessity, 'required');
});

test('the shared 72-line, top-ten and content-version contract also governs nDCG', () => {
  const rows = Array.from({ length: 73 }, (_, i) => `line ${i + 1}`);
  const query = label([evidence(73, 'line 73')]);
  assert.equal(evaluateNdcgQuery(query, response([{ start: 1, body: rows.join('\n') }]), source).ndcg_at_10, 0);
  const late = response([...Array.from({ length: 10 }, (_, i) => ({ start: i + 100, body: `decoy ${i}` })),
    { start: 73, body: 'line 73' }]);
  assert.equal(evaluateNdcgQuery(query, late, source).ndcg_at_10, 0);
  const mismatch = response([{ start: 73, body: 'line 73' }]);
  mismatch.fragments[0].file_sha256 = 'd'.repeat(64);
  assert.equal(evaluateNdcgQuery(query, mismatch, source).ndcg_at_10, 0);
});

test('supplementary raw bytes are validated before assigning their grade', () => {
  const query = label([evidence(1, 'required'), evidence(2, 'optional', 'supplementary')]);
  query.expected_evidence[1].raw_excerpt += 'tampered';
  assert.throws(() => evaluateNdcgQuery(query, response([]), source), /integrity/);
});

test('thirty-trial means precede equal-question macros and missing trials are rejected', () => {
  const first = label([evidence(1, 'first')]);
  const second = { ...label([evidence(2, 'second')]), id: 'Q2', domain: 'doc' };
  const labels = { source_commit: source, queries: [first, second] };
  const observations = Array.from({ length: 30 }, (_, i) => [
    { ...response(i < 10 ? [{ start: 1, body: 'first' }] : []), trial: i + 1 },
    { ...response(i < 20 ? [{ start: 2, body: 'second' }] : [], 'Q2'), trial: i + 1 },
  ]).flat().reverse();
  const result = evaluateRepeatedNdcg(labels, observations);
  assert.equal(result.acceptance_gate, false);
  assert.equal(result.ndcg_at_10_macro, .5);
  assert.equal(result.results[0].ndcg_at_10_mean, 1 / 3);
  assert.equal(result.domains.doc.hard_ndcg_at_10_macro, 2 / 3);
  assert.deepEqual(result.results[0].ndcg_at_10_range, [0, 1]);
  assert.throws(() => evaluateRepeatedNdcg(labels, observations.slice(1)), /Incomplete/);
});
