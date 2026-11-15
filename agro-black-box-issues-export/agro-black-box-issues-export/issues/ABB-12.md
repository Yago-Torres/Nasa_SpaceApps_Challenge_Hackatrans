# [ABB-12] Integrar HLS como observación de cobertura vegetal

<!-- AGRO-ISSUE-ID: ABB-12 -->
## Objetivo
Integrar HLS como observación de cobertura vegetal. Contribución a **Best Use of Data**. Trabajo de fase **F1**, prioridad **P1**.

**Responsable recomendado:** Persona A (A = usuario/ChatGPT, B = Claude científico, C = Claude producto). Cualquier integrante puede implementarla si el equipo aprueba la asignación.

**Dependencias previas:** ABB-07, ABB-09.
**Votación humana:** 3/3; revisar `docs/governance/FEATURE_POLICY.md`. La creación de esta Issue **no implica aprobación**.

## Pasos de implementación
- [ ] Seleccionar colecciones HLS, autorización, búsqueda y manejo de nubes/QA.
- [ ] Calcular o recuperar indicadores de vegetación por fechas y geometría autorizada.
- [ ] Documentar resolución de 30 m y escala de interpretación; no igualar NDVI con salud del suelo.
- [ ] Mostrar periodos de observación válidos y ausentes.

## Criterios de aceptación
- [ ] Un caso muestra imágenes/índices observados con QA y metadatos verificables.
- [ ] Las fechas sin escenas útiles aparecen como falta de dato.
- [ ] Existe test del pipeline con fixtures y una verificación real documentada.

## Archivos o dominios afectados
- `backend/agroblackbox/services/`
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

