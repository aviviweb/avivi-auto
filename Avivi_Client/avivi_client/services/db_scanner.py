from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any

# Optional drivers
try:
    import pymysql
except ImportError:
    pymysql = None  # type: ignore

try:
    import psycopg2
except ImportError:
    psycopg2 = None  # type: ignore

try:
    import pyodbc
except ImportError:
    pyodbc = None  # type: ignore

try:
    from pymongo import MongoClient
except ImportError:
    MongoClient = None  # type: ignore

PORTS = [3306, 5432, 1433, 27017]

KEYWORDS = ("customer", "order", "lead", "client", "sale")

MAX_TABLES = 40
MAX_COLS = 24


def probe_local_ports(host: str = "127.0.0.1") -> dict[int, bool]:
    open_ports: dict[int, bool] = {}
    for p in PORTS:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.4)
        try:
            s.connect((host, p))
            open_ports[p] = True
        except OSError:
            open_ports[p] = False
        finally:
            s.close()
    return open_ports


def _match(name: str) -> bool:
    n = name.lower()
    return any(k in n for k in KEYWORDS)


def _columns_mysql(cur, database: str, table: str) -> list[str]:
    cur.execute(
        "SELECT COLUMN_NAME FROM information_schema.columns "
        "WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position LIMIT %s",
        (database, table, MAX_COLS),
    )
    return [r[0] for r in cur.fetchall()]


def summarize_mysql(host: str, user: str, password: str, database: str) -> dict[str, Any]:
    if not pymysql:
        return {"error": "pymysql not installed"}
    conn = pymysql.connect(host=host, user=user, password=password, database=database, connect_timeout=5)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT TABLE_NAME FROM information_schema.tables WHERE table_schema=%s",
                (database,),
            )
            all_tables = [r[0] for r in cur.fetchall()]
            tables = [t for t in all_tables if _match(t)][:MAX_TABLES]
            table_details: list[dict[str, Any]] = []
            for t in tables:
                cols = _columns_mysql(cur, database, t)
                table_details.append({"name": t, "columns": cols})
        return {
            "engine": "mysql",
            "database": database,
            "highlight_tables": [x["name"] for x in table_details],
            "tables": table_details,
        }
    finally:
        conn.close()


def summarize_postgres(host: str, user: str, password: str, database: str) -> dict[str, Any]:
    if not psycopg2:
        return {"error": "psycopg2 not installed"}
    conn = psycopg2.connect(host=host, user=user, password=password, dbname=database, connect_timeout=5)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
            )
            tables = [r[0] for r in cur.fetchall() if _match(r[0])][:MAX_TABLES]
            table_details: list[dict[str, Any]] = []
            for t in tables:
                cur.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position LIMIT %s",
                    (t, MAX_COLS),
                )
                cols = [r[0] for r in cur.fetchall()]
                table_details.append({"name": t, "columns": cols})
        return {
            "engine": "postgres",
            "database": database,
            "highlight_tables": [x["name"] for x in table_details],
            "tables": table_details,
        }
    finally:
        conn.close()


def summarize_mssql(host: str, port: int, user: str, password: str, database: str) -> dict[str, Any]:
    if not pyodbc:
        return {"error": "pyodbc not installed"}
    drivers = [
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "SQL Server",
    ]
    last_err = ""
    for drv in drivers:
        try:
            conn_str = (
                f"DRIVER={{{drv}}};SERVER={host},{port};DATABASE={database};UID={user};PWD={password};"
                "TrustServerCertificate=yes;"
            )
            conn = pyodbc.connect(conn_str, timeout=8)
            break
        except Exception as e:
            last_err = str(e)
            continue
    else:
        return {"error": f"SQL Server: {last_err[:200]}"}
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT TOP {MAX_TABLES} TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE'"
        )
        names = [r[0] for r in cur.fetchall() if _match(r[0])]
        table_details: list[dict[str, Any]] = []
        for t in names[:MAX_TABLES]:
            cur.execute(
                f"SELECT TOP {MAX_COLS} COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_NAME=? ORDER BY ORDINAL_POSITION",
                (t,),
            )
            cols = [r[0] for r in cur.fetchall()]
            table_details.append({"name": t, "columns": cols})
        return {
            "engine": "mssql",
            "database": database,
            "highlight_tables": [x["name"] for x in table_details],
            "tables": table_details,
        }
    finally:
        conn.close()


def summarize_mongodb(host: str, port: int, user: str, password: str, database: str) -> dict[str, Any]:
    if not MongoClient:
        return {"error": "pymongo not installed"}
    client = MongoClient(
        host=host,
        port=port,
        username=user or None,
        password=password or None,
        serverSelectionTimeoutMS=5000,
    )
    try:
        db = client[database]
        names = sorted(db.list_collection_names())[:MAX_TABLES]
        coll_details: list[dict[str, Any]] = []
        for n in names:
            if not _match(n):
                continue
            doc = db[n].find_one({}) or {}
            keys = [k for k in doc.keys() if k != "_id"][:MAX_COLS]
            coll_details.append({"name": n, "sample_fields": keys})
        return {
            "engine": "mongodb",
            "database": database,
            "highlight_tables": [x["name"] for x in coll_details],
            "collections": coll_details,
        }
    finally:
        client.close()


def build_context_bundle(
    port_status: dict[int, bool],
    mysql_cfg: dict[str, str] | None,
    pg_cfg: dict[str, str] | None,
    mssql_cfg: dict[str, str] | None = None,
    mongo_cfg: dict[str, str] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {"open_ports": port_status, "engines": []}
    if mysql_cfg and port_status.get(3306):
        try:
            out["engines"].append(
                summarize_mysql(
                    mysql_cfg.get("host", "127.0.0.1"),
                    mysql_cfg["user"],
                    mysql_cfg["password"],
                    mysql_cfg["database"],
                )
            )
        except Exception as e:
            out["engines"].append({"engine": "mysql", "error": str(e)})
    if pg_cfg and port_status.get(5432):
        try:
            out["engines"].append(
                summarize_postgres(
                    pg_cfg.get("host", "127.0.0.1"),
                    pg_cfg["user"],
                    pg_cfg["password"],
                    pg_cfg["database"],
                )
            )
        except Exception as e:
            out["engines"].append({"engine": "postgres", "error": str(e)})
    if mssql_cfg and port_status.get(1433):
        try:
            port = int(mssql_cfg.get("port", "1433"))
            out["engines"].append(
                summarize_mssql(
                    mssql_cfg.get("host", "127.0.0.1"),
                    port,
                    mssql_cfg["user"],
                    mssql_cfg["password"],
                    mssql_cfg["database"],
                )
            )
        except Exception as e:
            out["engines"].append({"engine": "mssql", "error": str(e)})
    if mongo_cfg and port_status.get(27017):
        try:
            port = int(mongo_cfg.get("port", "27017"))
            out["engines"].append(
                summarize_mongodb(
                    mongo_cfg.get("host", "127.0.0.1"),
                    port,
                    mongo_cfg.get("user", ""),
                    mongo_cfg.get("password", ""),
                    mongo_cfg["database"],
                )
            )
        except Exception as e:
            out["engines"].append({"engine": "mongodb", "error": str(e)})
    return out


def write_semantic_context(base_dir: Path, bundle: dict[str, Any]) -> Path:
    """Persist DB semantic scan for agent / mission context (no credentials)."""
    d = base_dir / "context"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "db_semantic.json"
    p.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    return p
