from .data import load_json
"""Attribute missing development links to candidate recall, ranking or deduplication."""
import json,collections
from pathlib import Path
from .refine import development_data

def audit(folder='local-data/cities'):
 d=Path(folder);pages=json.loads((d/'corpus.json').read_text());split=json.loads((d/'manifest.json').read_text())['source_split'];gold=load_json(d/'gold.json')
 records,_,gold=development_data(pages,gold,split);by={p['url']:p for p in pages};blocks={(p['url'],b['id']):b for p in pages for b in p['blocks']}
 pred=json.loads((d/'refinement/predictions.json').read_text());pk={(r['source'],r['block'],r['target']) for r in pred};edges={(r['source'],r['target']) for r in pred};ck={(r['source'],r['block'],r['target']) for r in records};counts=collections.Counter();samples=collections.defaultdict(list);seen=set()
 for g in gold:
  k=(g['source'],g['block'],g['target'])
  if split[g['source']]!='dev' or g['target'] not in by or g['source']==g['target'] or k in seen:continue
  seen.add(k)
  reason='recovered' if k in pk else 'missing_candidate' if k not in ck else 'other_block_selected' if (g['source'],g['target']) in edges else 'below_threshold_or_overlap'
  counts[reason]+=1
  if reason!='recovered' and len(samples[reason])<15:samples[reason].append(dict(source=by[g['source']]['title'],target=by[g['target']]['title'],anchor=g['anchor'],text=blocks[g['source'],g['block']]['text']))
 result=dict(split='dev_only',counts=dict(counts),samples=dict(samples));(d/'refinement/misses.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':audit()
