"""Initial crop catalogue (ABB-11) — taxonomy only, no agronomic parameters.

Policy (docs/science/FARM_PROFILE.md):
- Entries carry identity data only: code, EN/ES common names, scientific name, botanical
  family and a coarse crop group. Legume status is derived from the family (Fabaceae).
- No sowing windows, crop coefficients, water demand, yields or nitrogen figures are
  included. Those vary by cultivar, climate and management and must come from the
  farmer's local calendar or a separately reviewed source.
- Every entry starts as ``PENDING`` review: a person must confirm it against a taxonomic
  authority before the catalogue is described as reviewed.
"""
from __future__ import annotations

import unicodedata
from typing import Literal

from pydantic import Field as PydanticField

from .schemas import ReviewStatus, VersionedContract

CATALOG_VERSION = 'crop-catalog-0.1.0'
LEGUME_FAMILY = 'Fabaceae'

CropGroup = Literal['CEREAL', 'GRAIN_LEGUME', 'FORAGE_LEGUME', 'OILSEED', 'ROOT_TUBER', 'INDUSTRIAL', 'VEGETABLE']

CATALOG_SOURCES = [
    'Scientific names and botanical families follow standard botanical nomenclature; '
    'pending reviewer confirmation against a taxonomic authority (e.g. GBIF or POWO).',
]
CATALOG_LIMITATIONS = [
    'Identity data only: no sowing windows, crop coefficients, water demand, yield or nitrogen values.',
    'Crop group is a coarse planning label, not an agronomic classification of every cultivar or use.',
    'Entries are pending human review; do not cite this catalogue as a reviewed source yet.',
]


class CropCatalogEntry(VersionedContract):
    code: str = PydanticField(pattern=r'^[a-z][a-z0-9_]{1,40}$')
    common_name_en: str = PydanticField(min_length=1, max_length=80)
    common_name_es: str = PydanticField(min_length=1, max_length=80)
    scientific_name: str = PydanticField(min_length=3, max_length=120)
    botanical_family: str = PydanticField(min_length=3, max_length=80)
    crop_group: CropGroup
    is_legume: bool
    review_status: ReviewStatus = ReviewStatus.PENDING
    agronomic_parameters: None = None
    sources: list[str] = PydanticField(min_length=1)
    limitations: list[str] = PydanticField(min_length=1)


class CropCatalog(VersionedContract):
    catalog_version: str
    entries: list[CropCatalogEntry]
    sources: list[str]
    limitations: list[str]


# code, English, Spanish, scientific name, family, group
_RAW: list[tuple[str, str, str, str, str, CropGroup]] = [
    ('wheat_soft', 'Common wheat', 'Trigo blando', 'Triticum aestivum', 'Poaceae', 'CEREAL'),
    ('wheat_durum', 'Durum wheat', 'Trigo duro', 'Triticum durum', 'Poaceae', 'CEREAL'),
    ('barley', 'Barley', 'Cebada', 'Hordeum vulgare', 'Poaceae', 'CEREAL'),
    ('oats', 'Oats', 'Avena', 'Avena sativa', 'Poaceae', 'CEREAL'),
    ('maize', 'Maize', 'Maíz', 'Zea mays', 'Poaceae', 'CEREAL'),
    ('rice', 'Rice', 'Arroz', 'Oryza sativa', 'Poaceae', 'CEREAL'),
    ('sorghum', 'Sorghum', 'Sorgo', 'Sorghum bicolor', 'Poaceae', 'CEREAL'),
    ('chickpea', 'Chickpea', 'Garbanzo', 'Cicer arietinum', 'Fabaceae', 'GRAIN_LEGUME'),
    ('lentil', 'Lentil', 'Lenteja', 'Lens culinaris', 'Fabaceae', 'GRAIN_LEGUME'),
    ('pea', 'Pea', 'Guisante', 'Pisum sativum', 'Fabaceae', 'GRAIN_LEGUME'),
    ('faba_bean', 'Faba bean', 'Haba', 'Vicia faba', 'Fabaceae', 'GRAIN_LEGUME'),
    ('soybean', 'Soybean', 'Soja', 'Glycine max', 'Fabaceae', 'GRAIN_LEGUME'),
    ('common_bean', 'Common bean', 'Judía', 'Phaseolus vulgaris', 'Fabaceae', 'GRAIN_LEGUME'),
    ('alfalfa', 'Alfalfa', 'Alfalfa', 'Medicago sativa', 'Fabaceae', 'FORAGE_LEGUME'),
    ('common_vetch', 'Common vetch', 'Veza', 'Vicia sativa', 'Fabaceae', 'FORAGE_LEGUME'),
    ('sunflower', 'Sunflower', 'Girasol', 'Helianthus annuus', 'Asteraceae', 'OILSEED'),
    ('rapeseed', 'Rapeseed', 'Colza', 'Brassica napus', 'Brassicaceae', 'OILSEED'),
    ('sugar_beet', 'Sugar beet', 'Remolacha azucarera', 'Beta vulgaris', 'Amaranthaceae', 'INDUSTRIAL'),
    ('potato', 'Potato', 'Patata', 'Solanum tuberosum', 'Solanaceae', 'ROOT_TUBER'),
    ('tomato', 'Tomato', 'Tomate', 'Solanum lycopersicum', 'Solanaceae', 'VEGETABLE'),
    ('cotton', 'Cotton', 'Algodón', 'Gossypium hirsutum', 'Malvaceae', 'INDUSTRIAL'),
]

ENTRIES: dict[str, CropCatalogEntry] = {
    code: CropCatalogEntry(
        code=code, common_name_en=en, common_name_es=es, scientific_name=sci,
        botanical_family=family, crop_group=group, is_legume=family == LEGUME_FAMILY,
        sources=list(CATALOG_SOURCES), limitations=list(CATALOG_LIMITATIONS),
    )
    for code, en, es, sci, family, group in _RAW
}


def _key(text: str) -> str:
    folded = unicodedata.normalize('NFKD', text).casefold()
    return ' '.join(''.join(c for c in folded if not unicodedata.combining(c)).replace('_', ' ').split())


_ALIASES: dict[str, str] = {}
for _entry in ENTRIES.values():
    for _name in (_entry.code, _entry.common_name_en, _entry.common_name_es, _entry.scientific_name):
        _ALIASES[_key(_name)] = _entry.code


def resolve_crop(code_or_name: str | None) -> CropCatalogEntry | None:
    """Exact (accent/case-insensitive) match on code, EN/ES name or scientific name. No fuzzy guessing."""
    if not code_or_name:
        return None
    code = _ALIASES.get(_key(code_or_name))
    return ENTRIES.get(code) if code else None


def catalog() -> CropCatalog:
    return CropCatalog(catalog_version=CATALOG_VERSION, entries=list(ENTRIES.values()),
                       sources=list(CATALOG_SOURCES), limitations=list(CATALOG_LIMITATIONS))
