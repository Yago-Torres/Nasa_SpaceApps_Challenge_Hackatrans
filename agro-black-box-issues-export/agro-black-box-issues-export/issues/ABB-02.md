# [ABB-02] Congelar contrato API y esquemas de datos v1

<!-- AGRO-ISSUE-ID: ABB-02 -->
## Objetivo
Congelar contrato API y esquemas de datos v1. Contribución a **Best Use of Data; transversal**. Trabajo de fase **F0**, prioridad **P0**.

**Responsable recomendado:** Persona A (A = usuario/ChatGPT, B = Claude científico, C = Claude producto). Cualquier integrante puede implementarla si el equipo aprueba la asignación.

**Dependencias previas:** ABB-01.
**Votación humana:** 3/3; revisar `docs/governance/FEATURE_POLICY.md`. La creación de esta Issue **no implica aprobación**.

## Pasos de implementación
- [ ] Inventariar rutas actuales y tipos de respuesta en FastAPI y React.
- [ ] Diseñar Pydantic: Case, Field, SourceManifest, Observation, Anomaly, Hypothesis, Paper, EvidenceClaim, Rotation, Review y Report.
- [ ] Definir errores, nulos, unidades, metadatos de resolución, privacidad y versionado API.
- [ ] Revisar con responsables B y C y registrar ADR y contrato actualizado.

## Criterios de aceptación
- [ ] OpenAPI refleja esquemas completos con ejemplos reales o claramente marcados como fixtures.
- [ ] Contrato pasa una prueba de validación JSON y otra de error 422/4xx.
- [ ] A, B y C aprueban el cambio de contrato antes de codificar dependencias.

## Archivos o dominios afectados
- `backend/agroblackbox/app.py`
- `docs/architecture/API_CONTRACTS.md`
- `docs/architecture/ADRs/`

## Contrato de entrega
- [ ] Cambios vinculados a esta Issue y revisados por otra persona cuando el equipo habilite su flujo Git.
- [ ] Tests/comprobaciones ejecutados y resultados registrados en la Issue o en la revisión (no inventados).
- [ ] Contratos y ADR actualizados si cambian; `CURRENT_STATE.md` solo tras validación.
- [ ] Handoff entre agentes según `docs/ai/HANDOFF_TEMPLATE.md`.

**Aprobaciones humanas (completar antes de programar):**
- [ ] Voto 1:
- [ ] Voto 2:
- [ ] Voto 3 (si se requieren 3/3):

