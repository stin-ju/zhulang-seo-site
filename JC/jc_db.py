#!/usr/bin/env python3
"""
jc_db.py - 数据库访问层（直连 PostgreSQL via psycopg2）

替代原先通过 HTTP 代理 Node.js /api/internal/query 的方式，
直接使用 psycopg2 连接数据库，消除 HTTP 代理单点故障。

保持与原接口完全兼容：connect() / cursor() / execute(sql, params) / fetchall / fetchone
"""
import os
import json
import psycopg2
# import psycopg2.extras  # 不需要，避免与本地 psycopg2.py 冲突

DEFAULT_DB_URL = "postgresql://postgres:1538PQKpnIj0buIb6Y@cp-alive-flake-931e9663.pg2.aidap-global.cn-beijing.volces.com:5432/postgres"


class Cursor:
    """psycopg2 cursor 的薄封装，保持与旧 jc_db.Cursor 接口一致"""

    def __init__(self, pg_cursor):
        self._cur = pg_cursor

    @property
    def description(self):
        return self._cur.description

    @property
    def rowcount(self):
        return self._cur.rowcount

    def execute(self, sql, params=None):
        self._cur.execute(sql, params)

    def fetchall(self):
        return self._cur.fetchall()

    def fetchone(self):
        return self._cur.fetchone()

    def fetchmany(self, size=None):
        if size is None:
            return self._cur.fetchall()
        return self._cur.fetchmany(size)

    def close(self):
        self._cur.close()

    def __iter__(self):
        return iter(self._cur)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class Connection:
    """psycopg2 connection 的薄封装"""

    def __init__(self, pg_conn):
        self._conn = pg_conn

    def cursor(self):
        return Cursor(self._conn.cursor())

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def set_client_encoding(self, encoding):
        self._conn.set_client_encoding(encoding)

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def connect(url=None):
    """连接数据库，返回 Connection 对象"""
    db_url = url or os.environ.get('DATABASE_URL', '') or DEFAULT_DB_URL
    pg_conn = psycopg2.connect(db_url)
    return Connection(pg_conn)
