# [ABB-04] Configurar gobierno del equipo, GitHub Project y protección de main

<!-- AGRO-ISSUE-ID: ABB-04 -->
## Objetivo
Configurar gobierno del equipo, GitHub Project y protección de main. Contribución a **Global Connection; transversal**. Fase **F0**, prioridad **P0**.

**Responsable sugerido:** C (A = Codex/ChatGPT; B = Claude ciencia/agronomía; C = Claude interfaz/producto). La asignación es flexible: cualquier integrante o agente puede avanzar esta tarea.

**Dependencias técnicas orientativas:** ABB-01. No son bloqueos de aprobación: se puede trabajar en componentes independientes, tests, prototipos o contratos provisionales mientras se integran dependencias.

## Pasos de implementación
- [ ] Activar Issues, etiquetas y un tablero sencillo (Backlog, Ready, In Progress, Review, Done).
- [ ] Invitar a los tres colaboradores y documentar cómo se asignan Issues y se comparten avances.
- [ ] Configurar CODEOWNERS para ciencia, backend, frontend y documentación.
- [ ] Añadir a las plantillas PR enlaces a Issue, pruebas y cambios de contratos.

## Criterios de aceptación
- [ ] Las Issues tienen propietario, estado y criterios verificables.
- [ ] La CI comunica con claridad los fallos; los integrantes pueden revisar cambios y decidir cuándo integrarlos.
- [ ] El tablero permite que los agentes trabajen directamente sobre las Issues.

## Archivos o dominios afectados
- `.github/`
- `docs/governance/`
- `docs/ai/`

## Comprobaciones y entrega
- [ ] Ejecutar las pruebas que correspondan y registrar resultados reales; indicar claramente las no ejecutadas.
- [ ] Mantener contratos y documentación sincronizados con los cambios implementados.
- [ ] Dejar una nota breve de integración o handoff si otro agente utiliza este módulo.

**Flujo de trabajo:** la Issue está lista para implementarse. Coordinad únicamente las interfaces y los archivos compartidos cuando sea necesario. El equipo decidirá cuándo crear ramas, commits o PRs.
