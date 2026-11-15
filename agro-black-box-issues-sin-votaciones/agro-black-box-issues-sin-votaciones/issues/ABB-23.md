# [ABB-23] Explorador visual de papers y Evidence Graph

<!-- AGRO-ISSUE-ID: ABB-23 -->
## Objetivo
Explorador visual de papers y Evidence Graph. Contribución a **Best Use of Data; Global Connection**. Fase **F3**, prioridad **P1**.

**Responsable sugerido:** C (A = Codex/ChatGPT; B = Claude ciencia/agronomía; C = Claude interfaz/producto). La asignación es flexible: cualquier integrante o agente puede avanzar esta tarea.

**Dependencias técnicas orientativas:** ABB-14, ABB-16, ABB-20. No son bloqueos de aprobación: se puede trabajar en componentes independientes, tests, prototipos o contratos provisionales mientras se integran dependencias.

## Pasos de implementación
- [ ] Mostrar búsqueda, ficha de artículo, claim revisado/no revisado, contexto y limitaciones.
- [ ] Construir grafo navegable desde observación hasta conclusión y DOI.
- [ ] Visualizar contradicciones, transferibilidad y anotaciones de revisión.
- [ ] Asegurar legibilidad sin depender de color y respeto de permisos.

## Criterios de aceptación
- [ ] Desde una conclusión se abre el conjunto de evidencias pertinentes.
- [ ] El sistema muestra claramente evidencias no revisadas.
- [ ] Los enlaces DOI resuelven a sus URL originales sin inventar bibliografía.

## Archivos o dominios afectados
- `frontend/src/`

## Comprobaciones y entrega
- [ ] Ejecutar las pruebas que correspondan y registrar resultados reales; indicar claramente las no ejecutadas.
- [ ] Mantener contratos y documentación sincronizados con los cambios implementados.
- [ ] Dejar una nota breve de integración o handoff si otro agente utiliza este módulo.

**Flujo de trabajo:** la Issue está lista para implementarse. Coordinad únicamente las interfaces y los archivos compartidos cuando sea necesario. El equipo decidirá cuándo crear ramas, commits o PRs.
