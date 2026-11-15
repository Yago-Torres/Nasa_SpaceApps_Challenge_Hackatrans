# [ABB-29] Suite E2E y contratos entre backend y frontend

<!-- AGRO-ISSUE-ID: ABB-29 -->
## Objetivo
Suite E2E y contratos entre backend y frontend. Contribución a **Transversal**. Fase **F4**, prioridad **P0**.

**Responsable sugerido:** C (A = Codex/ChatGPT; B = Claude ciencia/agronomía; C = Claude interfaz/producto). La asignación es flexible: cualquier integrante o agente puede avanzar esta tarea.

**Dependencias técnicas orientativas:** ABB-06, ABB-10, ABB-14, ABB-17, ABB-21, ABB-22, ABB-24, ABB-26. No son bloqueos de aprobación: se puede trabajar en componentes independientes, tests, prototipos o contratos provisionales mientras se integran dependencias.

## Pasos de implementación
- [ ] Preparar fixtures explícitas, marcadas como sintéticas, y casos de red real separados.
- [ ] Añadir tests end-to-end de creación → NASA → evidencia → 3 rotaciones → revisión → informe.
- [ ] Comprobar contrato OpenAPI frente a tipos de frontend; fallos, nulos y permisos.
- [ ] Automatizar ejecución de pruebas en CI y documentar evidencia reproducible.

## Criterios de aceptación
- [ ] Pasa el recorrido principal completo en CI con fixtures controladas.
- [ ] Existe un smoke test de fuentes reales ejecutado manualmente y documentado.
- [ ] Los fallos conocidos del recorrido principal quedan detectados y documentados por las pruebas.

## Archivos o dominios afectados
- `backend/tests/`
- `frontend/`
- `.github/workflows/ci.yml`

## Comprobaciones y entrega
- [ ] Ejecutar las pruebas que correspondan y registrar resultados reales; indicar claramente las no ejecutadas.
- [ ] Mantener contratos y documentación sincronizados con los cambios implementados.
- [ ] Dejar una nota breve de integración o handoff si otro agente utiliza este módulo.

**Flujo de trabajo:** la Issue está lista para implementarse. Coordinad únicamente las interfaces y los archivos compartidos cuando sea necesario. El equipo decidirá cuándo crear ramas, commits o PRs.
