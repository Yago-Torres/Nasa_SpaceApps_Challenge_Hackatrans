# [ABB-09] Integrar GPM IMERG con armonización espacial y temporal

<!-- AGRO-ISSUE-ID: ABB-09 -->
## Objetivo
Integrar GPM IMERG con armonización espacial y temporal. Contribución a **Best Use of Data**. Fase **F1**, prioridad **P1**.

**Responsable sugerido:** A (A = Codex/ChatGPT; B = Claude ciencia/agronomía; C = Claude interfaz/producto). La asignación es flexible: cualquier integrante o agente puede avanzar esta tarea.

**Dependencias técnicas orientativas:** ABB-07, ABB-08. No son bloqueos de aprobación: se puede trabajar en componentes independientes, tests, prototipos o contratos provisionales mientras se integran dependencias.

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

## Comprobaciones y entrega
- [ ] Ejecutar las pruebas que correspondan y registrar resultados reales; indicar claramente las no ejecutadas.
- [ ] Mantener contratos y documentación sincronizados con los cambios implementados.
- [ ] Dejar una nota breve de integración o handoff si otro agente utiliza este módulo.

**Flujo de trabajo:** la Issue está lista para implementarse. Coordinad únicamente las interfaces y los archivos compartidos cuando sea necesario. El equipo decidirá cuándo crear ramas, commits o PRs.
