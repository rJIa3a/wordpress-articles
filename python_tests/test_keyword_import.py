import csv
import io

import pytest

from interlinker.keyword_import import parse_csv, prepare_rows, preview
from interlinker.keyword_ranker import rules_for_pages, candidates


def test_parses_sem_yadro_cp1251_export_with_trailing_empty_column():
    raw = (
        'Запрос;Страница;Позиция;Частотность;\r\n'
        'переезд в Пермь;https://dagorod.ru/pereezd-v-perm/;3;120;\r\n'
    ).encode('cp1251')

    result = preview('keys.csv', raw)

    assert result['columns'] == ['Запрос', 'Страница', 'Позиция', 'Частотность']
    assert result['row_count'] == 1
    assert result['sample'][0]['Запрос'] == 'переезд в Пермь'
    prepared, stats = prepare_rows(
        'keys.csv', raw, 'Запрос', 'Страница', 'https://dagorod.ru'
    )
    assert stats == {'read': 1, 'valid': 1, 'skipped': 0}
    assert prepared[0]['target_url'] == 'https://dagorod.ru/pereezd-v-perm/'
    assert prepared[0]['details'] == '{"Позиция": "3", "Частотность": "120"}'


def test_keyword_import_skips_other_hosts_and_keeps_source_fields():
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=['Запрос', 'URL', 'Позиция'])
    writer.writeheader()
    writer.writerow({'Запрос': 'переезд в Пермь', 'URL': 'https://dagorod.ru/perm/', 'Позиция': '5'})
    writer.writerow({'Запрос': 'чужой сайт', 'URL': 'https://example.org/page/', 'Позиция': '1'})
    writer.writerow({'Запрос': '', 'URL': 'https://dagorod.ru/empty/', 'Позиция': '2'})
    payload = stream.getvalue().encode()

    prepared, stats = prepare_rows('mapped.csv', payload, 'Запрос', 'URL', 'https://dagorod.ru')

    assert stats == {'read': 3, 'valid': 1, 'skipped': 2}
    assert prepared[0]['query'] == 'переезд в Пермь'
    assert prepared[0]['details'] == '{"Позиция": "5"}'


@pytest.mark.parametrize(
    ('filename', 'payload', 'query_column', 'url_column'),
    [
        ('keys.txt', b'q,u\na,b\n', 'q', 'u'),
        ('keys.csv', b'q,u\na,b\n', 'missing', 'u'),
        ('keys.csv', b'q,u\na,b\n', 'q', 'q'),
    ],
)
def test_rejects_invalid_upload_or_column_mapping(filename, payload, query_column, url_column):
    with pytest.raises(ValueError):
        prepare_rows(filename, payload, query_column, url_column, 'https://dagorod.ru')


def test_key_candidate_requires_exact_natural_text_and_imported_target():
    target = {'url': 'https://dagorod.ru/perm/', 'title': 'Климат Перми'}
    source = {
        'url': 'https://dagorod.ru/relocation/', 'links': [],
        'blocks': [{'id': '0', 'section': '', 'text': 'Летом климат в Перми кажется довольно мягким и удобным для прогулок.'}],
    }
    rows = [
        {'query': 'климат в перми', 'target_url': target['url'], 'source_file': 'keys.csv'},
        {'query': 'воронеж в', 'target_url': target['url'], 'source_file': 'keys.csv'},
        {'query': 'климат в перми', 'target_url': 'https://other.example/perm/', 'source_file': 'keys.csv'},
    ]

    class Retrieval:
        def retrieve(self, page, block):
            return [{'target': target['url'], 'retrieval': .6, 'components': {'semantic': .6, 'bm25': .5}}]

    rules = rules_for_pages(rows, [target, source])
    assert len(rules) == 1
    found = candidates(source, rules, Retrieval(), threshold=75)
    assert len(found) == 1
    assert found[0]['anchor'] == 'климат в Перми'
    assert found[0]['origin'] == 'key'
    assert found[0]['target'] == target['url']
    assert candidates({**source, 'links': [{'target': target['url']}]}, rules, Retrieval(), 75) == []
