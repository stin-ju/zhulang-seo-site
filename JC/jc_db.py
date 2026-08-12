import os, json, urllib.request, urllib.error
SERVER_PORT = os.environ.get('DEPLOY_RUN_PORT', '5000')
SERVER_URL = f'http://127.0.0.1:{SERVER_PORT}/api/internal/query'

class Cursor:
    def __init__(self, conn):
        self.conn = conn
        self.description = None
        self._rows = []
        self._rowcount = 0
        self._index = 0
    @property
    def rowcount(self): return self._rowcount
    def execute(self, sql, params=None):
        converted_sql = sql
        converted_params = []
        if params:
            param_idx = 0
            parts = []
            i = 0
            while i < len(sql):
                if sql[i] == '%':
                    if i+1 < len(sql) and sql[i+1] == 's':
                        param_idx += 1
                        parts.append(f'${param_idx}')
                        converted_params.append(params[param_idx-1])
                        i += 2
                        continue
                    elif i+1 < len(sql) and sql[i+1] == '%':
                        parts.append('%')
                        i += 2
                        continue
                parts.append(sql[i])
                i += 1
            converted_sql = ''.join(parts)
        payload = json.dumps({'sql': converted_sql, 'params': converted_params}).encode('utf-8')
        req = urllib.request.Request(SERVER_URL, data=payload, headers={'Content-Type': 'application/json'}, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            raise Exception(f'DB proxy error ({e.code}): {e.read().decode()}')
        except urllib.error.URLError as e:
            raise Exception(f'DB proxy connection error: {e.reason}')
        self._rows = result.get('rows', [])
        self._rowcount = result.get('rowCount', len(self._rows))
        self._index = 0
        fields = result.get('fields', [])
        if fields and self._rows:
            self.description = [(f, None, None, None, None, None, None) for f in fields]
    def fetchall(self):
        result = []
        for row in self._rows:
            result.append(tuple(row.values()) if isinstance(row, dict) else row)
        self._rows = []
        return result
    def fetchone(self):
        if self._index < len(self._rows):
            row = self._rows[self._index]
            self._index += 1
            return tuple(row.values()) if isinstance(row, dict) else row
        return None
    def fetchmany(self, size=None):
        if size is None: size = len(self._rows) - self._index
        result = []
        for _ in range(min(size, len(self._rows) - self._index)):
            row = self._rows[self._index]
            self._index += 1
            result.append(tuple(row.values()) if isinstance(row, dict) else row)
        return result
    def close(self): pass
    def __iter__(self): return iter(self.fetchall())
    def __enter__(self): return self
    def __exit__(self, *a): self.close()

class Connection:
    def __init__(self, url=None):
        self.url = url
        self._closed = False
    def cursor(self): return Cursor(self)
    def commit(self): pass
    def rollback(self): pass
    def close(self): self._closed = True
    def __enter__(self): return self
    def __exit__(self, *a): self.close()

def connect(url=None):
    if url is None: url = os.environ.get('DATABASE_URL', '')
    return Connection(url)
