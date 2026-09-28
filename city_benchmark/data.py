"""Compressed JSON support for large, reproducible corpus annotations."""
import gzip,json
from pathlib import Path

def load_json(path):
 path=Path(path);compressed=path.with_name(path.name+'.gz')
 if compressed.exists():
  with gzip.open(compressed,'rt',encoding='utf-8') as f:return json.load(f)
 return json.loads(path.read_text())

def save_compressed(path,data):
 path=Path(path)
 with gzip.open(path.with_name(path.name+'.gz'),'wt',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False)
