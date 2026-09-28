"""Stage-specific reconstruction diagnostics; never read test gold into the audit."""
import argparse
from collections import Counter
import json
from pathlib import Path
from .data import load_json


def diagnose(records, predictions, gold, known):
    def key(r):
        return r['source'], r['block'], r['target']
    eligible = {key(r) for r in gold if r['target'] in known and r['source'] != r['target']}
    candidates = {key(r) for r in records}
    selected = {key(r) for r in predictions}
    edges = {(s, t) for s, _, t in selected}
    counts = Counter()
    for k in eligible:
        counts['recovered' if k in selected else 'candidate_missing' if k not in candidates
               else 'different_block_selected' if (k[0], k[2]) in edges else 'not_selected'] += 1
    reachable = eligible & candidates
    # An oracle subject to one target per article cannot recover multiple blocks.
    pair_cap = len({(s, t) for s, _, t in reachable})
    return dict(gold_blocks=len(eligible), candidate_blocks=len(candidates),
                candidate_recall=len(reachable)/max(1, len(eligible)),
                one_per_target_recall_ceiling=pair_cap/max(1, len(eligible)),
                outcomes=dict(sorted(counts.items())),
                unmatched_predictions=len(selected-eligible),
                note='Unmatched predictions are not automatically editorially incorrect. The ceiling ignores overlap conflicts.')


def run(folder, output):
    d = Path(folder)
    split = load_json(d/'manifest.json')['source_split']
    records = load_json(d/'refinement-sentences/training-records.json')
    predictions = load_json(d/'refinement-ranking/predictions.json')
    if any(split[r['source']] not in ('train', 'dev') for r in records):
        raise ValueError('Candidate artifact contains test sources')
    if any(split[r['source']] != 'dev' for r in predictions):
        raise ValueError('Predictions must be development only')
    gold = [r for r in load_json(d/'gold-audit/gold-v2-train-dev.json') if split[r['source']] == 'dev']
    known = {p['url'] for p in load_json(d/'corpus.json')}
    result = diagnose([r for r in records if split[r['source']] == 'dev'], predictions, gold, known)
    result.update(split='dev_only', test_evaluated=False, predictions='refinement-ranking',
                  all_gold_occurrences=len(gold), eligible_gold_occurrences=sum(r['target'] in known and r['source'] != r['target'] for r in gold))
    Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--data', default='local-data/cities')
    p.add_argument('--output', default='docs/bottlenecks-dev.json')
    args = p.parse_args()
    run(args.data, args.output)
