#!/usr/bin/env python3
"""Create the synthetic ABB-31/ABB-32 demo journey through the public API.

This script is deliberately not a production seed. Every account, parcel, note and
comment is invented, uses ``example.invalid`` and is labelled SYNTHETIC. It must not
be used as evidence of a real farmer, pilot or international collaboration.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from typing import Any

import httpx


PASSWORD = os.getenv("CROPSTORY_DEMO_PASSWORD", "synthetic-demo-correct-horse-42")
TITLE = "SYNTHETIC DEMO — ABB-31 local pilot / ABB-32 exchange"
NOTES_MARKER = "--- AGRO BLACK BOX wizard answers v1 (structured; edit them in the wizard) ---"


def email_for(role: str, run_id: str) -> str:
    safe = re.sub(r"[^a-z0-9-]+", "-", run_id.lower()).strip("-") or "demo"
    return f"synthetic.{role}.{safe}@example.invalid"


def check(response: httpx.Response, expected: set[int], action: str) -> dict[str, Any]:
    if response.status_code not in expected:
        raise RuntimeError(f"{action}: HTTP {response.status_code}: {response.text[:500]}")
    return response.json() if response.content else {}


def account(client: httpx.Client, email: str, display_name: str) -> dict[str, Any]:
    registered = client.post("/api/v1/auth/register", json={
        "email": email, "password": PASSWORD, "display_name": display_name,
    })
    if registered.status_code not in {201, 409}:
        check(registered, {201}, f"register {email}")
    login = check(client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}), {200}, f"login {email}")
    return {"email": email, "display_name": display_name, "token": login["access_token"]}


def case_payload() -> dict[str, Any]:
    """Plausible Spanish agronomy inputs, still explicitly synthetic."""
    block = {
        "v": 1, "incidentYear": "2022", "symptomsStart": "2022-05", "symptomsEnd": "2022-07",
        "affectedShare": "35", "constraints": {
            "water": "rainfed", "soilKnown": True,
            "soilNotes": "Textura franca arcillosa; pH 8,1. Medición sintética de demostración.",
            "priorities": "Reducir el riesgo de estrés hídrico y mantener una ventana de cosecha manejable.",
        },
        "crops": [
            {"year": "2020", "crop": "trigo duro", "notes": "Siembra otoñal"},
            {"year": "2021", "crop": "garbanzo", "notes": "Sin riego"},
            {"year": "2022", "crop": "trigo duro", "notes": "Síntomas al final de primavera"},
        ],
    }
    return {
        "title": TITLE,
        "incident_start": "2022-05-01", "incident_end": "2022-07-31",
        "crop_history": ["2020: trigo duro", "2021: garbanzo", "2022: trigo duro"],
        "incident_notes": "Amarilleo irregular y pérdida de vigor en una primavera seca; fixture sintético para la demo.\n\n"
                          + NOTES_MARKER + "\n" + json.dumps(block, ensure_ascii=False),
        "fields": [
            {"label": "Parcela norte (sintética)", "privacy_tier": "APPROXIMATE", "latitude": 41.65,
             "longitude": -0.88, "region_label": "Valle del Ebro (sintético)", "rounding_deg": 0.5,
             "limitations": ["Caso sintético; no representa una explotación real"]},
            {"label": "Parcela de comparación (sintética)", "privacy_tier": "REGION_ONLY", "latitude": 41.75,
             "longitude": -0.65, "region_label": "Comarca de comparación (sintética)",
             "limitations": ["Sin observaciones asociadas; solo comparación de interfaz"]},
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.getenv("CROPSTORY_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--run-id", default="demo", help="Stable suffix so rerunning the demo reuses its accounts.")
    args = parser.parse_args()

    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=20.0) as client:
        owner = account(client, email_for("owner", args.run_id), "SYNTHETIC local pilot owner")
        external = account(client, email_for("reviewer", args.run_id), "SYNTHETIC external reviewer")
        owner_headers = {"Authorization": f"Bearer {owner['token']}"}
        external_headers = {"Authorization": f"Bearer {external['token']}"}

        cases = check(client.get("/api/v1/cases", headers=owner_headers), {200}, "list owner cases")["items"]
        case = next((item for item in cases if item["title"] == TITLE), None)
        payload = case_payload()
        if case is None:
            case = check(client.post("/api/v1/cases", headers=owner_headers, json=payload), {201}, "create synthetic case")
        else:
            case = check(client.patch(f"/api/v1/cases/{case['id']}", headers=owner_headers, json={
                "version": case["version"], **{key: payload[key] for key in ("title", "incident_start", "incident_end", "crop_history", "incident_notes")},
            }), {200}, "refresh synthetic case")
            version = case["version"]
            for index, field in enumerate(payload["fields"]):
                if index < len(case["fields"]):
                    case = check(client.patch(f"/api/v1/cases/{case['id']}/fields/{case['fields'][index]['id']}", headers=owner_headers,
                                               json={"version": version, **field}), {200}, "refresh synthetic field")
                    version = case["version"]
                else:
                    case = check(client.post(f"/api/v1/cases/{case['id']}/fields", headers=owner_headers,
                                              json={"version": version, "field": field}), {201}, "add synthetic field")
                    version = case["version"]

        invitations = check(client.get(f"/api/v1/cases/{case['id']}/invitations", headers=owner_headers), {200}, "list invitations")["items"]
        invitation = next((item for item in invitations if item["email"] == external["email"] and item["status"] == "PENDING"), None)
        if invitation is None and not any(item["email"] == external["email"] and item["status"] == "ACCEPTED" for item in invitations):
            invitation = check(client.post(f"/api/v1/cases/{case['id']}/invitations", headers=owner_headers, json={
                "email": external["email"], "role": "REVIEWER", "note": "SYNTHETIC demo exchange: review the stated limits, not a real result.", "expires_in_days": 7,
            }), {201}, "invite synthetic reviewer")
        if invitation:
            check(client.post(f"/api/v1/invitations/{invitation['id']}/accept", headers=external_headers), {200, 404}, "accept synthetic invitation")

        evidence_status = "not attempted"
        imported = client.post(f"/api/v1/cases/{case['id']}/claims/pilot-import", headers=owner_headers)
        if imported.status_code == 200:
            evidence_status = imported.json()
        else:
            evidence_status = {"status": "unavailable", "detail": imported.text[:300]}

        comments = check(client.get(f"/api/v1/cases/{case['id']}/comments", headers=owner_headers), {200}, "list comments")["items"]
        feedback = "Comentario sintético de la revisora externa: conviene separar el déficit hídrico observado de cualquier afirmación sobre rendimiento medido y declarar la limitación de no tener una medición local."
        if not any(item["body"] == feedback for item in comments):
            check(client.post(f"/api/v1/cases/{case['id']}/comments", headers=external_headers, json={"body": feedback}), {201}, "write synthetic feedback")
        owner_note = "Respuesta sintética de la propietaria: se incorpora la limitación y no se presenta ningún resultado agronómico como medido."
        if not any(item["body"] == owner_note for item in comments):
            check(client.post(f"/api/v1/cases/{case['id']}/comments", headers=owner_headers, json={"body": owner_note}), {201}, "write synthetic response")

        print(json.dumps({
            "synthetic": True,
            "warning": "Demo fixtures are not real people, farms, observations or collaboration evidence.",
            "base_url": args.base_url.rstrip("/"),
            "case_id": case["id"],
            "case_title": case["title"],
            "owner_email": owner["email"],
            "reviewer_email": external["email"],
            "password": PASSWORD,
            "case_url": f"{args.base_url.rstrip('/')}/#/cases/{case['id']}",
            "evidence": evidence_status,
        }, indent=2))


if __name__ == "__main__":
    main()
