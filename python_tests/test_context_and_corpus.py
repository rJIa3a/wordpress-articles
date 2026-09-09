import pytest
from interlinker.context import validate_decision

def test_llm_must_use_candidates_and_natural_anchor():
 candidates=[{'url':'https://a.org/moscow'}];text='Поездка в Москву запланирована на лето.'
 valid={'should_link':True,'target_url':candidates[0]['url'],'anchor':'Москву','confidence':.93}
 assert validate_decision(valid,candidates,text)
 assert validate_decision(valid|{'target_url':'https://bad.org'},candidates,text) is None
 assert validate_decision(valid|{'anchor':'купить билеты дешево'},candidates,text) is None
 assert validate_decision(valid|{'confidence':float('nan')},candidates,text) is None
 assert validate_decision(valid|{'should_link':False},candidates,text) is None

def test_wiki_prose_offsets_and_hidden_links():
 pytest.importorskip('mwparserfromhell')
 from city_benchmark.collect import clean
 p,g=clean("{{Город|название=Тест}}\nГород расположен неподалеку от [[Москва|Москвы]], на берегу большой реки и рядом с несколькими районами.\n\n== История ==\nПозднее появилась дорога в [[Казань]], которая позволила расширить торговлю между городами.\n== Примечания ==\n<references />",'Тест')
 assert len(g)==2
 for a in g:
  b=next(b for b in p['blocks'] if b['id']==a['block']);assert b['text'][a['start']:a['end']]==a['anchor']
 assert 'target_title' not in str(p) and '[[Москва' not in str(p)

def test_city_registry_does_not_learn_test_anchors():
 pytest.importorskip('mwparserfromhell')
 from city_benchmark.experiment import candidates
 pages=[dict(url='a',title='ГородА',blocks=[dict(id='0',section='',text='В тексте встречается Скрытыйалиас рядом с описанием района.')]),dict(url='b',title='ГородБ',blocks=[])]
 gold=[dict(source='a',target='b',anchor='Скрытыйалиас')]*2
 r,_=candidates(pages,gold,{'a':'test','b':'train'});assert not r
