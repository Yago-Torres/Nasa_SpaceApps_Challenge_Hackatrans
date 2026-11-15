# [ABB-01] Estabilizar herramientas, locks y CI reproducible

<!-- AGRO-ISSUE-ID: ABB-01 -->
## Objetivo
Estabilizar herramientas, locks y CI reproducible. Contribución a **Best Use of Data; transversal**. Trabajo de fase **F0**, prioridad **P0**.

**Responsable recomendado:** Persona A (A = usuario/ChatGPT, B = Claude científico, C = Claude producto). Cualquier integrante puede implementarla si el equipo aprueba la asignación.

**Dependencias previas:** ninguna.
**Votación humana:** 2/3; revisar `docs/governance/FEATURE_POLICY.md`. La creación de esta Issue **no implica aprobación**.

## Pasos de implementación
- [ ] Generar y commitear `backend/uv.lock` con `uv lock`; instalar mediante `uv sync --locked --extra dev`.
- [ ] Generar y commitear `frontend/package-lock.json`; en CI ejecutar `npm ci`, no instalar versiones flotantes.
- [ ] Verificar el arranque en Ubuntu/WSL y Omarchy; documentar errores reales y sus soluciones.
- [ ] Confirmar `api-tests`, `web-build` y `context-policy` en una instalación limpia.

## Criterios de aceptación
- [ ] CI pasa con lockfiles en un checkout limpio.
- [ ] `uv run pytest -q`, `npm run build` y `scripts/check_context.py` reproducibles.
- [ ] README documenta el flujo de trabajo sin pip ni activación manual.

## Archivos o dominios afectados
- `backend/pyproject.toml`
- `backend/uv.lock`
- `frontend/package-lock.json`
- `.github/workflows/ci.yml`
- `README.md`

## Contrato de entrega
- [ ] Cambios vinculados a esta Issue y revisados por otra persona cuando el equipo habilite su flujo Git.
- [ ] Tests/comprobaciones ejecutados y resultados registrados en la Issue o en la revisión (no inventados).
- [ ] Contratos y ADR actualizados si cambian; `CURRENT_STATE.md` solo tras validación.
- [ ] Handoff entre agentes según `docs/ai/HANDOFF_TEMPLATE.md`.

**Aprobaciones humanas (completar antes de programar):**
- [ ] Voto 1:
- [ ] Voto 2:
- [ ] Voto 3 (si se requieren 3/3):

