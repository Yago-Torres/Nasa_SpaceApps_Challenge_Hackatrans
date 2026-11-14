# Collaboration: invitations, comments, activity and consented share links (ABB-25)

Status: **API and web UI implemented and tested** (case tabs Collaborators and Discussion, the Collaboration page for received invitations and the public `#/shared/<token>` view). Migration `a7c2e9d4b158` (after `a19f3b7c2d64`). Authentication, roles, the 404/403 rules and location redaction come from ADR-0004 and are not changed here.

## Model

| Concept | Storage | Audit |
|---|---|---|
| Invitation (e-mail + role + note + expiry) | `case_invitations` | `case_history` actions `INVITATION_CREATED`, `INVITATION_ACCEPTED`, `INVITATION_DECLINED`, `INVITATION_REVOKED` (no e-mail address) |
| Comment / reply | `case_comments` (tombstone on delete) | the row itself (author, `created_at`, `edited_at`, `deleted_at`, `deleted_by`) |
| Comment edit history | `case_comment_revisions` (replaced text, editor, instant) | itself |
| Share link (consent + sections) | `case_share_links` (SHA-256 of the token only) | `case_history` actions `SHARE_LINK_CREATED`, `SHARE_LINK_REVOKED` |
| Activity feed | **not stored**: computed on read from `case_history`, `evidence_claim_events`, `claim_disagreement_reviews`, `case_comments`, `case_comment_revisions` | — |

Invitation, permission and share-link changes do not bump the case `version` (as ABB-06 already did for permissions), so collaboration never conflicts with concurrent editors. Deleting a case erases all of these rows.

## Roles

| Action | OWNER | EDITOR | REVIEWER | VIEWER | Non-member | No session |
|---|---|---|---|---|---|---|
| Create / list / revoke invitations | yes | 403 | 403 | 403 | 404 | 401 |
| See pending invitations addressed to my e-mail; accept / decline | any signed-in account whose e-mail matches | | | | | 401 |
| Post comments and replies (any status; not on archived cases) | yes | yes | yes | yes | 404 | 401 |
| Edit a comment | author only (403 otherwise) | | | | 404 | 401 |
| Delete a comment (tombstone) | author, or OWNER as moderator | author | author | author | 404 | 401 |
| Read comments, revisions, activity feed | yes | yes | yes | yes | 404 | 401 |
| Create / list / revoke share links | yes | 403 | 403 | 403 | 404 | 401 |
| Read a shared view | anyone holding an active token, no account | | | | | |

Decision: **VIEWER may comment.** The Issue requires that "un invitado puede comentar"; comments do not change case content or scientific records, so read-only members can raise objections without being able to edit or review. Reviews (claims, conclusions, edges, hypothesis evaluation, REVIEWED status) keep their ABB-06/14/16 roles.

## Invitations

- The owner invites an e-mail address with role EDITOR, REVIEWER or VIEWER, an optional note (≤ 500 characters, plain text) and an expiry of 1–30 days (default 14).
- **No account enumeration:** the response (201, same fields) and the history entry are identical whether or not an account exists for that e-mail; no user lookup happens at creation. The only 409s are "that is your own e-mail", "already a member" (information the owner already has from the member list) and "a pending invitation for that e-mail exists".
- No e-mail is sent and no token exists. The invitee signs in (or registers) with the invited address and sees the invitation in `GET /api/v1/invitations` (case title, role, note, inviter display name, expiry — never coordinates or e-mails). Accepting creates the `case_permissions` row immediately and updates `visibility`; declining leaves no access.
- Anything that is not a pending, unexpired invitation addressed to the caller's e-mail returns the same 404 to the invitee (other people's invitations, answered, revoked, expired, nonexistent).
- `EXPIRED` is derived from `expires_at` on read; expired pending rows are marked `EXPIRED` when the same e-mail is invited again. Only `PENDING` invitations can be revoked (409 otherwise); revocation is effective on the invitee's next request.
- The direct grant `POST /cases/{id}/permissions` (existing account, immediate) still works.

**Limitation:** ABB-05 has no e-mail verification. Whoever registers an address first receives the invitations sent to it. Until verification exists (ABB-28) owners should only invite addresses whose holder they have confirmed out of band, and the UI should say so.

## Comments

- Plain text, 1–4000 characters after cleaning. Cleaning: Unicode NFC, `\r\n`/`\r` → `\n`, removal of C0/C1 control characters except tab and newline, zero-width space, LRM/RLM, bidirectional embeddings/overrides/isolates and BOM (Trojan-source style reordering), and outer whitespace. ZWJ/ZWNJ are kept. **Nothing else is altered:** `<`, `>`, `&` and quotes are stored and returned verbatim.
- The API never renders or interprets comment text. Responses are `application/json` and carry `body_format: "text/plain"`. **Clients must render bodies as text nodes (React default escaping), never with `innerHTML`/`dangerouslySetInnerHTML` or a Markdown renderer.** This is the XSS boundary.
- Targets: `CASE` (no id) or a record of the same case — `FIELD`, `OBSERVATION`, `ANOMALY`, `HYPOTHESIS`, `CLAIM`, `CONCLUSION`, `GRAPH_EDGE`, `TIMELINE_EVENT` (derived timeline event id). A target from another case or a nonexistent one is rejected with 422. A comment keeps its target id if the record is deleted later (comments do not block deletion).
- Replies: one level deep; a reply inherits its parent's target and cannot be posted to a deleted comment (409).
- Editing requires the current comment `version` (409 if stale) and keeps the replaced text as a numbered revision readable by every member (`GET …/revisions`).
- Deletion is a tombstone: `deleted: true`, `body: null`, `revision_count: 0`; revisions answer 410. The text and revisions **stay in the database for audit** and are erased with the case. Owners can delete any comment (moderation); the activity feed records who deleted it.
- Limits: 5000 comments per case (soft limit, not locked against races).

## Activity feed

`GET /api/v1/cases/{id}/activity?limit=&offset=&order=` merges, chronologically, the existing audit sources with a SQL `UNION ALL` and pages it (limit 1–200, default 50; `order=desc` by default). Each entry has `id` (`history:<uuid>`, `claim-event:<uuid>`, `disagreement-review:<uuid>`, `comment:<uuid>[:revision:<n>|:deleted]`), `source`, `kind`, `category` (`CASE | WORKFLOW | PERMISSION | INVITATION | SHARING | EVIDENCE | REVIEW | COMMENT`), `actor`, `created_at`, `target {kind, id}`, `note`, `evidence` and `changes`.

- `changes` from `case_history` follows `GET /history`: coordinates are `"REDACTED"` for REVIEWER/VIEWER.
- `evidence` is what the source recorded at decision time: claim reviews → paper identity snapshot (DOI/title), claim version and `source_consulted`; disagreement decisions → both claim ids and versions; hypothesis evaluations → supporting/contradicting evidence ids and missing evidence; conclusion reviews → the cited edges (from, to, relation); edge reviews → the reviewed edge. The last three are written by ABB-25 into new `case_history` rows (additive key `evidence`); rows written before this change have `evidence: null`.
- Comment events never repeat the comment text.

## Consented share links

- Owner only. The request must contain `consent: true` and **every** section choice explicitly: `incident_notes`, `field_labels`, `location_detail` (`NONE | REGION | APPROXIMATE`), `hypotheses`, `evidence_claims`, `conclusions`, `member_names`, `comments`; optional `label` (≤ 120) and `expires_in_days` 1–30 (default 14). At most 10 active links per case.
- The token (`secrets.token_urlsafe(32)`, 256 bits) is returned once together with its path; only its SHA-256 digest is stored. Revocation and expiry apply to the next request. `GET /api/v1/shared/{token}` needs no account and returns the same 404 body for unknown, malformed, revoked and expired tokens. Responses carry `Cache-Control: no-store`, `Referrer-Policy: no-referrer`, `X-Robots-Tag: noindex, nofollow`, `X-Content-Type-Options: nosniff`.
- The view is built on each request from the current case (later edits appear while the link is active). Always included: title, workflow status, incident dates, crop history, case version and last update. Never included: case id, exact coordinates, e-mail addresses, user ids, observations and source manifests (their request parameters hold the field location), invitations, member lists, deleted comments, history.
- Location per field is the **more private** of the owner's choice and the field's tier: `APPROXIMATE` choice + `APPROXIMATE` tier → grid-cell centre of `rounding_deg` (same formula as ADR-0004); `EXACT` and `REGION_ONLY` tiers → region label only; `WITHHELD` or choice `NONE` → nothing. Consent given to members for the precise location (`precise_location_consent`) does **not** extend to share links.
- Field labels become `Field 1`, `Field 2`… unless `field_labels` is true. Comment authors become `Member 1`, `Member 2`… (order of first appearance) unless `member_names` is true; comment references are positional (`C1`, `C2`…).

## Web UI

- `features/cases/CollaborationPanel.tsx` (tab **Collaborators**): members with revoke (two-step) and an optional direct grant; for the owner, the invitation form (warns that no e-mail is sent and addresses are not verified) with revoke, and the share-link form where nothing is pre-selected, a free-text warning is shown, consent is a required checkbox and the link is shown once (`#/shared/<token>`, so the token stays in the URL fragment).
- `features/cases/DiscussionPanel.tsx` (tab **Discussion**): comments as ReviewSlips rendered as React text nodes (no `innerHTML`, no Markdown), one-level replies, author edits with the version read and the earlier versions on demand, tombstones, owner moderation; the paginated activity feed with translated actions (unknown actions show their code) and the recorded evidence/changes as text. Archived cases replace the composer with an explanation.
- `features/Collaboration.tsx`: pending invitations for the signed-in e-mail with accept/decline; `features/SharedCase.tsx`: the public view, which says which sections were not shared.

## Limitations and open decisions

- Free text written by people (title, crop history, hypothesis statements and evaluation notes, conclusions, comments) is shared as written when its section is selected; the server cannot detect a location or a name typed into prose. The UI must warn the owner before creating a link.
- Comment authors are not asked for consent when the owner opts in to sharing comments; the UI should show members when a case has an active link that includes comments. Candidate follow-up.
- No rate limiting on the public endpoint or on invitation creation (no Redis yet; ABB-28). Token entropy makes guessing impractical, but scraping of a leaked link is only limited by expiry and revocation.
- No e-mail delivery or e-mail verification (see Invitations).
- No notifications, mentions, reactions or comment resolution states. Comments are not reviews: they do not change any review status.
- Activity is offset-paginated; entries inserted while paging can shift pages (use `order=asc` and re-fetch for complete exports). No per-category filter yet.
- A frozen, versioned public snapshot and its link to the report export are left to ABB-26.
