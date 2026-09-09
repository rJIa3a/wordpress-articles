import json
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Literal
from fastapi import FastAPI,HTTPException,BackgroundTasks,Request
from fastapi.responses import FileResponse,JSONResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel,Field
from . import storage as db,service
from .content import normalize
@asynccontextmanager
async def lifespan(app):db.init();yield
app=FastAPI(title='Universal Interlinker',lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=['localhost','127.0.0.1','testserver'])
@app.middleware('http')
async def local_only(request:Request,call_next):
 origin=request.headers.get('origin')
 if request.method!='GET' and origin and origin.rstrip('/')!=str(request.base_url).rstrip('/'):
  return JSONResponse({'detail':'Cross-origin mutation blocked'},status_code=403)
 return await call_next(request)
@app.get('/')
def home():return FileResponse(Path(__file__).with_name('index.html'))
@app.get('/api/sites')
def sites():return db.rows('SELECT * FROM sites')
class Site(BaseModel):url:str
@app.post('/api/sites')
def add_site(s:Site):
 u=normalize(s.url)
 if not u:raise HTTPException(422,'Нужен HTTP(S) URL без параметров')
 from urllib.parse import urlsplit
 p=urlsplit(u);u=p.scheme+'://'+p.netloc
 with db.connect() as c:
  c.execute('INSERT OR IGNORE INTO sites(url,name) VALUES(?,?)',(u,p.netloc))
 return sites()
def require_site(site):
 if not db.rows('SELECT id FROM sites WHERE id=?',(site,)):raise HTTPException(404,'Сайт не найден')
@app.post('/api/import')
def import_existing():return {'imported':service.import_exports(Path(__file__).resolve().parent.parent/'articles')}
@app.post('/api/import-database')
def import_database():
 from .wordpress_db import import_database
 try:
  with service.LOCK:return {'imported':import_database()}
 except ValueError as e:raise HTTPException(422,str(e))
@app.get('/api/sites/{site}/pages')
def pages(site:int):
 require_site(site);return [{k:v for k,v in p.items() if k not in ('html','blocks')} for p in db.pages(site)]
@app.get('/api/sites/{site}/graph')
def graph(site:int):require_site(site);return service.graph(site)
@app.get('/api/sites/{site}/recommendations')
def recs(site:int,status:str='',minimum:float=0,query:str=''):
 require_site(site);out=[]
 for r in db.rows('SELECT * FROM recommendations WHERE site_id=? AND score>=? ORDER BY score DESC',(site,minimum)):
  if status and r['status']!=status:continue
  data=json.loads(r.pop('data'));r={**data,**r}
  if query.casefold() not in (r['source']+' '+r['target']+' '+r['source_title']+' '+r['target_title']).casefold():continue
  out.append(r)
 return out
class Decision(BaseModel):status:Literal['approved','rejected','pending']
@app.post('/api/recommendations/{rid}/review')
def review(rid:int,d:Decision):
 with service.LOCK,db.connect() as c:
  r=c.execute('SELECT * FROM recommendations WHERE id=?',(rid,)).fetchone()
  if not r:raise HTTPException(404,'Нет рекомендации')
  if r['status']=='stale':raise HTTPException(409,'Исходный контент изменился')
  data=json.loads(r['data'])
  c.execute("UPDATE recommendations SET status=?,approved=CASE WHEN ?='approved' THEN CURRENT_TIMESTAMP ELSE NULL END WHERE id=?",(d.status,d.status,rid))
  c.execute('INSERT INTO change_history(recommendation_id,action,old_html,new_html) VALUES(?,?,?,?)',(rid,d.status,data['old_html'],data['new_html']))
 return {'status':d.status}
@app.post('/api/recommendations/{rid}/apply')
def apply(rid:int):raise HTTPException(409,'Версия 0.2 работает read-only. Публикация и rollback WordPress ещё не реализованы.')
@app.get('/api/sites/{site}/history')
def history(site:int):return db.rows('SELECT h.* FROM change_history h JOIN recommendations r ON r.id=h.recommendation_id WHERE r.site_id=? ORDER BY h.id DESC',(site,))
class Priority(BaseModel):
 kind:Literal['url','directory','category'];value:str;weight:float=Field(ge=0,le=5,default=3);blocked:bool=False
@app.get('/api/sites/{site}/priorities')
def priorities(site:int):require_site(site);return db.rows('SELECT * FROM seo_priorities WHERE site_id=?',(site,))
@app.post('/api/sites/{site}/priorities')
def save_priority(site:int,p:Priority):
 require_site(site)
 if p.kind!='category':
  from urllib.parse import urlsplit
  norm=normalize(p.value);s=db.rows('SELECT url FROM sites WHERE id=?',(site,))[0]
  if not norm or urlsplit(norm).netloc!=urlsplit(s['url']).netloc:raise HTTPException(422,'URL должен принадлежать сайту')
  p.value=norm
 with service.LOCK,db.connect() as c:c.execute('INSERT INTO seo_priorities(site_id,kind,value,weight,blocked) VALUES(?,?,?,?,?) ON CONFLICT(site_id,kind,value) DO UPDATE SET weight=excluded.weight,blocked=excluded.blocked',(site,p.kind,p.value,p.weight,int(p.blocked)))
 return priorities(site)
class Settings(BaseModel):
 city_mode:bool=False;contextual:bool=False;confidence_threshold:float=Field(default=.85,ge=.5,le=1);provider:Literal['lsa','ollama','minilm']='lsa';minimum_score:float=Field(default=78,ge=0,le=100);max_per_page:int=Field(default=3,ge=1,le=10);anchor_repetition_limit:int=Field(default=3,ge=1,le=20)
@app.get('/api/sites/{site}/settings')
def settings(site:int):require_site(site);return service.settings(site)
@app.post('/api/sites/{site}/settings')
def save_settings(site:int,s:Settings):
 require_site(site)
 with service.LOCK,db.connect() as c:c.execute('INSERT INTO settings(site_id,data) VALUES(?,?) ON CONFLICT(site_id) DO UPDATE SET data=excluded.data',(site,s.model_dump_json()))
 return s

def task(run,site,kind):
 try:
  result=service.crawl(site) if kind=='crawl' else {'stored':service.generate(site),'visited':0}
  with db.connect() as c:c.execute("UPDATE crawl_runs SET status='completed',stored=?,visited=?,error=?,finished=CURRENT_TIMESTAMP WHERE id=?",(result['stored'],result['visited'],json.dumps(result.get('errors',[]),ensure_ascii=False),run))
 except Exception as e:
  with db.connect() as c:c.execute("UPDATE crawl_runs SET status='failed',error=?,finished=CURRENT_TIMESTAMP WHERE id=?",(str(e),run))
@app.post('/api/sites/{site}/jobs/{kind}')
def start(site:int,kind:Literal['crawl','generate'],tasks:BackgroundTasks):
 require_site(site)
 with db.connect() as c:
  if c.execute("SELECT id FROM crawl_runs WHERE site_id=? AND status IN ('crawl','generate')",(site,)).fetchone():raise HTTPException(409,'Уже идёт обработка этого сайта')
  run=c.execute('INSERT INTO crawl_runs(site_id,status) VALUES(?,?)',(site,kind)).lastrowid
 tasks.add_task(task,run,site,kind);return {'id':run}
@app.get('/api/sites/{site}/jobs')
def jobs(site:int):return db.rows('SELECT * FROM crawl_runs WHERE site_id=? ORDER BY id DESC LIMIT 10',(site,))
