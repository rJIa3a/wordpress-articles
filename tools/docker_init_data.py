"""Seed the Docker volume from the existing local SQLite database once."""
import os
import sqlite3

source='/seed/interlinker.sqlite3'
target='/data/interlinker.sqlite3'
if not os.path.exists(target) and os.path.exists(source):
    src=sqlite3.connect(source,timeout=30)
    dst=sqlite3.connect(target,timeout=30)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
os.chown('/data',10001,999)
if os.path.exists(target):
    os.chown(target,10001,999)
