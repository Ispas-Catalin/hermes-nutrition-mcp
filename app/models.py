from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Totals:
    kcal: float = 0
    protein_g: float = 0
    carbs_g: float = 0
    fat_g: float = 0
    fiber_g: float = 0
    sugars_g: float = 0
    saturated_fat_g: float = 0
    salt_g: float = 0

    def as_dict(self) -> dict[str, float]:
        return {
            "kcal": self.kcal,
            "protein_g": self.protein_g,
            "carbs_g": self.carbs_g,
            "fat_g": self.fat_g,
            "fiber_g": self.fiber_g,
            "sugars_g": self.sugars_g,
            "saturated_fat_g": self.saturated_fat_g,
            "salt_g": self.salt_g,
        }
