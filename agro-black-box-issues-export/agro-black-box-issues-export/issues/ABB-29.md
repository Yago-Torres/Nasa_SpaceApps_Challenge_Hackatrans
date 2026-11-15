# [ABB-29] Suite E2E y contratos entre backend y frontend

<!-- AGRO-ISSUE-ID: ABB-29 -->
## Objetivo
Suite E2E y contratos entre backend y frontend. Contribución a **Transversal**. Trabajo de fase **F4**, prioridad **P0**.

**Responsable recomendado:** Persona C (A = usuario/ChatGPT, B = Claude científico, C = Claude producto). Cualquier integrante puede implementarla si el equipo aprueba la asignación.

**Dependencias previas:** ABB-06, ABB-10, ABB-14, ABB-17, ABB-21, ABB-22, ABB-24, ABB-26.
**Votación humana:** 2/3; revisar `docs/governance/FEATURE_POLICY.md`. La creación de esta Issue **no implica aprobación**.

## Pasos de implementación
- [ ] Preparar fixtures explícitas, marcadas como sintéticas, y casos de red real separados.
- [ ] Añadir tests end-to-end de creación → NASA → evidencia → 3 rotaciones → revisión → informe.
- [ ] Comprobar contrato OpenAPI frente a tipos de frontend; fallos, nulos y permisos.
- [ ] Automatizar ejecución de pruebas en PR y documentar evidencia reproducible.

## Criterios de aceptación
- [ ] Pasa el recorrido principal completo en CI con fixtures controladas.
- [ ] Existe un smoke test de fuentes reales ejecutado manualmente y documentado.
- [ ] No se fusionan regresiones conocidas del flujo principal.

## Archivos o dominios afectados
- `backend/tests/`
- `frontend/`
- `.github/workflows/ci.yml`

## Contrato de entrega
- [ ] Cambios vinculados a esta Issue y revisados por otra persona cuando el equipo habilite su flujo Git.
- [ ] Tests/comprobaciones ejecutados y resultados registrados en la Issue o en la revisión (no inventados).
- [ ] Contratos y ADR actualizados si cambian; `CURRENT_STATE.md` solo tras validación.
- [ ] Handoff entre agentes según `docs/ai/HANDOFF_TEMPLATE.md`.

**Aprobaciones humanas (completar antes de programar):**
- [ ] Voto 1:
- [ ] Voto 2:
- [ ] Voto 3 (si se requieren 3/3):

