import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import test from 'node:test';
import { verifyRetrievalBatch } from './audit-python-baselines.mjs';

function fixture() {
  const query = { id: 'C01', query: '查询证据' };
  const arguments_ = { query_type: 'task', query: query.query, max_files: 6,
    max_symbols: 12, max_tokens: 12000, include_history: true, include_memory: true };
  const text = 'TASK CONTEXT\n查询证据\nCURATED EXCERPTS\nactual source';
  const call = 'phase0_fresh_process_1_C01';
  const row = { group: 'fresh_process', trial: 1, query_id: query.id, arguments: arguments_,
    sdk_prompt_request_ms: 5, query_dispatch_to_complete_return_ms: 4,
    observed_tool_start_to_result_ms: 2, context_bytes: Buffer.byteLength(text),
    estimated_tokens: Math.floor(Array.from(text).length / 4),
    context_sha256: crypto.createHash('sha256').update(text).digest('hex') };
  const raw = { ...row, context_string: text,
    response: { type: 'prompt.result', result: { success: true } },
    requests: [{ received_ns: 1000000, body: { messages: [] } },
      { received_ns: 5500000, body: { messages: [
        { role: 'assistant', tool_calls: [{ id: call, function: { arguments: JSON.stringify(arguments_) } }] },
        { role: 'tool', tool_call_id: call, content: text }] } }],
    events: [[2000000, { type: 'prompt.event', event: { type: 'ui.event', event: {
      event: 'tool_start', tool_call_id: call } } }],
      [4000000, { type: 'prompt.event', event: { type: 'ui.event', event: {
        event: 'tool_result', tool_call_id: call, success: true, output: text } } }]] };
  const batch = { group: row.group, trial: 1, queries: [row], complete_query_batch_ms: 4,
    complete_sdk_batch_ms: 5, context_status: { ready: true, indexing: false, files: 1451, backend: 'python' } };
  return { query, raw, batch };
}

test('released retrieval audit binds the returned body to the actual tool and query', () => {
  const { query, raw, batch } = fixture();
  assert.doesNotThrow(() => verifyRetrievalBatch(batch, [query], () => raw));
  raw.requests[1].body.messages[1].content = 'different response';
  assert.throws(() => verifyRetrievalBatch(batch, [query], () => raw));
});

test('reported timings must fit raw transport timestamps and match the tool events', () => {
  const { query, raw, batch } = fixture();
  raw.events[1][0]++;
  assert.throws(() => verifyRetrievalBatch(batch, [query], () => raw));
  raw.events[1][0]--;
  batch.queries[0].query_dispatch_to_complete_return_ms = 8;
  raw.query_dispatch_to_complete_return_ms = 8;
  batch.complete_query_batch_ms = 8;
  assert.throws(() => verifyRetrievalBatch(batch, [query], () => raw));
});

test('missing, reordered or mismatched trials cannot become a complete query batch', () => {
  const { query, raw, batch } = fixture();
  assert.throws(() => verifyRetrievalBatch(batch, [query, { id: 'C02' }], () => raw));
  raw.trial = 2;
  assert.throws(() => verifyRetrievalBatch(batch, [query], () => raw));
  raw.trial = 1;
  batch.context_status.indexing = true;
  assert.throws(() => verifyRetrievalBatch(batch, [query], () => raw));
});
