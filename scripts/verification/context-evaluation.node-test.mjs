import test from 'node:test';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import { estimateTokens, evaluateQuery, evaluateSet } from './context-evaluation.mjs';

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

test('the 72-line bound is enforced independently of relevance', () => {
  const long = Array.from({ length: 73 }, (_, i) => `line ${i}`).join('\n');
  assert.throws(() => evaluateQuery(label, response('Q1', [{ start: 1, text: long }]), commit), /line bound/);
  const bounded = response('Q1', [{ start: 1, text: long.split('\n').slice(0, 72).join('\n') }]);
  assert.doesNotThrow(() => evaluateQuery(label, bounded, commit));
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
