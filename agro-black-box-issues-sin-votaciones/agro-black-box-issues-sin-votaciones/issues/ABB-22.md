# [ABB-22] Visualización avanzada de timeline, anomalías y fuentes NASA

<!-- AGRO-ISSUE-ID: ABB-22 -->
## Objetivo
Visualización avanzada de timeline, anomalías y fuentes NASA. Contribución a **Best Use of Data**. Fase **F3**, prioridad **P0**.

**Responsable sugerido:** C (A = Codex/ChatGPT; B = Claude ciencia/agronomía; C = Claude interfaz/producto). La asignación es flexible: cualquier integrante o agente puede avanzar esta tarea.

**Dependencias técnicas orientativas:** ABB-08, ABB-10, ABB-20. No son bloqueos de aprobación: se puede trabajar en componentes independientes, tests, prototipos o contratos provisionales mientras se integran dependencias.

## Pasos de implementación
- [ ] Añadir gráfico de series y anomalías con selección temporal y capas disponibles.
- [ ] Mostrar unidad, periodo base, QA, procedencia y resolución por variable.
- [ ] Diferenciar NASA real, datos locales y escenarios simulados en leyenda permanente.
- [ ] Diseñar estados de carga, sin datos, error externo y datos parciales.

## Criterios de aceptación
- [ ] El usuario puede inspeccionar cada hallazgo hasta su origen.
- [ ] Los gráficos no interpolan silenciosamente huecos de datos.
- [ ] La UI representa errores NASA sin inventar valores.

## Archivos o dominios afectados
- `frontend/src/`

## Comprobaciones y entrega
- [ ] Ejecutar las pruebas que correspondan y registrar resultados reales; indicar claramente las no ejecutadas.
- [ ] Mantener contratos y documentación sincronizados con los cambios implementados.
- [ ] Dejar una nota breve de integración o handoff si otro agente utiliza este módulo.

**Flujo de trabajo:** la Issue está lista para implementarse. Coordinad únicamente las interfaces y los archivos compartidos cuando sea necesario. El equipo decidirá cuándo crear ramas, commits o PRs.
