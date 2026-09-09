import re,hashlib,html as htmlmod
from urllib.parse import urljoin,urlsplit,urlunsplit
from bs4 import BeautifulSoup
from html.parser import HTMLParser

def normalize(url,base=None):
 u=urlsplit(urljoin(base or url,url))
 if u.scheme not in ('http','https') or not u.hostname or u.username or u.password or u.query:return None
 host=u.hostname.lower()
 if u.port and u.port not in (80,443):return None
 path=u.path or '/'
 if re.search(r'/(wp-admin|wp-login\.php|feed|page/\d+|cart|checkout|search)(/|$)',path,re.I):return None
 return urlunsplit((u.scheme,host,path,'',''))

def parse(url,raw,title='',depth=0,meta=None):
 url=normalize(url)
 if not url:return None
 soup=BeautifulSoup(raw,'html.parser');meta=meta or {}
 robots=soup.find('meta',attrs={'name':re.compile('^(robots|googlebot)$',re.I)})
 if robots and 'noindex' in robots.get('content','').lower():return None
 if meta.get('robots',{}).get('index')=='noindex':return None
 can=soup.find('link',rel='canonical');canonical=normalize(can.get('href',''),url) if can else normalize(meta.get('canonical',url),url)
 if canonical and canonical!=url:return None
 h1=soup.find('h1');t=soup.find('title');description=soup.find('meta',attrs={'name':'description'})
 title=BeautifulSoup(title,'html.parser').get_text(' ',strip=True) if title else (t.get_text(' ',strip=True) if t else h1.get_text(' ',strip=True) if h1 else url)
 root=soup.select_one('article .entry-content, .entry-content, article, main') or soup.body or soup
 links=[]
 for a in soup.find_all('a',href=True):
  target=normalize(a['href'],url)
  if target and urlsplit(target).netloc==urlsplit(url).netloc:
   contextual=bool(root in a.parents and not a.find_parent(['nav','header','footer','aside']))
   links.append(dict(target=target,anchor=a.get_text(' ',strip=True),contextual=int(contextual)))
 for node in root.select('script,style,nav,header,footer,aside,form,.related-posts,.sharedaddy'):node.decompose()
 blocks=[];section=''
 for node in root.find_all(['p','li','h2','h3']):
  if node.name in ('h2','h3'):section=node.get_text(' ',strip=True);continue
  if node.find_parent(['p','li']):continue
  text=node.get_text()
  if len(text.strip())<40:continue
  blocks.append(dict(id=str(len(blocks)),text=text,html=str(node),section=section))
 return dict(url=url,title=title,h1=h1.get_text(' ',strip=True) if h1 else title,description=description.get('content','') if description else meta.get('description',''),canonical=canonical or url,status=200,depth=depth,html=raw,blocks=blocks,links=links,categories=[str(x) for x in meta.get('categories',[])],page_type=meta.get('type','page'),fingerprint=hashlib.sha256(root.get_text().encode()).hexdigest())

class TextLocations(HTMLParser):
 def __init__(self,raw):
  super().__init__(convert_charrefs=False);self.raw=raw;self.offsets=[0];self.stack=[];self.ranges=[]
  for m in re.finditer('\n',raw):self.offsets.append(m.end())
 def handle_starttag(self,tag,attrs):
  if tag not in ('br','img','hr','input','meta','link','source','wbr','area','base','col','embed','param','track'):self.stack.append(tag)
 def handle_endtag(self,tag):
  if tag in self.stack:self.stack=self.stack[:len(self.stack)-1-self.stack[::-1].index(tag)]
 def handle_data(self,data):
  if any(t in self.stack for t in ('a','script','style','code','pre')):return
  line,col=self.getpos();start=self.offsets[line-1]+col;self.ranges.append((start,start+len(data)))

def insert_preview(raw,anchor,target):
 if not anchor or not normalize(target):raise ValueError('Недопустимый анкор или URL')
 p=TextLocations(raw);p.feed(raw)
 matches=[]
 for start,end in p.ranges:
  for m in re.finditer(re.escape(anchor),raw[start:end]):matches.append(start+m.start())
 if len(matches)!=1:raise ValueError('Анкор должен однозначно находиться в одном свободном текстовом узле')
 start=matches[0];return raw[:start]+'<a href="'+htmlmod.escape(target,quote=True)+'">'+raw[start:start+len(anchor)]+'</a>'+raw[start+len(anchor):]
