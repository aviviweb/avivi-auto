from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openclaw_launcher.services.db_profiles_store import DbProfile

MAX_TABLES = 40
MAX_COLS_PER_TABLE = 24
MAX_COL_NAME_LEN = 64
MAX_MONGO_COLLECTIONS = 30


def _trim(s: str, n: int) -> str:
    s = s.strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def introspect_schema(prof: DbProfile) -> tuple[bool, str, str]:
    """
    Read-only metadata introspection. Returns (ok, message, markdown_body).
    markdown_body is empty if not ok.
    """
    try:
        if prof.engine in ("postgresql", "postgres"):
            body = _pg_markdown(prof)
            return True, "PostgreSQL schema snapshot OK", body
        if prof.engine in ("mysql", "mariadb"):
            body = _mysql_markdown(prof)
            return True, "MySQL schema snapshot OK", body
        if prof.engine in ("mssql", "sqlserver"):
            body = _mssql_markdown(prof)
            return True, "SQL Server schema snapshot OK", body
        if prof.engine == "mongodb":
            body = _mongo_markdown(prof)
            return True, "MongoDB collections snapshot OK", body
        return False, f"Unsupported engine for introspection: {prof.engine}", ""
    except Exception as e:
        return False, f"Introspection failed: {e!s}"[:500], ""


def _pg_markdown(prof: DbProfile) -> str:
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
    lines: list[str] = []
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE table_type = 'BASE TABLE'
                  AND table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY table_schema, table_name
                LIMIT %s
                """,
                (MAX_TABLES,),
            )
            tables = list(cur.fetchall())
            for t in tables:
                schema = t["table_schema"]
                name = t["table_name"]
                cur.execute(
                    """
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = %s
                    ORDER BY ordinal_position
                    LIMIT %s
                    """,
                    (schema, name, MAX_COLS_PER_TABLE),
                )
                cols = cur.fetchall()
                col_bits = [
                    f"`{_trim(str(c['column_name']), MAX_COL_NAME_LEN)}`: {c['data_type']}"
                    for c in cols
                ]
                lines.append(f"- **{schema}.{name}**: " + ", ".join(col_bits))
    finally:
        conn.close()
    return "\n".join(lines) if lines else "_No user tables found._"


def _mysql_markdown(prof: DbProfile) -> str:
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
    lines: list[str] = []
    try:
        with conn.cursor(DictCursor) as cur:
            cur.execute(
                """
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE table_type = 'BASE TABLE'
                  AND table_schema NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys')
                ORDER BY table_schema, table_name
                LIMIT %s
                """,
                (MAX_TABLES,),
            )
            tables = list(cur.fetchall())
            for t in tables:
                schema = t["table_schema"]
                name = t["table_name"]
                cur.execute(
                    """
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = %s
                    ORDER BY ordinal_position
                    LIMIT %s
                    """,
                    (schema, name, MAX_COLS_PER_TABLE),
                )
                cols = cur.fetchall()
                col_bits = [
                    f"`{_trim(str(c['column_name']), MAX_COL_NAME_LEN)}`: {c['data_type']}"
                    for c in cols
                ]
                lines.append(f"- **{schema}.{name}**: " + ", ".join(col_bits))
    finally:
        conn.close()
    return "\n".join(lines) if lines else "_No user tables found._"


def _mssql_markdown(prof: DbProfile) -> str:
    try:
        import pyodbc
    except ImportError as e:
        raise RuntimeError("pyodbc required for SQL Server introspection") from e
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
            break
        except Exception as ex:
            last = ex
            continue
    else:
        raise RuntimeError(str(last) if last else "SQL Server connection failed")
    lines: list[str] = []
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT TOP {MAX_TABLES} TABLE_SCHEMA, TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_TYPE = 'BASE TABLE'
            ORDER BY TABLE_SCHEMA, TABLE_NAME
            """
        )
        tables = cur.fetchall()
        for schema, name in tables:
            cur.execute(
                f"""
                SELECT TOP {MAX_COLS_PER_TABLE} COLUMN_NAME, DATA_TYPE
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
                ORDER BY ORDINAL_POSITION
                """,
                (schema, name),
            )
            cols = cur.fetchall()
            col_bits = [f"`{_trim(str(cn), MAX_COL_NAME_LEN)}`: {dt}" for cn, dt in cols]
            lines.append(f"- **{schema}.{name}**: " + ", ".join(col_bits))
    finally:
        conn.close()
    return "\n".join(lines) if lines else "_No user tables found._"


def _mongo_markdown(prof: DbProfile) -> str:
    try:
        from pymongo import MongoClient
    except ImportError as e:
        raise RuntimeError("pymongo not installed") from e
    client = MongoClient(
        host=prof.host,
        port=prof.port,
        username=prof.user or None,
        password=prof.password or None,
        serverSelectionTimeoutMS=8000,
    )
    try:
        db = client[prof.database]
        names = sorted(db.list_collection_names())[:MAX_MONGO_COLLECTIONS]
        lines: list[str] = []
        for n in names:
            coll = db[n]
            doc = coll.find_one({})
            keys = sorted(doc.keys()) if isinstance(doc, dict) else []
            if "_id" in keys:
                keys.remove("_id")
                keys = ["_id"] + keys[:20]
            sample = ", ".join(f"`{k}`" for k in keys[:12]) or "_empty sample_"
            lines.append(f"- **{n}**: fields (sample) {sample}")
        return "\n".join(lines) if lines else "_No collections found._"
    finally:
        client.close()


def write_schema_context_file(workspace_root: Path, profile_id: str, body_md: str) -> Path:
    """Write database_mappings/schema_context_{profile_id}.md"""
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in profile_id)[:80]
    out = workspace_root / "database_mappings" / f"schema_context_{safe}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    text = (
        f"<!-- profile_id={profile_id} generated_utc={now} -->\n"
        f"# Database schema context: `{profile_id}`\n\n"
        "Use this as reference for read-only queries via the launcher DB bridge.\n\n"
        f"{body_md}\n"
    )
    out.write_text(text, encoding="utf-8")
    return out


def write_schema_context_json(workspace_root: Path, profile_id: str, payload: dict[str, Any]) -> Path:
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in profile_id)[:80]
    out = workspace_root / "database_mappings" / f"schema_context_{safe}.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return out
