"""SYNTHETIC fixtures for ABB-15 (documented in docs/science/CONTRADICTIONS_APPLICABILITY.md).

Limited-transfer example: a claim from a *synthetic* global meta-analysis (maize/rice/soybean,
mixed water regimes, acid-to-neutral soils, humid climates) compared with a *synthetic* rainfed
Mediterranean case (durum wheat/chickpea, calcareous clay loam, Csa). Values are invented for
tests and are not attributed to any real paper or farm.
"""
from __future__ import annotations

GLOBAL_META_CONTEXT = {
    "crops": ["maize", "rice", "soybean"],
    "region": "Global (SYNTHETIC)",
    "climate": "Several humid climates (SYNTHETIC)",
    "water_regime": "MIXED",
    "soil_ph_min": 5.5,
    "soil_ph_max": 7.5,
    "geographic_scope": "GLOBAL",
    "climate_classes": ["Cfa", "Dfa", "Aw"],
}

MEDITERRANEAN_PROFILE = {
    "soil": [
        {"property": "CLAY", "value": 28, "unit": "%", "depth_top_cm": 0, "depth_bottom_cm": 30,
         "origin": "LOCAL_MEASUREMENT", "method": "SYNTHETIC pipette method", "sampled_on": "2022-03-01"},
        {"property": "SILT", "value": 32, "unit": "%", "depth_top_cm": 0, "depth_bottom_cm": 30,
         "origin": "LOCAL_MEASUREMENT", "method": "SYNTHETIC pipette method", "sampled_on": "2022-03-01"},
        {"property": "SAND", "value": 40, "unit": "%", "depth_top_cm": 0, "depth_bottom_cm": 30,
         "origin": "LOCAL_MEASUREMENT", "method": "SYNTHETIC pipette method", "sampled_on": "2022-03-01"},
        {"property": "PH", "value": 8.2, "unit": "pH", "depth_top_cm": 0, "depth_bottom_cm": 30,
         "origin": "LOCAL_MEASUREMENT", "method": "SYNTHETIC 1:2.5 water", "sampled_on": "2022-03-01"},
    ],
    "crop_history": [
        {"crop_code": "wheat_durum", "crop_label": "Durum wheat", "season_year": 2021, "water_regime": "RAINFED"},
        {"crop_code": "chickpea", "crop_label": "Chickpea", "season_year": 2022, "water_regime": "RAINFED"},
    ],
    "constraints": {"water_regime": "RAINFED"},
}
MEDITERRANEAN_COUNTRY = "ES"
MEDITERRANEAN_CLIMATE = "Csa"

#: Expected per-dimension statuses for the example above.
LIMITED_TRANSFER_EXPECTED = {
    "CROPS": "MISMATCH",
    "WATER_REGIME": "PARTIAL",
    "SOIL_TEXTURE": "UNKNOWN",
    "SOIL_PH": "MISMATCH",
    "REGION": "PARTIAL",
    "CLIMATE": "MISMATCH",
}

FORBIDDEN_NUMERIC_KEYS = ("score", "probability", "confidence", "weight", "percent")


def numeric_score_keys(value, path="$") -> list[str]:
    """Paths of any key that looks like a numeric applicability score (must stay empty)."""
    found = []
    if isinstance(value, dict):
        for key, item in value.items():
            if any(word in key.lower() for word in FORBIDDEN_NUMERIC_KEYS):
                found.append(f"{path}.{key}")
            found += numeric_score_keys(item, f"{path}.{key}")
    elif isinstance(value, list):
        for i, item in enumerate(value):
            found += numeric_score_keys(item, f"{path}[{i}]")
    return found
