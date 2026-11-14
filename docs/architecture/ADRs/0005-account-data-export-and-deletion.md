# ADR-0005 — Account data export and deletion (data minimisation and retention)

- Status: accepted for ABB-28 (2026-11-14).
- Date: 2026-11-14
- Related GitHub Issues: ABB-28 / #28 (security, privacy and data operations); context ABB-05 / #5, ABB-06 / #6 (ADR-0004), ABB-14/15/16/19 (append-only review history)
- Reviewers / coordination notes: implemented by the agent acting for C on the user's instruction. Depends on ADR-0004's session/permission model, which this ADR extends rather than changes. A human privacy/security review is still required before this is relied on for a real deployment.

## Context

ABB-28's acceptance criteria require that "a user can export and request to delete their data according to a defined policy," and ADR-0004 explicitly left this open: *"Deleting a case ... is the privacy-erasure path pending the retention policy of ABB-28."* The product has no admin role and no support-ticket workflow, so the policy must be self-service and enforced by the API itself.

The data model (`backend/agroblackbox/db/models.py`) already encodes a retention decision for most tables: a user's own authored content is reachable from a case via `ON DELETE CASCADE` on `case_id`, so deleting a case already erases everything scoped to it (fields, permissions, history, observations, anomalies, source manifests, hypotheses, evidence claims and their review events, claim disagreement reviews, uncertainty answers and question events, evidence graph conclusions and edges, rotations, reviews and reports). But several tables reference the *acting user* directly with `ON DELETE RESTRICT`, by explicit design: `evidence_claims.created_by`, `evidence_claim_events.actor_id`, `claim_disagreement_reviews.reviewer_id`, `uncertainty_answers.answered_by`/`reviewed_by`, `evidence_conclusions.reviewed_by`, `evidence_graph_edges.reviewed_by`, `reviews.reviewer_id`. The comment on `EvidenceClaimEvent.actor_id` states the reason directly: *"The actor FK is RESTRICT so the reviewer is never lost."* `cases.owner_id` is also `RESTRICT`. These constraints protect **other users'** shared case evidence trails, which are append-only and reviewed by people other than their author — a hard delete of a `users` row would either raise an `IntegrityError` (if the user ever authored or reviewed anything on a case they do not own) or require deleting records on cases that belong to someone else, which is not the deleting user's data to erase.

## Options considered

1. **Hard delete the `users` row and cascade everywhere.** Rejected: would require changing several `RESTRICT` foreign keys to `CASCADE`/`SET NULL` on shared evidence/review tables, which the roadmap Issue explicitly says not to weaken, and would let one user's deletion silently remove or orphan another case owner's reviewed evidence, contradicting the append-only audit design of ABB-14/15/16/19.
2. **Soft-delete flag only (`deleted_at` column, data kept, login blocked).** Rejected as the sole mechanism: it satisfies "stop processing" but not "erase," and the acceptance criterion says the user can request their data be *deleted*, not merely flagged.
3. **Hybrid: hard-delete everything the user owns, revoke everything they can merely see, anonymise the identity record that other users' evidence still legitimately references.** Selected.

## Decision

`GET /api/v1/account/export` and `POST /api/v1/account/delete` (`backend/agroblackbox/api/account.py`) implement:

- **Export** returns the account's profile, every case it is a member of — rendered through the same `_case_view`/`visible_location` redaction already used by `GET /api/v1/cases`, so a reviewer's export shows exactly what that reviewer already sees and nothing more — and this account's own session metadata (`id`, `created_at`, `expires_at`, `revoked`, `current`), never a raw token or its digest. This is read-only and carries no destructive side effect.
- **Deletion** requires re-entering the current password in the request body even though the caller already holds a valid bearer token, as a confirmation step before an irreversible action; a wrong password uses the same per-account lockout as `/auth/login` (`MAX_FAILED_LOGINS`/`LOCKOUT_DURATION` from `agroblackbox.security`, reusing `users.failed_login_count`/`locked_until` — no new column), so a stolen short-lived token cannot be used to brute-force the confirmation. On success it:
  1. deletes every case the account **owns**, which cascades (existing `ON DELETE CASCADE` on `case_id`) through fields, permissions, history and every case-scoped scientific/review record, exactly as `DELETE /api/v1/cases/{id}` already does for a single case;
  2. deletes the account's remaining `CasePermission` rows (membership on cases owned by someone else — anything on an owned case is already gone from step 1);
  3. revokes every session belonging to the account (`revoked_at = now`), including the one used for the request itself;
  4. **anonymises** the `users` row in place: `email` becomes a unique `deleted-<uuid>@deleted.invalid` placeholder (freeing the real address for reuse), `display_name` becomes `"Deleted account"`, `password_hash` is set to `NULL` (the existing "cannot log in" sentinel from ABB-05), and the lockout counters are reset. The row is **not** deleted, so every `RESTRICT` reference from another user's case evidence (steps above) stays valid; nothing about who reviewed or authored that evidence is lost, but it no longer carries the deleted person's real identity.

The response (`AccountDeletionReceipt`) states exactly what happened — counts of cases deleted, memberships revoked and sessions revoked — rather than a bare "deleted," consistent with the project's scientific/privacy honesty policy (do not overstate what a change actually did).

Session retention: `agroblackbox/retention.py` adds `purge_stale_sessions`, a maintenance function (not an HTTP endpoint — there is no admin role to gate one, and exposing session deletion to any authenticated user would be its own privilege question) that deletes `sessions` rows expired or revoked more than 30 days ago. It is invoked manually or by a future scheduled job; it is not wired to a scheduler yet, since no job runner is deployed (see the Redis row in `docs/operations/CURRENT_STATE.md`).

## Tradeoffs and consequences

- "Delete my account" does **not** mean every row that ever mentioned the user disappears from the database; it means every case the user owns is gone, every access the user held elsewhere is revoked, and the user's own identifying fields are scrubbed from whatever shared records remain. This is a real difference from a naive reading of "right to erasure" and must be stated to users in the product's privacy notice (`docs/operations/LEGAL_AND_DATA_POLICY.md`), not left implicit.
- A `RESTRICT`-referencing row that is never anonymised (e.g. a user who is only ever an `OWNER`) still goes through the same code path; the anonymisation step is unconditional and idempotent, so it does not need to special-case which FKs apply to a given account.
- Re-registration with the same e-mail works immediately after deletion (the address is freed), which means a new account cannot be distinguished from "the same person signed up again" at the database level; this is accepted because no identity-continuity guarantee is promised anywhere in the product.
- The password-confirmation lockout shares `failed_login_count`/`locked_until` with the login endpoint: five wrong attempts on either locks both for 15 minutes. This is intentional (one brute-force budget per account) and is covered by a test.
- Session purge has no retention exception for legal hold or active investigation; a future Issue may need one if that becomes relevant.
- This ADR does not add e-mail verification, password reset, invitation acceptance or IP-based rate limiting; those remain open (ADR-0004, `docs/operations/CURRENT_STATE.md`).

## Rollout / rollback

No migration: both endpoints use existing tables and existing columns (`users.password_hash`/`failed_login_count`/`locked_until`, which already encode "disabled, cannot log in"). Rollback is removing the two routes from `api/__init__.py#include_api_v1` and deleting `api/account.py`/`retention.py`; no data format changes to revert.
