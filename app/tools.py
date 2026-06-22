from __future__ import annotations

import json
import sqlite3
from datetime import UTC, date as Date, datetime, timedelta
from typing import Any

from app.config import Settings
from app.db import SCHEMA_VERSION, initialize_database, local_now, now_iso, transaction
from app.exports import utc_timestamp, write_daily_exports
from app.tables import ascii_table, build_totals, daily_totals_table, foods_table, normalize_alias


MACRO_FIELDS = ("kcal", "protein_g", "carbs_g", "fat_g", "fiber_g")


class NutritionService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        initialize_database(settings)

    def add_food(
        self,
        name: str,
        kcal: float,
        protein_g: float,
        carbs_g: float,
        fat_g: float,
        serving_name: str = "1 serving",
        brand: str | None = None,
        grams_per_serving: float | None = None,
        fiber_g: float = 0,
        source: str = "manual",
        notes: str | None = None,
        aliases: list[str] | None = None,
        default_quantity: float = 1,
    ) -> dict[str, Any]:
        aliases = aliases or []
        _require_text(name, "name")
        _require_text(serving_name, "serving_name")
        _validate_positive(default_quantity, "default_quantity")
        if grams_per_serving is not None:
            _validate_positive(grams_per_serving, "grams_per_serving")
        _validate_macros(kcal, protein_g, carbs_g, fat_g, fiber_g)
        created_at = now_iso(self.settings.timezone)
        with transaction(self.settings) as conn:
            cursor = conn.execute(
                """
                INSERT INTO foods(
                    name, brand, serving_name, grams_per_serving, kcal,
                    protein_g, carbs_g, fat_g, fiber_g, source, notes,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    brand,
                    serving_name,
                    grams_per_serving,
                    kcal,
                    protein_g,
                    carbs_g,
                    fat_g,
                    fiber_g,
                    source,
                    notes,
                    created_at,
                    created_at,
                ),
            )
            food_id = int(cursor.lastrowid)
            created_aliases = [
                _create_alias(conn, alias, default_quantity=default_quantity, food_id=food_id)
                for alias in aliases
            ]
            food = _get_food(conn, food_id)
            return {"food": food, "aliases": created_aliases}

    def update_food(
        self,
        food_id: int,
        name: str | None = None,
        kcal: float | None = None,
        protein_g: float | None = None,
        carbs_g: float | None = None,
        fat_g: float | None = None,
        serving_name: str | None = None,
        brand: str | None = None,
        grams_per_serving: float | None = None,
        fiber_g: float | None = None,
        source: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        for field, value in {
            "name": name,
            "serving_name": serving_name,
            "brand": brand,
            "grams_per_serving": grams_per_serving,
            "kcal": kcal,
            "protein_g": protein_g,
            "carbs_g": carbs_g,
            "fat_g": fat_g,
            "fiber_g": fiber_g,
            "source": source,
            "notes": notes,
        }.items():
            if value is not None:
                updates[field] = value
        if not updates:
            raise ValueError("At least one field must be provided.")
        if grams_per_serving is not None:
            _validate_positive(grams_per_serving, "grams_per_serving")
        for field in MACRO_FIELDS:
            if field in updates and float(updates[field]) < 0:
                raise ValueError(f"{field} must be greater than or equal to 0.")

        with transaction(self.settings) as conn:
            _get_food(conn, food_id)
            updates["updated_at"] = now_iso(self.settings.timezone)
            assignments = ", ".join(f"{field} = ?" for field in updates)
            conn.execute(
                f"UPDATE foods SET {assignments} WHERE id = ?",
                [*updates.values(), food_id],
            )
            return {
                "food": _get_food(conn, food_id),
                "message": "Food updated. Historical meal entries keep their stored snapshots.",
            }

    def add_alias(
        self,
        alias: str,
        food_id: int | None = None,
        default_quantity: float = 1,
        recipe_id: int | None = None,
    ) -> dict[str, Any]:
        with transaction(self.settings) as conn:
            return _create_alias(
                conn,
                alias,
                default_quantity=default_quantity,
                food_id=food_id,
                recipe_id=recipe_id,
            )

    def search_foods(self, query: str, limit: int = 10) -> dict[str, Any]:
        _require_text(query, "query")
        limit = _clean_limit(limit, 1, 50)
        needle = f"%{query.strip().lower()}%"
        with transaction(self.settings) as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT f.*
                FROM foods f
                LEFT JOIN aliases a ON a.food_id = f.id
                WHERE lower(f.name) LIKE ?
                   OR lower(coalesce(f.brand, '')) LIKE ?
                   OR a.normalized_alias LIKE ?
                ORDER BY f.name
                LIMIT ?
                """,
                (needle, needle, needle, limit),
            ).fetchall()
            return {"foods": [_food_with_aliases(conn, row["id"]) for row in rows]}

    def get_food(self, food_id: int | None = None, alias: str | None = None) -> dict[str, Any]:
        with transaction(self.settings) as conn:
            food, alias_row = _resolve_food(conn, food_id=food_id, alias=alias)
            result = _food_with_aliases(conn, food["id"])
            return {
                "food": result,
                "matched_alias": dict(alias_row) if alias_row is not None else None,
            }

    def list_foods(self, query: str | None = None, limit: int = 50) -> dict[str, Any]:
        limit = _clean_limit(limit, 1, 200)
        params: list[Any] = []
        where = ""
        if query:
            where = """
            WHERE lower(f.name) LIKE ?
               OR lower(coalesce(f.brand, '')) LIKE ?
               OR a.normalized_alias LIKE ?
            """
            needle = f"%{query.strip().lower()}%"
            params.extend([needle, needle, needle])
        params.append(limit)
        with transaction(self.settings) as conn:
            rows = conn.execute(
                f"""
                SELECT DISTINCT f.*
                FROM foods f
                LEFT JOIN aliases a ON a.food_id = f.id
                {where}
                ORDER BY lower(f.name), f.id
                LIMIT ?
                """,
                params,
            ).fetchall()
            foods = [_food_with_aliases(conn, row["id"]) for row in rows]
            return {"foods": foods, "table": foods_table(foods)}

    def add_recipe(
        self,
        name: str,
        ingredients: list[dict[str, Any]],
        aliases: list[str] | None = None,
        serving_name: str = "1 serving",
        default_quantity: float = 1,
        notes: str | None = None,
    ) -> dict[str, Any]:
        aliases = aliases or []
        _require_text(name, "name")
        _require_text(serving_name, "serving_name")
        _validate_positive(default_quantity, "default_quantity")
        if not ingredients:
            raise ValueError("ingredients must contain at least one item.")

        created_at = now_iso(self.settings.timezone)
        with transaction(self.settings) as conn:
            cursor = conn.execute(
                """
                INSERT INTO recipes(name, serving_name, default_quantity, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (name, serving_name, default_quantity, notes, created_at, created_at),
            )
            recipe_id = int(cursor.lastrowid)
            _replace_recipe_items(conn, recipe_id, ingredients, self.settings.timezone)
            created_aliases = [
                _create_alias(conn, alias, default_quantity=default_quantity, recipe_id=recipe_id)
                for alias in aliases
            ]
            return {
                "recipe": _recipe_with_items(conn, recipe_id),
                "aliases": created_aliases,
                "message": "Recipe created from food ingredients. Logs will snapshot adjusted components.",
            }

    def update_recipe(
        self,
        recipe_id: int,
        name: str | None = None,
        ingredients: list[dict[str, Any]] | None = None,
        serving_name: str | None = None,
        default_quantity: float | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        for field, value in {
            "name": name,
            "serving_name": serving_name,
            "default_quantity": default_quantity,
            "notes": notes,
        }.items():
            if value is not None:
                updates[field] = value
        if default_quantity is not None:
            _validate_positive(default_quantity, "default_quantity")
        if not updates and ingredients is None:
            raise ValueError("At least one field or ingredients must be provided.")

        with transaction(self.settings) as conn:
            _get_recipe(conn, recipe_id)
            if updates:
                updates["updated_at"] = now_iso(self.settings.timezone)
                assignments = ", ".join(f"{field} = ?" for field in updates)
                conn.execute(
                    f"UPDATE recipes SET {assignments} WHERE id = ?",
                    [*updates.values(), recipe_id],
                )
            if ingredients is not None:
                if not ingredients:
                    raise ValueError("ingredients must contain at least one item.")
                _replace_recipe_items(conn, recipe_id, ingredients, self.settings.timezone)
            return {
                "recipe": _recipe_with_items(conn, recipe_id),
                "message": "Recipe updated. Historical meal entries keep their stored snapshots.",
            }

    def get_recipe(self, recipe_id: int | None = None, alias: str | None = None) -> dict[str, Any]:
        with transaction(self.settings) as conn:
            recipe, _alias_row = _resolve_recipe(conn, recipe_id=recipe_id, alias=alias)
            return {"recipe": _recipe_with_items(conn, recipe["id"])}

    def search_recipes(self, query: str, limit: int = 10) -> dict[str, Any]:
        _require_text(query, "query")
        limit = _clean_limit(limit, 1, 50)
        needle = f"%{query.strip().lower()}%"
        with transaction(self.settings) as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT r.*
                FROM recipes r
                LEFT JOIN aliases a ON a.recipe_id = r.id
                WHERE lower(r.name) LIKE ?
                   OR a.normalized_alias LIKE ?
                ORDER BY r.name
                LIMIT ?
                """,
                (needle, needle, limit),
            ).fetchall()
            return {"recipes": [_recipe_with_items(conn, row["id"]) for row in rows]}

    def log_food(
        self,
        alias: str | None = None,
        food_id: int | None = None,
        quantity: float | None = None,
        grams: float | None = None,
        date: str | None = None,
        time: str | None = None,
        note: str | None = None,
        raw_message: str | None = None,
    ) -> dict[str, Any]:
        date_value, time_value = self._date_time(date, time)
        created_at = now_iso(self.settings.timezone)
        with transaction(self.settings) as conn:
            food, alias_row = _resolve_food(conn, food_id=food_id, alias=alias)
            quantity_value = _quantity_from_inputs(
                food,
                quantity=quantity,
                grams=grams,
                default_quantity=alias_row["default_quantity"] if alias_row else None,
            )
            macros = _food_macros(food, quantity_value)
            cursor = conn.execute(
                """
                INSERT INTO meal_entries(
                    date, time, food_id, alias_used, food_name_snapshot,
                    brand_snapshot, serving_name_snapshot, quantity, kcal_snapshot,
                    protein_snapshot, carbs_snapshot, fat_snapshot, fiber_snapshot,
                    note, raw_message, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    date_value,
                    time_value,
                    food["id"],
                    alias,
                    food["name"],
                    food["brand"],
                    food["serving_name"],
                    quantity_value,
                    macros["kcal"],
                    macros["protein_g"],
                    macros["carbs_g"],
                    macros["fat_g"],
                    macros["fiber_g"],
                    note,
                    raw_message,
                    created_at,
                    created_at,
                ),
            )
            entry = _get_entry(conn, int(cursor.lastrowid))
            return {"entry": entry, "day": self._get_day_with_conn(conn, date_value)}

    def log_recipe(
        self,
        alias: str | None = None,
        recipe_id: int | None = None,
        quantity: float | None = None,
        date: str | None = None,
        time: str | None = None,
        note: str | None = None,
        raw_message: str | None = None,
        adjustments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        date_value, time_value = self._date_time(date, time)
        created_at = now_iso(self.settings.timezone)
        with transaction(self.settings) as conn:
            recipe, alias_row = _resolve_recipe(conn, recipe_id=recipe_id, alias=alias)
            quantity_value = quantity
            if quantity_value is None and alias_row is not None:
                quantity_value = float(alias_row["default_quantity"])
            if quantity_value is None:
                quantity_value = float(recipe["default_quantity"])
            _validate_positive(quantity_value, "quantity")

            components = _recipe_components(conn, recipe["id"])
            adjusted_components = _apply_adjustments(conn, components, adjustments or [])
            totals = _components_totals(adjusted_components, multiplier=quantity_value)
            snapshot = _component_snapshot(adjusted_components, multiplier=quantity_value)

            cursor = conn.execute(
                """
                INSERT INTO meal_entries(
                    date, time, recipe_id, alias_used, food_name_snapshot,
                    serving_name_snapshot, quantity, kcal_snapshot, protein_snapshot,
                    carbs_snapshot, fat_snapshot, fiber_snapshot,
                    recipe_components_snapshot, note, raw_message, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    date_value,
                    time_value,
                    recipe["id"],
                    alias,
                    recipe["name"],
                    recipe["serving_name"],
                    quantity_value,
                    totals["kcal"],
                    totals["protein_g"],
                    totals["carbs_g"],
                    totals["fat_g"],
                    totals["fiber_g"],
                    json.dumps(snapshot, ensure_ascii=False),
                    note,
                    raw_message,
                    created_at,
                    created_at,
                ),
            )
            entry = _get_entry(conn, int(cursor.lastrowid))
            return {"entry": entry, "day": self._get_day_with_conn(conn, date_value)}

    def get_day(self, date: str | None = None) -> dict[str, Any]:
        date_value, _time_value = self._date_time(date, None)
        with transaction(self.settings) as conn:
            return self._get_day_with_conn(conn, date_value)

    def get_entries(
        self,
        from_date: str | None = None,
        to_date: str | None = None,
        limit: int = 500,
    ) -> dict[str, Any]:
        from_value, to_value = self._date_range(from_date, to_date)
        limit = _clean_limit(limit, 1, 2000)
        with transaction(self.settings) as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM meal_entries
                WHERE date BETWEEN ? AND ?
                ORDER BY date, time, id
                LIMIT ?
                """,
                (from_value, to_value, limit + 1),
            ).fetchall()
            entries = [_entry_to_dict(row) for row in rows[:limit]]
            days = self._days_with_entries(conn, from_value, to_value)
            totals = build_totals(entries)
            return {
                "from_date": from_value,
                "to_date": to_value,
                "entries": entries,
                "totals": totals,
                "days": days,
                "table": ascii_table(entries, totals),
                "daily_table": daily_totals_table(days),
                "truncated": len(rows) > limit,
            }

    def delete_entry(self, entry_id: int) -> dict[str, Any]:
        with transaction(self.settings) as conn:
            entry = _get_entry(conn, entry_id)
            conn.execute("DELETE FROM meal_entries WHERE id = ?", (entry_id,))
            return {
                "deleted_entry_id": entry_id,
                "day": self._get_day_with_conn(conn, entry["date"]),
            }

    def delete_food(self, food_id: int) -> dict[str, Any]:
        with transaction(self.settings) as conn:
            food = _food_with_aliases(conn, food_id)
            meal_count = _count_rows(conn, "meal_entries", "food_id", food_id)
            recipe_count = _count_rows(conn, "recipe_items", "food_id", food_id)
            if meal_count:
                raise ValueError(
                    f"Food id {food_id} has {meal_count} logged entries and cannot be deleted."
                )
            if recipe_count:
                raise ValueError(
                    f"Food id {food_id} is used in {recipe_count} recipe items and cannot be deleted."
                )
            conn.execute("DELETE FROM aliases WHERE food_id = ?", (food_id,))
            conn.execute("DELETE FROM foods WHERE id = ?", (food_id,))
            return {"deleted_food": food}

    def delete_recipe(self, recipe_id: int) -> dict[str, Any]:
        with transaction(self.settings) as conn:
            recipe = _recipe_with_items(conn, recipe_id)
            meal_count = _count_rows(conn, "meal_entries", "recipe_id", recipe_id)
            if meal_count:
                raise ValueError(
                    f"Recipe id {recipe_id} has {meal_count} logged entries and cannot be deleted."
                )
            conn.execute("DELETE FROM aliases WHERE recipe_id = ?", (recipe_id,))
            conn.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))
            return {"deleted_recipe": recipe}

    def update_entry(
        self,
        entry_id: int,
        quantity: float | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        with transaction(self.settings) as conn:
            entry = _get_entry(conn, entry_id)
            updates: dict[str, Any] = {}
            if quantity is not None:
                _validate_positive(quantity, "quantity")
                if entry["food_id"] is not None:
                    food = _get_food(conn, entry["food_id"])
                    macros = _food_macros(food, quantity)
                else:
                    ratio = quantity / float(entry["quantity"])
                    macros = {
                        "kcal": float(entry["kcal_snapshot"]) * ratio,
                        "protein_g": float(entry["protein_snapshot"]) * ratio,
                        "carbs_g": float(entry["carbs_snapshot"]) * ratio,
                        "fat_g": float(entry["fat_snapshot"]) * ratio,
                        "fiber_g": float(entry["fiber_snapshot"]) * ratio,
                    }
                updates.update(
                    {
                        "quantity": quantity,
                        "kcal_snapshot": macros["kcal"],
                        "protein_snapshot": macros["protein_g"],
                        "carbs_snapshot": macros["carbs_g"],
                        "fat_snapshot": macros["fat_g"],
                        "fiber_snapshot": macros["fiber_g"],
                    }
                )
            if note is not None:
                updates["note"] = note
            if not updates:
                raise ValueError("At least one of quantity or note must be provided.")
            updates["updated_at"] = now_iso(self.settings.timezone)
            assignments = ", ".join(f"{field} = ?" for field in updates)
            conn.execute(
                f"UPDATE meal_entries SET {assignments} WHERE id = ?",
                [*updates.values(), entry_id],
            )
            updated = _get_entry(conn, entry_id)
            return {"entry": updated, "day": self._get_day_with_conn(conn, updated["date"])}

    def finalize_day(self, date: str | None = None) -> dict[str, Any]:
        date_value, _time_value = self._date_time(date, None)
        generated_at = utc_timestamp()
        with transaction(self.settings) as conn:
            day = self._get_day_with_conn(conn, date_value)
            paths = write_daily_exports(
                self.settings.exports_dir,
                date_value,
                day["entries"],
                day["totals"],
                generated_at,
            )
            conn.execute(
                """
                INSERT INTO daily_exports(date, markdown_path, csv_path, json_path, finalized_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    markdown_path = excluded.markdown_path,
                    csv_path = excluded.csv_path,
                    json_path = excluded.json_path,
                    finalized_at = excluded.finalized_at
                """,
                (
                    date_value,
                    paths["markdown_path"],
                    paths["csv_path"],
                    paths["json_path"],
                    generated_at,
                ),
            )
            return {"date": date_value, "paths": paths, "day": day}

    def get_weekly_report(self, date: str | None = None) -> dict[str, Any]:
        anchor = self._date_value(date)
        start = anchor - timedelta(days=anchor.weekday())
        end = start + timedelta(days=6)
        from_value = start.isoformat()
        to_value = end.isoformat()
        with transaction(self.settings) as conn:
            days = self._days_with_entries(conn, from_value, to_value)
            rows = conn.execute(
                """
                SELECT *
                FROM meal_entries
                WHERE date BETWEEN ? AND ?
                ORDER BY date, time, id
                """,
                (from_value, to_value),
            ).fetchall()
            entries = [_entry_to_dict(row) for row in rows]
            totals = build_totals(entries)
            return {
                "week_start": from_value,
                "week_end": to_value,
                "entries": entries,
                "days": days,
                "totals": totals,
                "daily_table": daily_totals_table(days, total_label="WEEK"),
            }

    def list_aliases(self, query: str | None = None, limit: int = 50) -> dict[str, Any]:
        limit = _clean_limit(limit, 1, 200)
        params: list[Any] = []
        where = ""
        if query:
            where = "WHERE a.normalized_alias LIKE ?"
            params.append(f"%{normalize_alias(query)}%")
        params.append(limit)
        with transaction(self.settings) as conn:
            rows = conn.execute(
                f"""
                SELECT
                    a.*,
                    f.name AS food_name,
                    r.name AS recipe_name
                FROM aliases a
                LEFT JOIN foods f ON f.id = a.food_id
                LEFT JOIN recipes r ON r.id = a.recipe_id
                {where}
                ORDER BY a.normalized_alias
                LIMIT ?
                """,
                params,
            ).fetchall()
            aliases = []
            for row in rows:
                item = dict(row)
                item["target_type"] = "recipe" if row["recipe_id"] is not None else "food"
                item["target_name"] = row["recipe_name"] or row["food_name"]
                aliases.append(item)
            return {"aliases": aliases}

    def health(self) -> dict[str, Any]:
        with transaction(self.settings) as conn:
            version = conn.execute(
                "SELECT value FROM schema_meta WHERE key = 'schema_version'"
            ).fetchone()
        return {
            "status": "ok",
            "db_path": str(self.settings.db_path),
            "exports_path": str(self.settings.exports_dir),
            "timezone": self.settings.timezone,
            "schema_version": version["value"] if version else SCHEMA_VERSION,
        }

    def _get_day_with_conn(self, conn: sqlite3.Connection, date: str) -> dict[str, Any]:
        rows = conn.execute(
            """
            SELECT *
            FROM meal_entries
            WHERE date = ?
            ORDER BY time, id
            """,
            (date,),
        ).fetchall()
        entries = [_entry_to_dict(row) for row in rows]
        totals = build_totals(entries)
        return {
            "date": date,
            "entries": entries,
            "totals": totals,
            "table": ascii_table(entries, totals),
        }

    def _days_with_entries(
        self,
        conn: sqlite3.Connection,
        from_date: str,
        to_date: str,
    ) -> list[dict[str, Any]]:
        start = _parse_date(from_date)
        end = _parse_date(to_date)
        days = []
        current = start
        while current <= end:
            day = self._get_day_with_conn(conn, current.isoformat())
            days.append(
                {
                    "date": day["date"],
                    "entry_count": len(day["entries"]),
                    "totals": day["totals"],
                }
            )
            current += timedelta(days=1)
        return days

    def _date_time(self, date: str | None, time: str | None) -> tuple[str, str]:
        current = local_now(self.settings.timezone)
        date_value = date or current.date().isoformat()
        _validate_date(date_value)
        time_value = time or current.strftime("%H:%M:%S")
        _require_text(time_value, "time")
        return date_value, time_value

    def _date_value(self, date: str | None) -> Date:
        current = local_now(self.settings.timezone)
        date_value = date or current.date().isoformat()
        return _parse_date(date_value)

    def _date_range(self, from_date: str | None, to_date: str | None) -> tuple[str, str]:
        current = local_now(self.settings.timezone).date().isoformat()
        from_value = from_date or to_date or current
        to_value = to_date or from_date or current
        start = _parse_date(from_value)
        end = _parse_date(to_value)
        if start > end:
            raise ValueError("from_date must be on or before to_date.")
        return from_value, to_value


def register_tools(mcp: Any, service: NutritionService) -> None:
    mcp.tool()(service.add_food)
    mcp.tool()(service.update_food)
    mcp.tool()(service.add_alias)
    mcp.tool()(service.search_foods)
    mcp.tool()(service.get_food)
    mcp.tool()(service.list_foods)
    mcp.tool()(service.add_recipe)
    mcp.tool()(service.update_recipe)
    mcp.tool()(service.get_recipe)
    mcp.tool()(service.search_recipes)
    mcp.tool()(service.log_food)
    mcp.tool()(service.log_recipe)
    mcp.tool()(service.get_day)
    mcp.tool()(service.get_entries)
    mcp.tool()(service.delete_entry)
    mcp.tool()(service.delete_food)
    mcp.tool()(service.delete_recipe)
    mcp.tool()(service.update_entry)
    mcp.tool()(service.finalize_day)
    mcp.tool()(service.get_weekly_report)
    mcp.tool()(service.list_aliases)
    mcp.tool()(service.health)


def _create_alias(
    conn: sqlite3.Connection,
    alias: str,
    default_quantity: float,
    food_id: int | None = None,
    recipe_id: int | None = None,
) -> dict[str, Any]:
    _require_text(alias, "alias")
    _validate_positive(default_quantity, "default_quantity")
    if (food_id is None and recipe_id is None) or (food_id is not None and recipe_id is not None):
        raise ValueError("Exactly one of food_id or recipe_id is required.")
    if food_id is not None:
        _get_food(conn, food_id)
    if recipe_id is not None:
        _get_recipe(conn, recipe_id)
    normalized = normalize_alias(alias)
    if not normalized:
        raise ValueError("alias must contain at least one searchable character.")
    created_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    try:
        cursor = conn.execute(
            """
            INSERT INTO aliases(
                alias, normalized_alias, food_id, recipe_id, default_quantity, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (alias, normalized, food_id, recipe_id, default_quantity, created_at, created_at),
        )
    except sqlite3.IntegrityError as exc:
        existing = conn.execute(
            "SELECT * FROM aliases WHERE normalized_alias = ?",
            (normalized,),
        ).fetchone()
        if existing:
            target = existing["food_id"] if existing["food_id"] is not None else existing["recipe_id"]
            target_type = "food_id" if existing["food_id"] is not None else "recipe_id"
            raise ValueError(f"Alias '{alias}' already exists for {target_type}={target}.") from exc
        raise
    return dict(conn.execute("SELECT * FROM aliases WHERE id = ?", (cursor.lastrowid,)).fetchone())


def _resolve_food(
    conn: sqlite3.Connection,
    food_id: int | None = None,
    alias: str | None = None,
) -> tuple[dict[str, Any], sqlite3.Row | None]:
    if food_id is None and not alias:
        raise ValueError("Either alias or food_id is required.")
    if food_id is not None and alias:
        raise ValueError("Provide either alias or food_id, not both.")
    if food_id is not None:
        return _get_food(conn, food_id), None
    normalized = normalize_alias(alias or "")
    row = conn.execute("SELECT * FROM aliases WHERE normalized_alias = ?", (normalized,)).fetchone()
    if row is None:
        raise ValueError(f"Alias '{alias}' not found. Use search_foods or add_food first.")
    if row["food_id"] is None:
        raise ValueError(f"Alias '{alias}' refers to a recipe. Use log_recipe instead.")
    return _get_food(conn, row["food_id"]), row


def _resolve_recipe(
    conn: sqlite3.Connection,
    recipe_id: int | None = None,
    alias: str | None = None,
) -> tuple[dict[str, Any], sqlite3.Row | None]:
    if recipe_id is None and not alias:
        raise ValueError("Either alias or recipe_id is required.")
    if recipe_id is not None and alias:
        raise ValueError("Provide either alias or recipe_id, not both.")
    if recipe_id is not None:
        return _get_recipe(conn, recipe_id), None
    normalized = normalize_alias(alias or "")
    row = conn.execute("SELECT * FROM aliases WHERE normalized_alias = ?", (normalized,)).fetchone()
    if row is None:
        raise ValueError(f"Alias '{alias}' not found. Use search_recipes or add_recipe first.")
    if row["recipe_id"] is None:
        raise ValueError(f"Alias '{alias}' refers to a food. Use log_food instead.")
    return _get_recipe(conn, row["recipe_id"]), row


def _replace_recipe_items(
    conn: sqlite3.Connection,
    recipe_id: int,
    ingredients: list[dict[str, Any]],
    timezone: str,
) -> None:
    conn.execute("DELETE FROM recipe_items WHERE recipe_id = ?", (recipe_id,))
    timestamp = now_iso(timezone)
    merged: dict[int, dict[str, Any]] = {}
    for spec in ingredients:
        food, _alias_row = _resolve_food(
            conn,
            food_id=spec.get("food_id"),
            alias=spec.get("alias"),
        )
        quantity = _quantity_from_inputs(food, quantity=spec.get("quantity"), grams=spec.get("grams"))
        existing = merged.get(food["id"])
        if existing:
            existing["quantity"] += quantity
            if spec.get("note"):
                existing["note"] = spec["note"]
        else:
            merged[food["id"]] = {"quantity": quantity, "note": spec.get("note")}
    for food_id, item in merged.items():
        conn.execute(
            """
            INSERT INTO recipe_items(recipe_id, food_id, quantity, note, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (recipe_id, food_id, item["quantity"], item["note"], timestamp, timestamp),
        )


def _recipe_components(conn: sqlite3.Connection, recipe_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT ri.*, f.name, f.brand, f.serving_name, f.grams_per_serving,
               f.kcal, f.protein_g, f.carbs_g, f.fat_g, f.fiber_g
        FROM recipe_items ri
        JOIN foods f ON f.id = ri.food_id
        WHERE ri.recipe_id = ?
        ORDER BY ri.id
        """,
        (recipe_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _apply_adjustments(
    conn: sqlite3.Connection,
    components: list[dict[str, Any]],
    adjustments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_food_id = {int(component["food_id"]): dict(component) for component in components}
    for adjustment in adjustments:
        if not isinstance(adjustment, dict):
            raise ValueError("Each adjustment must be an object.")
        food, _alias_row = _resolve_food(
            conn,
            food_id=adjustment.get("food_id"),
            alias=adjustment.get("alias"),
        )
        food_id = int(food["id"])
        current = by_food_id.get(food_id)
        current_quantity = float(current["quantity"]) if current else 0.0
        new_quantity: float
        if adjustment.get("quantity") is not None or adjustment.get("grams") is not None:
            new_quantity = _quantity_from_inputs(
                food,
                quantity=adjustment.get("quantity"),
                grams=adjustment.get("grams"),
            )
        elif adjustment.get("delta_quantity") is not None:
            new_quantity = current_quantity + float(adjustment["delta_quantity"])
        elif adjustment.get("delta_grams") is not None:
            delta = _grams_to_quantity(food, float(adjustment["delta_grams"]))
            new_quantity = current_quantity + delta
        else:
            raise ValueError(
                "Adjustment requires one of quantity, grams, delta_quantity, or delta_grams."
            )
        if new_quantity < 0:
            raise ValueError("Adjusted ingredient quantity must be greater than or equal to 0.")
        if new_quantity == 0:
            by_food_id.pop(food_id, None)
            continue
        base = current or {
            "food_id": food_id,
            "note": None,
            "name": food["name"],
            "brand": food["brand"],
            "serving_name": food["serving_name"],
            "grams_per_serving": food["grams_per_serving"],
            "kcal": food["kcal"],
            "protein_g": food["protein_g"],
            "carbs_g": food["carbs_g"],
            "fat_g": food["fat_g"],
            "fiber_g": food["fiber_g"],
        }
        base["quantity"] = new_quantity
        if adjustment.get("note") is not None:
            base["note"] = adjustment["note"]
        by_food_id[food_id] = base
    return list(by_food_id.values())


def _components_totals(components: list[dict[str, Any]], multiplier: float = 1) -> dict[str, float]:
    totals = {field: 0.0 for field in MACRO_FIELDS}
    for component in components:
        quantity = float(component["quantity"]) * multiplier
        totals["kcal"] += float(component["kcal"]) * quantity
        totals["protein_g"] += float(component["protein_g"]) * quantity
        totals["carbs_g"] += float(component["carbs_g"]) * quantity
        totals["fat_g"] += float(component["fat_g"]) * quantity
        totals["fiber_g"] += float(component["fiber_g"]) * quantity
    return totals


def _component_snapshot(components: list[dict[str, Any]], multiplier: float) -> list[dict[str, Any]]:
    snapshot = []
    for component in components:
        quantity = float(component["quantity"]) * multiplier
        snapshot.append(
            {
                "food_id": component["food_id"],
                "food_name": component["name"],
                "brand": component["brand"],
                "serving_name": component["serving_name"],
                "quantity": quantity,
                **_food_macros(component, quantity),
            }
        )
    return snapshot


def _recipe_with_items(conn: sqlite3.Connection, recipe_id: int) -> dict[str, Any]:
    recipe = _get_recipe(conn, recipe_id)
    components = _recipe_components(conn, recipe_id)
    aliases = [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM aliases WHERE recipe_id = ? ORDER BY normalized_alias",
            (recipe_id,),
        ).fetchall()
    ]
    recipe["ingredients"] = _component_snapshot(components, multiplier=1)
    recipe["totals"] = _components_totals(components, multiplier=1)
    recipe["aliases"] = aliases
    return recipe


def _food_with_aliases(conn: sqlite3.Connection, food_id: int) -> dict[str, Any]:
    food = _get_food(conn, food_id)
    food["aliases"] = [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM aliases WHERE food_id = ? ORDER BY normalized_alias",
            (food_id,),
        ).fetchall()
    ]
    return food


def _get_food(conn: sqlite3.Connection, food_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM foods WHERE id = ?", (food_id,)).fetchone()
    if row is None:
        raise ValueError(f"Food id {food_id} not found.")
    return dict(row)


def _get_recipe(conn: sqlite3.Connection, recipe_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    if row is None:
        raise ValueError(f"Recipe id {recipe_id} not found.")
    return dict(row)


def _get_entry(conn: sqlite3.Connection, entry_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM meal_entries WHERE id = ?", (entry_id,)).fetchone()
    if row is None:
        raise ValueError(f"Entry id {entry_id} not found.")
    return _entry_to_dict(row)


def _count_rows(conn: sqlite3.Connection, table: str, column: str, value: int) -> int:
    row = conn.execute(
        f"SELECT COUNT(*) AS count FROM {table} WHERE {column} = ?",
        (value,),
    ).fetchone()
    return int(row["count"])


def _entry_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    entry = dict(row)
    snapshot = entry.get("recipe_components_snapshot")
    if snapshot:
        entry["recipe_components"] = json.loads(snapshot)
    return entry


def _food_macros(food: dict[str, Any], quantity: float) -> dict[str, float]:
    return {
        "kcal": float(food["kcal"]) * quantity,
        "protein_g": float(food["protein_g"]) * quantity,
        "carbs_g": float(food["carbs_g"]) * quantity,
        "fat_g": float(food["fat_g"]) * quantity,
        "fiber_g": float(food["fiber_g"]) * quantity,
    }


def _quantity_from_inputs(
    food: dict[str, Any],
    quantity: float | None = None,
    grams: float | None = None,
    default_quantity: float | None = None,
) -> float:
    if quantity is not None and grams is not None:
        raise ValueError("Provide either quantity or grams, not both.")
    if grams is not None:
        return _grams_to_quantity(food, float(grams))
    quantity_value = quantity if quantity is not None else default_quantity
    if quantity_value is None:
        quantity_value = 1
    _validate_positive(quantity_value, "quantity")
    return float(quantity_value)


def _grams_to_quantity(food: dict[str, Any], grams: float) -> float:
    _validate_positive(grams, "grams")
    grams_per_serving = food.get("grams_per_serving")
    if grams_per_serving is None or float(grams_per_serving) <= 0:
        raise ValueError(
            f"Food '{food['name']}' needs grams_per_serving before grams can be used."
        )
    return grams / float(grams_per_serving)


def _validate_positive(value: float, field: str) -> None:
    if float(value) <= 0:
        raise ValueError(f"{field} must be greater than 0.")


def _validate_macros(kcal: float, protein_g: float, carbs_g: float, fat_g: float, fiber_g: float) -> None:
    for field, value in {
        "kcal": kcal,
        "protein_g": protein_g,
        "carbs_g": carbs_g,
        "fat_g": fat_g,
        "fiber_g": fiber_g,
    }.items():
        if float(value) < 0:
            raise ValueError(f"{field} must be greater than or equal to 0.")


def _validate_date(value: str) -> None:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("date must be YYYY-MM-DD.") from exc
    if parsed.date().isoformat() != value:
        raise ValueError("date must be YYYY-MM-DD.")


def _parse_date(value: str) -> Date:
    _validate_date(value)
    return datetime.strptime(value, "%Y-%m-%d").date()


def _require_text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required.")


def _clean_limit(limit: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(limit)))
