# [ABB-23] Explorador visual de papers y Evidence Graph

<!-- AGRO-ISSUE-ID: ABB-23 -->
## Objetivo
Explorador visual de papers y Evidence Graph. Contribución a **Best Use of Data; Global Connection**. Trabajo de fase **F3**, prioridad **P1**.

**Responsable recomendado:** Persona C (A = usuario/ChatGPT, B = Claude científico, C = Claude producto). Cualquier integrante puede implementarla si el equipo aprueba la asignación.

**Dependencias previas:** ABB-14, ABB-16, ABB-20.
**Votación humana:** 2/3; revisar `docs/governance/FEATURE_POLICY.md`. La creación de esta Issue **no implica aprobación**.

## Pasos de implementación
- [ ] Mostrar búsqueda, ficha de artículo, claim revisado/no revisado, contexto y limitaciones.
- [ ] Construir grafo navegable desde observación hasta conclusión y DOI.
- [ ] Visualizar contradicciones, transferibilidad y anotaciones de revisión.
- [ ] Asegurar legibilidad sin depender de color y respeto de permisos.

## Criterios de aceptación
- [ ] Desde una conclusión se abre el conjunto de evidencias pertinentes.
- [ ] El sistema muestra claramente evidencias no revisadas.
- [ ] Los enlaces DOI resuelven a sus URL originales sin inventar bibliografía.

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

