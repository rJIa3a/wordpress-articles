from .data import load_json,save_compressed
"""Reparse train/dev raw revisions with linktrail handling; keep v1 immutable."""
import json,hashlib,collections
from pathlib import Path
from .collect import clean,url

def run(folder='local-data/cities'):
 d=Path(folder);pages=json.loads((d/'corpus.json').read_text());by={p['title']:p for p in pages};split=json.loads((d/'manifest.json').read_text())['source_split'];old=load_json(d/'gold.json');raw={}
 for f in sorted((d/'raw').glob('*.json')):
  for p in json.loads(f.read_text()).get('query',{}).get('pages',[]):
   if p.get('revisions') and p['title'] in by and split[by[p['title']]['url']] in ('train','dev'):raw[p['title']]=p
 corrected=[];changed=0;checked=0
 for title,p in sorted(raw.items()):
  article,gold=clean(p['revisions'][0]['slots']['main']['content'],title,linktrail=True)
  if article['blocks']!=by[title]['blocks']:raise ValueError('Text changed during gold-only correction: '+title)
  previous={(g['block'],g['start']):g for g in old if g['source']==article['url']}
  for g in gold:
   g=dict(source=article['url'],**g,target=url(g['target_title']));b=article['blocks'][int(g['block'])];assert b['text'][g['start']:g['end']]==g['anchor'];checked+=1
   prior=previous.get((g['block'],g['start']))
   if prior is None:raise ValueError('Unmatched original annotation')
   g['target']=prior['target'];g['target_title']=prior['target_title']
   if prior and prior['end']!=g['end']:changed+=1
   corrected.append(g)
 report=dict(split='train_dev_only',articles=len(raw),checked_links=checked,changed_anchor_spans=changed,text_changed=False,v1_sha256=hashlib.sha256(json.dumps(old,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),reason='Russian lowercase linktrail after wikilink; v1 preserved. Redirect resolution not included.')
 out=d/'gold-audit';out.mkdir(exist_ok=True);save_compressed(out/'gold-v2-train-dev.json',corrected);(out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
if __name__=='__main__':run()
