from .data import load_json
"""Compare bounded cross-section repetition on development predictions only."""
import collections,json,argparse
from pathlib import Path
from .experiment import metrics

def select_sections(records,threshold=.5,repeat_threshold=.65,max_per_target=2,min_block_gap=3):
    chosen=[];pairs=collections.defaultdict(list);spans=collections.defaultdict(list)
    for r in sorted(records,key=lambda r:(-r['score'],r['source'],int(r['block']),r['start'])):
        if r['score']<threshold:continue
        pair=(r['source'],r['target']);block=(r['source'],r['block']);prior=pairs[pair]
        if r['source']==r['target'] or len(prior)>=max_per_target:continue
        if prior and (r['score']<repeat_threshold or not r['section'] or any(r['section']==p['section'] or abs(int(r['block'])-int(p['block']))<min_block_gap for p in prior)):continue
        if any(r['start']<e and r['end']>s for s,e in spans[block]):continue
        pairs[pair].append(r);spans[block].append((r['start'],r['end']))
        chosen.append({k:v for k,v in r.items() if k!='features'}|{'score':round(r['score']*100,2)})
    return chosen

def run(folder,experiment='refinement'):
    if experiment not in ('refinement','refinement-morphology'):raise ValueError('Unknown experiment')
    d=Path(folder);records=json.loads((d/experiment/'scored-dev.json').read_text());split=json.loads((d/'manifest.json').read_text())['source_split']
    if any(split[r['source']]!='dev' for r in records):raise ValueError('Only dev sources may be evaluated')
    known={p['url'] for p in json.loads((d/'corpus.json').read_text())};gold=[g for g in load_json(d/'gold.json') if split[g['source']]=='dev'];runs=[];predictions=[]
    for max_per_target,repeat_threshold in [(1,.5),(2,.5),(2,.65),(2,.8),(3,.65)]:
        pred=select_sections(records,repeat_threshold=repeat_threshold,max_per_target=max_per_target)
        result=dict(max_per_target=max_per_target,threshold=.5,repeat_threshold=repeat_threshold,metrics=metrics(pred,gold,known));runs.append(result);predictions.append(pred);print(json.dumps(result),flush=True)
    best=max(range(len(runs)),key=lambda i:runs[i]['metrics']['block']['f05'])
    result=dict(split='dev_only',test_evaluated=False,runs=runs,selected=runs[best])
    (d/experiment/'selection-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    (d/experiment/'selection-predictions.json').write_text(json.dumps(predictions[best],ensure_ascii=False,indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',default='local-data/cities');p.add_argument('--experiment',choices=['refinement','refinement-morphology'],default='refinement');a=p.parse_args();run(a.data,a.experiment)
