"""Published WordPress content import using a SELECT-only MySQL connection."""
import os,re,datetime
from urllib.parse import urlsplit
from . import storage as db
from .content import normalize,parse

def import_database():
 from dotenv import load_dotenv
 import pymysql
 load_dotenv(override=False)
 required=['WP_DB_HOST','WP_DB_NAME','WP_DB_USER','WP_DB_PASSWORD','WP_SITE_URL']
 missing=[name for name in required if not os.getenv(name)]
 if missing:raise ValueError('Настройте локальный .env: '+', '.join(missing))
 prefix=os.getenv('WP_DB_PREFIX','wp_')
 if not re.fullmatch(r'[A-Za-z0-9_]+',prefix):raise ValueError('Недопустимый префикс таблиц')
 base=normalize(os.environ['WP_SITE_URL'])
 if not base or urlsplit(base).path!='/':raise ValueError('WP_SITE_URL должен содержать корень сайта')
 base=base.rstrip('/')
 kwargs=dict(host=os.environ['WP_DB_HOST'],port=int(os.getenv('WP_DB_PORT','3306')),user=os.environ['WP_DB_USER'],password=os.environ['WP_DB_PASSWORD'],database=os.environ['WP_DB_NAME'],charset='utf8mb4',connect_timeout=10,read_timeout=30,cursorclass=pymysql.cursors.DictCursor,autocommit=False)
 if os.getenv('WP_DB_SSL_CA'):kwargs.update(ssl_ca=os.environ['WP_DB_SSL_CA'],ssl_verify_cert=True,ssl_verify_identity=True)
 try:conn=pymysql.connect(**kwargs)
 except Exception:raise ValueError('Нет соединения с MySQL. Проверьте локальные настройки, VPN/SSH-туннель и права пользователя.') from None
 count=0
 try:
  with conn.cursor() as c:
   c.execute('SET SESSION TRANSACTION READ ONLY');c.execute('START TRANSACTION READ ONLY')
   c.execute(f'SELECT option_value FROM {prefix}options WHERE option_name=%s',('permalink_structure',));row=c.fetchone();pattern=row['option_value'] if row else ''
   unsupported=set(re.findall(r'%\w+%',pattern))-{'%postname%','%post_id%','%year%','%monthnum%','%day%','%hour%','%minute%','%second%'}
   if unsupported:raise ValueError('Структура URL требует отдельного resolver: '+', '.join(sorted(unsupported)))
   with db.connect() as local:
    local.execute('INSERT OR IGNORE INTO sites(url,name) VALUES(?,?)',(base,urlsplit(base).netloc));site=local.execute('SELECT id FROM sites WHERE url=?',(base,)).fetchone()[0]
   last=0
   while True:
    c.execute(f"SELECT ID,post_title,post_name,post_content,post_date FROM {prefix}posts WHERE post_status=%s AND post_type=%s AND ID>%s ORDER BY ID LIMIT 100",('publish','post',last));posts=c.fetchall()
    if not posts:break
    for post in posts:
     last=post['ID'];date=post['post_date']
     if not pattern:raise ValueError('Plain permalinks требуют REST resolver; импорт остановлен')
     path=pattern
     replacements={'%postname%':post['post_name'],'%post_id%':str(last),'%year%':f'{date.year:04}','%monthnum%':f'{date.month:02}','%day%':f'{date.day:02}','%hour%':f'{date.hour:02}','%minute%':f'{date.minute:02}','%second%':f'{date.second:02}'}
     for key,val in replacements.items():path=path.replace(key,val)
     c.execute(f"SELECT meta_key,meta_value FROM {prefix}postmeta WHERE post_id=%s AND meta_key IN (%s,%s)",(last,'_yoast_wpseo_meta-robots-noindex','_yoast_wpseo_canonical'));meta={r['meta_key']:r['meta_value'] for r in c.fetchall()}
     if meta.get('_yoast_wpseo_meta-robots-noindex')=='1':continue
     url=base+'/'+path.lstrip('/');canonical=meta.get('_yoast_wpseo_canonical') or url
     page=parse(url,post['post_content'],post['post_title'],meta={'canonical':canonical,'type':'post'})
     if page:page['wordpress_id']=last;page['source']='mysql_raw';db.save_page(site,page);count+=1
  conn.rollback() # no writes; explicit end of read-only transaction
 finally:conn.close()
 return count
