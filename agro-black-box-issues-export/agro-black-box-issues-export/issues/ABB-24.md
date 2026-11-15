# [ABB-24] Constructor y comparador interactivo de rotaciones

<!-- AGRO-ISSUE-ID: ABB-24 -->
## Objetivo
Constructor y comparador interactivo de rotaciones. Contribución a **Galactic Impact; Local Impact**. Trabajo de fase **F3**, prioridad **P0**.

**Responsable recomendado:** Persona C (A = usuario/ChatGPT, B = Claude científico, C = Claude producto). Cualquier integrante puede implementarla si el equipo aprueba la asignación.

**Dependencias previas:** ABB-17, ABB-18, ABB-20.
**Votación humana:** 2/3; revisar `docs/governance/FEATURE_POLICY.md`. La creación de esta Issue **no implica aprobación**.

## Pasos de implementación
- [ ] Crear editor de secuencia actual y dos alternativas, con años y estaciones.
- [ ] Añadir preferencias del agricultor y restricciones con formularios validados.
- [ ] Mostrar calendario, criterios, riesgos, explicaciones y por qué cada estrategia entra o se descarta.
- [ ] Incluir accesibilidad, estados de cálculo/error y guardado de selección.

## Criterios de aceptación
- [ ] Se pueden evaluar tres estrategias desde la UI.
- [ ] Cambiar las prioridades recalcula el resultado autorizado desde backend.
- [ ] No se presentan ahorros numéricos sin un modelo y fuente verificados.

## Archivos o dominios afectados
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

