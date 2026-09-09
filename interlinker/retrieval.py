"""No gold annotations imported. All candidate/anchor features derive from clean text."""
import json, re
from functools import lru_cache
import pymorphy3
MORPH=pymorphy3.MorphAnalyzer()
@lru_cache(maxsize=30000)
def lemma(word):
    return MORPH.parse(word.lower())[0].normal_form
def lemmas(text):
    return {lemma(w) for w in re.findall(r"\w+",text.lower()) if len(w)>1 and w not in STOP and not w.isdigit()}
from urllib.request import Request,urlopen
from collections import Counter
import numpy as np
from nltk.stem.snowball import RussianStemmer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import normalize
STEM=RussianStemmer()
STOP=set('и в на с по для из к от а но или это как что при до не его ее их во также который которые быть может'.split())
def tokens(text):
    return [STEM.stem(w) for w in re.findall(r'[\w]+',text.lower()) if len(w)>1 and w not in STOP and not w.isdigit()]

class LSA:
    """Local latent-semantic baseline, NOT pretrained neural embeddings."""
    name='lsa-local'
    def fit(self,texts):
        self.v=TfidfVectorizer(tokenizer=tokens,token_pattern=None,max_features=30000)
        x=self.v.fit_transform(texts)
        self.svd=TruncatedSVD(n_components=max(1,min(64,x.shape[0]-1,x.shape[1]-1)),random_state=42)
        self.svd.fit(x)
        return normalize(self.svd.transform(x))
    def encode(self,texts):return normalize(self.svd.transform(self.v.transform(texts)))

class Ollama:
    name='ollama'
    def __init__(self,base='http://localhost:11434',model='qwen3-embedding:0.6b'):
        self.base=base;self.model=model
    def encode(self,texts):
        vectors=[]
        for start in range(0,len(texts),16):
            req=Request(self.base+'/api/embed',data=json.dumps({'model':self.model,'input':texts[start:start+16]}).encode(),headers={'Content-Type':'application/json'})
            with urlopen(req,timeout=180) as r:vectors.extend(json.load(r)['embeddings'])
        return normalize(np.array(vectors))
    def fit(self,texts):return self.encode(texts)

class MiniLM:
    name='minilm'
    def __init__(self):
        from fastembed import TextEmbedding
        self.model=TextEmbedding('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2',cache_dir='local-data/models',threads=2)
    def encode(self,texts):
        import hashlib,sqlite3
        from pathlib import Path
        from importlib.metadata import version
        Path('local-data').mkdir(exist_ok=True)
        namespace=str(self.model.model._model_dir)+version('fastembed')
        keys=[hashlib.sha256((namespace+'\0'+t).encode()).hexdigest() for t in texts]
        with sqlite3.connect('local-data/embeddings.sqlite3',timeout=60) as c:
            c.execute('CREATE TABLE IF NOT EXISTS vectors(key TEXT PRIMARY KEY, data BLOB NOT NULL)')
            found={}
            for k in set(keys):
                row=c.execute('SELECT data FROM vectors WHERE key=?',(k,)).fetchone()
                if row:found[k]=np.frombuffer(row[0],dtype=np.float32)
            missing={k:t for k,t in zip(keys,texts) if k not in found}
            ordered=sorted(missing,key=lambda k:len(missing[k]))
            for start in range(0,len(ordered),32):
                group=ordered[start:start+32]
                vectors=list(self.model.embed([missing[k] for k in group],batch_size=32))
                for k,v in zip(group,vectors):
                    found[k]=np.asarray(v,dtype=np.float32)
                    c.execute('INSERT OR IGNORE INTO vectors(key,data) VALUES(?,?)',(k,found[k].tobytes()))
                c.commit()
        return normalize(np.array([found[k] for k in keys]))
    def fit(self,texts):return self.encode(texts)

class Engine:
    def __init__(self,pages,provider=None):
        self.pages=pages;self.provider=provider or LSA()
        self.docs=[p['title']+' '+p['title']+' '+ ' '.join(b['text'] for b in p['blocks'])[:12000] for p in pages]
        # Block-level semantic indexing, max 16 chunks per target.
        self.units=[];self.owner=[]
        for i,p in enumerate(pages):
            self.units.append(p['title']+' '+self.docs[i][:1200]);self.owner.append(i)
            for b in p['blocks'][:16]:
                self.units.append(p['title']+' '+b['section']+' '+b['text'][:1500]);self.owner.append(i)
        self.vectors=self.provider.fit(self.units)
        self.counts=[Counter(tokens(d)) for d in self.docs]
        self.length=np.array([sum(c.values()) for c in self.counts]);self.avg=max(1,self.length.mean())
        df=Counter(t for c in self.counts for t in c)
        self.idf={t:float(np.log(1+(len(pages)-n+.5)/(n+.5))) for t,n in df.items()}
        self.title_tokens=[set(tokens(p.get('entity_name',p['title']))) for p in pages]
        self.entities=[set(re.findall(r'\b[A-ZА-ЯЁ][A-ZА-ЯЁ\d-]{1,}\b',d)) for d in self.docs]
        self.query_cache={}
    def retrieve(self,source,block,mode='hybrid',k=20):
        text=block['section']+' '+block['text'];q=set(tokens(text))
        bm=np.array([sum(self.idf.get(t,0)*c.get(t,0)*2.5/(c.get(t,0)+1.5*(.25+.75*l/self.avg)) for t in q) for c,l in zip(self.counts,self.length)])
        bm=bm/(bm.max()+1e-9)
        key=(source['url'],block['id'])
        if key not in self.query_cache:
            sims=self.vectors@self.provider.encode([text])[0]
            sem=np.zeros(len(self.pages))
            for i,v in zip(self.owner,sims):sem[i]=max(sem[i],float(v))
            self.query_cache[key]=sem
        sem=self.query_cache[key]
        entities=set(re.findall(r'\b[A-ZА-ЯЁ][A-ZА-ЯЁ\d-]{1,}\b',text))
        candidates=[]
        for i,p in enumerate(self.pages):
            if p['url']==source['url']:continue
            keyword=len(q & self.title_tokens[i])/max(1,len(self.title_tokens[i]))
            entity=len(entities & self.entities[i])/max(1,len(entities))
            taxonomy=len(set(source['categories']) & set(p['categories']))/max(1,len(set(source['categories'])|set(p['categories'])))
            comp=dict(semantic=float(sem[i]),bm25=float(bm[i]),keyword=keyword,entity=entity,taxonomy=taxonomy)
            score=(.65*bm[i]+.35*keyword) if mode=='lexical' else (.45*sem[i]+.30*bm[i]+.18*keyword+.04*entity+.03*taxonomy)
            candidates.append(dict(target=p['url'],index=i,retrieval=float(score),components=comp))
        return sorted(candidates,key=lambda c:-c['retrieval'])[:k]
    def anchor(self,text,target_index):
        expected=lemmas(self.pages[target_index].get('entity_name',self.pages[target_index]['title']))
        words=list(re.finditer(r'\w+',text));best=None
        stems=[lemmas(w.group()) for w in words]
        for i in range(len(words)):
            for n in range(1,min(7,len(words)-i)+1):
                start,end=words[i].start(),words[i+n-1].end(); phrase=text[start:end]
                if words[i].group().lower() in STOP or words[i+n-1].group().lower() in STOP:continue
                if re.search(r'[,;:.!?\n]',phrase):continue
                ts=set().union(*stems[i:i+n]); overlap=ts&expected
                if not overlap:continue
                precision=len(overlap)/max(1,len(ts));recall=len(overlap)/max(1,len(expected))
                quality=2*precision*recall/max(1e-9,precision+recall)
                if not best or quality>best['quality']:
                    best=dict(anchor=phrase,start=start,end=end,quality=quality,type='natural')
        return best
    def recommend(self,source,mode='hybrid',threshold=.65,semantic_min=.25):
        options=[];retrieved=[];rejections=Counter()
        for b in source['blocks']:
            candidates=self.retrieve(source,b,mode)
            retrieved.append(dict(source=source['url'],block=b['id'],targets=[c['target'] for c in candidates]))
            for c in candidates:
                a=self.anchor(b['text'],c['index'])
                if not a or a['quality']<.65:rejections['weak_or_missing_anchor']+=1;continue
                from .geography import intent_allowed
                if not intent_allowed(b['text'],self.pages[c['index']],a['anchor']):rejections['destination_intent_mismatch']+=1;continue
                if mode!='lexical' and c['components']['semantic']<semantic_min:rejections['low_semantic']+=1;continue
                score=.65*c['retrieval']+.35*a['quality']
                if score<threshold:rejections['low_score']+=1;continue
                options.append(dict(source=source['url'],block=b['id'],target=c['target'],**a,score=round(score*100,2),components=c['components']))
        chosen=[];seen=set();spans={}
        for r in sorted(options,key=lambda x:-x['score']):
            if r['target'] in seen:rejections['repeated_target']+=1;continue
            if any(r['start']<e and r['end']>s for s,e in spans.get(r['block'],[])):rejections['overlap']+=1;continue
            chosen.append(r);seen.add(r['target']);spans.setdefault(r['block'],[]).append((r['start'],r['end']))
            if len(chosen)>=30:break
        return chosen,retrieved,dict(rejections)
