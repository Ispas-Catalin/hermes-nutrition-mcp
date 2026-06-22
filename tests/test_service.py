from __future__ import annotations

import json
import sqlite3

import pytest

from app.db import connect, initialize_database
from app.tools import NutritionService


def test_database_initialization(settings) -> None:
    initialize_database(settings)
    assert settings.db_path.exists()
    assert settings.exports_dir.exists()
    with connect(settings.db_path) as conn:
        tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        food_columns = {row["name"] for row in conn.execute("PRAGMA table_info(foods)")}
        entry_columns = {row["name"] for row in conn.execute("PRAGMA table_info(meal_entries)")}
    assert "foods" in tables
    assert "recipes" in tables
    assert "meal_entries" in tables
    assert {"sugars_g", "saturated_fat_g", "salt_g"} <= food_columns
    assert {"sugars_snapshot", "saturated_fat_snapshot", "salt_snapshot"} <= entry_columns


def test_add_food(service: NutritionService) -> None:
    result = service.add_food(
        name="Babybel",
        kcal=70,
        protein_g=4,
        carbs_g=0,
        fat_g=5,
        serving_name="1 piece",
        aliases=["babybel"],
    )
    assert result["food"]["id"] == 1
    assert result["aliases"][0]["normalized_alias"] == "babybel"


def test_add_alias(seeded_service: NutritionService) -> None:
    result = seeded_service.add_alias("mini cheese", food_id=1)
    assert result["normalized_alias"] == "mini cheese"


def test_duplicate_alias_error(seeded_service: NutritionService) -> None:
    with pytest.raises(ValueError, match="already exists"):
        seeded_service.add_alias(" Babybel ", food_id=2)


def test_missing_alias_error(seeded_service: NutritionService) -> None:
    with pytest.raises(ValueError, match="not found"):
        seeded_service.log_food(alias="missing")


def test_log_food_by_alias(seeded_service: NutritionService) -> None:
    result = seeded_service.log_food(alias="babybel", quantity=2, date="2026-06-22", time="10:00")
    entry = result["entry"]
    assert entry["kcal_snapshot"] == 140
    assert result["day"]["totals"]["protein_g"] == 8
    assert "Babybel" in result["day"]["table"]


def test_log_food_by_food_id(seeded_service: NutritionService) -> None:
    result = seeded_service.log_food(food_id=2, quantity=1, date="2026-06-22", time="11:00")
    assert result["entry"]["food_name_snapshot"] == "Greek yogurt"
    assert result["day"]["totals"]["kcal"] == 180


def test_get_food_by_alias(seeded_service: NutritionService) -> None:
    result = seeded_service.get_food(alias="babybel")
    assert result["food"]["name"] == "Babybel"
    assert result["food"]["aliases"][0]["normalized_alias"] == "babybel"
    assert result["matched_alias"]["alias"] == "babybel"


def test_list_foods_without_query(seeded_service: NutritionService) -> None:
    result = seeded_service.list_foods()
    assert [food["name"] for food in result["foods"]] == ["Babybel", "Greek yogurt"]
    assert "Babybel" in result["table"]
    assert "greek yogurt" in result["table"]


def test_get_day_totals(seeded_service: NutritionService) -> None:
    seeded_service.log_food(alias="babybel", quantity=2, date="2026-06-22", time="10:00")
    seeded_service.log_food(alias="greek yogurt", quantity=1, date="2026-06-22", time="11:00")
    day = seeded_service.get_day(date="2026-06-22")
    assert day["totals"]["kcal"] == 320
    assert day["totals"]["protein_g"] == 28


def test_get_entries_range(seeded_service: NutritionService) -> None:
    seeded_service.log_food(alias="babybel", quantity=1, date="2026-06-22", time="10:00")
    seeded_service.log_food(alias="greek yogurt", quantity=1, date="2026-06-23", time="11:00")
    seeded_service.log_food(alias="babybel", quantity=3, date="2026-06-25", time="12:00")
    result = seeded_service.get_entries(from_date="2026-06-22", to_date="2026-06-23")
    assert len(result["entries"]) == 2
    assert result["totals"]["kcal"] == 250
    assert [day["date"] for day in result["days"]] == ["2026-06-22", "2026-06-23"]
    assert "2026-06-22" in result["daily_table"]


def test_get_entries_validates_range(seeded_service: NutritionService) -> None:
    with pytest.raises(ValueError, match="from_date"):
        seeded_service.get_entries(from_date="2026-06-24", to_date="2026-06-23")


def test_update_entry(seeded_service: NutritionService) -> None:
    result = seeded_service.log_food(alias="babybel", quantity=2, date="2026-06-22")
    entry_id = result["entry"]["id"]
    updated = seeded_service.update_entry(entry_id, quantity=3)
    assert updated["entry"]["quantity"] == 3
    assert updated["entry"]["kcal_snapshot"] == 210


def test_delete_entry(seeded_service: NutritionService) -> None:
    result = seeded_service.log_food(alias="babybel", quantity=2, date="2026-06-22")
    deleted = seeded_service.delete_entry(result["entry"]["id"])
    assert deleted["deleted_entry_id"] == result["entry"]["id"]
    assert deleted["day"]["entries"] == []
    assert deleted["day"]["totals"]["kcal"] == 0


def test_delete_unused_food(service: NutritionService) -> None:
    result = service.add_food(
        name="Typo food",
        kcal=10,
        protein_g=1,
        carbs_g=1,
        fat_g=1,
        aliases=["typo food"],
    )
    deleted = service.delete_food(result["food"]["id"])
    assert deleted["deleted_food"]["name"] == "Typo food"
    assert service.list_foods()["foods"] == []


def test_delete_logged_food_is_blocked(seeded_service: NutritionService) -> None:
    seeded_service.log_food(alias="babybel", quantity=1, date="2026-06-22")
    with pytest.raises(ValueError, match="logged entries"):
        seeded_service.delete_food(1)


def test_finalize_day_exports(seeded_service: NutritionService) -> None:
    seeded_service.log_food(alias="babybel", quantity=2, date="2026-06-22")
    result = seeded_service.finalize_day(date="2026-06-22")
    for path in result["paths"].values():
        assert path
    assert (seeded_service.settings.exports_dir / "daily" / "2026-06-22.md").exists()
    assert (seeded_service.settings.exports_dir / "csv" / "2026-06-22.csv").exists()
    json_path = seeded_service.settings.exports_dir / "json" / "2026-06-22.json"
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["totals"]["kcal"] == 140
    assert payload["totals"]["sugars_g"] == 0


def test_new_nutrients_are_logged_and_exported(service: NutritionService) -> None:
    service.add_food(
        name="Pizza label slice",
        serving_name="1 slice",
        kcal=500,
        protein_g=25,
        carbs_g=60,
        fat_g=20,
        fiber_g=3,
        sugars_g=0.7,
        saturated_fat_g=16.8,
        salt_g=1.4,
        aliases=["pizza slice"],
    )
    result = service.log_food(alias="pizza slice", quantity=1, date="2026-06-22")
    entry = result["entry"]
    assert entry["sugars_snapshot"] == pytest.approx(0.7)
    assert entry["saturated_fat_snapshot"] == pytest.approx(16.8)
    assert entry["salt_snapshot"] == pytest.approx(1.4)
    assert result["day"]["totals"]["sugars_g"] == pytest.approx(0.7)
    assert result["day"]["totals"]["saturated_fat_g"] == pytest.approx(16.8)
    assert result["day"]["totals"]["salt_g"] == pytest.approx(1.4)
    assert "SatFat" in result["day"]["table"]
    exported = service.finalize_day(date="2026-06-22")
    json_path = service.settings.exports_dir / "json" / "2026-06-22.json"
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["totals"]["salt_g"] == pytest.approx(1.4)
    csv_path = exported["paths"]["csv_path"]
    assert "saturated_fat_g" in open(csv_path, encoding="utf-8").read()


def test_food_grams_logging(service: NutritionService) -> None:
    service.add_food(
        name="Default tuna",
        serving_name="100 g",
        grams_per_serving=100,
        kcal=120,
        protein_g=26,
        carbs_g=0,
        fat_g=1,
        aliases=["default tuna"],
    )
    result = service.log_food(alias="default tuna", grams=60, date="2026-06-22")
    assert result["entry"]["quantity"] == 0.6
    assert result["entry"]["protein_snapshot"] == pytest.approx(15.6)


def test_recipe_with_adjustment(service: NutritionService) -> None:
    service.add_food(
        name="Pizza dough",
        serving_name="100 g",
        grams_per_serving=100,
        kcal=250,
        protein_g=8,
        carbs_g=50,
        fat_g=2,
        aliases=["pizza dough"],
    )
    service.add_food(
        name="Default tuna",
        serving_name="100 g",
        grams_per_serving=100,
        kcal=120,
        protein_g=26,
        carbs_g=0,
        fat_g=1,
        aliases=["default tuna"],
    )
    service.add_food(
        name="Cheese",
        serving_name="100 g",
        grams_per_serving=100,
        kcal=300,
        protein_g=25,
        carbs_g=2,
        fat_g=22,
        aliases=["cheese"],
    )
    recipe = service.add_recipe(
        name="Tuna pizza",
        aliases=["tuna pizza"],
        ingredients=[
            {"alias": "pizza dough", "grams": 165},
            {"alias": "default tuna", "grams": 60},
            {"alias": "cheese", "grams": 40},
        ],
    )
    assert recipe["recipe"]["totals"]["kcal"] == pytest.approx(604.5)
    logged = service.log_recipe(
        alias="tuna pizza",
        adjustments=[{"alias": "cheese", "delta_grams": 20}],
        date="2026-06-22",
    )
    assert logged["entry"]["kcal_snapshot"] == pytest.approx(664.5)
    assert len(logged["entry"]["recipe_components"]) == 3


def test_delete_unused_recipe(service: NutritionService) -> None:
    service.add_food(
        name="Cheese",
        serving_name="100 g",
        grams_per_serving=100,
        kcal=300,
        protein_g=25,
        carbs_g=2,
        fat_g=22,
        aliases=["cheese"],
    )
    recipe = service.add_recipe(
        name="Cheese snack",
        aliases=["cheese snack"],
        ingredients=[{"alias": "cheese", "grams": 30}],
    )
    deleted = service.delete_recipe(recipe["recipe"]["id"])
    assert deleted["deleted_recipe"]["name"] == "Cheese snack"
    assert service.search_recipes("cheese snack")["recipes"] == []


def test_delete_logged_recipe_is_blocked(service: NutritionService) -> None:
    service.add_food(
        name="Cheese",
        serving_name="100 g",
        grams_per_serving=100,
        kcal=300,
        protein_g=25,
        carbs_g=2,
        fat_g=22,
        aliases=["cheese"],
    )
    recipe = service.add_recipe(
        name="Cheese snack",
        aliases=["cheese snack"],
        ingredients=[{"alias": "cheese", "grams": 30}],
    )
    service.log_recipe(alias="cheese snack", date="2026-06-22")
    with pytest.raises(ValueError, match="logged entries"):
        service.delete_recipe(recipe["recipe"]["id"])


def test_weekly_report_uses_monday_to_sunday(seeded_service: NutritionService) -> None:
    seeded_service.log_food(alias="babybel", quantity=1, date="2026-06-22")
    seeded_service.log_food(alias="greek yogurt", quantity=1, date="2026-06-28")
    seeded_service.log_food(alias="babybel", quantity=10, date="2026-06-29")
    report = seeded_service.get_weekly_report(date="2026-06-24")
    assert report["week_start"] == "2026-06-22"
    assert report["week_end"] == "2026-06-28"
    assert report["totals"]["kcal"] == 250
    assert len(report["days"]) == 7
    assert "WEEK" in report["daily_table"]
