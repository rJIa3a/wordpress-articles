import json,sqlite3,os
from pathlib import Path
from contextlib import contextmanager
DB=os.environ.get('INTERLINKER_DB','local-data/interlinker.sqlite3')
@contextmanager
def connect():
 Path(DB).parent.mkdir(parents=True,exist_ok=True)
 c=sqlite3.connect(DB,timeout=30);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');c.execute('PRAGMA journal_mode=WAL')
 try:yield c;c.commit()
 except Exception:c.rollback();raise
 finally:c.close()
def init():
 with connect() as c:c.executescript('''
 CREATE TABLE IF NOT EXISTS sites(id INTEGER PRIMARY KEY,url TEXT UNIQUE NOT NULL,name TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS pages(id INTEGER PRIMARY KEY,site_id INTEGER REFERENCES sites(id),url TEXT NOT NULL,title TEXT,html TEXT,data TEXT NOT NULL,UNIQUE(site_id,url));
 CREATE TABLE IF NOT EXISTS content_blocks(id INTEGER PRIMARY KEY,page_id INTEGER REFERENCES pages(id) ON DELETE CASCADE,locator TEXT,text TEXT,html TEXT,section TEXT);
 CREATE TABLE IF NOT EXISTS links(id INTEGER PRIMARY KEY,page_id INTEGER REFERENCES pages(id) ON DELETE CASCADE,target TEXT,anchor TEXT,contextual INTEGER);
 CREATE TABLE IF NOT EXISTS recommendations(id INTEGER PRIMARY KEY,site_id INTEGER REFERENCES sites(id),source TEXT,target TEXT,block TEXT,anchor TEXT,score REAL,data TEXT,status TEXT DEFAULT 'pending',created TEXT DEFAULT CURRENT_TIMESTAMP,approved TEXT,UNIQUE(site_id,source,target,block));
 CREATE TABLE IF NOT EXISTS seo_priorities(id INTEGER PRIMARY KEY,site_id INTEGER REFERENCES sites(id),kind TEXT,value TEXT,weight REAL,blocked INTEGER DEFAULT 0,UNIQUE(site_id,kind,value));
 CREATE TABLE IF NOT EXISTS crawl_runs(id INTEGER PRIMARY KEY,site_id INTEGER REFERENCES sites(id),status TEXT,visited INTEGER DEFAULT 0,stored INTEGER DEFAULT 0,error TEXT,created TEXT DEFAULT CURRENT_TIMESTAMP,finished TEXT);
 CREATE TABLE IF NOT EXISTS change_history(id INTEGER PRIMARY KEY,recommendation_id INTEGER REFERENCES recommendations(id),action TEXT,old_html TEXT,new_html TEXT,created TEXT DEFAULT CURRENT_TIMESTAMP);
 CREATE TABLE IF NOT EXISTS generation_diagnostics(site_id INTEGER PRIMARY KEY REFERENCES sites(id),data TEXT NOT NULL,created TEXT DEFAULT CURRENT_TIMESTAMP);
 CREATE TABLE IF NOT EXISTS settings(site_id INTEGER PRIMARY KEY REFERENCES sites(id),data TEXT);
 ''')
def rows(sql,args=()):
 with connect() as c:return [dict(r) for r in c.execute(sql,args)]
def pages(site):return [dict(id=r['id'],**json.loads(r['data'])) for r in rows('SELECT * FROM pages WHERE site_id=?',(site,))]
def save_page(site,p):
 with connect() as c:
  old=c.execute('SELECT data FROM pages WHERE site_id=? AND url=?',(site,p['url'])).fetchone()
  if old and json.loads(old['data']).get('html')!=p['html']:
   c.execute("UPDATE recommendations SET status='stale' WHERE site_id=? AND source=? AND status IN ('pending','approved')",(site,p['url']))
  c.execute('INSERT INTO pages(site_id,url,title,html,data) VALUES(?,?,?,?,?) ON CONFLICT(site_id,url) DO UPDATE SET title=excluded.title,html=excluded.html,data=excluded.data',(site,p['url'],p['title'],p['html'],json.dumps(p,ensure_ascii=False)))
  pid=c.execute('SELECT id FROM pages WHERE site_id=? AND url=?',(site,p['url'])).fetchone()[0]
  c.execute('DELETE FROM content_blocks WHERE page_id=?',(pid,));c.execute('DELETE FROM links WHERE page_id=?',(pid,))
  c.executemany('INSERT INTO content_blocks(page_id,locator,text,html,section) VALUES(?,?,?,?,?)',[(pid,b['id'],b['text'],b['html'],b['section']) for b in p['blocks']])
  c.executemany('INSERT INTO links(page_id,target,anchor,contextual) VALUES(?,?,?,?)',[(pid,l['target'],l['anchor'],l['contextual']) for l in p['links']])
