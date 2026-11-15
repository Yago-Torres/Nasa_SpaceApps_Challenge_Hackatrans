#!/usr/bin/env python3
"""Reset the known demo accounts and seed a small realistic-looking collection.

All names, addresses and cases are fictional. The ``example.invalid`` domain and the
``— Synthetic`` suffix are intentional and must remain visible in screenshots.
"""
from __future__ import annotations

import argparse
import json
from typing import Any

import httpx

from seed_demo_cases import PASSWORD, account, check

OLD_EMAILS = (
    "synthetic.owner.abb-demo@example.invalid",
    "synthetic.reviewer.abb-demo@example.invalid",
)
OWNER_EMAIL = "lucia.martin.abb-demo@example.invalid"
REVIEWER_EMAIL = "marek.nowak.abb-demo@example.invalid"
OWNER_NAME = "Lucía Martín (Synthetic)"
REVIEWER_NAME = "Marek Nowak (Synthetic)"

CASES = [
    {
        "title": "Amarilleo del trigo de secano — Synthetic",
        "start": "2022-05-01", "end": "2022-07-31",
        "crops": ["2020: trigo duro", "2021: garbanzo", "2022: trigo duro"],
        "symptoms": "Amarilleo irregular y pérdida de vigor tras una primavera seca.",
        "share": "35",
    },
    {
        "title": "Nascencia desigual después de lluvias intensas — Synthetic",
        "start": "2023-03-01", "end": "2023-05-31",
        "crops": ["2021: cebada", "2022: girasol", "2023: cebada"],
        "symptoms": "Nascencia desigual y rodales con suelo encharcado después de varios episodios de lluvia.",
        "share": "20",
    },
    {
        "title": "Comparación trigo-garbanzo en una rotación de secano — Synthetic",
        "start": "2021-04-01", "end": "2021-06-30",
        "crops": ["2019: trigo duro", "2020: barbecho", "2021: garbanzo"],
        "symptoms": "Diferencias de cobertura y vigor entre dos campañas de secano.",
        "share": "15",
    },
]


def delete_account(client: httpx.Client, email: str) -> None:
    login = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    if login.status_code != 200:
        return
    token = login.json()["access_token"]
    response = client.post("/api/v1/account/delete", headers={"Authorization": f"Bearer {token}"}, json={"password": PASSWORD})
    # The account endpoint returns a JSON deletion summary (200); older builds
    # returned an empty 204, so accept both while keeping the reset idempotent.
    check(response, {200, 204}, f"delete demo account {email}")


def payload(spec: dict[str, str | list[str]]) -> dict[str, Any]:
    crops = spec["crops"]
    block = {
        "v": 1, "incidentYear": str(spec["start"])[:4], "symptomsStart": str(spec["start"])[:7],
        "symptomsEnd": str(spec["end"])[:7], "affectedShare": spec["share"],
        "constraints": {"water": "rainfed", "soilKnown": True,
                        "soilNotes": "Textura franca arcillosa; medición sintética de demostración.",
                        "priorities": "Reducir el riesgo de estrés hídrico y mantener una cosecha manejable."},
        "crops": [{"year": item[:4], "crop": item[6:], "notes": "Dato sintético de demo"} for item in crops],
    }
    return {
        "title": spec["title"], "incident_start": spec["start"], "incident_end": spec["end"],
        "crop_history": crops,
        "incident_notes": f"{spec['symptoms']} Caso sintético para la demostración; no es una explotación real.\n\n"
                          "--- AGRO BLACK BOX wizard answers v1 (structured; edit them in the wizard) ---\n"
                          + json.dumps(block, ensure_ascii=False),
        "fields": [{
            "label": "Parcela principal (Synthetic)", "privacy_tier": "APPROXIMATE", "latitude": 41.65,
            "longitude": -0.88, "region_label": "Valle del Ebro (Synthetic)", "rounding_deg": 0.5,
            "limitations": ["Caso sintético; no representa una explotación real"],
        }],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--reset", action="store_true", help="Delete the two old and two replacement demo accounts first.")
    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=30.0) as client:
        if args.reset:
            for email in (*OLD_EMAILS, OWNER_EMAIL, REVIEWER_EMAIL):
                delete_account(client, email)
        owner = account(client, OWNER_EMAIL, OWNER_NAME)
        reviewer = account(client, REVIEWER_EMAIL, REVIEWER_NAME)
        owner_headers = {"Authorization": f"Bearer {owner['token']}"}
        reviewer_headers = {"Authorization": f"Bearer {reviewer['token']}"}
        created: list[dict[str, Any]] = []
        for spec in CASES:
            case = check(client.post("/api/v1/cases", headers=owner_headers, json=payload(spec)), {201}, "create demo case")
            invitation = check(client.post(f"/api/v1/cases/{case['id']}/invitations", headers=owner_headers, json={
                "email": REVIEWER_EMAIL, "role": "REVIEWER", "note": "Revisión sintética del caso y de sus limitaciones.", "expires_in_days": 7,
            }), {201}, "invite demo reviewer")
            check(client.post(f"/api/v1/invitations/{invitation['id']}/accept", headers=reviewer_headers), {200}, "accept demo invitation")
            check(client.post(f"/api/v1/cases/{case['id']}/comments", headers=reviewer_headers, json={
                "body": "Comentario de revisión (Synthetic): separar la señal climática de cualquier afirmación sobre rendimiento medido.",
            }), {201}, "add reviewer feedback")
            evidence: dict[str, Any] | None = None
            imported = client.post(f"/api/v1/cases/{case['id']}/claims/pilot-import", headers=owner_headers)
            evidence = imported.json() if imported.status_code == 200 else {
                "status": "unavailable", "detail": imported.text[:300]
            }
            created.append({"id": case["id"], "title": case["title"], "evidence": evidence})
        print(json.dumps({"synthetic": True, "owner_email": OWNER_EMAIL, "reviewer_email": REVIEWER_EMAIL,
                          "password": PASSWORD, "cases": created,
                          "warning": "Fictional demo data; not a real pilot or collaboration."}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
