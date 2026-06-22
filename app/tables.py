from __future__ import annotations

import re
import string
from typing import Any


SAFE_EDGE_PUNCTUATION = "".join(ch for ch in string.punctuation if ch not in "+-")


def normalize_alias(alias: str) -> str:
    normalized = alias.strip().lower()
    normalized = normalized.strip(SAFE_EDGE_PUNCTUATION)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def format_quantity(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.3f}".rstrip("0").rstrip(".")


def format_macro(value: float) -> str:
    return f"{value:.1f}g"


def value(row: dict[str, Any], key: str) -> float:
    return float(row.get(key, 0) or 0)


def truncate(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    if width <= 3:
        return text[:width]
    return text[: width - 3] + "..."


def build_totals(entries: list[dict[str, Any]]) -> dict[str, float]:
    return {
        "kcal": sum(value(row, "kcal_snapshot") for row in entries),
        "protein_g": sum(value(row, "protein_snapshot") for row in entries),
        "carbs_g": sum(value(row, "carbs_snapshot") for row in entries),
        "fat_g": sum(value(row, "fat_snapshot") for row in entries),
        "fiber_g": sum(value(row, "fiber_snapshot") for row in entries),
        "sugars_g": sum(value(row, "sugars_snapshot") for row in entries),
        "saturated_fat_g": sum(value(row, "saturated_fat_snapshot") for row in entries),
        "salt_g": sum(value(row, "salt_snapshot") for row in entries),
    }


def ascii_table(entries: list[dict[str, Any]], totals: dict[str, float] | None = None) -> str:
    totals = totals or build_totals(entries)
    headers = ["Food", "Qty", "kcal", "Protein", "Carbs", "Sugar", "Fat", "SatFat", "Fiber", "Salt"]
    rows = []
    for entry in entries:
        rows.append(
            [
                truncate(str(entry["food_name_snapshot"]), 22),
                format_quantity(float(entry["quantity"])),
                str(round(value(entry, "kcal_snapshot"))),
                format_macro(value(entry, "protein_snapshot")),
                format_macro(value(entry, "carbs_snapshot")),
                format_macro(value(entry, "sugars_snapshot")),
                format_macro(value(entry, "fat_snapshot")),
                format_macro(value(entry, "saturated_fat_snapshot")),
                format_macro(value(entry, "fiber_snapshot")),
                format_macro(value(entry, "salt_snapshot")),
            ]
        )

    total_row = [
        "TOTAL",
        "",
        str(round(float(totals["kcal"]))),
        format_macro(float(totals["protein_g"])),
        format_macro(float(totals["carbs_g"])),
        format_macro(float(totals["sugars_g"])),
        format_macro(float(totals["fat_g"])),
        format_macro(float(totals["saturated_fat_g"])),
        format_macro(float(totals["fiber_g"])),
        format_macro(float(totals["salt_g"])),
    ]

    all_rows = rows + [total_row]
    max_widths = [22, 6, 6, 9, 7, 7, 6, 7, 7, 6]
    widths = []
    for index, header in enumerate(headers):
        content_width = max([len(header), *(len(row[index]) for row in all_rows)])
        widths.append(min(max_widths[index], content_width))

    def border() -> str:
        return "+" + "+".join("-" * (width + 2) for width in widths) + "+"

    def fmt(row: list[str]) -> str:
        cells = []
        for value, width in zip(row, widths, strict=True):
            cells.append(f" {truncate(value, width).ljust(width)} ")
        return "|" + "|".join(cells) + "|"

    lines = [border(), fmt(headers), border()]
    lines.extend(fmt(row) for row in rows)
    lines.extend([border(), fmt(total_row), border()])
    return "\n".join(lines)


def markdown_table(entries: list[dict[str, Any]], totals: dict[str, float]) -> str:
    lines = [
        "| Food | Qty | kcal | Protein | Carbs | Sugar | Fat | Sat fat | Fiber | Salt |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for entry in entries:
        lines.append(
            "| {food} | {qty} | {kcal} | {protein} | {carbs} | {sugars} | {fat} | {sat_fat} | {fiber} | {salt} |".format(
                food=str(entry["food_name_snapshot"]).replace("|", "\\|"),
                qty=format_quantity(value(entry, "quantity")),
                kcal=round(value(entry, "kcal_snapshot")),
                protein=format_macro(value(entry, "protein_snapshot")),
                carbs=format_macro(value(entry, "carbs_snapshot")),
                sugars=format_macro(value(entry, "sugars_snapshot")),
                fat=format_macro(value(entry, "fat_snapshot")),
                sat_fat=format_macro(value(entry, "saturated_fat_snapshot")),
                fiber=format_macro(value(entry, "fiber_snapshot")),
                salt=format_macro(value(entry, "salt_snapshot")),
            )
        )
    lines.append(
        "| **TOTAL** |  | **{kcal}** | **{protein}** | **{carbs}** | **{sugars}** | **{fat}** | **{sat_fat}** | **{fiber}** | **{salt}** |".format(
            kcal=round(float(totals["kcal"])),
            protein=format_macro(float(totals["protein_g"])),
            carbs=format_macro(float(totals["carbs_g"])),
            sugars=format_macro(float(totals["sugars_g"])),
            fat=format_macro(float(totals["fat_g"])),
            sat_fat=format_macro(float(totals["saturated_fat_g"])),
            fiber=format_macro(float(totals["fiber_g"])),
            salt=format_macro(float(totals["salt_g"])),
        )
    )
    return "\n".join(lines)


def foods_table(foods: list[dict[str, Any]]) -> str:
    headers = ["ID", "Food", "Aliases", "kcal", "Protein", "Carbs", "Fat"]
    rows = []
    for food in foods:
        aliases = ", ".join(alias["alias"] for alias in food.get("aliases", []))
        rows.append(
            [
                str(food["id"]),
                truncate(str(food["name"]), 22),
                truncate(aliases, 24),
                str(round(float(food["kcal"]))),
                format_macro(float(food["protein_g"])),
                format_macro(float(food["carbs_g"])),
                format_macro(float(food["fat_g"])),
            ]
        )
    if not rows:
        rows = [["", "(none)", "", "", "", "", ""]]
    max_widths = [5, 22, 24, 7, 9, 7, 6]
    widths = []
    for index, header in enumerate(headers):
        content_width = max([len(header), *(len(row[index]) for row in rows)])
        widths.append(min(max_widths[index], content_width))

    def border() -> str:
        return "+" + "+".join("-" * (width + 2) for width in widths) + "+"

    def fmt(row: list[str]) -> str:
        return "|" + "|".join(
            f" {truncate(value, width).ljust(width)} "
            for value, width in zip(row, widths, strict=True)
        ) + "|"

    return "\n".join([border(), fmt(headers), border(), *(fmt(row) for row in rows), border()])


def daily_totals_table(days: list[dict[str, Any]], total_label: str = "TOTAL") -> str:
    headers = ["Date", "kcal", "Protein", "Carbs", "Sugar", "Fat", "SatFat", "Fiber", "Salt"]
    rows = []
    for day in days:
        totals = day["totals"]
        rows.append(
            [
                day["date"],
                str(round(float(totals["kcal"]))),
                format_macro(float(totals["protein_g"])),
                format_macro(float(totals["carbs_g"])),
                format_macro(float(totals["sugars_g"])),
                format_macro(float(totals["fat_g"])),
                format_macro(float(totals["saturated_fat_g"])),
                format_macro(float(totals["fiber_g"])),
                format_macro(float(totals["salt_g"])),
            ]
        )
    grand_totals = {
        "kcal": sum(float(day["totals"]["kcal"]) for day in days),
        "protein_g": sum(float(day["totals"]["protein_g"]) for day in days),
        "carbs_g": sum(float(day["totals"]["carbs_g"]) for day in days),
        "fat_g": sum(float(day["totals"]["fat_g"]) for day in days),
        "fiber_g": sum(float(day["totals"]["fiber_g"]) for day in days),
        "sugars_g": sum(float(day["totals"]["sugars_g"]) for day in days),
        "saturated_fat_g": sum(float(day["totals"]["saturated_fat_g"]) for day in days),
        "salt_g": sum(float(day["totals"]["salt_g"]) for day in days),
    }
    total_row = [
        total_label,
        str(round(float(grand_totals["kcal"]))),
        format_macro(float(grand_totals["protein_g"])),
        format_macro(float(grand_totals["carbs_g"])),
        format_macro(float(grand_totals["sugars_g"])),
        format_macro(float(grand_totals["fat_g"])),
        format_macro(float(grand_totals["saturated_fat_g"])),
        format_macro(float(grand_totals["fiber_g"])),
        format_macro(float(grand_totals["salt_g"])),
    ]
    all_rows = rows + [total_row]
    widths = []
    for index, header in enumerate(headers):
        widths.append(max(len(header), *(len(row[index]) for row in all_rows)))

    def border() -> str:
        return "+" + "+".join("-" * (width + 2) for width in widths) + "+"

    def fmt(row: list[str]) -> str:
        return "|" + "|".join(
            f" {value.ljust(width)} "
            for value, width in zip(row, widths, strict=True)
        ) + "|"

    return "\n".join(
        [border(), fmt(headers), border(), *(fmt(row) for row in rows), border(), fmt(total_row), border()]
    )
