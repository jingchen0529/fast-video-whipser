#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("TMPDIR", str(PROJECT_ROOT / "temp_files"))

import pymysql
import pymysql.cursors

from app.auth.security import normalize_timestamp_ms
from app.core.config import settings
from app.db.mysql import (
    TIMESTAMP_COLUMN_DEFINITIONS,
    _backfill_project_media_links,
    _parse_database_url,
    create_connection,
)
from scripts.migrate_mysql_schema import migrate_mysql_schema


def create_mysql_connection(database_url: str | None = None) -> pymysql.connections.Connection:
    kwargs, database = _parse_database_url(database_url)
    kwargs["database"] = database
    kwargs["cursorclass"] = pymysql.cursors.DictCursor
    return pymysql.connect(**kwargs)


def load_sqlite_dump(dump_path: Path) -> sqlite3.Connection:
    sql_text = dump_path.read_text(encoding="utf-8")
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(sql_text)
    return connection


def list_sqlite_tables(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name ASC
        """
    ).fetchall()
    return [str(row["name"]) for row in rows]


def get_sqlite_columns(connection: sqlite3.Connection, table_name: str) -> list[str]:
    rows = connection.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    return [str(row["name"]) for row in rows]


def get_mysql_columns(
    connection: pymysql.connections.Connection,
    table_name: str,
) -> list[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION ASC
            """,
            (table_name,),
        )
        return [str(row["COLUMN_NAME"]) for row in cursor.fetchall()]


def truncate_mysql_tables(connection: pymysql.connections.Connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        cursor.execute(
            """
            SELECT TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
            ORDER BY TABLE_NAME ASC
            """
        )
        table_names = [str(row["TABLE_NAME"]) for row in cursor.fetchall()]
        for table_name in table_names:
            cursor.execute(f"TRUNCATE TABLE `{table_name}`")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
    connection.commit()


def transform_value(table_name: str, column_name: str, value: Any) -> Any:
    if column_name in TIMESTAMP_COLUMN_DEFINITIONS.get(table_name, {}):
        return normalize_timestamp_ms(value)
    if isinstance(value, memoryview):
        return bytes(value)
    return value


def import_table(
    sqlite_connection: sqlite3.Connection,
    mysql_connection: pymysql.connections.Connection,
    table_name: str,
    *,
    chunk_size: int,
) -> int:
    sqlite_columns = get_sqlite_columns(sqlite_connection, table_name)
    mysql_columns = get_mysql_columns(mysql_connection, table_name)
    if not mysql_columns:
        raise RuntimeError(f"MySQL 中缺少目标表: {table_name}")

    mysql_column_set = set(mysql_columns)
    common_columns = [column for column in sqlite_columns if column in mysql_column_set]
    if not common_columns:
        print(f"[import] skip {table_name}: no common columns")
        return 0

    quoted_sqlite_columns = ", ".join(f'"{column}"' for column in common_columns)
    insert_columns_sql = ", ".join(f"`{column}`" for column in common_columns)
    placeholders_sql = ", ".join(["%s"] * len(common_columns))
    insert_sql = f"INSERT INTO `{table_name}` ({insert_columns_sql}) VALUES ({placeholders_sql})"

    sqlite_cursor = sqlite_connection.execute(
        f'SELECT {quoted_sqlite_columns} FROM "{table_name}"'
    )
    total_rows = 0

    while True:
        rows = sqlite_cursor.fetchmany(chunk_size)
        if not rows:
            break

        payload: list[tuple[Any, ...]] = []
        for row in rows:
            payload.append(
                tuple(
                    transform_value(table_name, column_name, row[column_name])
                    for column_name in common_columns
                )
            )

        with mysql_connection.cursor() as cursor:
            cursor.executemany(insert_sql, payload)
        mysql_connection.commit()
        total_rows += len(payload)

    print(f"[import] {table_name}: rows={total_rows}")
    return total_rows


def verify_counts(
    sqlite_connection: sqlite3.Connection,
    mysql_connection: pymysql.connections.Connection,
    table_names: list[str],
) -> None:
    for table_name in table_names:
        sqlite_count = int(
            sqlite_connection.execute(f'SELECT COUNT(1) AS count FROM "{table_name}"').fetchone()["count"]
        )
        with mysql_connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(1) AS count FROM `{table_name}`")
            mysql_count = int(cursor.fetchone()["count"])
        print(f"[verify] {table_name}: sqlite={sqlite_count} mysql={mysql_count}")
        if sqlite_count != mysql_count:
            raise RuntimeError(
                f"表 {table_name} 导入后行数不一致: sqlite={sqlite_count}, mysql={mysql_count}"
            )


def import_sqlite_dump(
    dump_file: Path,
    *,
    database_url: str | None = None,
    chunk_size: int = 200,
) -> None:
    migrate_mysql_schema(database_url)

    sqlite_connection = load_sqlite_dump(dump_file)
    mysql_connection = create_mysql_connection(database_url)
    try:
        table_names = list_sqlite_tables(sqlite_connection)
        truncate_mysql_tables(mysql_connection)
        with mysql_connection.cursor() as cursor:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        mysql_connection.commit()

        try:
            for table_name in table_names:
                import_table(
                    sqlite_connection,
                    mysql_connection,
                    table_name,
                    chunk_size=chunk_size,
                )
        finally:
            with mysql_connection.cursor() as cursor:
                cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
            mysql_connection.commit()

        project_connection = create_connection(database_url)
        try:
            _backfill_project_media_links(project_connection)
            project_connection.commit()
        finally:
            project_connection.close()

        verify_counts(sqlite_connection, mysql_connection, table_names)
    finally:
        mysql_connection.close()
        sqlite_connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="将 SQLite dump 安全导入到 MySQL，并把时间列转成 BIGINT 毫秒时间戳。")
    parser.add_argument(
        "--dump-file",
        default="all.sql",
        help="SQLite dump 文件路径，默认使用项目根目录下的 all.sql。",
    )
    parser.add_argument(
        "--database-url",
        default=settings.database_url,
        help="目标 MySQL DATABASE_URL，默认读取当前项目配置。",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=200,
        help="批量写入 MySQL 的分块大小。",
    )
    args = parser.parse_args()

    dump_file = Path(args.dump_file).expanduser().resolve()
    if not dump_file.exists():
        raise FileNotFoundError(f"未找到 dump 文件: {dump_file}")

    import_sqlite_dump(
        dump_file,
        database_url=args.database_url,
        chunk_size=max(1, args.chunk_size),
    )
    print("[import] completed")


if __name__ == "__main__":
    main()
