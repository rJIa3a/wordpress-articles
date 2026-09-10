import json,threading,collections,ipaddress,socket,time
from pathlib import Path
from urllib.parse import urlsplit,urljoin
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree
import httpx
from . import storage as db
from .content import normalize,parse,insert_preview
from .retrieval import Engine,Ollama,MiniLM
LOCK=threading.RLock()
DEFAULTS=dict(city_mode=False,contextual=False,confidence_threshold=.85,provider='lsa',minimum_score=78,max_per_page=3,anchor_repetition_limit=3)
def settings(site):
 r=db.rows('SELECT data FROM settings WHERE site_id=?',(site,));return {**DEFAULTS,**(json.loads(r[0]['data']) if r else {})}
def graph(site):
 pages=db.pages(site);by={p['url']:p for p in pages};inc=collections.Counter();out=collections.Counter();edges=set();anchors=collections.Counter()
 for p in pages:
  for l in p['links']:
   if l['target']!=p['url']:
    out[p['url']]+=1;anchors[(l['target'],l['anchor'])]+=1
    if l['target'] in by:edges.add((p['url'],l['target']))
 for _,t in edges:inc[t]+=1
 n=len(by);rank={u:1/max(1,n) for u in by};neighbors={u:[] for u in by}
 for s,t in edges:neighbors[s].append(t)
 for _ in range(40):
  dangling=sum(rank[u] for u in by if not neighbors[u]);new={u:(.15+.85*dangling)/max(1,n) for u in by}
  for u,targets in neighbors.items():
   for t in targets:new[t]+=.85*rank[u]/len(targets)
  rank=new
 return dict(nodes=[dict(id=p['id'],url=u,title=p['title'],incoming=inc[u],outgoing=out[u],pagerank=rank[u],depth=p['depth'],orphan=inc[u]==0,weak=inc[u]<2) for u,p in by.items()],edges=[dict(source=s,target=t) for s,t in sorted(edges)],anchors=[dict(target=t,anchor=a,count=n) for (t,a),n in anchors.items()])
def priority(page,rules):
 matches=[r for r in rules if (r['kind']=='url' and page['url']==r['value']) or (r['kind']=='directory' and page['url'].startswith(r['value'])) or (r['kind']=='category' and r['value'] in page['categories'])]
 return max([r['weight'] for r in matches]+[0]),any(r['blocked'] for r in matches)

def generate(site):
 with LOCK:
  cfg=settings(site);pages=db.pages(site)
  if len(pages)<2:raise ValueError('Сначала загрузите минимум две страницы')
  if cfg['provider'] not in ('lsa','ollama','minilm'):raise ValueError('Неизвестный provider')
  if cfg['city_mode']:
   from .geography import annotate
   annotate(pages)
  engine=Engine(pages,Ollama() if cfg['provider']=='ollama' else MiniLM() if cfg['provider']=='minilm' else None)
  rules=db.rows('SELECT * FROM seo_priorities WHERE site_id=?',(site,));by={p['url']:p for p in pages}
  diagnostics=collections.Counter();page_diagnostics=[]
  accepted=[];repeat=collections.Counter((l['target'],l['anchor'].casefold()) for p in pages for l in p['links'])
  with db.connect() as c:c.execute("DELETE FROM recommendations WHERE site_id=? AND status='pending' AND NOT EXISTS (SELECT 1 FROM change_history h WHERE h.recommendation_id=recommendations.id)",(site,))
  existing=db.rows('SELECT * FROM recommendations WHERE site_id=?',(site,));existing_keys={(r['source'],r['target'],r['block']) for r in existing if r['status']!='stale'}
  for r in existing:
   if r['status'] in ('approved','pending'):repeat[(r['target'],r['anchor'].casefold())]+=1
  for p in pages:
   if priority(p,rules)[1]:continue
   recs,_,reasons=engine.recommend(p,threshold=cfg['minimum_score']/100)
   diagnostics.update(reasons);page_diagnostics.append(dict(source=p['url'],retrieval_accepted=len(recs),rejections=reasons))
   used={l['target'] for l in p['links']};kept=sum(r['source']==p['url'] and r['status'] in ('approved','pending') for r in existing)
   for r in recs:
    if cfg['contextual']:
     from .context import judge
     b=next(b for b in p['blocks'] if b['id']==r['block'])
     decision=judge(p,b,[by[r['target']]],cfg['confidence_threshold'])
     if not decision:diagnostics['context_rejected']+=1;continue
     r['anchor']=decision['anchor'];r['context_reason']=decision['reason'];r['confidence']=decision['confidence']
    target=by[r['target']];weight,blocked=priority(target,rules)
    if blocked:diagnostics['blacklisted_target']+=1;continue
    if r['target'] in used:diagnostics['existing_target']+=1;continue
    if target['fingerprint']==p['fingerprint']:diagnostics['identical_page']+=1;continue
    if (p['url'],r['target'],r['block']) in existing_keys:diagnostics['previously_reviewed']+=1;continue
    if repeat[(r['target'],r['anchor'].casefold())]>=cfg['anchor_repetition_limit']:diagnostics['anchor_repetition']+=1;continue
    b=next(b for b in p['blocks'] if b['id']==r['block'])
    try:new=insert_preview(b['html'],r['anchor'],r['target'])
    except ValueError:diagnostics['unsafe_html_location']+=1;continue
    if kept>=cfg['max_per_page']:diagnostics['page_limit']+=1;break
    # Priority bonus only after relevance gate. Never rescues a rejected match.
    r.update(score=min(100,r['score']+min(5,weight)),source_title=p['title'],target_title=target['title'],old_html=b['html'],new_html=new,original_text=b['text'],provider=cfg['provider'],priority=weight)
    r['components']['seo_priority_bonus']=min(5,weight)
    accepted.append(r);kept+=1;used.add(r['target']);repeat[(r['target'],r['anchor'].casefold())]+=1
  with db.connect() as c:
   for r in accepted:c.execute("INSERT INTO recommendations(site_id,source,target,block,anchor,score,data) VALUES(?,?,?,?,?,?,?) ON CONFLICT(site_id,source,target,block) DO UPDATE SET anchor=excluded.anchor,score=excluded.score,data=excluded.data,status='pending',approved=NULL WHERE recommendations.status='stale'",(site,r['source'],r['target'],r['block'],r['anchor'],r['score'],json.dumps(r,ensure_ascii=False)))
  with db.connect() as c:c.execute('INSERT INTO generation_diagnostics(site_id,data) VALUES(?,?) ON CONFLICT(site_id) DO UPDATE SET data=excluded.data,created=CURRENT_TIMESTAMP',(site,json.dumps(dict(provider=cfg['provider'],accepted=len(accepted),rejections=dict(diagnostics),pages=page_diagnostics),ensure_ascii=False)))
  return len(accepted)

def import_exports(folder):
 with LOCK:
  count=0
  for path in sorted(Path(folder).glob('*.json')):
   data=json.loads(path.read_text());url=normalize(data.get('link',''))
   if not url or data.get('status')!='publish':continue
   root=urlsplit(url);base=root.scheme+'://'+root.netloc
   with db.connect() as c:
    c.execute('INSERT OR IGNORE INTO sites(url,name) VALUES(?,?)',(base,root.netloc));site=c.execute('SELECT id FROM sites WHERE url=?',(base,)).fetchone()[0]
   meta={**data.get('yoast_head_json',{}),'categories':data.get('categories',[]),'type':data.get('type','post')}
   p=parse(url,data['content']['rendered'],data['title']['rendered'],meta=meta)
   if p:db.save_page(site,p);count+=1
  return count

def public_url(url):
 u=urlsplit(url)
 if u.scheme not in ('http','https') or not u.hostname or u.username or u.password or u.port not in (None,80,443):raise ValueError('Требуется публичный HTTP(S) URL')
 for entry in socket.getaddrinfo(u.hostname,u.port or 443,type=socket.SOCK_STREAM):
  if not ipaddress.ip_address(entry[4][0]).is_global:raise ValueError('Локальные адреса недоступны crawler')
 return url

def crawl(site,limit=25):
 with LOCK:
  s=db.rows('SELECT * FROM sites WHERE id=?',(site,))[0];base=s['url'];queue=collections.deque([(base+'/',0)]);seen=set();stored=0
  def get(url):
   public_url(url)
   if urlsplit(url).netloc!=urlsplit(base).netloc:raise ValueError('Переход на другой домен пропущен')
   with httpx.Client(timeout=15,follow_redirects=False,headers={'User-Agent':'UniversalInterlinker/0.2 (read-only)'}) as client:
    with client.stream('GET',url) as r:
     chunks=[];size=0
     for chunk in r.iter_bytes():
      size+=len(chunk)
      if size>3_000_000:raise ValueError('Страница больше 3 МБ')
      chunks.append(chunk)
     return r.status_code,dict(r.headers),b''.join(chunks).decode('utf-8',errors='replace')
  code,_,robots=get(base+'/robots.txt');rp=RobotFileParser();rp.set_url(base+'/robots.txt')
  if code==200:rp.parse(robots.splitlines())
  elif code==404:rp.parse([])
  else:raise ValueError('Не удалось проверить robots.txt: '+str(code))
  # Bounded sitemap discovery; sitemap indexes are intentionally not traversed in v0.2.
  if rp.can_fetch('*',base+'/sitemap.xml'):
   try:
    code,_,xml=get(base+'/sitemap.xml')
    if code==200:
     tree=ElementTree.fromstring(xml)
     if tree.tag.endswith('urlset'):
      for e in tree.iter():
       if e.tag.endswith('loc') and e.text:
        u=normalize(e.text)
        if u and urlsplit(u).netloc==urlsplit(base).netloc:queue.append((u,None))
   except (ValueError,ElementTree.ParseError,httpx.HTTPError):pass
  errors=[]
  while queue and len(seen)<limit:
   url,depth=queue.popleft();url=normalize(url)
   if not url or url in seen:continue
   seen.add(url)
   if not rp.can_fetch('*',url):continue
   try:
    code,headers,html=get(url)
    if code!=200 or 'noindex' in headers.get('x-robots-tag','').lower() or 'text/html' not in headers.get('content-type',''):continue
    p=parse(url,html,depth=depth)
    if p:
     db.save_page(site,p);stored+=1
     for link in p['links']:
      if link['target'] not in seen and len(queue)<limit*20:queue.append((link['target'],depth+1 if depth is not None else None))
   except (ValueError,httpx.HTTPError,OSError) as e:errors.append(str(e))
   time.sleep(.2)
  return dict(visited=len(seen),stored=stored,errors=errors[:5])
