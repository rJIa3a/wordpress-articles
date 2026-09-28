from fastapi.testclient import TestClient

from interlinker import storage
from interlinker.app import app


def test_keyword_csv_preview_import_and_list_are_project_scoped(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'DB', str(tmp_path / 'service.sqlite3'))
    payload = (
        'Запрос;Страница;Позиция;\r\n'
        'переезд в Пермь;https://dagorod.ru/pereezd-v-perm/;3;\r\n'
    ).encode('cp1251')

    with TestClient(app) as client:
        registered = client.post('/api/auth/register', json={
            'email': 'keyword-import@example.test', 'password': 'Long-test-password-123',
        })
        assert registered.status_code == 200
        logged_in = client.post('/api/auth/login', json={
            'email': 'keyword-import@example.test', 'password': 'Long-test-password-123',
        })
        assert logged_in.status_code == 200
        added = client.post('/api/sites', json={'url': 'https://dagorod.ru'})
        assert added.status_code == 200
        site_id = added.json()[0]['id']

        preview = client.post(
            f'/api/sites/{site_id}/keywords/preview',
            files={'file': ('sem-yadro.csv', payload, 'text/csv')},
        )
        assert preview.status_code == 200
        assert preview.json()['columns'][:2] == ['Запрос', 'Страница']

        data = {'query_column': 'Запрос', 'url_column': 'Страница'}
        imported = client.post(
            f'/api/sites/{site_id}/keywords/import', data=data,
            files={'file': ('sem-yadro.csv', payload, 'text/csv')},
        )
        assert imported.status_code == 200
        assert imported.json()['inserted'] == 1
        assert imported.json()['skipped'] == 0

        duplicate = client.post(
            f'/api/sites/{site_id}/keywords/import', data=data,
            files={'file': ('sem-yadro.csv', payload, 'text/csv')},
        )
        assert duplicate.json()['inserted'] == 0
        assert duplicate.json()['already_present'] == 1

        listed = client.get(f'/api/sites/{site_id}/keywords')
        assert listed.status_code == 200
        assert listed.json()['total'] == 1
        assert listed.json()['items'][0]['query'] == 'переезд в Пермь'
        assert listed.json()['items'][0]['target_imported'] is False
