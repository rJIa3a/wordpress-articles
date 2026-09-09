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

def test_city_intent_and_long_editorial_title(tmp_path):
 import json
 from interlinker.geography import annotate,intent_allowed
 pages=[dict(title='Достопримечательности Москвы: что посмотреть',url='site')]
 corpus=tmp_path/'cities.json';corpus.write_text(json.dumps([dict(title='Москва')]))
 assert annotate(pages,corpus)==1 and pages[0]['entity_name']=='Москва'
 assert not intent_allowed('Писатель родился в Москве в XIX веке.',pages[0],'Москве')
 assert intent_allowed('Путешественники осматривают музеи в Москве.',pages[0],'Москве')

def test_embedding_cache_preserves_order_and_resumes(tmp_path, monkeypatch):
 import numpy as np
 from types import SimpleNamespace
 from interlinker.retrieval import MiniLM
 monkeypatch.chdir(tmp_path)
 monkeypatch.setattr('importlib.metadata.version',lambda _: 'test')
 calls=[]
 class FakeModel:
  model=SimpleNamespace(_model_dir='fixed-model')
  def embed(self,texts,batch_size):
   calls.extend(texts)
   return [np.array([len(t),1.0]) for t in texts]
 provider=MiniLM.__new__(MiniLM);provider.model=FakeModel()
 first=provider.encode(['longer','a','longer'])
 assert calls==['a','longer']
 second=provider.encode(['a','longer'])
 assert calls==['a','longer']
 np.testing.assert_allclose(first[[1,0]],second)
 np.testing.assert_allclose(np.linalg.norm(second,axis=1),1)

def test_city_disambiguation_preserves_actual_city_mentions():
 from interlinker.entities import noncity_name
 for text in ['на реке Воронеж','у реки Лесной Воронеж','улица Москва']:
  assert noncity_name(text,text.rfind(' ')+1)
 for text in ['город Воронеж','из Москвы в Воронеж','на реке Дон находится Воронеж']:
  assert not noncity_name(text,text.rfind(' ')+1)

def test_refinement_excludes_test_sources_and_labels():
 from city_benchmark.refine import development_data
 pages=[dict(url=u,title=t,blocks=[dict(id='0',section='',text='Путь из Москвы в Казань описан подробно.')]) for u,t in [('a','Москва'),('b','Казань'),('c','Самара')]]
 gold=[dict(source='c',target='b',anchor='Секретныйалиас')]*2
 r,_,g=development_data(pages,gold,{'a':'train','b':'dev','c':'test'})
 assert r and all(x['source']!='c' for x in r) and not g
