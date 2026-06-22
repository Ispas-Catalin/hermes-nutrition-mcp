from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.tables import markdown_table


def write_daily_exports(
    exports_dir: Path,
    date: str,
    entries: list[dict[str, Any]],
    totals: dict[str, float],
    generated_at: str,
) -> dict[str, str]:
    daily_dir = exports_dir / "daily"
    csv_dir = exports_dir / "csv"
    json_dir = exports_dir / "json"
    for directory in (daily_dir, csv_dir, json_dir):
        directory.mkdir(parents=True, exist_ok=True)

    markdown_path = daily_dir / f"{date}.md"
    csv_path = csv_dir / f"{date}.csv"
    json_path = json_dir / f"{date}.json"

    markdown = "\n\n".join(
        [
            f"# Nutrition log - {date}",
            markdown_table(entries, totals),
            "## Totals",
            (
                f"- kcal: {round(totals['kcal'])}\n"
                f"- protein: {totals['protein_g']:.1f}g\n"
                f"- carbs: {totals['carbs_g']:.1f}g\n"
                f"- fat: {totals['fat_g']:.1f}g\n"
                f"- fiber: {totals['fiber_g']:.1f}g"
            ),
            f"Generated at: {generated_at}",
        ]
    )
    markdown_path.write_text(markdown + "\n", encoding="utf-8")

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "id",
                "date",
                "time",
                "food",
                "brand",
                "serving",
                "quantity",
                "kcal",
                "protein_g",
                "carbs_g",
                "fat_g",
                "fiber_g",
                "note",
            ],
        )
        writer.writeheader()
        for entry in entries:
            writer.writerow(
                {
                    "id": entry["id"],
                    "date": entry["date"],
                    "time": entry["time"],
                    "food": entry["food_name_snapshot"],
                    "brand": entry["brand_snapshot"],
                    "serving": entry["serving_name_snapshot"],
                    "quantity": entry["quantity"],
                    "kcal": entry["kcal_snapshot"],
                    "protein_g": entry["protein_snapshot"],
                    "carbs_g": entry["carbs_snapshot"],
                    "fat_g": entry["fat_snapshot"],
                    "fiber_g": entry["fiber_snapshot"],
                    "note": entry["note"],
                }
            )
        writer.writerow(
            {
                "food": "TOTAL",
                "kcal": totals["kcal"],
                "protein_g": totals["protein_g"],
                "carbs_g": totals["carbs_g"],
                "fat_g": totals["fat_g"],
                "fiber_g": totals["fiber_g"],
            }
        )

    payload = {
        "date": date,
        "entries": entries,
        "totals": totals,
        "generated_at": generated_at,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "markdown_path": str(markdown_path),
        "csv_path": str(csv_path),
        "json_path": str(json_path),
    }


def utc_timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
