/** Maintainer-approved nDCG observation; it introduces no acceptance gate. */
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { covers, evaluateRepeatedSet, QUALITY_TRIALS, selectEvaluationFragments, TOP_K, validateEvidence } from './context-evaluation.mjs';

const grade = evidence => evidence.necessity === 'required' ? 2 : 1;
const dcg = grades => grades.reduce((sum, value, index) => sum + (2 ** value - 1) / Math.log2(index + 2), 0);
const mean = values => values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
const range = values => [Math.min(...values), Math.max(...values)];
const sha256 = bytes => crypto.createHash('sha256').update(bytes).digest('hex');

export function evaluateNdcgQuery(label, response, sourceCommit) {
  if (response.query_id !== label.id) throw new Error('Query identity mismatch');
  const { selected } = selectEvaluationFragments(response);
  const evidence = label.expected_evidence;
  for (const item of evidence) {
    validateEvidence(item);
    if (!['required', 'supplementary'].includes(item.necessity)) throw new Error('Unknown evidence relevance');
  }
  if (!evidence.some(item => item.necessity === 'required')) throw new Error('A scored query needs required evidence');
  const edges = selected.map(fragment => evidence.map((item, index) =>
    covers(item, fragment, item.source_commit || sourceCommit) ? index : -1).filter(index => index >= 0));
  const rankByEvidence = new Map();
  // Augmenting matches resolve ambiguous equal-grade coverage without losing
  // an earlier rank. Required matches retain priority over supplementary ones.
  function assign(rank, relevance, seen) {
    for (const index of edges[rank]) {
      if (grade(evidence[index]) !== relevance || seen.has(index)) continue;
      seen.add(index);
      const owner = rankByEvidence.get(index);
      if (owner === undefined || assign(owner, relevance, seen)) {
        rankByEvidence.set(index, rank);
        return true;
      }
    }
    return false;
  }
  for (let rank = 0; rank < selected.length; rank++) assign(rank, 2, new Set());
  const requiredRanks = new Set(rankByEvidence.values());
  for (let rank = 0; rank < selected.length; rank++) {
    if (!requiredRanks.has(rank)) assign(rank, 1, new Set());
  }
  const grades = selected.map(() => 0);
  const assignments = [...rankByEvidence].map(([index, rank]) => {
    grades[rank] = grade(evidence[index]);
    return { rank: rank + 1, evidence_index: index, necessity: evidence[index].necessity, grade: grades[rank] };
  }).sort((a, b) => a.rank - b.rank);
  const actual = dcg(grades), ideal = dcg(evidence.map(grade).sort((a, b) => b - a).slice(0, TOP_K));
  return { query_id: label.id, domain: label.domain, family: label.family,
    dcg_at_10: actual, ideal_dcg_at_10: ideal, ndcg_at_10: actual / ideal,
    ranked_grades: grades, one_to_one_assignments: assignments };
}

export function evaluateRepeatedNdcg(labels, responses) {
  const recall = evaluateRepeatedSet(labels, responses);
  const labelsById = new Map(labels.queries.map(item => [item.id, item]));
  const byQuery = new Map(labels.queries.map(item => [item.id, []]));
  for (const response of responses) byQuery.get(response.query_id).push({ trial: response.trial,
    ...evaluateNdcgQuery(labelsById.get(response.query_id), response, labels.source_commit) });
  const results = labels.queries.map(query => {
    const trials = byQuery.get(query.id).sort((a, b) => a.trial - b.trial);
    const values = trials.map(item => item.ndcg_at_10), average = mean(values);
    return { query_id: query.id, domain: query.domain, family: query.family, trials_per_query: trials.length,
      ndcg_at_10_mean: average, ndcg_at_10_range: range(values),
      ndcg_at_10_population_stddev: Math.sqrt(mean(values.map(value => (value - average) ** 2))), trials };
  });
  const familyMean = (items, family) => mean(items.filter(item => item.family === family).map(item => item.ndcg_at_10_mean));
  return { schema: 'reverie.context-evaluation.ndcg-observation.v1', source_commit: labels.source_commit,
    observations: responses.length, queries: results.length, trials_per_query: QUALITY_TRIALS,
    acceptance_gate: false, budget: recall.budget,
    policy: { required_grade: 2, supplementary_grade: 1, gain: '2^grade-1', discount: 'log2(rank+1)',
      matching: 'one-to-one; ranks in returned order, required first, augment equal-grade matches',
      ideal: 'all frozen evidence grades descending, at most ten',
      aggregation: 'mean per question over thirty trials, then equal-weight macro average' },
    ndcg_at_10_macro: mean(results.map(item => item.ndcg_at_10_mean)),
    basic_ndcg_at_10_macro: familyMean(results, 'basic'), hard_ndcg_at_10_macro: familyMean(results, 'hard'),
    domains: Object.fromEntries([...new Set(results.map(item => item.domain))].map(domain => {
      const items = results.filter(item => item.domain === domain);
      return [domain, { basic_ndcg_at_10_macro: familyMean(items, 'basic'), hard_ndcg_at_10_macro: familyMean(items, 'hard') }];
    })), results };
}

if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) {
  const [labelPath, responsePath, outputPath] = process.argv.slice(2);
  if (!outputPath) throw new Error('Usage: node context-ndcg.mjs labels.json responses.json new-output.json');
  const labelBytes = fs.readFileSync(labelPath), responseBytes = fs.readFileSync(responsePath);
  const labels = JSON.parse(labelBytes);
  if (labels.status !== 'frozen_after_independent_cross_review') throw new Error('Use the independently frozen labels');
  const result = { ...evaluateRepeatedNdcg(labels, JSON.parse(responseBytes)),
    computed_at: new Date().toISOString(), labels_sha256: sha256(labelBytes), responses_sha256: sha256(responseBytes) };
  fs.writeFileSync(outputPath, JSON.stringify(result, null, 2) + '\n', { flag: 'wx' });
  console.log(JSON.stringify({ queries: result.queries, observations: result.observations,
    ndcg_at_10_macro: result.ndcg_at_10_macro, output: path.resolve(outputPath) }));
}
