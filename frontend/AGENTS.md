# Frontend-specific agent instructions

Inherit repository `AGENTS.md`.
- TypeScript strict; React components should not implement scientific algorithms.
- When migrating from current local fetch types, use generated typed clients from the FastAPI OpenAPI contract.
- Label every value as observed, hypothesized, literature-backed, modeled or illustrative.
- Show loading, stale/offline and error states. No silently invented or simulated NASA data.
- Accessibility: keyboard usable, distinguish status by text not color alone, responsive layouts, locale-safe units.
- Follow `docs/product/UX_FLOWS.md` and the roadmap Issue; do not fabricate UI backed by nonexistent endpoints without marking it explicitly pending.
- Design language: follow `.claude/skills/agro-design-system/SKILL.md`; review with `.claude/skills/agro-ui-review/SKILL.md`.
