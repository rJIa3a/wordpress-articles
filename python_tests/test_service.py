import json
import pytest
from fastapi.testclient import TestClient
from interlinker import storage as db,service
from interlinker.content import normalize,parse,insert_preview
from interlinker.app import app
@pytest.fixture
def client(tmp_path,monkeypatch):
 monkeypatch.setattr(db,'DB',str(tmp_path/'test.sqlite'))
 with TestClient(app) as c:yield c

def test_normalization():
 assert normalize('https://EXAMPLE.org/a#b')=='https://example.org/a'
 for u in ['javascript:alert(1)','https://example.org/?a=1','https://example.org/wp-admin/a','https://example.org/page/2/']:
  assert normalize(u) is None

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
 assert client.post('/api/import-database',json={}).status_code==422
