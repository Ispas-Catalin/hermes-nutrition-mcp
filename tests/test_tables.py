from __future__ import annotations

from app.tables import ascii_table, normalize_alias


def test_alias_normalization() -> None:
    assert normalize_alias(" Babybel ") == "babybel"
    assert normalize_alias("LIDL Skyr") == "lidl skyr"
    assert normalize_alias("  iaurt   grecesc  ") == "iaurt grecesc"
    assert normalize_alias("...Branza de vaci!!!") == "branza de vaci"


def test_ascii_table_formatting() -> None:
    table = ascii_table(
        [
            {
                "food_name_snapshot": "A very very very long food name",
                "quantity": 2,
                "kcal_snapshot": 140,
                "protein_snapshot": 10,
                "carbs_snapshot": 0,
                "fat_snapshot": 10,
                "fiber_snapshot": 0,
            }
        ]
    )
    assert "A very very very lo..." in table
    assert "TOTAL" in table
    assert "140" in table

