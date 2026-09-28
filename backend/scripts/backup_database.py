from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings
from app.db.session import engine


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _table_counts() -> dict[str, int]:
    inspector = inspect(engine)
    tables = sorted(inspector.get_table_names())
    with engine.connect() as connection:
        return {
            table: int(connection.execute(text(f"SELECT COUNT(*) FROM `{table}`")).scalar_one())
            for table in tables
        }


def backup_mysql(output_dir: Path) -> tuple[Path, Path]:
    url = make_url(settings.database_url)
    if url.get_backend_name() != "mysql":
        raise RuntimeError(f"Only MySQL is supported by this backup script, got {url.get_backend_name()!r}")

    executable = shutil.which("mysqldump")
    if not executable:
        raise RuntimeError("mysqldump was not found on PATH")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    database_name = url.database or "database"
    output_dir.mkdir(parents=True, exist_ok=True)
    dump_path = (output_dir / f"{database_name}_{timestamp}.sql").resolve()
    manifest_path = dump_path.with_suffix(".manifest.json")

    environment = os.environ.copy()
    if url.password:
        environment["MYSQL_PWD"] = url.password

    command = [
        executable,
        "--single-transaction",
        "--routines",
        "--triggers",
        "--events",
        "--hex-blob",
        "--set-gtid-purged=OFF",
        "--default-character-set=utf8mb4",
        f"--host={url.host or '127.0.0.1'}",
        f"--port={url.port or 3306}",
        f"--user={url.username or 'root'}",
        f"--result-file={dump_path}",
        database_name,
    ]
    subprocess.run(command, env=environment, check=True)

    if not dump_path.is_file() or dump_path.stat().st_size == 0:
        raise RuntimeError("mysqldump completed without producing a non-empty backup")
    tail = dump_path.read_bytes()[-4096:].decode("utf-8", errors="replace")
    if "Dump completed on" not in tail:
        raise RuntimeError("backup is missing the mysqldump completion marker")

    counts = _table_counts()
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "database": database_name,
        "dialect": url.get_backend_name(),
        "dump_file": dump_path.name,
        "size_bytes": dump_path.stat().st_size,
        "sha256": _sha256(dump_path),
        "table_count": len(counts),
        "table_row_counts": counts,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dump_path, manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Create and verify a logical MySQL backup for Reading Map")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "backups",
        help="Directory for the SQL dump and verification manifest",
    )
    args = parser.parse_args()
    dump_path, manifest_path = backup_mysql(args.output_dir)
    print(dump_path)
    print(manifest_path)


if __name__ == "__main__":
    main()
