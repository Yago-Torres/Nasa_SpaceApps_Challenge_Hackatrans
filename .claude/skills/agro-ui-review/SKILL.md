---
name: agro-ui-review
description: Audits AGRO BLACK BOX frontend changes for UX, accessibility, scientific honesty in the UI (epistemic tags, provenance, no fake NASA data), i18n EN/ES, privacy of farm locations and adherence to the Solar Industrial design system, then screenshots the app at desktop/mobile in both themes for visual critique. Use it before opening or approving any PR that touches frontend/, after building or restyling a screen, and whenever someone asks to "review the UI", "check accessibility", "audit UX", "is this screen OK", "revisar la interfaz", or wants a design QA pass — even if they only mention one component.
---

# AGRO BLACK BOX — UI review

A UI change in this product can be wrong in three ways: it can be hard to use, it can be inaccessible, or it can **mislead people about evidence** (e.g. an illustrative number that looks observed). The third kind is the most serious here, because users make farming decisions from these screens. This skill checks all three and also checks consistency with the design system.

## Inputs

- A target: changed files (`git diff --name-only origin/main...HEAD -- frontend/`), a path/glob, or a running page URL. If nothing is given, review the current branch's frontend diff.
- Context to read first: `frontend/AGENTS.md`, `docs/product/UX_FLOWS.md`, `docs/science/SCIENTIFIC_POLICY.md`, the linked Issue, and the `agro-design-system` skill (`.claude/skills/agro-design-system/SKILL.md`).

## Procedure

1. **Read the code** of every changed component and its styles. Check which API endpoints it calls against `docs/architecture/API_CONTRACTS.md`.
2. **Apply the checklist** in `references/checklist.md`, in its priority order: A (scientific honesty & privacy) → B (states & failure) → C (accessibility) → D (design-system adherence) → E (interaction, forms, content, performance, i18n).
3. **Look at it.** If a dev server can run (`cd frontend && npm run dev`, backend optional), screenshot it:
   ```bash
   node .claude/skills/agro-ui-review/scripts/screenshot.mjs http://localhost:5173 .ui-shots
   ```
   It captures 1440×900 and 390×844 in daylight and night-shift themes and flags console errors and horizontal overflow. Open the PNGs and actually look: hierarchy, alignment, clipped text, contrast, whether the epistemic tags are visible, whether the boldness is spent in one place. `.ui-shots/` is scratch output; don't commit it.
   Also exercise at least one failure path (stop the backend or use an invalid input) and screenshot the error state.
4. **Run the mechanical checks** that apply:
   ```bash
   cd frontend && npm run build                                       # typecheck + build
   node .claude/skills/agro-design-system/scripts/check-contrast.mjs  # if tokens changed
   ```
   Grep for raw colours and other easy violations, e.g. `rg -n "#[0-9a-fA-F]{3,8}\b" frontend/src --glob '!**/tokens.css'` and `rg -n "transition:\s*all|outline:\s*none|user-scalable" frontend/src`.
5. **Report** in the format below. Report only problems you can point to; don't pad with praise or generic advice.

## Output format

Group by file, most severe first, `file:line` so editors can jump to it. Prefix each finding with its severity and checklist ID.

```text
## frontend/src/features/forensics/WeatherChart.tsx

frontend/src/features/forensics/WeatherChart.tsx:42  [BLOCKER A2] chart has no epistemic tag; values look like field measurements
frontend/src/features/forensics/WeatherChart.tsx:88  [MAJOR C6] SVG chart lacks role="img"/accessible summary and table alternative
frontend/src/features/forensics/WeatherChart.tsx:17  [MINOR D1] raw #e39d5d — use --viz-dry-2

## frontend/src/design/components/Button.tsx

✓ pass

## Visual pass (.ui-shots)
mobile-dark.png: data plate SHA wraps mid-hash outside its cell — add overflow-wrap:anywhere (D)
desktop-light.png: two orange primary buttons in one view (D3)

## Verdict
2 blockers, 1 major, 2 minor. Not ready: fix A2 and the error state (B1) first.
```

Severity:
- **BLOCKER** — misleads about evidence, leaks private location data, presents sample/fake data as real, breaks the build, or makes a core flow unusable by keyboard/screen reader.
- **MAJOR** — missing async state, inaccessible control, hardcoded user-facing string, broken mobile layout, design-system violation visible to users.
- **MINOR** — polish, consistency, copy, small token misuse.

## Boundaries

- This skill reviews; it doesn't approve PRs or features (humans do — see `docs/governance/FEATURE_POLICY.md`). Say "ready for human review", never "approved".
- If a finding implies a backend or contract change (e.g. the API doesn't return spatial resolution so the data plate can't show it), report it as a dependency for the domain owner instead of suggesting the frontend invent the value.
- When asked to fix findings, fix BLOCKER and MAJOR items within the PR's approved scope; list anything out of scope as follow-up.

## Attribution

Sections C and E of the checklist adapt the Vercel Web Interface Guidelines (MIT, © 2025 Vercel Labs; license in `references/LICENSE-vercel-web-interface-guidelines.txt`). Sections A, B and D are specific to AGRO BLACK BOX.
