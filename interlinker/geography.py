"""City entity extraction and destination intent checks for editorial site pages."""
import json,re
from pathlib import Path
from .retrieval import lemma

def tokens(text):return [lemma(w) for w in re.findall(r'[А-Яа-яЁёA-Za-z]+(?:-[А-Яа-яЁёA-Za-z]+)*',text)]
SIGHTS=set(tokens('достопримечательности экскурсии туризм турист путешествие музеи посмотреть отдых парки архитектура театры памятники'))
MOVE=set(tokens('переезд переехать жить жизнь жилье работа зарплата квартиры стоимость климат недвижимость'))

def annotate(pages,corpus='local-data/cities/corpus.json'):
 path=Path(corpus)
 if not path.exists():raise ValueError('Для городского режима сначала соберите corpus.json Википедии')
 registry={}
 for p in json.loads(path.read_text()):
  name=re.sub(r'\s*\([^)]*\)','',p['title']);key=tuple(tokens(name));registry.setdefault(key,[]).append(name)
 mapped=0
 for p in pages:
  ws=tokens(p['title']);matches=set()
  for i in range(len(ws)):
   for size in range(1,min(5,len(ws)-i)+1):
    candidates=registry.get(tuple(ws[i:i+size]),[])
    if len(candidates)==1:matches.add(candidates[0])
  if len(matches)==1:
   p['entity_name']=next(iter(matches));p['destination_intent']='sights' if set(ws)&SIGHTS else 'relocation' if set(ws)&MOVE else 'general';mapped+=1
 return mapped

def intent_allowed(text,page,anchor):
 intent=page.get('destination_intent','general')
 if intent=='general':return True
 start=text.find(anchor)
 context=set(tokens(text[max(0,start-180):start+len(anchor)+180]))
 return bool(context&(SIGHTS if intent=='sights' else MOVE))
