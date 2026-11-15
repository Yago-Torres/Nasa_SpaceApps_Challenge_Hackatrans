# [ABB-08] Motor de anomalías y control de calidad científico

<!-- AGRO-ISSUE-ID: ABB-08 -->
## Objetivo
Motor de anomalías y control de calidad científico. Contribución a **Best Use of Data**. Fase **F1**, prioridad **P0**.

**Responsable sugerido:** A (A = Codex/ChatGPT; B = Claude ciencia/agronomía; C = Claude interfaz/producto). La asignación es flexible: cualquier integrante o agente puede avanzar esta tarea.

**Dependencias técnicas orientativas:** ABB-07. No son bloqueos de aprobación: se puede trabajar en componentes independientes, tests, prototipos o contratos provisionales mientras se integran dependencias.

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

## Comprobaciones y entrega
- [ ] Ejecutar las pruebas que correspondan y registrar resultados reales; indicar claramente las no ejecutadas.
- [ ] Mantener contratos y documentación sincronizados con los cambios implementados.
- [ ] Dejar una nota breve de integración o handoff si otro agente utiliza este módulo.

**Flujo de trabajo:** la Issue está lista para implementarse. Coordinad únicamente las interfaces y los archivos compartidos cuando sea necesario. El equipo decidirá cuándo crear ramas, commits o PRs.
