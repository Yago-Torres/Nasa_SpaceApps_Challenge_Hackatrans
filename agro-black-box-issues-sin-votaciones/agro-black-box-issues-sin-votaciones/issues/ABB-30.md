# [ABB-30] Despliegue seguro, monitorización y recuperación

<!-- AGRO-ISSUE-ID: ABB-30 -->
## Objetivo
Despliegue seguro, monitorización y recuperación. Contribución a **Galactic Impact; transversal**. Fase **F4**, prioridad **P1**.

**Responsable sugerido:** A (A = Codex/ChatGPT; B = Claude ciencia/agronomía; C = Claude interfaz/producto). La asignación es flexible: cualquier integrante o agente puede avanzar esta tarea.

**Dependencias técnicas orientativas:** ABB-01, ABB-03, ABB-05, ABB-27, ABB-29. No son bloqueos de aprobación: se puede trabajar en componentes independientes, tests, prototipos o contratos provisionales mientras se integran dependencias.

## Pasos de implementación
- [ ] Elegir plataforma y registrar costes, variables y controles de acceso.
- [ ] Configurar entornos de demo y release con migraciones, healthcheck, logs y seguimiento de errores.
- [ ] Definir backup/restauración de PostgreSQL y rollback de releases.
- [ ] Probar despliegue desde tag y recuperación ante una migración fallida simulada.

## Criterios de aceptación
- [ ] Hay URL de demo funcional accesible con el mínimo dato privado.
- [ ] El equipo puede repetir deploy, restaurar backup y revertir versión.
- [ ] Errores de fuentes externas son visibles en monitoreo sin exponer datos sensibles.

## Archivos o dominios afectados
- `.github/workflows/`
- `compose.yaml`
- `docs/operations/`

## Comprobaciones y entrega
- [ ] Ejecutar las pruebas que correspondan y registrar resultados reales; indicar claramente las no ejecutadas.
- [ ] Mantener contratos y documentación sincronizados con los cambios implementados.
- [ ] Dejar una nota breve de integración o handoff si otro agente utiliza este módulo.

**Flujo de trabajo:** la Issue está lista para implementarse. Coordinad únicamente las interfaces y los archivos compartidos cuando sea necesario. El equipo decidirá cuándo crear ramas, commits o PRs.
