# [ABB-15] Detector de contradicciones y aplicabilidad de estudios

<!-- AGRO-ISSUE-ID: ABB-15 -->
## Objetivo
Detector de contradicciones y aplicabilidad de estudios. Contribución a **Best Use of Data; Galactic Impact**. Trabajo de fase **F2**, prioridad **P1**.

**Responsable recomendado:** Persona B (A = usuario/ChatGPT, B = Claude científico, C = Claude producto). Cualquier integrante puede implementarla si el equipo aprueba la asignación.

**Dependencias previas:** ABB-11, ABB-14.
**Votación humana:** 3/3; revisar `docs/governance/FEATURE_POLICY.md`. La creación de esta Issue **no implica aprobación**.

## Pasos de implementación
- [ ] Definir reglas comparables por intervención, resultado y condiciones del estudio.
- [ ] Detectar desacuerdos entre claims sin afirmar que siempre se contradigan metodológicamente.
- [ ] Comparar clima, suelo, cultivos y prácticas del paper con las del caso; producir notas de transferibilidad.
- [ ] Integrar revisión humana y estado no concluyente.

## Criterios de aceptación
- [ ] Una contradicción real/revisada se muestra con sus dos referencias.
- [ ] Ausencia de datos impide un score de aplicabilidad falsamente preciso.
- [ ] Al menos un ejemplo de transferencia limitada documenta las diferencias.

## Archivos o dominios afectados
- `backend/agroblackbox/`
- `docs/science/`

## Contrato de entrega
- [ ] Cambios vinculados a esta Issue y revisados por otra persona cuando el equipo habilite su flujo Git.
- [ ] Tests/comprobaciones ejecutados y resultados registrados en la Issue o en la revisión (no inventados).
- [ ] Contratos y ADR actualizados si cambian; `CURRENT_STATE.md` solo tras validación.
- [ ] Handoff entre agentes según `docs/ai/HANDOFF_TEMPLATE.md`.

**Aprobaciones humanas (completar antes de programar):**
- [ ] Voto 1:
- [ ] Voto 2:
- [ ] Voto 3 (si se requieren 3/3):

