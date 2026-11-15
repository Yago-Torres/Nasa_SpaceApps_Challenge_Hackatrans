# [ABB-03] Modelo PostgreSQL, migraciones y repositorio de datos

<!-- AGRO-ISSUE-ID: ABB-03 -->
## Objetivo
Modelo PostgreSQL, migraciones y repositorio de datos. Contribución a **Local Impact; transversal**. Fase **F0**, prioridad **P0**.

**Responsable sugerido:** A (A = Codex/ChatGPT; B = Claude ciencia/agronomía; C = Claude interfaz/producto). La asignación es flexible: cualquier integrante o agente puede avanzar esta tarea.

**Dependencias técnicas orientativas:** ABB-02. No son bloqueos de aprobación: se puede trabajar en componentes independientes, tests, prototipos o contratos provisionales mientras se integran dependencias.

## Pasos de implementación
- [ ] Definir relaciones para usuarios, permisos, casos, parcelas, fuentes, observaciones, hipótesis, evidencias, rotaciones, revisiones e informes.
- [ ] Implementar SQLAlchemy + Alembic y migración inicial; no guardar coordenadas privadas en logs.
- [ ] Separar entidades, repositorios y lógica de negocio; añadir seeds explícitamente sintéticos.
- [ ] Probar creación, actualización, lectura, cambios concurrentes y rollback de migraciones.

## Criterios de aceptación
- [ ] Una base vacía se inicializa con migraciones reproducibles.
- [ ] Persisten casos y artefactos y se pueden leer tras reiniciar.
- [ ] Tests de integridad referencial y recuperación funcionan con PostgreSQL.

## Archivos o dominios afectados
- `backend/agroblackbox/`
- `compose.yaml`
- `backend/tests/`

## Comprobaciones y entrega
- [ ] Ejecutar las pruebas que correspondan y registrar resultados reales; indicar claramente las no ejecutadas.
- [ ] Mantener contratos y documentación sincronizados con los cambios implementados.
- [ ] Dejar una nota breve de integración o handoff si otro agente utiliza este módulo.

**Flujo de trabajo:** la Issue está lista para implementarse. Coordinad únicamente las interfaces y los archivos compartidos cuando sea necesario. El equipo decidirá cuándo crear ramas, commits o PRs.
