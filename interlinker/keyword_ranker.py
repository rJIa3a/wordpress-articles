"""Conservative, traceable candidates from imported query-to-URL mappings."""
import re

from .content import page_identity, same_page
from .retrieval import STOP, tokens

EDGE_STOP = STOP | {'о', 'у', 'за', 'под', 'над', 'об', 'про', 'без', 'через'}


def rules_for_pages(rows, pages):
    by_identity = {page_identity(page['url']): page for page in pages}
    rules = []
    seen = set()
    for row in rows:
        query = ' '.join(row['query'].split())
        words = re.findall(r'\w+(?:-\w+)*', query)
        if not 2 <= len(words) <= 7 or not 8 <= len(query) <= 80:
            continue
        if re.search(r'[^\w\s-]', query) or words[0].lower() in EDGE_STOP or words[-1].lower() in EDGE_STOP:
            continue
        target = by_identity.get(page_identity(row['target_url']))
        if not target:
            continue
        entity = target.get('entity_name')
        if entity:
            from .city_morphology import city_lemma
            query_entity = {city_lemma(word) for word in re.findall(r'\w+', query)}
            target_entity = {city_lemma(word) for word in re.findall(r'\w+', entity)}
            if not target_entity <= query_entity:
                continue
        elif len(set(tokens(query)) & set(tokens(target['title']))) < 2:
            continue
        key = (query.casefold(), page_identity(target['url']))
        if key in seen:
            continue
        seen.add(key)
        rules.append((query, target, row['source_file']))
    return rules


def candidates(source, rules, engine, threshold):
    """Keep only exact text spans mapped to a retrieved, relevant site page."""
    found = []
    used_targets = {page_identity(link['target']) for link in source['links']}
    for block in source['blocks']:
        text = block['text']
        folded = text.casefold()
        matches = []
        for query, target, source_file in rules:
            if query.casefold() not in folded:
                continue
            identity = page_identity(target['url'])
            if identity in used_targets or same_page(source['url'], target['url']):
                continue
            match = re.search(r'(?<!\w)' + re.escape(query) + r'(?!\w)', text, re.I)
            if match:
                matches.append((match, query, target, source_file))
        if not matches:
            continue
        retrieved = {page_identity(item['target']): item for item in engine.retrieve(source, block)}
        for match, query, target, source_file in matches:
            item = retrieved.get(page_identity(target['url']))
            if not item or item['components']['semantic'] < .25:
                continue
            anchor = text[match.start():match.end()]
            from .entities import noncity_name
            if target.get('entity_name') and noncity_name(text, match.start()):
                continue
            from .geography import intent_allowed
            if not intent_allowed(text, target, anchor):
                continue
            # Exact source wording and a user-supplied URL mapping add ten points.
            # Retrieval and semantic checks still apply; this score is not a probability.
            score = min(100, round((.65 * item['retrieval'] + .35 + .10) * 100, 2))
            if score < threshold:
                continue
            found.append(dict(
                source=source['url'], block=block['id'], target=target['url'],
                anchor=anchor, start=match.start(), end=match.end(), quality=1.0,
                type='key', origin='key', key_query=query, key_source_file=source_file,
                score=score, components={**item['components'], 'key_exact': 1, 'key_bonus': 10},
            ))
    return sorted(found, key=lambda item: (-item['score'], -len(item['anchor'])))
