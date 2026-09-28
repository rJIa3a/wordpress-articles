import json
from urllib.parse import parse_qs,urlsplit
import pytest
from fastapi.testclient import TestClient
from interlinker import storage as db,service
from interlinker.content import normalize,parse,insert_preview
from interlinker.app import app
@pytest.fixture
def client(tmp_path,monkeypatch):
 monkeypatch.setattr(db,'DB',str(tmp_path/'test.sqlite'))
 with TestClient(app) as c:
  registration=c.post('/api/auth/register',json={'email':'owner@example.org','password':'long-test-password-123'})
  if registration.json().get('verification_url'):
   token=parse_qs(urlsplit(registration.json()['verification_url']).query)['verify'][0]
   assert c.post('/api/auth/verify',json={'token':token}).status_code==200
  assert c.post('/api/auth/login',json={'email':'owner@example.org','password':'long-test-password-123'}).status_code==200
  yield c

def test_normalization():
 assert normalize('https://EXAMPLE.org/a#b')=='https://example.org/a'
 for u in ['javascript:alert(1)','https://example.org/?a=1','https://example.org/wp-admin/a','https://example.org/page/2/']:
  assert normalize(u) is None

def test_self_link_identity_collapses_common_url_variants_only():
 from interlinker.content import same_page
 assert same_page('https://dagorod.ru/pereezd-v-perm/','http://www.dagorod.ru/pereezd-v-perm')
 assert not same_page('https://dagorod.ru/pereezd-v-penzu/','https://dagorod.ru/pereezd-v-perm/')
 assert not same_page('https://dagorod.ru/Pereezd/','https://dagorod.ru/pereezd/')

def test_parse_noindex_canonical_navigation():
 assert parse('https://a.org/a','<meta name="robots" content="noindex">') is None
 assert parse('https://a.org/a','<link rel="canonical" href="/b">') is None
 p=parse('https://a.org/a','<nav><a href="/menu">Меню</a></nav><article><h2>Города</h2><p>Поездка в <a href="/moscow">Москву</a> начинается с подготовки маршрута и покупки билетов.</p></article>')
 assert p['links'][0]['contextual']==0 and p['links'][1]['contextual']==1
 assert p['blocks'][0]['section']=='Города'

def test_preview_does_not_touch_attributes_or_existing_links():
 h='<p title="Москва"><a href="/x">Москва</a> и Москва</p>'
 assert insert_preview(h,'Москва','https://a.org/moscow')=='<p title="Москва"><a href="/x">Москва</a> и <a href="https://a.org/moscow">Москва</a></p>'
 for h in ['<a>Москва</a>','<p>Москва и Москва</p>','<script>Москва</script>']:
  with pytest.raises(ValueError):insert_preview(h,'Москва','https://a.org/m')

def test_malformed_nested_heading_is_not_a_link_location_or_large_block():
 raw='<article><p><p>Длинное описание жизни в городе и его природных особенностей.</p><h2>Плюсы и минусы Омска</h2><p>В Омске есть красивые места для прогулок и отдыха всей семьёй.</p></p></article>'
 page=parse('https://a.org/omsk',raw,'Омск')
 assert page['blocks']
 assert all('Плюсы и минусы Омска' not in block['text'] for block in page['blocks'])
 assert all('<h2>' not in block['html'] for block in page['blocks'])
 with pytest.raises(ValueError):insert_preview('<p><h2>Плюсы и минусы Омска</h2></p>','Плюсы и минусы Омска','https://a.org/cities/omsk')
 assert insert_preview('<h2>Омск</h2><p>В Омске есть красивые места.</p>','Омске','https://a.org/cities/omsk').endswith('<p>В <a href="https://a.org/cities/omsk">Омске</a> есть красивые места.</p>')

def seed(client):
 client.post('/api/sites',json={'url':'https://a.org'})
 for u,title,text in [('travel','Поездки','Москва является крупным городом. В Москву приезжают на экскурсии и отдых.'),('moscow','Москва','Москва является столицей России. Город предлагает множество экскурсий.'),('kazan','Казань','Казань — крупный город России, расположенный на берегу Волги.')]:
  db.save_page(1,parse('https://a.org/'+u,'<article><p>'+text+'</p></article>',title))
 client.post('/api/sites/1/settings',json={'minimum_score':35,'max_per_page':3})

def test_full_review_and_no_live_apply(client):
 seed(client);service.generate(1)
 r=client.get('/api/sites/1/recommendations').json();assert r
 rid=r[0]['id'];assert client.post(f'/api/recommendations/{rid}/review',json={'status':'approved'}).status_code==200
 assert client.post(f'/api/recommendations/{rid}/apply',json={}).status_code==409
 assert len(client.get('/api/sites/1/history').json())==1
 assert client.post(f'/api/recommendations/{rid}/review',json={'status':'pending'}).status_code==200
 service.generate(1);pairs=[(x['source'],x['target'],x['block']) for x in client.get('/api/sites/1/recommendations').json()];assert len(pairs)==len(set(pairs))

def test_deferred_recommendation_is_kept_for_later_review(client):
 seed(client);service.generate(1)
 recommendation=client.get('/api/sites/1/recommendations').json()[0]
 result=client.post(f"/api/recommendations/{recommendation['id']}/review",json={'status':'deferred'})
 assert result.status_code==200 and result.json()['status']=='deferred'
 assert client.get('/api/sites/1/recommendations?status=deferred').json()[0]['id']==recommendation['id']
 assert client.get('/api/sites/1/history').json()[0]['action']=='deferred'
 service.generate(1)
 assert client.get('/api/sites/1/recommendations?status=deferred').json()[0]['id']==recommendation['id']

def test_blacklist_priority(client):
 seed(client);client.post('/api/sites/1/priorities',json={'kind':'url','value':'https://a.org/moscow','weight':5,'blocked':True})
 service.generate(1)
 assert all(r['source']!='https://a.org/moscow' and r['target']!='https://a.org/moscow' for r in client.get('/api/sites/1/recommendations').json())
 assert service.priority({'url':'https://a.org/moscow','categories':[]},[{'kind':'url','value':'https://a.org/moscow','weight':5,'blocked':False}])==(5,False)

def test_graph_and_stale_approval(client):
 seed(client);service.generate(1);r=client.get('/api/sites/1/recommendations').json()[0];client.post(f"/api/recommendations/{r['id']}/review",json={'status':'approved'})
 db.save_page(1,parse(r['source'],'<p>Измененный текст статьи больше не содержит прежнего контекста рекомендации.</p>','Новая версия'))
 assert client.post(f"/api/recommendations/{r['id']}/review",json={'status':'approved'}).status_code==409
 g=client.get('/api/sites/1/graph').json();assert len(g['nodes'])==3;assert sum(n['pagerank'] for n in g['nodes'])==pytest.approx(1)

def test_origin_and_missing_site(client):
 assert client.post('/api/sites',json={'url':'https://a.org'},headers={'Origin':'https://evil.org'}).status_code==403
 assert client.get('/api/sites/999/pages').status_code==404
 assert client.get('/').status_code==200

def test_db_requires_configuration(client,monkeypatch):
 for name in ['WP_DB_HOST','WP_DB_NAME','WP_DB_USER','WP_DB_PASSWORD','WP_SITE_URL']:monkeypatch.delenv(name,raising=False)
 assert client.post('/api/import-database',json={}).status_code==409

def test_generation_diagnostics(client):
 seed(client);service.generate(1)
 data=client.get('/api/sites/1/diagnostics').json()
 assert data['pages'] and data['accepted']>0 and data['rejections']
 assert all(v>=0 for v in data['rejections'].values())
 assert client.get('/api/sites/999/diagnostics').status_code==404

def test_generation_job_saves_selected_threshold_without_resetting_other_settings(client,monkeypatch):
 seed(client)
 selected=[]
 monkeypatch.setattr(service,'generate',lambda site:selected.append(service.settings(site)['minimum_score']) or 2)
 started=client.post('/api/sites/1/jobs/generate',json={'minimum_score':72.5})
 assert started.status_code==200
 assert selected==[72.5]
 settings=client.get('/api/sites/1/settings').json()
 assert settings['minimum_score']==72.5
 assert settings['max_per_page']==3
 assert client.get('/api/sites/1/jobs').json()[0]['status']=='completed'
 assert client.post('/api/sites/1/jobs/generate',json={'minimum_score':101}).status_code==422
 assert client.get('/api/sites/1/settings').json()['minimum_score']==72.5

def test_wordpress_public_rest_import(client,monkeypatch):
 client.post('/api/sites',json={'url':'https://a.org'})
 class Response:
  status_code=200
  headers={'X-WP-TotalPages':'1'}
  def __init__(self,data):self.data=data
  def json(self):return self.data
 class Client:
  def __init__(self,**kwargs):pass
  def __enter__(self):return self
  def __exit__(self,*args):pass
  def get(self,url):
   if url.endswith('/types'):return Response({'post':{},'page':{},'cities':{'rest_base':'cities'}})
   endpoint=url.split('/wp/v2/')[1].split('?')[0]
   slug={'posts':'travel','pages':'about','cities':'rostov'}[endpoint]
   item={'id':4,'type':endpoint[:-1] if endpoint!='cities' else 'cities','link':f'https://a.org/{slug}/','title':{'rendered':slug},'content':{'rendered':'<article><p>Москва является крупным городом. В Москву приезжают на экскурсии и отдых.</p></article>'},'categories':[2],'tags':[]}
   return Response([item])
 monkeypatch.setattr(service.httpx,'Client',Client)
 result=service.import_wordpress(1)
 assert result=={'visited':3,'stored':3,'errors':[]}
 assert len(db.pages(1))==3
 assert {p['title'] for p in db.pages(1)}=={'travel','about','rostov'}

def test_authentication_and_tenant_isolation(client,tmp_path):
 seed(client)
 with TestClient(app) as other:
  assert other.get('/api/sites').status_code==401
  reg=other.post('/api/auth/register',json={'email':'other@example.org','password':'another-long-password-456'})
  assert reg.json()['created'] and not reg.json()['verification_required']
  assert other.post('/api/auth/login',json={'email':'other@example.org','password':'another-long-password-456'}).status_code==200
  assert other.get('/api/sites').json()==[]
  assert other.get('/api/sites/1/pages').status_code==404
 assert client.post('/api/auth/logout',json={}).status_code==200
 assert client.get('/api/sites').status_code==401

def test_registration_password_policy(client):
 r=client.post('/api/auth/register',json={'email':'weak@example.org','password':'short'})
 assert r.status_code==422

def test_resend_verification_revokes_previous_local_link(client,monkeypatch):
 monkeypatch.setenv('EMAIL_VERIFICATION_REQUIRED','true')
 registration=client.post('/api/auth/register',json={'email':'resend@example.org','password':'resend-test-password-123'})
 old_token=parse_qs(urlsplit(registration.json()['verification_url']).query)['verify'][0]
 resend=client.post('/api/auth/resend-verification',json={'email':'RESEND@example.org'})
 assert resend.status_code==200 and resend.json()['verification_url']
 new_token=parse_qs(urlsplit(resend.json()['verification_url']).query)['verify'][0]
 assert new_token!=old_token
 assert client.post('/api/auth/verify',json={'token':old_token}).status_code==400
 assert client.post('/api/auth/verify',json={'token':new_token}).status_code==200
 assert client.post('/api/auth/resend-verification',json={'email':'resend@example.org'}).json().get('verification_url') is None

def test_local_registration_immediately_activates_and_logs_in(client):
 response=client.post('/api/auth/register',json={'email':'instant@example.org','password':'instant-test-password-123'})
 assert response.status_code==200
 assert response.json()['created'] and not response.json()['verification_required']
 assert 'verification_url' not in response.json()
 login=client.post('/api/auth/login',json={'email':'instant@example.org','password':'instant-test-password-123'})
 assert login.status_code==200
 assert client.get('/api/auth/me').json()['email']=='instant@example.org'
 assert db.rows('SELECT id FROM users WHERE email=? AND email_verified=1',('instant@example.org',))
 assert not db.rows('SELECT id FROM email_tokens WHERE user_id=(SELECT id FROM users WHERE email=?)',('instant@example.org',))

def test_production_requires_mail_and_uses_secure_cookie(client,monkeypatch):
 monkeypatch.setenv('APP_ENV','production');monkeypatch.delenv('SMTP_HOST',raising=False)
 headers={'Origin':'http://testserver'}
 assert client.post('/api/auth/register',json={'email':'new@example.org','password':'a-long-password-123'},headers=headers).status_code==503
 r=client.post('/api/auth/login',json={'email':'owner@example.org','password':'long-test-password-123'},headers=headers)
 assert r.status_code==200
 cookie=r.headers['set-cookie']
 assert cookie.startswith('__Host-ui_session=') and 'Secure' in cookie and 'HttpOnly' in cookie and 'SameSite=lax' in cookie

def test_registration_is_empty_and_adding_unowned_legacy_site_clears_snapshot(tmp_path,monkeypatch):
 monkeypatch.setattr(db,'DB',str(tmp_path/'bootstrap.sqlite'))
 db.init()
 with db.connect() as c:
  c.execute("INSERT INTO sites(url,name) VALUES('https://old.example.org','old.example.org')")
 db.save_page(1,parse('https://old.example.org/old','<p>Это старый снимок. Он должен быть очищен при добавлении сайта.</p>','Старый снимок'))
 with TestClient(app) as c:
  r=c.post('/api/auth/register',json={'email':'pilot@example.org','password':'bootstrap-password-123'})
  assert r.json()['created'] and not r.json()['verification_required']
  assert c.post('/api/auth/login',json={'email':'pilot@example.org','password':'bootstrap-password-123'}).status_code==200
  assert c.get('/api/sites').json()==[]
  added=c.post('/api/sites',json={'url':'https://old.example.org'})
  assert added.status_code==200 and len(added.json())==1
  assert c.get('/api/sites/1/pages').json()==[]
