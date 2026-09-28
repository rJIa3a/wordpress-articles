"""Safe parsing and validation for user supplied SEO keyword CSV exports."""
import csv
import hashlib
import io
import json
from pathlib import PurePath

from .content import normalize, page_identity

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_ROWS = 100_000


def parse_csv(filename, payload):
    if len(payload) > MAX_UPLOAD_BYTES:
        raise ValueError('CSV-файл слишком большой (лимит 15 МБ)')
    if not filename or PurePath(filename).suffix.lower() != '.csv':
        raise ValueError('Загрузите файл с расширением .csv')
    text = None
    for encoding in ('utf-8-sig', 'cp1251'):
        try:
            text = payload.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError('Не удалось прочитать кодировку CSV (поддерживаются UTF-8 и Windows-1251)')
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=';,\t')
        reader = csv.DictReader(io.StringIO(text, newline=''), dialect=dialect)
    except csv.Error:
        first = sample.splitlines()[0] if sample else ''
        delimiter = max((';', ',', '\t'), key=first.count)
        reader = csv.DictReader(io.StringIO(text, newline=''), delimiter=delimiter)
    columns = [str(c or '').strip() for c in (reader.fieldnames or [])]
    # SemYadro's exports contain a final empty column after a trailing semicolon.
    while columns and not columns[-1]:
        columns.pop()
    if len(columns) < 2 or any(not c for c in columns) or len(set(columns)) != len(columns):
        raise ValueError('В CSV нужны непустые уникальные заголовки колонок')
    reader.fieldnames = columns
    rows = []
    for row in reader:
        if len(rows) >= MAX_ROWS:
            raise ValueError('В CSV больше 100 000 строк; разделите файл на части')
        clean = {k: str(row.get(k, '') or '').strip() for k in columns}
        if any(clean.values()):
            rows.append(clean)
    if not rows:
        raise ValueError('В CSV нет строк с данными')
    return columns, rows


def preview(filename, payload):
    columns, rows = parse_csv(filename, payload)
    return {
        'filename': PurePath(filename).name,
        'columns': columns,
        'row_count': len(rows),
        'sample': rows[:5],
    }


def prepare_rows(filename, payload, query_column, url_column, site_url):
    columns, rows = parse_csv(filename, payload)
    if query_column not in columns or url_column not in columns:
        raise ValueError('Выберите колонки запроса и URL из заголовков CSV')
    if query_column == url_column:
        raise ValueError('Для запроса и URL нужно выбрать разные колонки')
    expected_host = page_identity(site_url)[0]
    prepared = []
    skipped = 0
    for row in rows:
        query = ' '.join(row.get(query_column, '').split())
        target = normalize(row.get(url_column, ''))
        if not query or len(query) > 500 or not target or len(target) > 2048:
            skipped += 1
            continue
        identity = page_identity(target)
        if not identity or identity[0] != expected_host:
            skipped += 1
            continue
        details = {k: v[:1000] for k, v in row.items() if k not in (query_column, url_column)}
        canonical = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        prepared.append({
            'query': query,
            'target_url': target,
            'source_file': PurePath(filename).name[:255],
            'details': json.dumps(details, ensure_ascii=False),
            'row_hash': hashlib.sha256(canonical.encode('utf-8')).hexdigest(),
        })
    if not prepared:
        raise ValueError('Не найдено строк с запросом и URL выбранного сайта')
    return prepared, {'read': len(rows), 'valid': len(prepared), 'skipped': skipped}
