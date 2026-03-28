from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from openclaw_launcher.services.db_profiles_store import DbProfile, DbProfilesStore

_SELECT_ONLY = re.compile(r"^\s*select\b", re.IGNORECASE | re.DOTALL)
# Block obvious side-effect / exfil patterns even when profile is not read-only.
_DANGEROUS_SQL = (
    " into ",
    " outfile ",
    " infile ",
    " dumpfile ",
    " copy ",
    " merge ",
    " replace ",
    " grant ",
    " revoke ",
)


def _validate_sql(sql: str) -> bool:
    s = sql.strip().rstrip(";")
    if not _SELECT_ONLY.match(s):
        return False
    if ";" in s:
        return False
    forbidden = (" insert ", " update ", " delete ", " drop ", " alter ", " truncate ", " exec ", " call ")
    low = f" {s.lower()} "
    if any(f in low for f in forbidden):
        return False
    if any(f in low for f in _DANGEROUS_SQL):
        return False
    return True


def _mongo_body_allowed(body: dict[str, Any], *, read_only: bool) -> tuple[bool, str]:
    """Read-only profiles: only benign find parameters; block obvious write hints."""
    if not read_only:
        return True, ""
    bad_keys = {"update", "delete", "replace", "insert", "pipeline", "aggregate", "bulkWrite"}
    for k in body:
        if k.lower() in bad_keys:
            return False, f"read_only_profile: field {k!r} not allowed"
    return True, ""


class DbBridgeHandler(BaseHTTPRequestHandler):
    store: DbProfilesStore
    workspace_root: Path

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def _send_json(self, code: int, body: dict) -> None:
        data = json.dumps(body, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json(200, {"ok": True})
            return
        self._send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/query":
            self._send_json(404, {"error": "not_found"})
            return
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self._send_json(400, {"error": "invalid_json"})
            return
        profile_id = body.get("profile_id", "")
        sql = body.get("sql", "")
        if not profile_id:
            self._send_json(400, {"error": "profile_id required"})
            return
        prof = type(self).store.get_full_profile(profile_id)
        if not prof:
            self._send_json(404, {"error": "unknown_profile"})
            return
        try:
            if prof.engine == "mongodb":
                ok_m, why = _mongo_body_allowed(body, read_only=prof.read_only)
                if not ok_m:
                    self._send_json(403, {"error": why})
                    return
                rows = _execute_mongo(prof, body)
            else:
                if not sql:
                    self._send_json(400, {"error": "sql required"})
                    return
                if not _validate_sql(sql):
                    self._send_json(400, {"error": "only_single_select_allowed"})
                    return
                rows = _execute_sql(prof, sql)
            self._send_json(200, {"ok": True, "rows": rows})
        except Exception as e:
            self._send_json(500, {"ok": False, "error": str(e)[:500]})


def _execute_sql(prof: DbProfile, sql: str) -> list[dict[str, Any]]:
    if prof.engine in ("postgresql", "postgres"):
        import psycopg2
        from psycopg2.extras import RealDictCursor

        conn = psycopg2.connect(
            host=prof.host,
            port=prof.port,
            user=prof.user,
            password=prof.password,
            dbname=prof.database,
            connect_timeout=10,
            sslmode="require" if prof.ssl else "prefer",
        )
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql)
                return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()
    if prof.engine in ("mysql", "mariadb"):
        import pymysql
        from pymysql.cursors import DictCursor

        conn = pymysql.connect(
            host=prof.host,
            port=prof.port,
            user=prof.user,
            password=prof.password,
            database=prof.database,
            connect_timeout=10,
        )
        try:
            with conn.cursor(DictCursor) as cur:
                cur.execute(sql)
                return list(cur.fetchall())
        finally:
            conn.close()
    if prof.engine in ("mssql", "sqlserver"):
        try:
            import pyodbc
        except ImportError as e:
            raise RuntimeError("pyodbc required for SQL Server") from e
        drivers = [
            "ODBC Driver 18 for SQL Server",
            "ODBC Driver 17 for SQL Server",
            "SQL Server",
        ]
        last: Exception | None = None
        for drv in drivers:
            try:
                conn_str = (
                    f"DRIVER={{{drv}}};SERVER={prof.host},{prof.port};"
                    f"DATABASE={prof.database};UID={prof.user};PWD={prof.password};"
                    "TrustServerCertificate=yes;"
                )
                conn = pyodbc.connect(conn_str, timeout=10)
                try:
                    cur = conn.cursor()
                    cur.execute(sql)
                    cols = [c[0] for c in cur.description] if cur.description else []
                    rows_out = []
                    for row in cur.fetchall():
                        rows_out.append(dict(zip(cols, row)))
                    return rows_out
                finally:
                    conn.close()
            except Exception as ex:
                last = ex
                continue
        raise RuntimeError(str(last) if last else "SQL Server connection failed")
    raise RuntimeError(f"Unsupported SQL engine: {prof.engine}")


def _execute_mongo(prof: DbProfile, body: dict) -> list[dict[str, Any]]:
    try:
        from pymongo import MongoClient
    except ImportError as e:
        raise RuntimeError("pymongo not installed") from e
    coll_name = str(body.get("collection", "leads"))
    limit = min(max(int(body.get("limit", 50)), 1), 200)
    client = MongoClient(
        host=prof.host,
        port=prof.port,
        username=prof.user or None,
        password=prof.password or None,
        serverSelectionTimeoutMS=8000,
    )
    try:
        db = client[prof.database]
        coll = db[coll_name]
        out = list(coll.find({}, limit=limit))
        for d in out:
            if "_id" in d:
                d["_id"] = str(d["_id"])
        return out
    finally:
        client.close()


def make_handler_class(store: DbProfilesStore, workspace_root: Path) -> type[DbBridgeHandler]:
    class H(DbBridgeHandler):
        pass

    H.store = store
    H.workspace_root = workspace_root
    return H


class DbBridgeServer:
    def __init__(self, host: str, port: int, store: DbProfilesStore, workspace_root: Path) -> None:
        self.host = host
        self.port = port
        self._store = store
        self._root = workspace_root
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> tuple[bool, str]:
        if self._httpd:
            return True, "already running"
        handler = make_handler_class(self._store, self._root)
        try:
            self._httpd = ThreadingHTTPServer((self.host, self.port), handler)
        except OSError as e:
            return False, str(e)

        def run() -> None:
            assert self._httpd
            self._httpd.serve_forever()

        self._thread = threading.Thread(target=run, name="db-bridge", daemon=True)
        self._thread.start()
        return True, f"listening on {self.host}:{self.port}"

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        self._thread = None
