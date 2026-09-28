from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings


PROTECTED_DATABASES = {"mysql", "information_schema", "performance_schema", "sys"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Drop and rebuild the local development database with Catalog v1.")
    parser.add_argument("--yes", action="store_true", help="Confirm the destructive reset")
    args = parser.parse_args()
    if not args.yes:
        raise SystemExit("Refusing to reset without --yes")

    database_url = make_url(settings.database_url)
    database_name = database_url.database or ""
    if database_url.get_backend_name() != "mysql":
        raise SystemExit("This reset helper only supports the configured MySQL development database")
    if database_name in PROTECTED_DATABASES or not re.fullmatch(r"[A-Za-z0-9_]+", database_name):
        raise SystemExit(f"Refusing unsafe database name: {database_name!r}")

    server_engine = create_engine(database_url.set(database=None), isolation_level="AUTOCOMMIT")
    with server_engine.connect() as connection:
        connection.execute(text(f"DROP DATABASE IF EXISTS `{database_name}`"))
        connection.execute(text(f"CREATE DATABASE `{database_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
    server_engine.dispose()

    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    alembic_config.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(alembic_config, "head")
    print(f"Rebuilt {database_name} at revision 20260907_0001")


if __name__ == "__main__":
    main()
