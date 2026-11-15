# [ABB-19] Uncertainty Hunter: carencias y comprobaciones útiles

<!-- AGRO-ISSUE-ID: ABB-19 -->
## Objetivo
Uncertainty Hunter: carencias y comprobaciones útiles. Contribución a **Best Use of Data; Local Impact**. Trabajo de fase **F2**, prioridad **P1**.

**Responsable recomendado:** Persona B (A = usuario/ChatGPT, B = Claude científico, C = Claude producto). Cualquier integrante puede implementarla si el equipo aprueba la asignación.

**Dependencias previas:** ABB-10, ABB-15, ABB-18.
**Votación humana:** 3/3; revisar `docs/governance/FEATURE_POLICY.md`. La creación de esta Issue **no implica aprobación**.

## Pasos de implementación
- [ ] Localizar datos que faltan o son poco fiables para decidir entre rotaciones.
- [ ] Definir preguntas locales concretas (suelo, riego, etapa fenológica, manejo) con justificación.
- [ ] Mostrar qué conclusión podría cambiar al introducir esa observación, sin prometer cálculo de valor de información sin modelo.
- [ ] Añadir estado de resolución por agricultor o experto.

## Criterios de aceptación
- [ ] Cada pregunta propuesta explica qué incertidumbre abordaría.
- [ ] La interfaz permite registrar una respuesta local revisable.
- [ ] Si no hay base para priorizar una medición, se dice explícitamente.

## Archivos o dominios afectados
- `backend/agroblackbox/`
- `frontend/src/`

## Contrato de entrega
- [ ] Cambios vinculados a esta Issue y revisados por otra persona cuando el equipo habilite su flujo Git.
- [ ] Tests/comprobaciones ejecutados y resultados registrados en la Issue o en la revisión (no inventados).
- [ ] Contratos y ADR actualizados si cambian; `CURRENT_STATE.md` solo tras validación.
- [ ] Handoff entre agentes según `docs/ai/HANDOFF_TEMPLATE.md`.

**Aprobaciones humanas (completar antes de programar):**
- [ ] Voto 1:
- [ ] Voto 2:
- [ ] Voto 3 (si se requieren 3/3):

