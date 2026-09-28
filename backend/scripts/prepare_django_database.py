"""One-time development cutover: snapshot the old database, create an EMPTY new one.

Never drops or changes the source database. The source snapshot stays in backups/.
"""
import argparse
import base64
from datetime import date, datetime, time, timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlparse

import MySQLdb
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]

def encode(value):
    if isinstance(value, (date, datetime, time, Decimal)):
        return str(value)
    if isinstance(value, bytes):
        return {"__bytes__": base64.b64encode(value).decode()}
    if isinstance(value, timedelta):
        return str(value)
    raise TypeError(type(value).__name__)

def connect_source():
    env = dotenv_values(ROOT / "backend" / ".env")
    url = urlparse(env["DATABASE_URL"])
    source_name = url.path.lstrip("/")
    connection = MySQLdb.connect(host=url.hostname or "127.0.0.1", port=url.port or 3306,
        user=unquote(url.username or ""), passwd=unquote(url.password or ""),
        db=source_name, charset="utf8mb4")
    return connection, source_name, env.get("DATABASE_NAME", "reading_map_django")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    connection, source_name, destination_name = connect_source()
    if destination_name != "reading_map_django" or destination_name == source_name:
        raise SystemExit("This one-time cutover only creates the separate reading_map_django database.")
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT")
            cursor.execute("SHOW TABLES")
            tables = [row[0] for row in cursor.fetchall()]
            snapshot = {"source_database": source_name, "created_at": datetime.now().isoformat(), "tables": {}}
            for table in tables:
                if not re.fullmatch(r"[a-zA-Z0-9_]+", table):
                    raise ValueError("Unsupported table name")
                cursor.execute(f"SHOW CREATE TABLE `{table}`")
                ddl = cursor.fetchone()[1]
                cursor.execute(f"SELECT * FROM `{table}`")
                columns = [col[0] for col in cursor.description]
                snapshot["tables"][table] = {"ddl": ddl, "columns": columns, "rows": [dict(zip(columns, row)) for row in cursor.fetchall()]}
            counts = {key: len(value["rows"]) for key, value in snapshot["tables"].items()}
            print(json.dumps({"source_database": source_name, "destination": destination_name, "counts": counts}, indent=2))
            connection.commit()
            if args.apply:
                target = ROOT / "backups" / "pre_django_database_20260916.json"
                if target.exists():
                    raise SystemExit("Snapshot already exists; refusing to overwrite it.")
                raw = json.dumps(snapshot, ensure_ascii=False, indent=2, default=encode).encode("utf-8")
                target.write_bytes(raw)
                target.with_suffix(".sha256").write_text(hashlib.sha256(raw).hexdigest(), encoding="ascii")
                print(f"Verified snapshot: {target} ({len(raw)} bytes)")
                # CREATE without IF NOT EXISTS deliberately refuses an already used destination.
                cursor.execute("CREATE DATABASE `reading_map_django` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                print("Created empty reading_map_django. Original database was not changed.")
    finally:
        connection.close()

if __name__ == "__main__":
    main()
