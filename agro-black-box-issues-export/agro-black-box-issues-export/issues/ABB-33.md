# [ABB-33] Validación de release 1.0 y cierre técnico

<!-- AGRO-ISSUE-ID: ABB-33 -->
## Objetivo
Validación de release 1.0 y cierre técnico. Contribución a **Transversal**. Trabajo de fase **F4**, prioridad **P0**.

**Responsable recomendado:** Persona A (A = usuario/ChatGPT, B = Claude científico, C = Claude producto). Cualquier integrante puede implementarla si el equipo aprueba la asignación.

**Dependencias previas:** ABB-09, ABB-12, ABB-15, ABB-19, ABB-23, ABB-25, ABB-26, ABB-28, ABB-29, ABB-30, ABB-31, ABB-32.
**Votación humana:** 3/3; revisar `docs/governance/FEATURE_POLICY.md`. La creación de esta Issue **no implica aprobación**.

## Pasos de implementación
- [ ] Pasar la checklist completa de `RELEASE_1_0.md`, módulos F-01 a F-12.
- [ ] Revisar resultados de CI, pruebas de permisos, pruebas en Linux/WSL/Omarchy y smoke externo.
- [ ] Actualizar CURRENT_STATE, changelog, contratos, limitaciones y manual de operación.
- [ ] Obtener validación humana de los tres y etiquetar release v1.0.0 solo si todos los gates pasan.

## Criterios de aceptación
- [ ] Cada criterio F-01...F-12 tiene prueba/PR o incidencia sin resolver; si falta, no llamar release final.
- [ ] La demo puede completarse sin operaciones manuales sobre la API.
- [ ] El tag está asociado a versión desplegada y reproducible.

## Archivos o dominios afectados
- `docs/product/RELEASE_1_0.md`
- `docs/operations/`
- `.github/`

## Contrato de entrega
- [ ] Cambios vinculados a esta Issue y revisados por otra persona cuando el equipo habilite su flujo Git.
- [ ] Tests/comprobaciones ejecutados y resultados registrados en la Issue o en la revisión (no inventados).
- [ ] Contratos y ADR actualizados si cambian; `CURRENT_STATE.md` solo tras validación.
- [ ] Handoff entre agentes según `docs/ai/HANDOFF_TEMPLATE.md`.

**Aprobaciones humanas (completar antes de programar):**
- [ ] Voto 1:
- [ ] Voto 2:
- [ ] Voto 3 (si se requieren 3/3):

