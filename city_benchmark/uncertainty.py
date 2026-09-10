"""Paired article bootstrap: descriptive uncertainty, not independent validation."""
import argparse,json
from pathlib import Path
import numpy as np

def counts_by_source(pred,gold,sources):
    ps={u:set() for u in sources};gs={u:set() for u in sources}
    for rows,dest in [(pred,ps),(gold,gs)]:
        for r in rows:
            if r['source'] in dest:dest[r['source']].add((r['block'],r['target']))
    return np.array([[len(ps[u]&gs[u]),len(ps[u]),len(gs[u])] for u in sources],dtype=float)

def measures(counts):
    hits,pred,gold=counts.T
    precision=hits/np.maximum(1,pred);recall=hits/np.maximum(1,gold)
    return np.stack([precision,recall,1.25*precision*recall/np.maximum(1e-12,.25*precision+recall)],axis=-1)

def run(folder):
    d=Path(folder);split=json.loads((d/'manifest.json').read_text())['source_split'];sources=sorted(u for u,s in split.items() if s=='dev')
    known={p['url'] for p in json.loads((d/'corpus.json').read_text())};gold=[g for g in json.loads((d/'gold.json').read_text()) if g['target'] in known and g['source']!=g['target']]
    before=json.loads((d/'refinement-morphology/predictions.json').read_text());after=json.loads((d/'refinement-sentences/predictions.json').read_text())
    if any(split[r['source']]!='dev' for r in before+after):raise ValueError('Dev only')
    a=counts_by_source(before,gold,sources);b=counts_by_source(after,gold,sources)
    rng=np.random.default_rng(17);idx=rng.integers(0,len(sources),size=(2000,len(sources)))
    deltas=measures(b[idx].sum(axis=1))-measures(a[idx].sum(axis=1))
    point=measures(b.sum(axis=0)[None,:])[0]-measures(a.sum(axis=0)[None,:])[0]
    result=dict(split='dev_only',resamples=2000,unit='source_article',caveat='Descriptive only: models selected on this dev set; articles may be topically dependent. Not a new holdout.',delta={name:dict(point=float(point[i]),interval95=np.quantile(deltas[:,i],[.025,.975]).tolist()) for i,name in enumerate(['precision','recall','f05'])})
    (d/'refinement-sentences/uncertainty.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',default='local-data/cities');a=p.parse_args();run(a.data)
