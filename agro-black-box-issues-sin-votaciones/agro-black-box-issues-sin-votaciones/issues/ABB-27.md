# [ABB-27] Caché, tareas asíncronas y resiliencia ante APIs externas

<!-- AGRO-ISSUE-ID: ABB-27 -->
## Objetivo
Caché, tareas asíncronas y resiliencia ante APIs externas. Contribución a **Best Use of Data**. Fase **F4**, prioridad **P1**.

**Responsable sugerido:** A (A = Codex/ChatGPT; B = Claude ciencia/agronomía; C = Claude interfaz/producto). La asignación es flexible: cualquier integrante o agente puede avanzar esta tarea.

**Dependencias técnicas orientativas:** ABB-03, ABB-07, ABB-13. No son bloqueos de aprobación: se puede trabajar en componentes independientes, tests, prototipos o contratos provisionales mientras se integran dependencias.

## Pasos de implementación
- [ ] Definir tareas con identificador, estado, timeout, reintento, cancelación y deduplicación.
- [ ] Integrar Redis/worker si se justifica mediante ADR y límites claros; evitar bloquear peticiones largas.
- [ ] Registrar cuota de upstream y política de caché por recurso y fecha.
- [ ] Probar caída de POWER/OpenAlex, reintentos limitados y recuperación.

## Criterios de aceptación
- [ ] Solicitudes repetidas no disparan descargas innecesarias.
- [ ] Un upstream caído produce error recuperable y nunca dato ficticio.
- [ ] Tareas largas reportan progreso/estado y pueden retomarse.

## Archivos o dominios afectados
- `backend/agroblackbox/`
- `compose.yaml`

## Comprobaciones y entrega
- [ ] Ejecutar las pruebas que correspondan y registrar resultados reales; indicar claramente las no ejecutadas.
- [ ] Mantener contratos y documentación sincronizados con los cambios implementados.
- [ ] Dejar una nota breve de integración o handoff si otro agente utiliza este módulo.

**Flujo de trabajo:** la Issue está lista para implementarse. Coordinad únicamente las interfaces y los archivos compartidos cuando sea necesario. El equipo decidirá cuándo crear ramas, commits o PRs.
