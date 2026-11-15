# [ABB-09] Integrar GPM IMERG con armonización espacial y temporal

<!-- AGRO-ISSUE-ID: ABB-09 -->
## Objetivo
Integrar GPM IMERG con armonización espacial y temporal. Contribución a **Best Use of Data**. Trabajo de fase **F1**, prioridad **P1**.

**Responsable recomendado:** Persona A (A = usuario/ChatGPT, B = Claude científico, C = Claude producto). Cualquier integrante puede implementarla si el equipo aprueba la asignación.

**Dependencias previas:** ABB-07, ABB-08.
**Votación humana:** 3/3; revisar `docs/governance/FEATURE_POLICY.md`. La creación de esta Issue **no implica aprobación**.

## Pasos de implementación
- [ ] Seleccionar producto/servicio GPM y documentar condiciones de acceso, resolución, unidades y latencia.
- [ ] Implementar adaptador de precipitación con descarga/acceso estable y metadatos.
- [ ] Comparar temporalmente con POWER sin confundir series/rejillas o interpolaciones.
- [ ] Ofrecer errores honestos y caché local; añadir datos para un episodio real.

## Criterios de aceptación
- [ ] Al menos un caso obtiene una serie GPM real, reproducible y documentada.
- [ ] La interfaz diferencia claramente producto GPM de POWER.
- [ ] Tests comprueban unidades, agregación, huecos y fallo de red.

## Archivos o dominios afectados
- `backend/agroblackbox/services/`
- `backend/tests/`
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

