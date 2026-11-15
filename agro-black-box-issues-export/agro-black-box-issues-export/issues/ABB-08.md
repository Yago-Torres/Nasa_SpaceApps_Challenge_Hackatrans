# [ABB-08] Motor de anomalías y control de calidad científico

<!-- AGRO-ISSUE-ID: ABB-08 -->
## Objetivo
Motor de anomalías y control de calidad científico. Contribución a **Best Use of Data**. Trabajo de fase **F1**, prioridad **P0**.

**Responsable recomendado:** Persona A (A = usuario/ChatGPT, B = Claude científico, C = Claude producto). Cualquier integrante puede implementarla si el equipo aprueba la asignación.

**Dependencias previas:** ABB-07.
**Votación humana:** 3/3; revisar `docs/governance/FEATURE_POLICY.md`. La creación de esta Issue **no implica aprobación**.

## Pasos de implementación
- [ ] Definir climatología de referencia, tratamiento de años incompletos, umbrales, fechas y unidades.
- [ ] Distinguir datos diarios/mensuales y evitar mezclar productos a distinta resolución sin documentar transformación.
- [ ] Registrar máscaras de calidad, faltantes y método empleado por indicador.
- [ ] Validar contra cálculos independientes y casos con datos sintéticos de resultado conocido.

## Criterios de aceptación
- [ ] Las anomalías reproducen resultados esperados de fixtures con tolerancias explícitas.
- [ ] Se etiquetan lagunas, incertidumbre y años sin cobertura suficiente.
- [ ] El informe puede explicar qué periodo y método generó cada indicador.

## Archivos o dominios afectados
- `backend/agroblackbox/services/metrics.py`
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

