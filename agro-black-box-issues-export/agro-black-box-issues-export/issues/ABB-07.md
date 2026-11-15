# [ABB-07] Robustecer NASA POWER y registrar procedencia

<!-- AGRO-ISSUE-ID: ABB-07 -->
## Objetivo
Robustecer NASA POWER y registrar procedencia. Contribución a **Best Use of Data**. Trabajo de fase **F1**, prioridad **P0**.

**Responsable recomendado:** Persona A (A = usuario/ChatGPT, B = Claude científico, C = Claude producto). Cualquier integrante puede implementarla si el equipo aprueba la asignación.

**Dependencias previas:** ABB-02.
**Votación humana:** 2/3; revisar `docs/governance/FEATURE_POLICY.md`. La creación de esta Issue **no implica aprobación**.

## Pasos de implementación
- [ ] Auditar `services/power.py`: parámetros, cobertura temporal, unidades, fill values y validación de coordenadas.
- [ ] Añadir timeouts, retries con backoff, caché, rate limits y estados de error claros.
- [ ] Guardar hash SHA-256, fecha de acceso, versión del producto, URL y resoluciones espaciales/temporales.
- [ ] Probar respuesta real autorizada y fixtures versionados por separado.

## Criterios de aceptación
- [ ] El mismo caso recupera variables con unidades y procedencia.
- [ ] Errores de NASA no devuelven valores simulados como observados.
- [ ] Existen tests de éxito, ausencia de datos, timeout y respuesta incompleta.

## Archivos o dominios afectados
- `backend/agroblackbox/services/power.py`
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

