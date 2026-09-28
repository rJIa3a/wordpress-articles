import json
import os
import re
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Literal
from fastapi import FastAPI,HTTPException,BackgroundTasks,Request,UploadFile,File,Form
from fastapi.responses import FileResponse,JSONResponse,Response
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel,Field
from . import storage as db,service,auth
from .content import normalize,page_identity
from .keyword_import import preview as preview_keywords,prepare_rows as prepare_keyword_rows,MAX_UPLOAD_BYTES
@asynccontextmanager
async def lifespan(app):db.init();yield
app=FastAPI(title='Universal Interlinker',lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=os.getenv('ALLOWED_HOSTS','localhost,127.0.0.1,testserver').split(','))
@app.middleware('http')
async def local_only(request:Request,call_next):
 origin=request.headers.get('origin')
 if os.getenv('APP_ENV','development').lower()=='production' and request.method not in ('GET','HEAD','OPTIONS') and not origin:
  return JSONResponse({'detail':'Origin header required'},status_code=403)
 if request.method!='GET' and origin and origin.rstrip('/')!=str(request.base_url).rstrip('/'):
  return JSONResponse({'detail':'Cross-origin mutation blocked'},status_code=403)
 path=request.url.path
 public_auth=path in ('/api/auth/register','/api/auth/verify','/api/auth/login','/api/auth/resend-verification')
 token=request.cookies.get(auth.cookie_name())
 user=auth.session_user(token)
 request.state.user=user
 if path.startswith('/api/') and path not in ('/api/auth/me','/api/health') and not public_auth and not user:
  return JSONResponse({'detail':'Требуется войти в аккаунт'},status_code=401)
 if user:
  site_match=re.match(r'^/api/sites/(\d+)(?:/|$)',path)
  if site_match and not db.rows('SELECT id FROM sites WHERE id=? AND owner_user_id=?',(int(site_match.group(1)),user['id'])):
   return JSONResponse({'detail':'Сайт не найден'},status_code=404)
  rec_match=re.match(r'^/api/recommendations/(\d+)(?:/|$)',path)
  if rec_match and not db.rows('SELECT r.id FROM recommendations r JOIN sites s ON s.id=r.site_id WHERE r.id=? AND s.owner_user_id=?',(int(rec_match.group(1)),user['id'])):
   return JSONResponse({'detail':'Рекомендация не найдена'},status_code=404)
 response=await call_next(request)
 response.headers.setdefault('X-Content-Type-Options','nosniff')
 response.headers.setdefault('X-Frame-Options','DENY')
 response.headers.setdefault('Referrer-Policy','no-referrer')
 if path.startswith('/api/auth/') or request.method!='GET':response.headers['Cache-Control']='no-store'
 return response
@app.get('/')
def home():return FileResponse(Path(__file__).with_name('index.html'))
@app.get('/api/health')
def health():return {'status':'ok'}
@app.get('/api/sites')
def sites(request:Request):return db.rows('SELECT id,url,name FROM sites WHERE owner_user_id=? ORDER BY id',(request.state.user['id'],))
class Register(BaseModel):email:str;password:str
class Login(BaseModel):email:str;password:str
class Verify(BaseModel):token:str
class ResendVerification(BaseModel):email:str
@app.post('/api/auth/register')
def register(data:Register,request:Request):
 ip=request.client.host if request.client else 'unknown'
 email=auth.validate_email(data.email or '') or 'invalid'
 if not auth.rate_allowed('register-ip:'+ip,5,3600) or not auth.rate_allowed('register-email:'+email,3,3600):raise HTTPException(429,'Слишком много попыток регистрации. Попробуйте позже.')
 try:result=auth.create_account(data.email,data.password,str(request.base_url))
 except ValueError as e:raise HTTPException(422,str(e))
 except RuntimeError as e:raise HTTPException(503,str(e))
 except Exception as e:
  if 'SMTP' in str(e):raise HTTPException(503,'Не удалось отправить письмо. Проверьте настройки почты.')
  raise
 if not result['created']:return {'message':'Если это новый адрес, аккаунт создан. Если аккаунт уже есть — войдите.','created':False,'verification_required':False}
 if not result['verification_required']:return {'message':'Аккаунт создан. Выполняется вход.','created':True,'verification_required':False}
 return {'message':'Проверьте почту и подтвердите адрес.','verification_required':True,'verification_url':result['verification_url']}
@app.post('/api/auth/resend-verification')
def resend_verification(data:ResendVerification,request:Request):
 ip=request.client.host if request.client else 'unknown'
 email=auth.validate_email(data.email or '') or 'invalid'
 if not auth.rate_allowed('resend-ip:'+ip,10,3600) or not auth.rate_allowed('resend-email:'+email,3,3600):raise HTTPException(429,'Слишком много запросов. Попробуйте позже.')
 try:result=auth.resend_verification(data.email,str(request.base_url))
 except Exception as e:
  if 'SMTP' in str(e):raise HTTPException(503,'Не удалось отправить письмо. Проверьте настройки почты.')
  raise
 response={'message':'Если адрес зарегистрирован и ещё не подтверждён, ссылка подтверждения отправлена.'}
 if result and result['verification_url']:response['verification_url']=result['verification_url']
 return response
@app.post('/api/auth/verify')
def verify(data:Verify,request:Request):
 ip=request.client.host if request.client else 'unknown'
 if not auth.rate_allowed('verify-ip:'+ip,20,3600):raise HTTPException(429,'Слишком много попыток подтверждения. Попробуйте позже.')
 if not auth.verify_email(data.token):raise HTTPException(400,'Ссылка недействительна или срок её действия истёк')
 return {'message':'Email подтверждён. Теперь войдите.'}
@app.post('/api/auth/login')
def login(data:Login,response:Response,request:Request):
 ip=request.client.host if request.client else 'unknown';email=auth.validate_email(data.email or '') or 'invalid'
 if not auth.rate_allowed('login-ip:'+ip,40,900) or not auth.rate_allowed('login-email:'+email,8,900):raise HTTPException(429,'Слишком много попыток входа. Попробуйте позже.')
 try:token,user=auth.login(data.email,data.password)
 except ValueError as e:raise HTTPException(401,str(e))
 auth.clear_rate_limit('login-email:'+email);auth.clear_rate_limit('login-ip:'+ip)
 secure=os.getenv('APP_ENV','development').lower()=='production'
 response.set_cookie(auth.cookie_name(),token,max_age=auth.SESSION_SECONDS,httponly=True,secure=secure,samesite='lax',path='/')
 response.headers['Cache-Control']='no-store'
 return user
@app.post('/api/auth/logout')
def logout(request:Request,response:Response):
 auth.logout(request.cookies.get(auth.cookie_name()))
 response.delete_cookie(auth.cookie_name(),path='/',secure=os.getenv('APP_ENV','development').lower()=='production',httponly=True,samesite='lax')
 return {'ok':True}
@app.get('/api/auth/me')
def me(request:Request):return request.state.user
class Site(BaseModel):url:str
@app.post('/api/sites')
def add_site(s:Site,request:Request):
 u=normalize(s.url)
 if not u:raise HTTPException(422,'Нужен HTTP(S) URL без параметров')
 from urllib.parse import urlsplit
 p=urlsplit(u);u=p.scheme+'://'+p.netloc
 with db.connect() as c:
  existing=c.execute('SELECT id,owner_user_id FROM sites WHERE url=?',(u,)).fetchone()
  if existing and existing['owner_user_id'] not in (None,request.state.user['id']):raise HTTPException(409,'Этот сайт уже подключён к другому аккаунту')
  if existing and existing['owner_user_id'] is None:
   db.clear_site(c,existing['id'])
   c.execute('UPDATE sites SET owner_user_id=? WHERE id=?',(request.state.user['id'],existing['id']))
  else:c.execute('INSERT OR IGNORE INTO sites(url,name,owner_user_id) VALUES(?,?,?)',(u,p.netloc,request.state.user['id']))
 return sites(request)
def require_site(site):
 if not db.rows('SELECT id FROM sites WHERE id=?',(site,)):raise HTTPException(404,'Сайт не найден')
@app.post('/api/import')
def import_existing():raise HTTPException(409,'Импорт общего demo-корпуса отключён в аккаунтном режиме. Добавьте сайт и импортируйте его WordPress REST API.')
@app.post('/api/import-database')
def import_database():
 raise HTTPException(409,'Подключение общей MySQL-базы отключено. Используйте публичный WordPress REST API для выбранного сайта.')
@app.get('/api/sites/{site}/pages')
def pages(site:int):
 require_site(site);return [{k:v for k,v in p.items() if k not in ('html','blocks')} for p in db.pages(site)]
@app.post('/api/sites/{site}/keywords/preview')
async def keywords_preview(site:int,file:UploadFile=File(...)):
 require_site(site)
 payload=await file.read(MAX_UPLOAD_BYTES+1)
 try:return preview_keywords(file.filename or '',payload)
 except ValueError as e:raise HTTPException(422,str(e))
@app.post('/api/sites/{site}/keywords/import')
async def keywords_import(site:int,file:UploadFile=File(...),query_column:str=Form(...),url_column:str=Form(...)):
 require_site(site)
 payload=await file.read(MAX_UPLOAD_BYTES+1)
 site_url=db.rows('SELECT url FROM sites WHERE id=?',(site,))[0]['url']
 try:prepared,stats=prepare_keyword_rows(file.filename or '',payload,query_column,url_column,site_url)
 except ValueError as e:raise HTTPException(422,str(e))
 with db.connect() as c:
  before=c.total_changes
  c.executemany('INSERT OR IGNORE INTO keyword_targets(site_id,query,target_url,source_file,details,row_hash) VALUES(?,?,?,?,?,?)',[(site,r['query'],r['target_url'],r['source_file'],r['details'],r['row_hash']) for r in prepared])
  inserted=c.total_changes-before
 return {**stats,'inserted':inserted,'already_present':len(prepared)-inserted}
@app.get('/api/sites/{site}/keywords')
def keywords(site:int,query:str='',limit:int=200,offset:int=0):
 require_site(site)
 limit=max(1,min(limit,500));offset=max(0,offset)
 all_rows=db.rows('SELECT * FROM keyword_targets WHERE site_id=? ORDER BY imported_at DESC,id DESC',(site,))
 if query:
  q=query.casefold();all_rows=[r for r in all_rows if q in r['query'].casefold() or q in r['target_url'].casefold() or q in r['source_file'].casefold()]
 pages={page_identity(p['url']):p for p in db.pages(site)}
 total=len(all_rows);items=[]
 for r in all_rows[offset:offset+limit]:
  target=pages.get(page_identity(r['target_url']))
  items.append({**r,'details':json.loads(r['details']),'target_imported':target is not None,'target_title':target['title'] if target else ''})
 return {'total':total,'items':items,'limit':limit,'offset':offset}
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
class Decision(BaseModel):status:Literal['approved','rejected','pending','deferred']
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
  result=service.crawl(site) if kind=='crawl' else service.import_wordpress(site) if kind=='wordpress' else {'stored':service.generate(site),'visited':0}
  with db.connect() as c:c.execute("UPDATE crawl_runs SET status='completed',stored=?,visited=?,error=?,finished=CURRENT_TIMESTAMP WHERE id=?",(result['stored'],result['visited'],json.dumps(result.get('errors',[]),ensure_ascii=False),run))
 except Exception as e:
  with db.connect() as c:c.execute("UPDATE crawl_runs SET status='failed',error=?,finished=CURRENT_TIMESTAMP WHERE id=?",(str(e),run))
class GenerateOptions(BaseModel):
 minimum_score:float|None=Field(default=None,ge=0,le=100)
@app.post('/api/sites/{site}/jobs/{kind}')
def start(site:int,kind:Literal['crawl','generate','wordpress'],tasks:BackgroundTasks,options:GenerateOptions|None=None):
 require_site(site)
 with db.connect() as c:
  if c.execute("SELECT id FROM crawl_runs WHERE site_id=? AND status IN ('crawl','generate','wordpress')",(site,)).fetchone():raise HTTPException(409,'Уже идёт обработка этого сайта')
  if kind=='generate' and options and options.minimum_score is not None:
   saved=c.execute('SELECT data FROM settings WHERE site_id=?',(site,)).fetchone()
   current={**service.DEFAULTS,**(json.loads(saved['data']) if saved else {})}
   current['minimum_score']=options.minimum_score
   c.execute('INSERT INTO settings(site_id,data) VALUES(?,?) ON CONFLICT(site_id) DO UPDATE SET data=excluded.data',(site,json.dumps(current,ensure_ascii=False)))
  run=c.execute('INSERT INTO crawl_runs(site_id,status) VALUES(?,?)',(site,kind)).lastrowid
 tasks.add_task(task,run,site,kind);return {'id':run}
@app.get('/api/sites/{site}/jobs')
def jobs(site:int):return db.rows('SELECT * FROM crawl_runs WHERE site_id=? ORDER BY id DESC LIMIT 10',(site,))

@app.get('/api/sites/{site}/diagnostics')
def diagnostics(site:int):
 require_site(site)
 rows=db.rows('SELECT data,created FROM generation_diagnostics WHERE site_id=?',(site,))
 return {**json.loads(rows[0]['data']),'created':rows[0]['created']} if rows else {'accepted':0,'rejections':{},'pages':[]}

@app.get('/{path:path}',include_in_schema=False)
def project_route(path:str):
 if path.startswith('api/'):
  raise HTTPException(404,'Not found')
 return FileResponse(Path(__file__).with_name('index.html'))
