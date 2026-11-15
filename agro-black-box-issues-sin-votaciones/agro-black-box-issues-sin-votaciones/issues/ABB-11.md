# [ABB-11] Registrar suelos, cultivos y calendario local del agricultor

<!-- AGRO-ISSUE-ID: ABB-11 -->
## Objetivo
Registrar suelos, cultivos y calendario local del agricultor. Contribución a **Local Impact**. Fase **F1**, prioridad **P0**.

**Responsable sugerido:** B (A = Codex/ChatGPT; B = Claude ciencia/agronomía; C = Claude interfaz/producto). La asignación es flexible: cualquier integrante o agente puede avanzar esta tarea.

**Dependencias técnicas orientativas:** ABB-02, ABB-06. No son bloqueos de aprobación: se puede trabajar en componentes independientes, tests, prototipos o contratos provisionales mientras se integran dependencias.

## Pasos de implementación
- [ ] Permitir propiedades de suelo locales, unidades, profundidad y fuente de medida.
- [ ] Modelar cultivos, sistema de secano/regadío, fechas, restricciones de equipos y mercados.
- [ ] Usar catálogo inicial revisado con origen científico, no inventar parámetros.
- [ ] Definir advertencias por dato ausente y validaciones agronómicas.

## Criterios de aceptación
- [ ] Se puede distinguir medición local de estimación regional.
- [ ] El usuario puede registrar historial de cultivos, suelo y restricciones.
- [ ] Datos no disponibles provocan resultados limitados, no certezas simuladas.

## Archivos o dominios afectados
- `backend/agroblackbox/`
- `docs/science/`
- `frontend/src/`

## Comprobaciones y entrega
- [ ] Ejecutar las pruebas que correspondan y registrar resultados reales; indicar claramente las no ejecutadas.
- [ ] Mantener contratos y documentación sincronizados con los cambios implementados.
- [ ] Dejar una nota breve de integración o handoff si otro agente utiliza este módulo.

**Flujo de trabajo:** la Issue está lista para implementarse. Coordinad únicamente las interfaces y los archivos compartidos cuando sea necesario. El equipo decidirá cuándo crear ramas, commits o PRs.
