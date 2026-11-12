"""
Database Access Tier with Connection Pooling & Managed MySQL Support
EV Charging Station Management System - Production Hardened
"""
import os
import ssl
import threading
from contextlib import contextmanager
from urllib.parse import urlparse, parse_qs, unquote

import pymysql
import pymysql.cursors
from dbutils.pooled_db import PooledDB
from flask import current_app

_POOLS = {}
_POOL_LOCK = threading.Lock()


def parse_database_url(database_url):
    """
    Parse a MySQL DATABASE_URL (mysql:// or mysql+pymysql://) into PyMySQL kwargs.
    Supports query parameters like ?ssl=true or ?ssl_mode=REQUIRED.
    """
    parsed = urlparse(database_url)
    if parsed.scheme not in ("mysql", "mysql+pymysql"):
        raise ValueError(f"Unsupported database scheme '{parsed.scheme}'. Expected mysql or mysql+pymysql.")

    qs = parse_qs(parsed.query)
    cfg = {
        "host": parsed.hostname or "127.0.0.1",
        "port": parsed.port or 3306,
        "user": unquote(parsed.username or "root"),
        "password": unquote(parsed.password or ""),
        "database": parsed.path.lstrip("/") or "ev_charging_db",
    }

    ssl_flag = (qs.get("ssl", [""])[0] or "").lower()
    ssl_mode = (qs.get("ssl_mode", [""])[0] or qs.get("ssl-mode", [""])[0] or "").upper()
    if ssl_flag in ("true", "1", "yes") or ssl_mode in ("REQUIRED", "VERIFY_CA", "VERIFY_IDENTITY"):
        cfg["ssl_required"] = True
    if "ssl_ca" in qs and qs["ssl_ca"][0]:
        cfg["ssl_ca"] = qs["ssl_ca"][0]
    return cfg


def get_db_config():
    """Retrieve database connection settings from Flask config or environment variables."""
    if current_app:
        db_url = current_app.config.get("DATABASE_URL") or os.getenv("DATABASE_URL", "").strip()
        ssl_ca = current_app.config.get("MYSQL_SSL_CA") or os.getenv("MYSQL_SSL_CA", "").strip()
        base = {
            "host": current_app.config.get("MYSQL_HOST", "127.0.0.1"),
            "port": int(current_app.config.get("MYSQL_PORT", 3306)),
            "user": current_app.config.get("MYSQL_USER", "root"),
            "password": current_app.config.get("MYSQL_PASSWORD", ""),
            "database": current_app.config.get("MYSQL_DATABASE", "ev_charging_db"),
        }
    else:
        db_url = os.getenv("DATABASE_URL", "").strip()
        ssl_ca = os.getenv("MYSQL_SSL_CA", "").strip()
        base = {
            "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
            "port": int(os.getenv("MYSQL_PORT", 3306)),
            "user": os.getenv("MYSQL_USER", "root"),
            "password": os.getenv("MYSQL_PASSWORD", ""),
            "database": os.getenv("MYSQL_DATABASE", "ev_charging_db"),
        }

    ssl_required = os.getenv("MYSQL_SSL_REQUIRED", "").strip().lower() in ("true", "1", "yes")
    if db_url:
        parsed_cfg = parse_database_url(db_url)
        ssl_required = ssl_required or parsed_cfg.pop("ssl_required", False)
        ssl_ca = parsed_cfg.pop("ssl_ca", ssl_ca)
        base.update(parsed_cfg)

    cfg = {
        "host": base["host"],
        "port": int(base["port"]),
        "user": base["user"],
        "password": base["password"],
        "database": base["database"],
        "charset": "utf8mb4",
        "cursorclass": pymysql.cursors.DictCursor,
        "autocommit": False,
        "connect_timeout": int(os.getenv("MYSQL_CONNECT_TIMEOUT", 10)),
        "read_timeout": int(os.getenv("MYSQL_READ_TIMEOUT", 30)),
        "write_timeout": int(os.getenv("MYSQL_WRITE_TIMEOUT", 30)),
    }

    if ssl_ca:
        cfg["ssl"] = {"ca": ssl_ca}
    elif ssl_required:
        cfg["ssl"] = {"ssl_mode": "REQUIRED", "cert_reqs": ssl.CERT_NONE}

    return cfg


def _get_pool():
    """Return or lazily create a thread-safe PooledDB instance for the active DB config."""
    cfg = get_db_config()
    ssl_key = str(cfg.get("ssl", ""))
    pool_key = (cfg["host"], cfg["port"], cfg["user"], cfg["database"], ssl_key)

    pool = _POOLS.get(pool_key)
    if pool is not None:
        return pool

    with _POOL_LOCK:
        pool = _POOLS.get(pool_key)
        if pool is not None:
            return pool

        is_serverless = os.getenv("VERCEL", "").strip() == "1"
        max_conns = int(os.getenv("MYSQL_POOL_MAX_CONNECTIONS", 5 if is_serverless else 15))
        min_cached = int(os.getenv("MYSQL_POOL_MIN_CACHED", 0 if is_serverless else 1))
        max_cached = int(os.getenv("MYSQL_POOL_MAX_CACHED", 2 if is_serverless else 5))

        pool = PooledDB(
            creator=pymysql,
            mincached=min_cached,
            maxcached=max_cached,
            maxconnections=max_conns,
            blocking=True,
            ping=1,  # Validate pooled connection before handing out
            **cfg,
        )
        _POOLS[pool_key] = pool
        return pool


def reset_pools():
    """Close and clear cached connection pools (useful for tests or config reloads)."""
    with _POOL_LOCK:
        for pool in _POOLS.values():
            try:
                pool.close()
            except Exception:
                pass
        _POOLS.clear()


def get_db_connection():
    """Borrow a validated MySQL connection from the pool."""
    return _get_pool().connection()


def query_all(sql, params=None):
    """Execute a parameterized query and return all rows as dicts."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()
    finally:
        conn.close()


def query_one(sql, params=None):
    """Execute a parameterized query and return the first row as dict."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchone()
    finally:
        conn.close()


def execute(sql, params=None):
    """Execute a parameterized INSERT/UPDATE/DELETE query and commit."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            conn.commit()
            return cur.lastrowid
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def call_proc(proc_name, params=None):
    """Call a MySQL stored procedure and commit."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.callproc(proc_name, params or ())
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def transaction():
    """Context manager for multi-statement atomic transactions."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
