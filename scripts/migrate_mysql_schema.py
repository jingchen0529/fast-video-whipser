#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("TMPDIR", str(PROJECT_ROOT / "temp_files"))

from app.core.config import settings
from app.db.mysql import initialize_database


def migrate_mysql_schema(database_url: str | None = None) -> None:
    initialize_database(database_url)


def main() -> None:
    parser = argparse.ArgumentParser(description="迁移 MySQL schema，并将时间列统一为 BIGINT 毫秒时间戳。")
    parser.add_argument(
        "--database-url",
        default=settings.database_url,
        help="目标 MySQL DATABASE_URL，默认读取当前项目配置。",
    )
    args = parser.parse_args()
    migrate_mysql_schema(args.database_url)
    print("[migrate] completed")


if __name__ == "__main__":
    main()
