from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Totals:
    kcal: float = 0
    protein_g: float = 0
    carbs_g: float = 0
    fat_g: float = 0
    fiber_g: float = 0

    def as_dict(self) -> dict[str, float]:
        return {
            "kcal": self.kcal,
            "protein_g": self.protein_g,
            "carbs_g": self.carbs_g,
            "fat_g": self.fat_g,
            "fiber_g": self.fiber_g,
        }

