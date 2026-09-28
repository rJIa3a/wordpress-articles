from .data import load_json
"""Competing mention ranking; original links are used on train only for fitting."""
import argparse,collections,json
from pathlib import Path
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from .experiment import select,metrics

def groups(records):
    out=collections.defaultdict(list)
    for i,r in enumerate(records):out[r['source'],r['target']].append(i)
    return out

def relative_features(X,records):
    result=np.zeros((len(X),X.shape[1]*2))
    for ids in groups(records).values():
        values=X[ids];result[ids,:X.shape[1]]=values-values.max(axis=0)
        result[ids,X.shape[1]:]=values-values.mean(axis=0)
    return np.hstack([X,result])

def pairwise_training(X,y,records,train):
    differences=[]
    for ids in groups(records).values():
        pos=[i for i in ids if train[i] and y[i]];neg=[i for i in ids if train[i] and not y[i]]
        # Deterministic bounded comparisons stop long articles dominating training.
        for i in pos[:8]:
            for j in neg[:8]:differences.append(X[i]-X[j])
    if not differences:raise ValueError('No within-page training comparisons')
    diffs=np.array(differences)
    return np.vstack([diffs,-diffs]),np.r_[np.ones(len(diffs)),np.zeros(len(diffs))]

def rerank(records,probability,preference,threshold,blend):
    scored=[]
    for ids in groups(records).values():
        if max(probability[ids])<threshold:continue
        candidates=[i for i in ids if probability[i]>=.15]
        if not candidates:continue
        pref=preference[candidates];pref=(pref-pref.mean())/(pref.std()+1e-8)
        logits=np.log(np.clip(probability[candidates],1e-6,1-1e-6)/(1-np.clip(probability[candidates],1e-6,1-1e-6)))
        i=candidates[int(np.argmax(logits+blend*pref))]
        scored.append((records[i],max(probability[ids])))
    return select([r for r,_ in scored],np.array([s for _,s in scored]),threshold)

def run(folder):
    d=Path(folder);cache=d/'refinement-sentences';a=np.load(cache/'training-features.npz');X,y,train=a['X'],a['y'],a['train'];records=json.loads((cache/'training-records.json').read_text())
    split=json.loads((d/'manifest.json').read_text())['source_split']
    if any(split[r['source']] not in ('train','dev') or bool(train[i])!=(split[r['source']]=='train') for i,r in enumerate(records)):raise ValueError('Invalid split')
    known={p['url'] for p in json.loads((d/'corpus.json').read_text())};gold=[g for g in load_json(d/'gold.json') if split[g['source']]=='dev'];dev=~train;dr=[r for r,t in zip(records,dev) if t];runs=[];preds=[]
    def record(name,threshold,pred):
        result=dict(name=name,threshold=threshold,metrics=metrics(pred,gold,known));runs.append(result);preds.append(pred);print(name,threshold,json.dumps(result['metrics']['block']),flush=True)
    def model(leaves=7,iterations=150):return HistGradientBoostingClassifier(max_iter=iterations,max_leaf_nodes=leaves,min_samples_leaf=60,l2_regularization=20,learning_rate=.06,early_stopping=False,random_state=17)
    base=model();base.fit(X[train],y[train]);prob=base.predict_proba(X[dev])[:,1]
    for threshold in [.35,.5,.65]:record('baseline',threshold,select(dr,prob,threshold))
    scaler=StandardScaler().fit(X[train]);scaled=scaler.transform(X)
    px,py=pairwise_training(scaled,y,records,train);pair=LogisticRegression(C=.1,max_iter=1000,fit_intercept=False,random_state=17).fit(px,py);preference=pair.decision_function(scaled[dev])
    for blend in [.25,.5,1]:record('pairwise_'+str(blend),.5,rerank(dr,prob,preference,.5,blend))
    larger=model(15,250);larger.fit(X[train],y[train]);larger_scores=larger.predict_proba(X[dev])[:,1]
    for threshold in [.35,.5,.65]:record('baseline_large',threshold,select(dr,larger_scores,threshold))
    relative=relative_features(X,records)
    for leaves,iterations in [(7,150),(15,250)]:
        m=model(leaves,iterations);m.fit(relative[train],y[train]);scores=m.predict_proba(relative[dev])[:,1]
        for threshold in [.35,.5,.65]:record('relative_'+str(leaves),threshold,select(dr,scores,threshold))
    best=max(range(len(runs)),key=lambda i:runs[i]['metrics']['block']['f05']);out=d/'refinement-ranking';out.mkdir(exist_ok=True)
    result=dict(split='dev_only',test_evaluated=False,train_pair_comparisons=len(py),runs=runs,selected=runs[best],method='Pairwise train-only preference and within-source-target relative features. Dev chooses F0.5; no independent validation.')
    (out/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));(out/'predictions.json').write_text(json.dumps(preds[best],ensure_ascii=False,indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',default='local-data/cities');a=p.parse_args();run(a.data)
