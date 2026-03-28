from __future__ import annotations

import httpx

from openclaw_launcher.services.db_profiles_store import DbProfile


def test_bridge_select_one(host: str, port: int, profile_id: str) -> tuple[bool, str]:
    """Verify the local launcher DB bridge with SELECT 1 (profile must exist in store)."""
    try:
        r = httpx.post(
            f"http://{host}:{port}/query",
            json={"profile_id": profile_id, "sql": "SELECT 1 AS ok"},
            timeout=20.0,
        )
        data = r.json()
        if r.status_code == 200 and data.get("ok"):
            return True, f"Bridge OK: {data.get('rows', [])}"
        return False, data.get("error", r.text)[:300]
    except Exception as e:
        return False, str(e)[:300]


def test_database_connection(prof: DbProfile) -> tuple[bool, str]:
    try:
        if prof.engine in ("postgresql", "postgres"):
            import psycopg2

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
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 AS ok")
                    row = cur.fetchone()
                    if row and row[0] == 1:
                        return True, "PostgreSQL: SELECT 1 OK"
                    return False, "PostgreSQL: unexpected result"
            finally:
                conn.close()

        if prof.engine in ("mysql", "mariadb"):
            import pymysql

            conn = pymysql.connect(
                host=prof.host,
                port=prof.port,
                user=prof.user,
                password=prof.password,
                database=prof.database,
                connect_timeout=10,
            )
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 AS ok")
                    row = cur.fetchone()
                    if row and int(row[0]) == 1:
                        return True, "MySQL: SELECT 1 OK"
                    return False, "MySQL: unexpected result"
            finally:
                conn.close()

        if prof.engine in ("mssql", "sqlserver"):
            try:
                import pyodbc
            except ImportError:
                return (
                    False,
                    "SQL Server: install pyodbc and Microsoft ODBC Driver for SQL Server",
                )
            drivers = [
                "ODBC Driver 18 for SQL Server",
                "ODBC Driver 17 for SQL Server",
                "SQL Server",
            ]
            last_err = ""
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
                        cur.execute("SELECT 1 AS ok")
                        row = cur.fetchone()
                        if row and row[0] == 1:
                            return True, "SQL Server: SELECT 1 OK"
                    finally:
                        conn.close()
                except Exception as e:
                    last_err = str(e)
                    continue
            return False, f"SQL Server: {last_err[:200]}"

        if prof.engine == "mongodb":
            try:
                from pymongo import MongoClient
            except ImportError:
                return False, "MongoDB: install pymongo"
            client = MongoClient(
                host=prof.host,
                port=prof.port,
                username=prof.user or None,
                password=prof.password or None,
                serverSelectionTimeoutMS=8000,
            )
            try:
                client.admin.command("ping")
                return True, "MongoDB: ping OK"
            finally:
                client.close()

        return False, f"Unsupported engine: {prof.engine}"
    except Exception as e:
        return False, f"Error: {e!s}"[:500]
