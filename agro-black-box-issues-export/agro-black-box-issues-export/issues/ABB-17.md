# [ABB-17] Motor de rotaciones con restricciones y tres estrategias

<!-- AGRO-ISSUE-ID: ABB-17 -->
## Objetivo
Motor de rotaciones con restricciones y tres estrategias. Contribución a **Local Impact; Galactic Impact**. Trabajo de fase **F2**, prioridad **P0**.

**Responsable recomendado:** Persona B (A = usuario/ChatGPT, B = Claude científico, C = Claude producto). Cualquier integrante puede implementarla si el equipo aprueba la asignación.

**Dependencias previas:** ABB-08, ABB-11, ABB-14.
**Votación humana:** 3/3; revisar `docs/governance/FEATURE_POLICY.md`. La creación de esta Issue **no implica aprobación**.

## Pasos de implementación
- [ ] Implementar secuencias multianuales y calendarios por cultivo, con rotación actual obligatoria.
- [ ] Construir dos alternativas viables bajo suelo, clima, agua, equipo, cultivos y prioridades declaradas.
- [ ] Excluir combinaciones imposibles y documentar reglas y referencias agrícolas.
- [ ] Ejecutar comparación basada en exposición, cobertura potencial y restricciones; evitar predicción no validada de rendimiento.

## Criterios de aceptación
- [ ] Siempre se comparan >=3 estrategias, incluida la actual, o se explica por qué no son factibles.
- [ ] Cada recomendación indica beneficios posibles, riesgos y condiciones que requieren revisión.
- [ ] Los casos de calendario incompatible se rechazan en tests.

## Archivos o dominios afectados
- `backend/agroblackbox/services/rotations.py`
- `backend/tests/`

## Contrato de entrega
- [ ] Cambios vinculados a esta Issue y revisados por otra persona cuando el equipo habilite su flujo Git.
- [ ] Tests/comprobaciones ejecutados y resultados registrados en la Issue o en la revisión (no inventados).
- [ ] Contratos y ADR actualizados si cambian; `CURRENT_STATE.md` solo tras validación.
- [ ] Handoff entre agentes según `docs/ai/HANDOFF_TEMPLATE.md`.

**Aprobaciones humanas (completar antes de programar):**
- [ ] Voto 1:
- [ ] Voto 2:
- [ ] Voto 3 (si se requieren 3/3):

