import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import { fileURLToPath } from 'node:url';

const source = '070fa25b07692c90c56a6b00a9a969ff2abb7804';
const base = '.runtime/phase0B/baseline';
const sha256 = value => crypto.createHash('sha256').update(value).digest('hex');
const read = name => JSON.parse(fs.readFileSync(name));
const median = values => {
  const sorted = [...values].sort((a, b) => a - b), middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
};
const distribution = values => ({ n: values.length, median: median(values),
  p95: [...values].sort((a, b) => a - b)[Math.ceil(values.length * .95) - 1],
  p95_method: 'nearest rank', samples: values });
const closed = result => {
  assert.equal(result.exit_code, 0);
  assert.deepEqual(result.owned_survivors, []);
};
const provenance = name => ({ path: name.replaceAll('\\', '/'),
  bytes: fs.statSync(name).size, sha256: sha256(fs.readFileSync(name)) });

export function verifyIndexResponse(row) {
  const result = row.response.result;
  assert.equal(row.response.type, 'workspace.indexed');
  for (const [field, value] of Object.entries({ files_scanned: 1454, files_parsed: 1451,
    files_failed: 0, files_skipped: 3, symbols_extracted: 33416,
    dependencies_extracted: 113787, total_bytes: 21759911 })) assert.equal(result[field], value, field);
  assert.deepEqual(result.errors, []);
  assert.deepEqual(result.fatal_errors, []);
  assert.equal(row.response.workspace.context_engine.backend, 'python');
  assert.equal(row.response.workspace.context_engine.indexing, false);
  assert(row.request_ms + 100 >= result.total_time_ms, 'Previous result cannot pass as a completed timed rebuild');
  if (row.persisted_index) {
    assert.equal(row.persisted_index.searchable_files, 1449);
    assert.equal(row.persisted_index.scanned_files, 1454);
    assert.equal(row.persisted_index.parsed_files, 1451);
  }
}

export function verifyRetrievalBatch(batch, queries, readRaw) {
  assert.deepEqual(batch.queries.map(row => row.query_id), queries.map(query => query.id));
  assert(batch.context_status.ready && !batch.context_status.indexing);
  assert.equal(batch.context_status.files, 1451);
  assert.equal(batch.context_status.backend, 'python');
  let chain = 0, sdk = 0;
  for (const [index, row] of batch.queries.entries()) {
    const raw = readRaw(row), query = queries[index];
    for (const key of Object.keys(row)) assert.deepEqual(raw[key], row[key], key);
    assert.equal(row.group, batch.group);
    assert.equal(row.trial, batch.trial);
    assert.deepEqual(row.arguments, { query_type: 'task', query: query.query, max_files: 6,
      max_symbols: 12, max_tokens: 12000, include_history: true, include_memory: true });
    assert.equal(sha256(raw.context_string), row.context_sha256);
    assert.equal(Buffer.byteLength(raw.context_string), row.context_bytes);
    assert.equal(Math.floor(Array.from(raw.context_string).length / 4), row.estimated_tokens);
    assert(row.estimated_tokens <= 12000);
    assert(raw.context_string.includes(query.query) && raw.context_string.includes('CURATED EXCERPTS') &&
      raw.context_string.includes('TASK CONTEXT'));
    assert.equal(raw.response.type, 'prompt.result');
    assert.equal(raw.response.result.success, true);
    assert.equal(raw.requests.length, 2);
    const callId = `phase0_${batch.group}_${batch.trial}_${query.id}`;
    const messages = raw.requests[1].body.messages;
    const calls = messages.flatMap(item => item.tool_calls || []).filter(item => item.id === callId);
    assert.equal(calls.length, 1);
    assert.deepEqual(JSON.parse(calls[0].function.arguments), row.arguments);
    const returns = messages.filter(item => item.role === 'tool' && item.tool_call_id === callId);
    assert.equal(returns.length, 1);
    assert.equal(returns[0].content, raw.context_string);
    const events = raw.events.filter(([, item]) => item.type === 'prompt.event' && item.event?.type === 'ui.event')
      .map(([stamp, item]) => [stamp, item.event.event]).filter(([, item]) => item.tool_call_id === callId);
    const starts = events.filter(([, item]) => item.event === 'tool_start');
    const ends = events.filter(([, item]) => item.event === 'tool_result');
    assert.equal(starts.length, 1);
    assert.equal(ends.length, 1);
    assert.equal(ends[0][1].success, true);
    assert.equal(ends[0][1].output, raw.context_string);
    assert.equal((ends[0][0] - starts[0][0]) / 1e6, row.observed_tool_start_to_result_ms);
    const requestGap = (raw.requests[1].received_ns - raw.requests[0].received_ns) / 1e6;
    assert(row.query_dispatch_to_complete_return_ms > 0 && row.query_dispatch_to_complete_return_ms <= requestGap);
    assert(row.sdk_prompt_request_ms >= row.query_dispatch_to_complete_return_ms);
    chain += row.query_dispatch_to_complete_return_ms;
    sdk += row.sdk_prompt_request_ms;
  }
  assert.equal(chain, batch.complete_query_batch_ms);
  assert.equal(sdk, batch.complete_sdk_batch_ms);
}

function persistentState(directory, expectedRevision) {
  const projects = path.join(directory, 'app/.reverie/projects');
  const caches = fs.readdirSync(projects, { withFileTypes: true }).filter(item => item.isDirectory())
    .map(item => path.join(projects, item.name, 'context_cache'))
    .filter(item => fs.existsSync(path.join(item, 'python-search.sqlite3')));
  assert.equal(caches.length, 1);
  const cache = caches[0], file = path.join(cache, 'python-search.sqlite3');
  // SQLite's Windows VFS needs the extended prefix for these archived paths.
  const database = new DatabaseSync(path.toNamespacedPath(file), { readOnly: true });
  let state;
  try {
    state = database.prepare('SELECT root, revision FROM state WHERE id=1').get();
    assert.equal(fs.realpathSync.native(state.root), fs.realpathSync.native('.runtime/phase0B/corpus'));
    assert.equal(state.revision, expectedRevision);
    assert.equal(database.prepare('SELECT COUNT(*) AS n FROM files').get().n, 1454);
    assert.equal(database.prepare('SELECT COUNT(*) AS n FROM files WHERE indexed=1').get().n, 1449);
  } finally { database.close(); }
  const snapshot = path.join(cache, 'python-snapshots', String(state.revision));
  const files = read(path.join(snapshot, 'files.json'));
  assert.equal(Object.keys(files).length, 1451);
  return { revision: state.revision, parsed_files: 1451, searchable_files: 1449, scanned_files: 1454,
    snapshot_index_sha256: sha256(fs.readFileSync(path.join(snapshot, 'index.json'))),
    snapshot_files_sha256: sha256(fs.readFileSync(path.join(snapshot, 'files.json'))) };
}

function main() {
  const output = process.argv[2];
  if (!output) throw new Error('Usage: node audit-python-baselines.mjs new-output.json');
  const sdkPath = `${base}/python-sdk-baseline-v1/report.json`;
  const warmPath = `${base}/python-sdk-warm-audited-v1/report.json`;
  const desktopPath = `${base}/python-desktop-baseline-v1/report.json`;
  const sdk = read(sdkPath), warm = read(warmPath), desktop = read(desktopPath);
  for (const report of [sdk, warm, desktop]) assert.equal(report.source_commit, source);
  assert.equal(sdk.startups.length, 60);
  const startups = Object.fromEntries(['fresh_profile', 'prewarmed_profile'].map(group => {
    const rows = sdk.startups.filter(row => row.group === group);
    assert.equal(rows.length, 30);
    assert.equal(new Set(rows.map(row => row.trial)).size, 30);
    rows.forEach(row => closed(row.close));
    return [group, distribution(rows.map(row => row.kernel_usable_ms))];
  }));
  assert.equal(sdk.cold_indexes.length, 30);
  const coldStates = [];
  for (const row of sdk.cold_indexes) {
    verifyIndexResponse(row);
    closed(row.close);
    const state = persistentState(`${base}/python-sdk-baseline-v1/index-${String(row.trial).padStart(2, '0')}`, 1);
    coldStates.push({ trial: row.trial, ...state });
    if (row.persisted_index) assert.deepEqual(state, row.persisted_index);
  }
  assert.equal(warm.warm_indexes.length, 30);
  assert.equal(warm.warmup_persisted_index.revision, 1);
  for (const [index, row] of warm.warm_indexes.entries()) {
    verifyIndexResponse(row);
    assert.equal(row.trial, index + 1);
    assert.equal(row.persisted_index.revision, index + 2);
  }
  closed(warm.warm_close);
  const finalWarm = persistentState(`${base}/python-sdk-warm-audited-v1/warm-index`, 31);
  assert.deepEqual(finalWarm, warm.warm_indexes.at(-1).persisted_index);
  assert.equal(desktop.startups.length, 60);
  assert.equal(desktop.no_index, true);
  assert.equal(desktop.semantic_models_loaded, false);
  assert.equal(desktop.gamer_running, false);
  const gui = Object.fromEntries(['fresh_profile', 'prewarmed_profile'].map(group => {
    const rows = desktop.startups.filter(row => row.group === group);
    assert.equal(rows.length, 30);
    assert.equal(new Set(rows.map(row => row.trial)).size, 30);
    for (const row of rows) {
      assert.equal(row.native_window.visible, true);
      closed(row.close);
      assert(row.resources_at_ready.processes.some(item => item.name === 'reverie.exe'));
    }
    return [group, distribution(rows.map(row => row.gui_and_kernel_usable_ms))];
  }));
  assert.equal(desktop.idle_samples.length, 60);
  assert.equal(desktop.idle_window.settle_seconds, 30);
  assert(desktop.idle_window.duration_seconds >= 59);
  const memory = Object.fromEntries(['working_set_bytes', 'private_commit_bytes'].map(field => {
    for (const row of desktop.idle_samples) {
      assert.equal(row[field], row.processes.reduce((sum, process) => sum + process[field], 0));
      assert(row.processes.some(item => item.name === 'reverie.exe'));
    }
    const values = desktop.idle_samples.map(row => row[field]);
    const stats = distribution(values);
    assert.equal(stats.median, desktop.idle_memory[field].median_bytes);
    assert.equal(stats.p95, desktop.idle_memory[field].p95_bytes);
    return [field, { ...stats, peak: Math.max(...values) }];
  }));
  const payloadPath = `${base}/desktop-release/payload-files.json`;
  const payload = read(payloadPath), prepared = read(`${base}/desktop-release/verified.json`);
  assert.equal(prepared.source_commit, source);
  assert.equal(sha256(fs.readFileSync(payloadPath)), prepared.payload_manifest_sha256);
  assert.equal(payload.length, prepared.payload_files);
  assert.equal(payload.reduce((sum, item) => sum + item.bytes, 0), prepared.payload_bytes);
  const releasePath = `${base}/release-identity-live-v1.json`;
  const release = read(releasePath);
  assert.equal(release.id, 454958491);
  assert.equal(release.target_commitish, source);
  assert.equal(release.tag_name, 'v2.5.5');
  assert.equal(release.draft, false);
  assert.equal(release.prerelease, false);
  assert.equal(release.assets.length, 17);
  const retrievalPath = `${base}/python-context-baseline-v1/report.json`;
  const retrieval = read(retrievalPath), retrievalRecords = [];
  assert.equal(retrieval.source_commit, source);
  assert(retrieval.passed && retrieval.formal);
  assert.equal(retrieval.labels_sha256, provenance('testdata/context-evaluation/queries-v1.json').sha256);
  const queries = read('testdata/context-evaluation/queries-v1.json').queries.filter(item => item.family === 'basic');
  assert.deepEqual(retrieval.query_ids, queries.map(query => query.id));
  assert.equal(retrieval.batches.length, 60);
  for (const batch of [...retrieval.batches, retrieval.warmup]) {
    verifyRetrievalBatch(batch, queries, row => {
      const name = `${base}/python-context-baseline-v1/${row.group}-${String(row.trial).padStart(2, '0')}-${row.query_id}.json`;
      retrievalRecords.push(provenance(name));
      return read(name);
    });
    if (batch.close) closed(batch.close);
  }
  closed(retrieval.warm_close);
  const retrievalGroups = Object.fromEntries(['fresh_process', 'prewarmed_process'].map(group => {
    const batches = retrieval.batches.filter(batch => batch.group === group);
    assert.deepEqual(batches.map(batch => batch.trial), Array.from({ length: 30 }, (_, index) => index + 1));
    return [group, { complete_query_batch: distribution(batches.map(batch => batch.complete_query_batch_ms)),
      complete_sdk_batch: distribution(batches.map(batch => batch.complete_sdk_batch_ms)),
      per_query: Object.fromEntries(queries.map(query => [query.id, distribution(batches.map(batch =>
        batch.queries.find(row => row.query_id === query.id).query_dispatch_to_complete_return_ms))])) }];
  }));
  const result = { schema: 'reverie.python-performance-baseline.v1', passed: true,
    audited_at: new Date().toISOString(), source_commit: source,
    corpus_manifest: provenance('testdata/context-evaluation/frozen-corpus-v1.json'),
    hardware: sdk.hardware, units: { latency: 'milliseconds', memory: 'bytes' },
    sdk_startup: startups, index: {
      fresh_process_missing_index: distribution(sdk.cold_indexes.map(row => row.request_ms)),
      prewarmed_complete_rebuild: distribution(warm.warm_indexes.map(row => row.request_ms)),
      cold_persistent_states: coldStates,
      final_persistent_state: finalWarm, previous_incomplete_warm_measurement_excluded: true },
    desktop_startup: gui, desktop_idle_memory: memory,
    basic_retrieval: { queries_per_batch: 16, batches_per_state: 30, observations: 960,
      measured_boundary: 'Local fixture dispatch through actual released retrieval to complete serialized tool return.',
      groups: retrievalGroups, raw_records: retrievalRecords, timing_gate_aggregation: 'deferred by maintainer to external validation',
      query_cache_expiry_wait_seconds: retrieval.query_cache_expiry_wait_seconds },
    desktop_payload: { bytes: prepared.payload_bytes, files: prepared.payload_files,
      manifest: provenance(payloadPath), desktop_exe_sha256: prepared.desktop_exe_sha256,
      folder_kernel_sha256: prepared.folder_kernel_sha256 },
    installation_assets: release.assets.filter(item => !item.name.endsWith('.json') && item.name !== 'SHA256SUMS'),
    installation_asset_scope: 'All platform compressed sizes from the unchanged published release; Windows Desktop extracted payload is separately measured.',
    release_identity: provenance(releasePath),
    input_reports: [sdkPath, warmPath, desktopPath, retrievalPath].map(provenance),
    limitations: ['Filesystem cache is uncontrolled.',
      'SDK uses the standalone one-file CLI; Desktop uses the release folder kernel.',
      'Desktop uses external read-only CDP readiness observation and inspector app.quit; observer overhead is not yet quantified.',
      'Desktop idle sampling uses an empty isolated history and the no-index scenario.',
      'Retrieval dispatch timestamps were not separately retained; reported values are bounded against raw request timestamps and tool-event timings are independently recomputed.',
      'Older warm snapshots were pruned by the unchanged product; trial fingerprints and the final actual database/snapshot are audited.',
      'These are Python baselines, not Rust performance or product acceptance.'] };
  fs.writeFileSync(output, JSON.stringify(result, null, 2) + '\n', { flag: 'wx' });
  console.log(JSON.stringify({ passed: true, output: path.resolve(output),
    sdk_startup_medians_ms: Object.fromEntries(Object.entries(startups).map(([k, v]) => [k, v.median])),
    gui_startup_medians_ms: Object.fromEntries(Object.entries(gui).map(([k, v]) => [k, v.median])) }));
}

if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) main();
