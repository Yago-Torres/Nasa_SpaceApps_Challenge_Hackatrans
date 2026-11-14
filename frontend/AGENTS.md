# Frontend-specific agent instructions

Inherit repository `AGENTS.md`.
- TypeScript strict; React components should not implement scientific algorithms.
- When migrating from current local fetch types, use generated typed clients from the FastAPI OpenAPI contract.
- Label every value as observed, hypothesized, literature-backed, modeled or illustrative.
- Show loading, stale/offline and error states. No silently invented or simulated NASA data.
- Accessibility: keyboard usable, distinguish status by text not color alone, responsive layouts, locale-safe units.
- Follow `docs/product/UX_FLOWS.md` and the roadmap Issue; do not fabricate UI backed by nonexistent endpoints without marking it explicitly pending.
- **Mandatory design system:** every screen, component, style, chart, image or piece of UI copy follows `.claude/skills/agro-design-system/SKILL.md` (tokens, components, screens, motion, imagery). Copy `assets/tokens.css` to `src/design/tokens.css`; components use semantic tokens only. Do not introduce another visual style, dark theme, UI kit or image source without updating the skill under ABB-20.
- **Mandatory review:** run `.claude/skills/agro-ui-review/SKILL.md` before handing off or publishing frontend changes and record its findings.
