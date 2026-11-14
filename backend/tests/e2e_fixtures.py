"""ABB-29 explicit SYNTHETIC fixtures for the end-to-end journey.

Everything here is invented for tests: people, parcel, coordinates, notes, the NASA POWER payload (built by
``test_api_timeline_hypotheses.power_payload``), the OpenAlex/Crossref replies (``evidence_fakes``) and the farmer
profile. Nothing here is, or may be presented as, a real observation, a real farm or a real result. Tests that
touch the real services live in ``test_real_sources_smoke.py`` and never run in CI.

``SYNTHETIC_LABEL`` is in every title/label so a leaked fixture is recognisable in any report or screenshot.
"""
from __future__ import annotations

FIXTURE_KIND = "SYNTHETIC"
SYNTHETIC_LABEL = "SYNTHETIC"
PASSWORD = "synthetic-correct-horse-42"
V1 = "/api/v1"

# Private data that must never reach a report, a reviewer response or a shared view.
PRIVATE_NOTE = "SYNTHETIC private note: neighbour Ana Example, phone 000-111."
OWNER = ("e2e-owner@example.test", "SYNTHETIC owner")
REVIEWER = ("e2e-reviewer@example.test", "SYNTHETIC reviewer")
VIEWER = ("e2e-viewer@example.test", "SYNTHETIC viewer")
STRANGER = ("e2e-stranger@example.test", "SYNTHETIC stranger")


def case_body(lat: float, lon: float) -> dict:
    return {
        "title": f"{SYNTHETIC_LABEL} case - not a real incident",
        "incident_start": "2022-05-01", "incident_end": "2022-08-31",
        "crop_history": ["wheat", "barley"], "incident_notes": PRIVATE_NOTE,
        "fields": [{"label": f"{SYNTHETIC_LABEL} parcel A", "privacy_tier": "APPROXIMATE", "latitude": lat,
                    "longitude": lon, "region_label": f"{SYNTHETIC_LABEL} region", "rounding_deg": 0.5,
                    "limitations": [f"{SYNTHETIC_LABEL} test parcel; not a real farm"]}],
    }


CLAIM_TEXT = f"{SYNTHETIC_LABEL}: legume pre-crops were associated with higher main-crop yield in pooled trials."
HYPOTHESIS_LIMITATION = f"{SYNTHETIC_LABEL} hypothesis: compatibility in time only."
CONCLUSION_TEXT = (f"{SYNTHETIC_LABEL}: June precipitation far below the reference is consistent with a water "
                   "deficit; not demonstrated as the cause.")
