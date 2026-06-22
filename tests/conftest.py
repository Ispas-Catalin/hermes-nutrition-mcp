from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings
from app.tools import NutritionService


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path, timezone="Europe/Bucharest")


@pytest.fixture()
def service(settings: Settings) -> NutritionService:
    return NutritionService(settings)


@pytest.fixture()
def seeded_service(service: NutritionService) -> NutritionService:
    service.add_food(
        name="Babybel",
        serving_name="1 piece",
        kcal=70,
        protein_g=4,
        carbs_g=0,
        fat_g=5,
        aliases=["babybel"],
    )
    service.add_food(
        name="Greek yogurt",
        serving_name="1 serving",
        kcal=180,
        protein_g=20,
        carbs_g=8,
        fat_g=4,
        aliases=["greek yogurt"],
    )
    return service
