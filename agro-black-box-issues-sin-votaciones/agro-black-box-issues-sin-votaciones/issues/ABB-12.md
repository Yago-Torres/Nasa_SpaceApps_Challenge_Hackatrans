# [ABB-12] Integrar HLS como observación de cobertura vegetal

<!-- AGRO-ISSUE-ID: ABB-12 -->
## Objetivo
Integrar HLS como observación de cobertura vegetal. Contribución a **Best Use of Data**. Fase **F1**, prioridad **P1**.

**Responsable sugerido:** A (A = Codex/ChatGPT; B = Claude ciencia/agronomía; C = Claude interfaz/producto). La asignación es flexible: cualquier integrante o agente puede avanzar esta tarea.

**Dependencias técnicas orientativas:** ABB-07, ABB-09. No son bloqueos de aprobación: se puede trabajar en componentes independientes, tests, prototipos o contratos provisionales mientras se integran dependencias.

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

## Comprobaciones y entrega
- [ ] Ejecutar las pruebas que correspondan y registrar resultados reales; indicar claramente las no ejecutadas.
- [ ] Mantener contratos y documentación sincronizados con los cambios implementados.
- [ ] Dejar una nota breve de integración o handoff si otro agente utiliza este módulo.

**Flujo de trabajo:** la Issue está lista para implementarse. Coordinad únicamente las interfaces y los archivos compartidos cuando sea necesario. El equipo decidirá cuándo crear ramas, commits o PRs.
