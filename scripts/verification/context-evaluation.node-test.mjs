import test from 'node:test';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import { estimateTokens, evaluateQuery, evaluateSet, evaluateRepeatedSet } from './context-evaluation.mjs';

const commit = 'a'.repeat(40), blob = 'b'.repeat(40), fileHash = 'c'.repeat(64);
const digest = text => crypto.createHash('sha256').update(text, 'utf8').digest('hex');
function evidence(start, text, necessity = 'required') {
  return { necessity, repo_relative_path: 'example.py', blob_sha1: blob, file_sha256: fileHash,
    start_line: start, end_line: start + text.trimEnd().split('\n').length - 1,
    raw_excerpt: text, raw_utf8_sha256: digest(text), byte_length: Buffer.byteLength(text, 'utf8') };
}
function response(id, parts, prefix = '') {
  let context = prefix;
  const fragments = parts.map(part => {
    const rendered = part.text.split('\n').map((line, i) => `${part.start + i} | ${line}`).join('\n');
    const start = Buffer.byteLength(context, 'utf8');
    context += rendered + '\n';
    return { repo_relative_path: 'example.py', source_commit: commit, blob_sha1: blob, file_sha256: fileHash,
      start_line: part.start, end_line: part.start + part.text.split('\n').length - 1,
      rendered_text: rendered, render_format: 'numbered_lines', context_start_byte: start,
      context_end_byte: start + Buffer.byteLength(rendered, 'utf8') };
  });
  return { query_id: id, context_string: context, fragments };
}
const label = { id: 'Q1', domain: 'code', family: 'hard', query_language: 'en',
  expected_evidence: [evidence(10, 'if ready:\n    do_work()\n    save()\n')] };

test('only a completely returned, version-bound required span counts', () => {
  const complete = response('Q1', [{ start: 10, text: 'if ready:\n    do_work()\n    save()' }]);
  assert.equal(evaluateQuery(label, complete, commit).recall_at_10, 1);
  const partial = response('Q1', [{ start: 10, text: 'if ready:\n    do_work()' }]);
  assert.equal(evaluateQuery(label, partial, commit).recall_at_10, 0);
  complete.fragments[0].file_sha256 = 'd'.repeat(64);
  assert.equal(evaluateQuery(label, complete, commit).recall_at_10, 0);
});

test('a claimed long range cannot conceal omitted middle evidence', () => {
  const missing = response('Q1', [{ start: 10, text: 'if ready:\n    save()' }]);
  missing.fragments[0].end_line = 12;
  assert.throws(() => evaluateQuery(label, missing, commit), /source lines/);
});

test('supplied fragment metadata cannot manufacture text absent from the response', () => {
  const value = response('Q1', [{ start: 10, text: 'if ready:\n    do_work()\n    save()' }]);
  value.context_string = 'Only a path and summary were returned.';
  assert.throws(() => evaluateQuery(label, value, commit), /returned text/);
});

test('the first ten unique fragments are evaluated in original order', () => {
  const fillers = Array.from({ length: 10 }, (_, i) => ({ start: i + 100, text: `distractor ${i}` }));
  const relevant = { start: 10, text: 'if ready:\n    do_work()\n    save()' };
  assert.equal(evaluateQuery(label, response('Q1', [...fillers, relevant]), commit).recall_at_10, 0);
  const duplicates = response('Q1', [...Array(10).fill(fillers[0]), relevant]);
  const result = evaluateQuery(label, duplicates, commit);
  assert.equal(result.unique_fragments, 2);
  assert.equal(result.recall_at_10, 1);
});

test('metadata cannot reorder a later hit ahead of actual returned distractors', () => {
  const value = response('Q1', [
    ...Array.from({ length: 10 }, (_, i) => ({ start: i + 100, text: `distractor ${i}` })),
    { start: 10, text: 'if ready:\n    do_work()\n    save()' },
  ]);
  value.fragments.unshift(value.fragments.pop());
  assert.throws(() => evaluateQuery(label, value, commit), /returned fragment order/);
});

test('only the first 72 lines count while the original long fragment stays intact', () => {
  const long = Array.from({ length: 93 }, (_, i) => `line ${i + 1}`).join('\n');
  const value = response('Q1', [{ start: 1, text: long }]);
  const original = JSON.stringify(value);
  const lastCovered = { ...label, expected_evidence: [evidence(70, 'line 70\nline 71\nline 72\n')] };
  const beyond = { ...label, expected_evidence: [evidence(72, 'line 72\nline 73\n')] };
  const result = evaluateQuery(lastCovered, value, commit);
  assert.equal(result.recall_at_10, 1);
  assert.equal(evaluateQuery(beyond, value, commit).recall_at_10, 0);
  assert.equal(result.overlength_fragments, 1);
  assert.equal(result.actual_fragment_bounds_passed, false);
  assert.equal(JSON.stringify(value), original);
});

test('exact deduplication uses complete originals before the 72-line cap', () => {
  const rows = Array.from({ length: 74 }, (_, i) => `line ${i + 1}`);
  const distinct = [{ start: 1, text: rows.slice(0, 73).join('\n') }, { start: 1, text: rows.join('\n') }];
  const fillers = Array.from({ length: 8 }, (_, i) => ({ start: i + 100, text: `distractor ${i}` }));
  const relevant = { start: 10, text: 'if ready:\n    do_work()\n    save()' };
  const result = evaluateQuery(label, response('Q1', [...distinct, ...fillers, relevant]), commit);
  assert.equal(result.unique_fragments, 11);
  assert.equal(result.recall_at_10, 0);
  assert.equal(result.overlength_fragments, 2);
});

test('historical token estimates count Unicode characters, including emoji', () => {
  assert.equal(estimateTokens('中文😀a'), 1);
  assert.equal(estimateTokens('😀'.repeat(48003)), 12000);
  assert.equal(estimateTokens('😀'.repeat(48004)), 12001);
  const oversized = response('Q1', [], '😀'.repeat(48004));
  assert.throws(() => evaluateQuery(label, oversized, commit), /token estimate budget/);
});

test('supplementary evidence never increases the required denominator or hit count', () => {
  const mixed = { ...label, expected_evidence: [evidence(1, 'first\n'), evidence(2, 'second\n'),
    evidence(3, 'extra\n', 'supplementary')] };
  const result = evaluateQuery(mixed, response('Q1', [{ start: 1, text: 'first' }, { start: 3, text: 'extra' }]), commit);
  assert.equal(result.required, 2);
  assert.equal(result.hits, 1);
  assert.equal(result.recall_at_10, .5);
});

test('macro averages give equal weight to questions with different evidence counts', () => {
  const first = { ...label, expected_evidence: [evidence(1, 'missing\n')] };
  const second = { ...label, id: 'Q2', domain: 'doc', expected_evidence:
    Array.from({ length: 4 }, (_, i) => evidence(i + 10, `fact ${i}\n`)) };
  const result = evaluateSet({ source_commit: commit, queries: [first, second] }, [response('Q1', []),
    response('Q2', [{ start: 10, text: 'fact 0\nfact 1\nfact 2\nfact 3' }])]);
  assert.equal(result.hard_recall_at_10_macro, .5);
  assert.equal(result.domains.code.hard_recall_at_10_macro, 0);
  assert.equal(result.domains.doc.hard_recall_at_10_macro, 1);
});

test('missing or duplicate query outputs cannot disappear from an aggregate', () => {
  const set = { source_commit: commit, queries: [label] };
  assert.throws(() => evaluateSet(set, []), /Incomplete/);
  assert.throws(() => evaluateSet(set, [response('Q1', []), response('Q1', [])]), /Duplicate/);
});

test('thirty trials are averaged per question before the macro average', () => {
  const first = { ...label, expected_evidence: [evidence(10, 'first\n')] };
  const second = { ...label, id: 'Q2', domain: 'doc', expected_evidence:
    Array.from({ length: 4 }, (_, i) => evidence(i + 20, `fact ${i}\n`)) };
  const observations = Array.from({ length: 30 }, (_, index) => [
    { ...response('Q1', index < 10 ? [{ start: 10, text: 'first' }] : []), trial: index + 1 },
    { ...response('Q2', index < 20 ? [{ start: 20, text: 'fact 0\nfact 1\nfact 2\nfact 3' }] : []), trial: index + 1 },
  ]).flat().reverse();
  const result = evaluateRepeatedSet({ source_commit: commit, queries: [first, second] }, observations);
  assert.equal(result.trials_per_query, 30);
  assert.equal(result.observations, 60);
  assert.equal(result.hard_recall_at_10_macro, .5);
  assert.equal(result.results[0].recall_at_10_mean, 1 / 3);
  assert.equal(result.results[1].recall_at_10_mean, 2 / 3);
  assert.deepEqual(result.results[0].recall_at_10_range, [0, 1]);
  assert.ok(Math.abs(result.results[0].recall_at_10_population_stddev - Math.sqrt(2 / 9)) < 1e-12);
  assert.equal(result.domains.code.hard_recall_at_10_macro, 1 / 3);
  assert.equal(result.domains.doc.hard_recall_at_10_macro, 2 / 3);
  assert.equal(result.results[0].trials.length, 30);
  assert.equal(result.ndcg_at_10, null);
});

test('every frozen question needs thirty distinct, identified trials', () => {
  const labels = { source_commit: commit, queries: [label] };
  const all = Array.from({ length: 30 }, (_, i) => ({ ...response('Q1', []), trial: i + 1 }));
  assert.throws(() => evaluateRepeatedSet(labels, all.slice(1)), /Incomplete/);
  assert.throws(() => evaluateRepeatedSet(labels, [...all.slice(0, 29), all[0]]), /Duplicate/);
  assert.throws(() => evaluateRepeatedSet(labels, [{ ...all[0], trial: 0 }, ...all.slice(1)]), /trial/);
  assert.throws(() => evaluateRepeatedSet(labels, [{ ...all[0], query_id: 'unlabelled' }, ...all.slice(1)]), /query/);
});

test('altered frozen evidence is rejected before computing recall', () => {
  const changed = structuredClone(label);
  changed.expected_evidence[0].raw_excerpt += 'silently added\n';
  assert.throws(() => evaluateQuery(changed, response('Q1', []), commit), /integrity/);
});

test('legacy trailing Unicode whitespace formatting keeps source identity intact', () => {
  const unicode = { ...label, expected_evidence: [evidence(10, 'fact\u3000\n')] };
  assert.equal(evaluateQuery(unicode, response('Q1', [{ start: 10, text: 'fact' }]), commit).recall_at_10, 1);
});

test('fragment byte offsets remain correct after Chinese text and emoji', () => {
  const value = response('Q1', [{ start: 10, text: 'if ready:\n    do_work()\n    save()' }], '中文😀\n');
  assert.equal(evaluateQuery(label, value, commit).recall_at_10, 1);
  value.fragments[0].context_start_byte = '中文😀\n'.length;
  assert.throws(() => evaluateQuery(label, value, commit), /actual returned text/);
});

test('the independently reviewed v1 labels and corpus retain their frozen identities', () => {
  const read = name => fs.readFileSync(new URL(`../../testdata/context-evaluation/${name}`, import.meta.url), 'utf8')
    .replace(/\r\n/g, '\n');
  const labelText = read('queries-v1.json'), corpusText = read('frozen-corpus-v1.json');
  assert.equal(digest(labelText), 'f05678ac19bf9538b852e64e0debcbaac78386123489cf23fec01e875eb80aaa');
  assert.equal(digest(corpusText), '1a6dff14965e8f3a8a734f170aeb2cad55ad0d60a83f97d0be93be57892ef25e');
  const labels = JSON.parse(labelText);
  assert.equal(labels.status, 'frozen_after_independent_cross_review');
  assert.equal(labels.retrieval_scores_observed_before_freeze, false);
  const audit = evaluateSet(labels, labels.queries.map(query => ({
    query_id: query.id, context_string: '', fragments: [],
  })));
  assert.equal(audit.queries, 48);
  assert.equal(audit.results.reduce((sum, query) => sum + query.required, 0), 130);
  assert.equal(labels.queries.flatMap(query => query.expected_evidence)
    .filter(item => item.necessity === 'supplementary').length, 23);
});
