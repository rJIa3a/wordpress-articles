"""Warm the same MiniLM cache from the end; can accompany the main forward pass."""
import argparse,json
from pathlib import Path
from .sentences import sentence_span
from interlinker.retrieval import MiniLM

def run(folder,threads):
 d=Path(folder);pages=json.loads((d/'corpus.json').read_text());records=json.loads((d/'refinement-sentences/training-records.json').read_text());blocks={(p['url'],b['id']):b for p in pages for b in p['blocks']};texts=[]
 for r in records:
  b=blocks[r['source'],r['block']];start,end=sentence_span(b['text'],r['start'],r['end']);start=max(start,r['start']-180);end=min(end,r['end']+180)
  texts.append(b['section'][:80]+'. '+b['text'][start:end])
 texts=list(dict.fromkeys(texts))[::-1];model=MiniLM(threads=threads)
 for start in range(0,len(texts),64):
  model.encode(texts[start:start+64]);print('reverse',min(start+64,len(texts)),len(texts),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--data',default='local-data/cities');p.add_argument('--threads',type=int,default=6);a=p.parse_args();run(a.data,a.threads)
