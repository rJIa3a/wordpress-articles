"""Evaluate section-aware repetition with the fixed winning ranker on dev only."""
import argparse
import json
from pathlib import Path
import numpy as np
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier
from .data import load_json
from .ranking import relative_features
from .selection import select_sections
from .experiment import metrics


def section_relative_features(X, records, sections):
    """Compare mentions within their own section without using link labels."""
    section_records = [r | {'source': (r['source'], sections[r['source'], r['block']])}
                       for r in records]
    return np.hstack([relative_features(X, records), relative_features(X, section_records)[:, X.shape[1]:]])


def run(folder):
    d = Path(folder)
    a = np.load(d/'refinement-sentences/training-features.npz')
    X, y, train = a['X'], a['y'], a['train']
    records = load_json(d/'refinement-sentences/training-records.json')
    split = load_json(d/'manifest.json')['source_split']
    if any(split[r['source']] not in ('train', 'dev') or
           bool(train[i]) != (split[r['source']] == 'train') for i, r in enumerate(records)):
        raise ValueError('Invalid train/dev artifact')
    pages = load_json(d/'corpus.json')
    sections = {(p['url'], b['id']): b['section'] for p in pages for b in p['blocks']}
    model = HistGradientBoostingClassifier(max_iter=250, max_leaf_nodes=15,
        min_samples_leaf=60, l2_regularization=20, learning_rate=.06,
        early_stopping=False, random_state=17)
    features = relative_features(X, records)
    model.fit(features[train], y[train])
    scores = model.predict_proba(features[~train])[:, 1]
    dev = [r for r, flag in zip(records, train) if not flag]
    scored = [r | {'score': float(s), 'section': sections[r['source'], r['block']]}
              for r, s in zip(dev, scores)]
    gold = [g for g in load_json(d/'gold-audit/gold-v2-train-dev.json')
            if split[g['source']] == 'dev']
    known = {p['url'] for p in pages}
    runs, predictions = [], []
    # Fixed small grid; precision floor is the reproduced control, not a lower target.
    for cap, repeat in [(1, .5), (2, .65), (2, .8), (2, .9), (3, .8)]:
        pred = select_sections(scored, max_per_target=cap, repeat_threshold=repeat)
        result = dict(model='page_relative', max_per_target=cap, repeat_threshold=repeat,
                      metrics=metrics(pred, gold, known))
        runs.append(result)
        predictions.append(pred)
        print(json.dumps(result), flush=True)
    section_features = section_relative_features(X, records, sections)
    model.fit(section_features[train], y[train])
    section_scores = model.predict_proba(section_features[~train])[:, 1]
    section_scored = [r | {'score': float(s)} for r, s in zip(scored, section_scores)]
    for cap, repeat in [(1, .5), (2, .65), (2, .8)]:
        pred = select_sections(section_scored, max_per_target=cap, repeat_threshold=repeat)
        result = dict(model='page_and_section_relative', max_per_target=cap,
                      repeat_threshold=repeat, metrics=metrics(pred, gold, known))
        runs.append(result)
        predictions.append(pred)
        print(json.dumps(result), flush=True)
    floor = runs[0]['metrics']['block']['precision']
    span_floor = runs[0]['metrics']['span']['precision']
    valid = [i for i, r in enumerate(runs)
             if r['metrics']['block']['precision'] >= floor
             and r['metrics']['span']['precision'] >= span_floor]
    best = max(valid, key=lambda i: runs[i]['metrics']['block']['recall'])
    out = d/'refinement-repeat-ranking'
    out.mkdir(exist_ok=True)
    historical = load_json(d/'refinement-ranking/results.json')['selected']['metrics']['block']
    result = dict(split='dev_only', test_evaluated=False, precision_floor=floor,
                  sklearn_version=sklearn.__version__, numpy_version=np.__version__,
                  historical_control=historical,
                  historical_control_reproduced=runs[0]['metrics']['block']==historical,
                  span_precision_floor=span_floor,
                  selection='Maximum block recall without lower block or exact-anchor precision than control',
                  runs=runs, selected=runs[best])
    (out/'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    (out/'predictions.json').write_text(json.dumps(predictions[best], ensure_ascii=False))
    decisions = []
    if runs[best]['model'] == 'page_and_section_relative':scored = section_scored
    select_sections(scored, max_per_target=runs[best]['max_per_target'],
                    repeat_threshold=runs[best]['repeat_threshold'], decisions=decisions)
    (out/'decisions.json').write_text(json.dumps(decisions, ensure_ascii=False))
    (out/'scored-dev.json').write_text(json.dumps(scored, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', default='local-data/cities')
    run(parser.parse_args().data)
