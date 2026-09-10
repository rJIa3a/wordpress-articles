"""Train on hidden-link reconstruction; dev chooses threshold; test is never tuned."""
import argparse,collections,hashlib,json,re,html
from pathlib import Path
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import normalize
from interlinker.retrieval import lemma,STOP,MiniLM

def words(text,geographic=False):
 from interlinker.city_morphology import city_lemma
 normalizer=city_lemma if geographic else lemma
 return [(m.group(),m.start(),m.end(),normalizer(m.group().casefold())) for m in re.finditer(r'[А-Яа-яЁёA-Za-z]+(?:-[А-Яа-яЁёA-Za-z]+)*',text)]
def key(text,geographic=False):return tuple(w[3] for w in words(text,geographic))
BANNED={'город','столица','область','район','россия','центр','страна','посёлок','городок','республика','он','она','здесь','там'}
FEATURES=['tfidf_context','early_in_page','first_target_mention','alias_words','unambiguous','train_anchor_frequency','history_section','geography_section','neural_context']

def candidates(pages,gold,split,geographic=False):
 registry=collections.defaultdict(set);known={p['url'] for p in pages};freq=collections.Counter()
 for p in pages:
  k=key(re.sub(r'\s*\([^)]*\)','',p['title']),geographic)
  if k:registry[k].add(p['url'])
 for g in gold:
  if split.get(g['source'])!='train' or g['target'] not in known:continue
  k=key(g['anchor'],geographic)
  if k and len(k)<=5 and not (set(k)&BANNED) and not any(w in STOP for w in k):freq[(k,g['target'])]+=1
 for (k,t),n in freq.items():
  if n>=2:registry[k].add(t)
 maxwords=min(5,max(map(len,registry)));records=[];texts={};counts=collections.Counter()
 for p in pages:
  occurrence=collections.Counter()
  for bi,b in enumerate(p['blocks']):
   ws=words(b['text'],geographic);i=0;blockkey=p['url']+'#'+b['id'];texts[blockkey]=b['section']+'\n'+b['text'][:1600]
   while i<len(ws):
    found=False
    for size in range(min(maxwords,len(ws)-i),0,-1):
     k=tuple(w[3] for w in ws[i:i+size]);targets=registry.get(k)
     if not targets:continue
     start,end=ws[i][1],ws[i+size-1][2];anchor=b['text'][start:end]
     if re.search(r'[,:;.!?\n]',anchor):continue
     # Capitalization avoids many common-noun/name collisions (e.g. орёл).
     if not ws[i][0][0].isupper():continue
     for target in sorted(targets):
      if target==p['url']:continue
      occurrence[target]+=1
      records.append(dict(source=p['url'],target=target,block=b['id'],blockkey=blockkey,start=start,end=end,anchor=anchor,features=[0,1-bi/max(1,len(p['blocks'])),int(occurrence[target]==1),min(1,size/3),int(len(targets)==1),min(1,np.log1p(freq[(k,target)])/5),int('истори' in b['section'].lower()),int('географ' in b['section'].lower()),0]))
     i+=size;found=True;break
    if not found:i+=1
 return records,texts

def metrics(pred,gold,known):
 g=[x for x in gold if x['target'] in known and x['source']!=x['target']]
 out={'suggestions':len(pred),'all_wikipedia_links':len(gold),'city_links':len(g)}
 for level in ['edge','block','span']:
  def k(r):return (r['source'],r['target'])+(() if level=='edge' else (r['block'],))+((r['start'],r['end']) if level=='span' else ())
  ps={k(x) for x in pred};gs={k(x) for x in g};hit=len(ps&gs);p=hit/max(1,len(ps));rec=hit/max(1,len(gs))
  out[level]=dict(hits=hit,predicted=len(ps),gold=len(gs),precision=p,recall=rec,f05=1.25*p*rec/max(1e-12,.25*p+rec))
 return out

def select(records,scores,threshold):
 selected=[];seen=set();spans=collections.defaultdict(list)
 for i in sorted(range(len(records)),key=lambda i:(-scores[i],records[i]['source'],int(records[i]['block']),records[i]['start'])):
  if scores[i]<threshold:continue
  r=records[i];pair=(r['source'],r['target']);b=(r['source'],r['block'])
  if pair in seen or any(r['start']<e and r['end']>s for s,e in spans[b]):continue
  seen.add(pair);spans[b].append((r['start'],r['end']));selected.append({k:v for k,v in r.items() if k!='features'}|{'score':round(float(scores[i])*100,2)})
 return selected

def run(folder,provider='minilm'):
 d=Path(folder);pages=json.loads((d/'corpus.json').read_text());gold=json.loads((d/'gold.json').read_text());manifest=json.loads((d/'manifest.json').read_text())
 if not manifest['complete']:raise ValueError('Corpus incomplete; refusing misleading benchmark')
 split=manifest['source_split'];by={p['url']:p for p in pages};known=set(by)
 records,texts=candidates(pages,gold,split);print('Candidate mentions:',len(records),'block contexts:',len({r['blockkey'] for r in records}),flush=True)
 used=sorted({r['blockkey'] for r in records});lookup={b:i for i,b in enumerate(used)};pidx={p['url']:i for i,p in enumerate(pages)}
 docs=[p['title']+' '+ ' '.join(b['text'] for b in p['blocks'][:3])[:1600] for p in pages]
 v=TfidfVectorizer(max_features=30000,ngram_range=(1,2));pv=v.fit_transform(docs);bv=v.transform([texts[b] for b in used])
 semantic=None
 if provider=='minilm':
  content_hash=hashlib.sha256(('\0'.join(docs+[texts[b] for b in used])).encode()).hexdigest()[:20];cache=d/('embeddings-'+content_hash+'.npz')
  if cache.exists():
   arr=np.load(cache);pe,be=arr['pages'],arr['blocks']
  else:
   model=MiniLM();pe=model.encode(docs);print('Target embeddings ready',flush=True);chunks=[]
   for start in range(0,len(used),128):
    chunks.append(model.encode([texts[b] for b in used[start:start+128]]));print('Context embeddings',min(start+128,len(used)),'/',len(used),flush=True)
   be=np.vstack(chunks);np.savez_compressed(cache,pages=pe,blocks=be)
  semantic=(pe,be)
 for r in records:
  pi=pidx[r['target']];bi=lookup[r['blockkey']];r['features'][0]=float(bv[bi].multiply(pv[pi]).sum())
  if semantic:r['features'][-1]=max(0,float(pe[pi]@be[bi]))
 X=np.array([r['features'] for r in records]);truth={(g['source'],g['block'],g['target']) for g in gold if g['target'] in known};y=np.array([(r['source'],r['block'],r['target']) in truth for r in records],dtype=int)
 train=np.array([split[r['source']]=='train' for r in records]);dev=np.array([split[r['source']]=='dev' for r in records]);test=np.array([split[r['source']]=='test' for r in records])
 configurations=[]
 baseline=np.array([.7 if r['features'][2] else .3 for r in records]);configurations.append(('names_first_mention',baseline,0.5,None))
 for name,cols in [('context_lexical',list(range(8)))]+([('context_neural',list(range(9)))] if semantic else []):
  model=LogisticRegression(C=.5,max_iter=1000,random_state=17);model.fit(X[train][:,cols],y[train]);scores=model.predict_proba(X[:,cols])[:,1]
  for threshold in [.35,.5,.65,.8]:configurations.append((name,scores,threshold,{'features':[FEATURES[c] for c in cols],'coefficients':model.coef_[0].tolist(),'intercept':model.intercept_[0]}))
 dev_records=[r for r,flag in zip(records,dev) if flag];dev_gold=[g for g in gold if split.get(g['source'])=='dev'];runs=[]
 for name,scores,threshold,coeff in configurations:
  pred=select(dev_records,scores[dev],threshold);m=metrics(pred,dev_gold,known);runs.append(dict(name=name,threshold=threshold,metrics=m,model=coeff));print('DEV',name,threshold,json.dumps(m['block']),flush=True)
 best=max(range(len(runs)),key=lambda i:runs[i]['metrics']['block']['f05']);name,scores,threshold,coeff=configurations[best]
 test_records=[r for r,flag in zip(records,test) if flag];test_gold=[g for g in gold if split.get(g['source'])=='test'];pred=select(test_records,scores[test],threshold);m=metrics(pred,test_gold,known)
 result=dict(provider=provider,articles=len(pages),split_counts=dict(collections.Counter(split.values())),train_candidates=int(train.sum()),dev=runs,selected=runs[best],test=m,feature_names=FEATURES,method='Aliases learned on train only. Article-disjoint deterministic split. Threshold/model selected on dev block F0.5. Test evaluated after freezing selection. Positive labels reflect Wikipedia, not complete link utility.')
 (d/'city-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));(d/'city-predictions.json').write_text(json.dumps(pred,ensure_ascii=False,indent=2))
 print('TEST',json.dumps(m),flush=True)
 report(d,result,pred,by,test_gold)

def report(d,result,pred,by,gold):
 esc=html.escape;cards=[];truth={(g['source'],g['block'],g['target']) for g in gold};sample=sorted(pred,key=lambda r:hashlib.sha256((r['source']+r['target']).encode()).hexdigest())[:100]
 for r in sample:
  p=by[r['source']];b=next(b for b in p['blocks'] if b['id']==r['block']);text=b['text'];a,z=r['start'],r['end'];annot=esc(text[:a])+'<mark>'+esc(text[a:z])+'</mark>'+esc(text[z:]);gs=[g for g in gold if g['source']==r['source'] and g['block']==r['block'] and g['target'] in by]
  original='; '.join(esc(g['anchor'])+' → '+esc(by[g['target']]['title']) for g in gs)
  cards.append(f'<article><h2>{esc(p["title"])} → {esc(by[r["target"]]["title"])}</h2><p>{"Совпало по абзацу и цели" if (r["source"],r["block"],r["target"]) in truth else "Нет совпадения: требуется ручная оценка"} · score {r["score"]}</p><p>{annot}</p><p>Оригинальные ссылки на города: {original or "нет"}</p><a href="{esc(r["source"])}">Источник и авторство</a></article>')
 (d/'city-comparison.html').write_text('<meta charset="utf-8"><title>Городская перелинковка</title><style>body{font:17px/1.6 system-ui;max-width:1050px;margin:auto;padding:30px;background:#edf3f5}article{background:white;padding:25px;margin:20px 0}mark{background:#bfe9d9}a{color:#00665d}</style><h1>Проверка на новых статьях</h1><p>Первые 100 предложений из детерминированной выборки. CC BY-SA 4.0, авторы Wikipedia; шаблоны и источники удалены.</p>'+''.join(cards))
 lines=['# Городской benchmark Universal Interlinker\n',f"Статей: {result['articles']}; разбиение: {result['split_counts']}; embeddings: {result['provider']}.\n",'|Вариант / dev|Порог|Предложений|Precision абзац+цель|Recall абзац+цель|','|---|---:|---:|---:|---:|']
 for r in result['dev']:
  m=r['metrics'];lines.append(f"|{r['name']}|{r['threshold']}|{m['suggestions']}|{m['block']['precision']:.1%}|{m['block']['recall']:.1%}|")
 lines+=['\n## Независимый test\n',json.dumps(result['test'],ensure_ascii=False,indent=2),'\n## Ограничения\n','- Оцениваются ссылки между городами из корпуса. Все остальные ссылки сохранены в gold, но их цели не входят в задачу.','- Википедия — неполный редакционный эталон: отсутствие ссылки не доказывает, что предложение бесполезно.','- Тексты очищены от шаблонов, таблиц, примечаний и источников; это не побайтовая копия отрендеренной статьи.','- Названия и алиасы дают shortlist целей. Контекстная лексика и neural embeddings ранжируют упоминания; LLM для этого прогона не используется.','- Алиасы извлечены только из train. Разбиение по статьям, а не по географическим регионам: тематическая зависимость остается.','- Нельзя повторно настраивать модель по просмотренному test. Для следующего цикла нужен новый holdout.','- Совпадение с Википедией не является подтверждением роста позиций сайта.']
 (d/'CITY_REPORT.md').write_text('\n'.join(lines))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--data',default='local-data/cities');p.add_argument('--provider',choices=['lexical','minilm'],default='minilm');a=p.parse_args();run(a.data,a.provider)
