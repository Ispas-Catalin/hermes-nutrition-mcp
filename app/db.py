from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.config import Settings


SCHEMA_VERSION = "3"


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def transaction(settings: Settings) -> Iterator[sqlite3.Connection]:
    conn = connect(settings.db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def local_now(timezone: str) -> datetime:
    return datetime.now(ZoneInfo(timezone))


def now_iso(timezone: str) -> str:
    return local_now(timezone).isoformat(timespec="seconds")


def initialize_database(settings: Settings) -> None:
    settings.ensure_dirs()
    with transaction(settings) as conn:
        _create_schema(conn)
        _ensure_column(conn, "aliases", "recipe_id", "INTEGER REFERENCES recipes(id)")
        _ensure_column(conn, "foods", "sugars_g", "REAL DEFAULT 0")
        _ensure_column(conn, "foods", "saturated_fat_g", "REAL DEFAULT 0")
        _ensure_column(conn, "foods", "salt_g", "REAL DEFAULT 0")
        _ensure_column(conn, "meal_entries", "recipe_id", "INTEGER REFERENCES recipes(id)")
        _ensure_column(conn, "meal_entries", "sugars_snapshot", "REAL NOT NULL DEFAULT 0")
        _ensure_column(conn, "meal_entries", "saturated_fat_snapshot", "REAL NOT NULL DEFAULT 0")
        _ensure_column(conn, "meal_entries", "salt_snapshot", "REAL NOT NULL DEFAULT 0")
        _ensure_column(conn, "meal_entries", "recipe_components_snapshot", "TEXT")
        conn.execute(
            """
            INSERT INTO schema_meta(key, value)
            VALUES('schema_version', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (SCHEMA_VERSION,),
        )


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS foods (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            brand TEXT,
            serving_name TEXT NOT NULL,
            grams_per_serving REAL,
            kcal REAL NOT NULL,
            protein_g REAL NOT NULL,
            carbs_g REAL NOT NULL,
            fat_g REAL NOT NULL,
            fiber_g REAL DEFAULT 0,
            sugars_g REAL DEFAULT 0,
            saturated_fat_g REAL DEFAULT 0,
            salt_g REAL DEFAULT 0,
            source TEXT DEFAULT 'manual',
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS recipes (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            serving_name TEXT NOT NULL DEFAULT '1 serving',
            default_quantity REAL DEFAULT 1,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS recipe_items (
            id INTEGER PRIMARY KEY,
            recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
            food_id INTEGER NOT NULL REFERENCES foods(id),
            quantity REAL NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS aliases (
            id INTEGER PRIMARY KEY,
            alias TEXT NOT NULL UNIQUE,
            normalized_alias TEXT NOT NULL UNIQUE,
            food_id INTEGER REFERENCES foods(id),
            recipe_id INTEGER REFERENCES recipes(id),
            default_quantity REAL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CHECK (
                (food_id IS NOT NULL AND recipe_id IS NULL)
                OR (food_id IS NULL AND recipe_id IS NOT NULL)
            )
        );

        CREATE TABLE IF NOT EXISTS meal_entries (
            id INTEGER PRIMARY KEY,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            food_id INTEGER REFERENCES foods(id),
            recipe_id INTEGER REFERENCES recipes(id),
            alias_used TEXT,
            food_name_snapshot TEXT NOT NULL,
            brand_snapshot TEXT,
            serving_name_snapshot TEXT,
            quantity REAL NOT NULL,
            kcal_snapshot REAL NOT NULL,
            protein_snapshot REAL NOT NULL,
            carbs_snapshot REAL NOT NULL,
            fat_snapshot REAL NOT NULL,
            fiber_snapshot REAL NOT NULL DEFAULT 0,
            sugars_snapshot REAL NOT NULL DEFAULT 0,
            saturated_fat_snapshot REAL NOT NULL DEFAULT 0,
            salt_snapshot REAL NOT NULL DEFAULT 0,
            recipe_components_snapshot TEXT,
            note TEXT,
            raw_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS daily_exports (
            date TEXT PRIMARY KEY,
            markdown_path TEXT,
            csv_path TEXT,
            json_path TEXT,
            finalized_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_aliases_normalized_alias
            ON aliases(normalized_alias);
        CREATE INDEX IF NOT EXISTS idx_meal_entries_date
            ON meal_entries(date);
        CREATE INDEX IF NOT EXISTS idx_meal_entries_food_id
            ON meal_entries(food_id);
        CREATE INDEX IF NOT EXISTS idx_meal_entries_recipe_id
            ON meal_entries(recipe_id);
        CREATE INDEX IF NOT EXISTS idx_recipe_items_recipe_id
            ON recipe_items(recipe_id);
        """
    )


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
