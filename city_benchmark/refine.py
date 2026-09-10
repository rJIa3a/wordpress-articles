"""Development-only experiments. Never evaluates or emits test predictions."""
import argparse, collections, hashlib, json, re
from pathlib import Path
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from .experiment import candidates, metrics, select, words, FEATURES
from interlinker.entities import noncity_name

EXTRA = ['mention_position','block_length','section_first_mention','log_occurrence',
         'transport','distance','biography','sport','institution','geography_local',
         'history_local','quoted_name','section_transport','section_people',
         'section_economy','section_culture','context_tfidf','target_mentions','noncity_name','list_block']

def local_features(record, text, section, occurrence, section_occurrence, count):
    start,end=record['start'],record['end']
    around=text[max(0,start-130):end+130].lower()
    def has(pattern): return int(bool(re.search(pattern,around)))
    s=section.lower()
    return [start/max(1,len(text)), min(3,np.log1p(len(text))/5),int(section_occurrence==1),
            np.log1p(occurrence),has(r'поезд|железнодорож|автобус|аэропорт|маршрут|трасс|дорог'),
            has(r'\bкм\b|километр|расстояни|север|южн|запад|восток'),
            has(r'родил|умер|похорон|окончил|учился'),has(r'футбол|хоккей|клуб|чемпион|команд'),
            has(r'университет|институт|завод|предприят|компани'),
            has(r'располож|находится|границ|област|район|берег'),
            has(r'войн|век|основан|импери|сражен'),
            int(start>0 and text[start-1] in '«"'),int('транспорт' in s),
            int(any(x in s for x in ['известн','персон','люди','урожен'])),
            int('эконом' in s),int(any(x in s for x in ['культур','спорт','образован'])),
            0,np.log1p(count),int(noncity_name(text,start)),int(text.count('\n')>=4)]

def development_data(pages,gold,split,geographic=False):
    # Test article contents can be target documents, but never source examples or labels.
    sources={u for u,s in split.items() if s in ('train','dev')}
    safe_gold=[g for g in gold if g['source'] in sources]
    records,texts=candidates(pages,[g for g in safe_gold if split[g['source']]=='train'],split,geographic)
    return [r for r in records if r['source'] in sources],texts,safe_gold

def run(folder,geographic=False,sentence_context=False):
    d=Path(folder);pages=json.loads((d/'corpus.json').read_text());manifest=json.loads((d/'manifest.json').read_text())
    if not manifest['complete']:raise ValueError('Corpus incomplete')
    split=manifest['source_split'];gold=json.loads((d/'gold.json').read_text())
    records,texts,gold=development_data(pages,gold,split,geographic)
    output_name='refinement-sentences' if sentence_context else 'refinement-morphology' if geographic else 'refinement'
    print('Train/dev candidates:',len(records),flush=True)
    by={p['url']:p for p in pages};pidx={p['url']:i for i,p in enumerate(pages)}
    blocks={(p['url'],b['id']):b for p in pages for b in p['blocks']}
    docs=[p['title']+' '+' '.join(b['text'] for b in p['blocks'][:3])[:1600] for p in pages]
    v=TfidfVectorizer(max_features=30000,ngram_range=(1,2));pv=v.fit_transform(docs)
    used=sorted({r['blockkey'] for r in records});bi={b:i for i,b in enumerate(used)};bv=v.transform([texts[b] for b in used])
    windows=[blocks[r['source'],r['block']]['text'][max(0,r['start']-240):r['end']+240] for r in records]
    wv=v.transform(windows);counts=collections.Counter((r['source'],r['target']) for r in records)
    occurrence=collections.Counter();section_occurrence=collections.Counter();features=[]
    for i,r in enumerate(records):
        b=blocks[r['source'],r['block']];pi=pidx[r['target']]
        r['features'][0]=float(bv[bi[r['blockkey']]].multiply(pv[pi]).sum())
        pair=(r['source'],r['target']);sp=pair+(b['section'],);occurrence[pair]+=1;section_occurrence[sp]+=1
        f=local_features(r,b['text'],b['section'],occurrence[pair],section_occurrence[sp],counts[pair])
        f[16]=float(wv[i].multiply(pv[pi]).sum());features.append(r['features'][:8]+f)
    if sentence_context:
        from .sentences import sentence_span,sentence_features
        fragments=[]
        for r in records:
            text=blocks[r['source'],r['block']]['text'];a,z=sentence_span(text,r['start'],r['end']);fragments.append(text[a:z])
        sv=v.transform(fragments)
        for i,r in enumerate(records):
            text=blocks[r['source'],r['block']]['text'];extra=sentence_features(text,r['start'],r['end'])
            extra[-1]=float(sv[i].multiply(pv[pidx[r['target']]]).sum());features[i].extend(extra)
    X=np.array(features);truth={(g['source'],g['block'],g['target']) for g in gold}
    y=np.array([(r['source'],r['block'],r['target']) in truth for r in records],dtype=int)
    train=np.array([split[r['source']]=='train' for r in records]);dev=~train
    dr=[r for r,t in zip(records,dev) if t];dg=[g for g in gold if split[g['source']]=='dev'];runs=[];predictions={}
    configs=[('baseline_logistic',LogisticRegression(C=.5,max_iter=1000,random_state=17),8),
             ('context_logistic',LogisticRegression(C=.5,max_iter=1000,random_state=17),28),
             ('context_trees',HistGradientBoostingClassifier(max_iter=150,max_leaf_nodes=7,min_samples_leaf=60,l2_regularization=20,learning_rate=.06,early_stopping=False,random_state=17),26),
             ('entity_context_trees',HistGradientBoostingClassifier(max_iter=150,max_leaf_nodes=7,min_samples_leaf=60,l2_regularization=20,learning_rate=.06,early_stopping=False,random_state=17),28)]
    if sentence_context:configs.append(('sentence_context_trees',HistGradientBoostingClassifier(max_iter=150,max_leaf_nodes=7,min_samples_leaf=60,l2_regularization=20,learning_rate=.06,early_stopping=False,random_state=17),X.shape[1]))
    score_sets={}
    for name,model,n in configs:
        model.fit(X[train,:n],y[train]);scores=model.predict_proba(X[dev,:n])[:,1];score_sets[name]=scores
        for threshold in [.35,.5,.65,.8]:
            pred=select(dr,scores,threshold);m=metrics(pred,dg,set(by))
            run=dict(name=name,threshold=threshold,metrics=m);runs.append(run);predictions[(name,threshold)]=pred
            print(name,threshold,json.dumps(m['block']),flush=True)
    best=max(runs,key=lambda x:x['metrics']['block']['f05']);scores=score_sets[best['name']]
    (d/output_name).mkdir(exist_ok=True)
    (d/output_name/'scored-dev.json').write_text(json.dumps([dict(r,score=float(score),section=blocks[r['source'],r['block']]['section']) for r,score in zip(dr,scores)],ensure_ascii=False))
    best=max(runs,key=lambda x:x['metrics']['block']['f05']);pred=predictions[best['name'],best['threshold']]
    out=d/output_name;out.mkdir(exist_ok=True)
    result=dict(sentence_context=sentence_context,geographic_morphology=geographic,split='dev_only',source_articles=sum(s=='dev' for s in split.values()),train_articles=sum(s=='train' for s in split.values()),features=FEATURES[:8]+EXTRA+(['sentence_position','sentence_fraction','parenthetical','capitalized_words','sentence_tfidf'] if sentence_context else []),runs=runs,selected=best,test_evaluated=False,corpus_sha256=hashlib.sha256((d/'corpus.json').read_bytes()).hexdigest())
    (out/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    (out/'predictions.json').write_text(json.dumps(pred,ensure_ascii=False,indent=2))
    # Deterministic disagreements for manual review on dev only.
    errors=[]
    for r in sorted(pred,key=lambda r:(-r['score'],r['source'])):
        if (r['source'],r['block'],r['target']) not in truth:
            b=blocks[r['source'],r['block']]
            errors.append(dict(source=by[r['source']]['title'],target=by[r['target']]['title'],section=b['section'],text=b['text'],anchor=r['anchor'],score=r['score']))
    (out/'errors.json').write_text(json.dumps(errors[:40],ensure_ascii=False,indent=2))
    print('SELECTED',json.dumps(best),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data',default='local-data/cities');parser.add_argument('--city-morphology',action='store_true');parser.add_argument('--sentence-context',action='store_true');args=parser.parse_args();run(args.data,args.city_morphology,args.sentence_context)
