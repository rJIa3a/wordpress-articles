"""Collect versioned Wikipedia wikitext; model corpus never contains link attributes."""
import json,re,time,hashlib,concurrent.futures,argparse,threading
from urllib.error import HTTPError
from pathlib import Path
from urllib.parse import urlencode,quote,unquote,urljoin,urlsplit
from urllib.request import Request,urlopen
import mwparserfromhell as mw
from bs4 import BeautifulSoup
ROOT='https://ru.wikipedia.org'
EXTRA=['Минск','Брест','Гродно','Витебск','Могилёв','Гомель','Алматы','Астана','Бишкек','Ташкент','Самарканд','Бухара','Душанбе','Ереван','Тбилиси','Баку','Варшава','Прага','Белград','София']
REQUEST_LOCK=threading.Lock()
LAST_REQUEST=0.0
def request(url):
 global LAST_REQUEST
 for attempt in range(4):
  try:
   with REQUEST_LOCK:
    delay=max(0,3-(time.monotonic()-LAST_REQUEST))
    if delay:time.sleep(delay)
    LAST_REQUEST=time.monotonic()
   with urlopen(Request(url,headers={'User-Agent':'UniversalInterlinker/0.2 (read-only city-link research)'}),timeout=60) as r:return r.read()
  except HTTPError as exc:
   if attempt==3:raise
   if exc.code==429:
    wait=max(30,int(exc.headers.get('Retry-After','30')))
    print('Wikipedia rate limit; respecting Retry-After',wait,flush=True)
    while wait>0:
     step=min(45,wait);time.sleep(step);wait-=step
   else:time.sleep(2+attempt*4)
  except Exception:
   if attempt==3:raise
   time.sleep(2+attempt*4)
def title_key(t):return str(t).replace('_',' ').split('#')[0].strip()
def url(t):return ROOT+'/wiki/'+quote(t.replace(' ','_'),safe='(),')
def city_titles(out):
 path=out/'city-list.html'
 if not path.exists():path.write_bytes(request(url('Список городов России')))
 soup=BeautifulSoup(path.read_text(),'html.parser');titles=[]
 for table in soup.select('table.standard'):
  rows=table.select('tr');headers=[c.get_text(' ',strip=True) for c in rows[0].find_all(['td','th'],recursive=False)]
  if 'Город' not in headers:continue
  idx=headers.index('Город')
  for row in rows[1:]:
   cells=row.find_all(['td','th'],recursive=False)
   if len(cells)<=idx:continue
   a=cells[idx].find('a',href=re.compile(r'^(?:https://ru\.wikipedia\.org/wiki/|/wiki/|\./)'))
   if a:
    href=a['href'];path=urlsplit(urljoin(ROOT+'/wiki/',href)).path;t=title_key(unquote(path[6:]))
    if ':' not in t and t not in titles:titles.append(t)
 if len(titles)<1000:raise ValueError(f'City-list parser returned only {len(titles)} Russian city rows')
 return list(dict.fromkeys(titles+EXTRA))

def clean(wikitext,title,linktrail=True):
 parts=[];links=[];section='';skip=False;blocks=[];gold=[];previous_wikilink=False
 def flush():
  nonlocal parts,links
  text=''.join(parts)
  # Split prose/list paragraphs while retaining exact offsets after cleaning.
  start=0
  for sep in list(re.finditer(r'\n\s*\n',text))+[None]:
   end=sep.start() if sep else len(text);chunk=text[start:end]
   if len(chunk.strip())>=60:
    bid=str(len(blocks));blocks.append(dict(id=bid,text=chunk,section=section))
    for a in links:
     if start<=a['start'] and a['end']<=end:gold.append(dict(block=bid,**{**a,'start':a['start']-start,'end':a['end']-start}))
   start=sep.end() if sep else len(text)
  parts=[];links=[]
 def add(text,target=None):
  start=sum(map(len,parts));parts.append(text)
  if target and title_key(target)!=title_key(title):links.append(dict(target_title=title_key(target),anchor=text,start=start,end=start+len(text)))
 def nodes(code):
  nonlocal previous_wikilink
  for node in code.nodes:
   trailing=previous_wikilink;previous_wikilink=False
   name=type(node).__name__
   if name=='Text':
    text=re.sub(r"'{2,5}",'',str(node));add(text)
    if linktrail and trailing and links:
     suffix=re.match(r'[a-zа-яё]+',str(node))
     if suffix:links[-1]['anchor']+=suffix.group();links[-1]['end']+=len(suffix.group())
   elif name=='Wikilink':
    target=title_key(node.title)
    if ':' in target:continue
    anchor=(node.text or node.title).strip_code(normalize=True,collapse=True)
    before=len(links);add(anchor,target);previous_wikilink=len(links)>before
   elif name=='ExternalLink':
    if node.title:add(node.title.strip_code())
   elif name=='HTMLEntity':add(node.normalize())
   elif name=='Tag':
    if str(node.tag).lower() in ('ref','references','gallery','table','math','timeline','score','syntaxhighlight','code','pre'):continue
    if node.contents:nodes(node.contents)
   # Templates, comments and extension markup are intentionally excluded.
 for node in mw.parse(wikitext).nodes:
  if type(node).__name__=='Heading':
   flush();section=node.title.strip_code().strip();skip=section in ('Примечания','Источники','Литература','Ссылки','См. также')
  elif not skip:nodes(mw.wikicode.Wikicode([node]))
 flush()
 return dict(title=title,url=url(title),categories=[],blocks=blocks),gold

def batch(titles,cache):
 key=hashlib.sha256('|'.join(titles).encode()).hexdigest();path=cache/(key+'.json')
 if path.exists():return json.loads(path.read_text())
 params=dict(action='query',format='json',formatversion=2,prop='revisions',rvprop='ids|timestamp|content',rvslots='main',redirects=1,titles='|'.join(titles),maxlag=5)
 try:
  result=json.loads(request(ROOT+'/w/api.php?'+urlencode(params)))
  if 'error' in result:raise ValueError(result['error'])
 except HTTPError as exc:
  if exc.code not in (413,414) or len(titles)==1:raise
  mid=len(titles)//2;left=batch(titles[:mid],cache);right=batch(titles[mid:],cache)
  result={'query':{'pages':left['query']['pages']+right['query']['pages'],'redirects':left['query'].get('redirects',[])+right['query'].get('redirects',[])}}

 path.write_text(json.dumps(result,ensure_ascii=False));return result

def collect(out,count=1150):
 out=Path(out);out.mkdir(parents=True,exist_ok=True);cache=out/'raw';cache.mkdir(exist_ok=True)
 titles=city_titles(out)
 (out/'requested_titles.json').write_text(json.dumps(titles[:count],ensure_ascii=False,indent=2))
 groups=[titles[i:i+15] for i in range(0,min(len(titles),count+10),15)]
 pages={};gold=[];versions=[];aliases={};failures=[]
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
  futures={pool.submit(batch,g,cache):g for g in groups}
  done=0
  for f in concurrent.futures.as_completed(futures):
   try:
    result=f.result();q=result['query']
    for a in q.get('redirects',[]):aliases[a['from']]=a['to']
    for row in q['pages']:
     if 'missing' in row or not row.get('revisions'):continue
     title=row['title']
     if title in pages:continue
     rev=row['revisions'][0];wiki=rev['slots']['main']['content'];p,gs=clean(wiki,title)
     if not p['blocks']:continue
     pages[title]=p;gold.extend(dict(source=p['url'],**g) for g in gs);versions.append(dict(title=title,url=p['url'],revision=rev['revid'],timestamp=rev['timestamp'],sha256=hashlib.sha256(wiki.encode()).hexdigest()))
   except Exception as e:failures.append(dict(titles=futures[f],error=str(e)))
   done+=1
   progress=dict(batches_done=done,batches_total=len(groups),pages=len(pages),failures=len(failures));(out/'progress.json').write_text(json.dumps(progress));print(json.dumps(progress),flush=True)
 order={aliases.get(t,t):i for i,t in reversed(list(enumerate(titles)))}
 selected=sorted(pages,key=lambda t:(order.get(t,len(titles)),t))[:count];selected_urls={pages[t]['url'] for t in selected}
 for a in gold:a['target']=url(aliases.get(a['target_title'],a['target_title']))
 gold=[a for a in gold if a['source'] in selected_urls]
 ordered=sorted(selected,key=lambda t:hashlib.sha256(t.encode()).hexdigest());split={pages[t]['url']:('train' if i<int(len(ordered)*.7) else 'dev' if i<int(len(ordered)*.85) else 'test') for i,t in enumerate(ordered)}
 manifest=dict(parser_version=2,requested=count,collected=len(selected),complete=len(selected)==count,source_split=split,versions=[v for v in versions if v['url'] in selected_urls],failures=failures,selection='Russian Wikipedia city-list entries supplemented by nearby-country cities; no gold-based target expansion',license='CC BY-SA 4.0; article histories provide author attribution; transformations remove templates and references, retaining supported prose and wikilink offsets',created=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
 for name,value in [('corpus',[pages[t] for t in selected]),('manifest',manifest)]: (out/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False))
 from .data import save_compressed
 save_compressed(out/'gold.json',gold)
 print('DONE',len(selected),'pages',len(gold),'gold links',flush=True)
 if len(selected)!=count:raise RuntimeError(f'Incomplete corpus: {len(selected)}/{count}. Rerun resumes cache.')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',default='local-data/cities');p.add_argument('--count',type=int,default=1150);a=p.parse_args();collect(a.out,a.count)
