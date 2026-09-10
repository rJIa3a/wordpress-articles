from .data import load_json
"""Pretrained multilingual semantic features on the fixed dev-only experiment."""
import argparse,json
from pathlib import Path
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from .ranking import relative_features
from .sentences import sentence_span
from .experiment import select,metrics
from interlinker.retrieval import MiniLM

def run(folder):
 d=Path(folder);cache=d/'refinement-sentences';a=np.load(cache/'training-features.npz');X,y,train=a['X'],a['y'],a['train'];records=json.loads((cache/'training-records.json').read_text());split=json.loads((d/'manifest.json').read_text())['source_split']
 if any(split[r['source']] not in ('train','dev') or bool(train[i])!=(split[r['source']]=='train') for i,r in enumerate(records)):raise ValueError('Invalid split')
 pages=json.loads((d/'corpus.json').read_text());by={p['url']:i for i,p in enumerate(pages)};blocks={(p['url'],b['id']):b for p in pages for b in p['blocks']}
 model=MiniLM();progress_dir=d/'refinement-neural';progress_dir.mkdir(exist_ok=True)
 def embed(texts,label):
  chunks=[]
  for start in range(0,len(texts),64):
   chunks.append(model.encode(texts[start:start+64]));(progress_dir/'progress.json').write_text(json.dumps(dict(stage=label,completed=min(start+64,len(texts)),total=len(texts),finished=False)));print(label,min(start+64,len(texts)),len(texts),flush=True)
  return np.vstack(chunks)
 docs=[p['title']+'. '+' '.join(b['text'] for b in p['blocks'][:2])[:400] for p in pages];targets=embed(docs,'targets');texts=[]
 for r in records:
  b=blocks[r['source'],r['block']];start,end=sentence_span(b['text'],r['start'],r['end'])
  # Center long sentences on the mention rather than truncating away the entity.
  start=max(start,r['start']-180);end=min(end,r['end']+180)
  texts.append(b['section'][:80]+'. '+b['text'][start:end])
 unique=list(dict.fromkeys(texts));vectors=embed(unique,'contexts');lookup={t:i for i,t in enumerate(unique)}
 similarity=np.array([float(vectors[lookup[t]]@targets[by[r['target']]]) for t,r in zip(texts,records)])
 out=d/'refinement-neural';out.mkdir(exist_ok=True);np.save(out/'semantic.npy',similarity)
 gold=[g for g in load_json(d/'gold.json') if split[g['source']]=='dev'];dev=~train;dr=[r for r,t in zip(records,dev) if t];runs=[];preds=[]
 for name,features in [('relative_baseline',relative_features(X,records)),('relative_neural',relative_features(np.column_stack([X,similarity]),records))]:
  m=HistGradientBoostingClassifier(max_iter=250,max_leaf_nodes=15,min_samples_leaf=60,l2_regularization=20,learning_rate=.06,early_stopping=False,random_state=17);m.fit(features[train],y[train]);scores=m.predict_proba(features[dev])[:,1]
  for threshold in [.35,.5,.65]:
   pred=select(dr,scores,threshold);result=dict(name=name,threshold=threshold,metrics=metrics(pred,gold,set(by)));runs.append(result);preds.append(pred);print('RESULT',json.dumps(result),flush=True)
 best=max(range(len(runs)),key=lambda i:runs[i]['metrics']['block']['f05'])
 (out/'results.json').write_text(json.dumps(dict(split='dev_only',test_evaluated=False,provider='multilingual-MiniLM-L12-v2',unique_contexts=len(unique),runs=runs,selected=runs[best]),ensure_ascii=False,indent=2));(out/'predictions.json').write_text(json.dumps(preds[best],ensure_ascii=False,indent=2));(out/'progress.json').write_text(json.dumps(dict(finished=True,stage='evaluated_dev')))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--data',default='local-data/cities');a=p.parse_args();run(a.data)
