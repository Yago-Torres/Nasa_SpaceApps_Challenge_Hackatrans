# Synthetic ABB-31/ABB-32 demo

This fixture is for a competition demonstration only. It proves the product flow and
privacy controls; it does **not** prove a real pilot or genuine external collaboration.
Every record created by the script is labelled `SYNTHETIC`, uses an `example.invalid`
address and contains no NASA observations or measured harvest result.

## Persistence and accounts

The project uses PostgreSQL 17, not SQLite. The local Compose stack starts it on
`127.0.0.1:5432`; the API requires `DATABASE_URL` and Alembic creates the account,
session, case, field, permission, invitation and comment tables. Registration and login
are real API flows, so the demo exercises the same persistence boundary as production.

Start the local stack and API:

```bash
docker compose up -d db
cd backend
DATABASE_URL=postgresql+psycopg://agro:local_dev_only@127.0.0.1:5432/agroblackbox uv run alembic upgrade head
DATABASE_URL=postgresql+psycopg://agro:local_dev_only@127.0.0.1:5432/agroblackbox uv run uvicorn agroblackbox.app:app --port 8000
```

In another terminal, seed the demo:

```bash
uv run --no-project python scripts/seed_demo_cases.py --base-url http://127.0.0.1:8000 --run-id abb-demo
```

The output contains the synthetic owner/reviewer credentials and the case URL. Open the
URL in the web app, sign in as the owner, then sign in as the reviewer in a separate
browser profile to show the invitation, approximate/region-only locations and the two
plain-text comments.

To reset only this demo, use the account deletion screen/API for both synthetic accounts
or recreate the local PostgreSQL volume. Never run this seed against a production database.

## What to say during the demo

- ABB-31: “This is a synthetic local pilot rehearsal. The reviewer feedback changes the
  stated limitation; it is not evidence of yield, savings or a measured farm outcome.”
- ABB-32: “This is a synthetic international-exchange rehearsal. The second account is
  not a real person, so this cannot close the genuine-collaboration acceptance gate.”
