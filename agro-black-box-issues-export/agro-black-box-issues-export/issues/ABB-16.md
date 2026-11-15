# [ABB-16] Modelo de grafo de evidencia y trazabilidad

<!-- AGRO-ISSUE-ID: ABB-16 -->
## Objetivo
Modelo de grafo de evidencia y trazabilidad. Contribución a **Best Use of Data; Global Connection**. Trabajo de fase **F2**, prioridad **P1**.

**Responsable recomendado:** Persona B (A = usuario/ChatGPT, B = Claude científico, C = Claude producto). Cualquier integrante puede implementarla si el equipo aprueba la asignación.

**Dependencias previas:** ABB-10, ABB-14.
**Votación humana:** 3/3; revisar `docs/governance/FEATURE_POLICY.md`. La creación de esta Issue **no implica aprobación**.

## Pasos de implementación
- [ ] Diseñar nodos observación, hipótesis, estudio, claim, limitación y conclusión.
- [ ] Registrar aristas con tipo y estado de revisión; prohibir referencias huérfanas.
- [ ] Exponer endpoint navegable por caso con fuente verificable y control de permisos.
- [ ] Probar que toda conclusión científica remite a datos y/o revisión humana.

## Criterios de aceptación
- [ ] Cada conclusión importante se rastrea hasta su evidencia original.
- [ ] Grafo no crea enlaces inexistentes y soporta hipótesis contradictorias.
- [ ] El endpoint respeta permisos privados de caso.

## Archivos o dominios afectados
- `backend/agroblackbox/`
- `docs/architecture/API_CONTRACTS.md`

## Contrato de entrega
- [ ] Cambios vinculados a esta Issue y revisados por otra persona cuando el equipo habilite su flujo Git.
- [ ] Tests/comprobaciones ejecutados y resultados registrados en la Issue o en la revisión (no inventados).
- [ ] Contratos y ADR actualizados si cambian; `CURRENT_STATE.md` solo tras validación.
- [ ] Handoff entre agentes según `docs/ai/HANDOFF_TEMPLATE.md`.

**Aprobaciones humanas (completar antes de programar):**
- [ ] Voto 1:
- [ ] Voto 2:
- [ ] Voto 3 (si se requieren 3/3):

