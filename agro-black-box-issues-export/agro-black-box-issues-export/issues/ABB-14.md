# [ABB-14] Registro estructurado de claims científicos con revisión humana

<!-- AGRO-ISSUE-ID: ABB-14 -->
## Objetivo
Registro estructurado de claims científicos con revisión humana. Contribución a **Best Use of Data**. Trabajo de fase **F2**, prioridad **P0**.

**Responsable recomendado:** Persona B (A = usuario/ChatGPT, B = Claude científico, C = Claude producto). Cualquier integrante puede implementarla si el equipo aprueba la asignación.

**Dependencias previas:** ABB-03, ABB-13.
**Votación humana:** 3/3; revisar `docs/governance/FEATURE_POLICY.md`. La creación de esta Issue **no implica aprobación**.

## Pasos de implementación
- [ ] Crear entidad EvidenceClaim: afirmación, población/cultivos/suelos, diseño, resultado, incertidumbre, DOI, página/fragmento y estatus.
- [ ] Implementar flujo unverified → reviewed/rejected y mantener historial.
- [ ] Exigir licencia y acceso legítimo para procesar contenido completo.
- [ ] Añadir fichas verificadas para el caso piloto y avisos cuando solo haya metadatos.

## Criterios de aceptación
- [ ] Ningún abstract se presenta automáticamente como resultado de un ensayo.
- [ ] La UI distingue claims revisados y no revisados.
- [ ] Se conserva qué persona revisó y qué fuente se consultó.

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

