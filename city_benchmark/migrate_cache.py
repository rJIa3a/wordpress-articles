"""Migrate a read-only SQLite snapshot to immutable embedding batches."""
import hashlib,sqlite3
from pathlib import Path
import numpy as np

def run():
 folder=Path('local-data/vector-cache');folder.mkdir(parents=True,exist_ok=True)
 with sqlite3.connect('file:local-data/embeddings-checkpoint.sqlite3?mode=ro',uri=True) as c:
  cursor=c.execute('SELECT key,data FROM vectors ORDER BY key');count=0
  while rows:=cursor.fetchmany(128):
   keys=[r[0] for r in rows];vectors=np.array([np.frombuffer(r[1],dtype=np.float32) for r in rows]);name=hashlib.sha256(''.join(keys).encode()).hexdigest()+'.npz'
   np.savez_compressed(folder/name,keys=np.array(keys),vectors=vectors);count+=len(keys)
 print('Migrated',count)
if __name__=='__main__':run()
