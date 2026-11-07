"""SQLite 스키마와 연결."""
import json
import sqlite3
from datetime import datetime

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    url           TEXT NOT NULL UNIQUE,
    naver_link    TEXT,
    title         TEXT NOT NULL,
    description   TEXT,
    pub_date      TEXT NOT NULL,          -- YYYY-MM-DD
    pub_datetime  TEXT,
    press         TEXT,
    domain        TEXT,
    source        TEXT NOT NULL,          -- naver|newstore|bigkinds|sample
    query         TEXT,
    topic         TEXT,
    cluster_id    INTEGER,
    views         INTEGER,
    views_checked TEXT,
    views_status  TEXT,
    collected_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_articles_date    ON articles(pub_date);
CREATE INDEX IF NOT EXISTS idx_articles_cluster ON articles(cluster_id);
CREATE INDEX IF NOT EXISTS idx_articles_press   ON articles(press);
CREATE INDEX IF NOT EXISTS idx_articles_topic   ON articles(topic);

CREATE TABLE IF NOT EXISTS clusters (
    id          INTEGER PRIMARY KEY,
    title       TEXT NOT NULL,
    first_date  TEXT,
    last_date   TEXT,
    article_cnt INTEGER,
    press_cnt   INTEGER,
    views_sum   INTEGER,
    topic       TEXT
);
CREATE INDEX IF NOT EXISTS idx_clusters_first ON clusters(first_date);

CREATE TABLE IF NOT EXISTS runs (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    step    TEXT NOT NULL,
    started TEXT NOT NULL,
    detail  TEXT
);
"""

_db_path = None


def use_sample(flag=True):
    global _db_path
    _db_path = config.SAMPLE_DB_PATH if flag else config.DB_PATH


def current_path():
    return _db_path or config.DB_PATH


def connect(path=None):
    p = path or current_path()
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.executescript(SCHEMA)
    return conn


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log_run(conn, step, detail):
    conn.execute(
        "INSERT INTO runs(step, started, detail) VALUES (?,?,?)",
        (step, now(), json.dumps(detail, ensure_ascii=False)),
    )
    conn.commit()
