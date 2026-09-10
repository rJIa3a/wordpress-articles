"""Geographic morphology for a city shortlist, never a relevance decision."""
from functools import lru_cache
from .retrieval import MORPH,lemma

@lru_cache(maxsize=30000)
def city_lemma(word):
    word=word.casefold()
    if '-' in word:return '-'.join(city_lemma(part) for part in word.split('-'))
    parses=MORPH.parse(word)
    geographic=[p for p in parses if 'Geox' in p.tag]
    return geographic[0].normal_form if geographic else lemma(word)
