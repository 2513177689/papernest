"""Local, single-user persistence. Each operation uses a short SQLite transaction."""
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get('PAPERNEST_DATA', ROOT / 'data')).resolve()
DATA.mkdir(parents=True, exist_ok=True)
FILES = DATA / 'papers'
FILES.mkdir(exist_ok=True)
DB = DATA / 'papernest.sqlite3'


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return uuid.uuid4().hex


@contextmanager
def connect():
    con = sqlite3.connect(DB, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init():
    with connect() as c:
        c.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS directions(id TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS papers(id TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS notes(id TEXT PRIMARY KEY, paper_id TEXT NOT NULL, data TEXT NOT NULL,
            FOREIGN KEY(paper_id) REFERENCES papers(id));
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS recommendations(direction_id TEXT NOT NULL, paper_id TEXT NOT NULL,
            data TEXT NOT NULL, PRIMARY KEY(direction_id,paper_id));
        CREATE TABLE IF NOT EXISTS courses(id TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS ai_cache(key TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS usage(id TEXT PRIMARY KEY, day TEXT NOT NULL, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS zotero_map(paper_id TEXT PRIMARY KEY, data TEXT NOT NULL);
        ''')


TABLES = {'directions','papers','jobs','courses','ai_cache','zotero_map'}


def all_rows(table):
    if table not in TABLES:
        raise ValueError('Unknown table')
    with connect() as c:
        return [json.loads(r['data']) for r in c.execute(f'SELECT data FROM {table}')]


def get(table, key):
    if table not in TABLES:
        raise ValueError('Unknown table')
    pk = 'key' if table == 'ai_cache' else 'paper_id' if table == 'zotero_map' else 'id'
    with connect() as c:
        row = c.execute(f'SELECT data FROM {table} WHERE {pk}=?', (key,)).fetchone()
        return json.loads(row['data']) if row else None


def put(table, key, value):
    if table not in TABLES:
        raise ValueError('Unknown table')
    pk = 'key' if table == 'ai_cache' else 'paper_id' if table == 'zotero_map' else 'id'
    with connect() as c:
        c.execute(f'INSERT INTO {table}({pk},data) VALUES (?,?) ON CONFLICT({pk}) DO UPDATE SET data=excluded.data',
                  (key, json.dumps(value, ensure_ascii=False)))


def setting(key, default=None):
    with connect() as c:
        row = c.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return json.loads(row['value']) if row else default


def set_setting(key, value):
    with connect() as c:
        c.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                  (key, json.dumps(value, ensure_ascii=False)))


def notes(paper_id=None):
    with connect() as c:
        rows = c.execute('SELECT data FROM notes' + (' WHERE paper_id=?' if paper_id else ''),
                         (paper_id,) if paper_id else ())
        return sorted([json.loads(r['data']) for r in rows], key=lambda x:x['created'], reverse=True)


def note_add(paper_id, text, quote='', page=0, rects=None, file_hash=''):
    item = dict(id=uid(), paper_id=paper_id, text=text, quote=quote, page=page,
                rects=rects or [], file_hash=file_hash, created=now())
    with connect() as c:
        c.execute('INSERT INTO notes VALUES (?,?,?)', (item['id'],paper_id,json.dumps(item,ensure_ascii=False)))
    return item
