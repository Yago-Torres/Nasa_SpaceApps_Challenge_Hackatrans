# [ABB-07] Robustecer NASA POWER y registrar procedencia

<!-- AGRO-ISSUE-ID: ABB-07 -->
## Objetivo
Robustecer NASA POWER y registrar procedencia. Contribución a **Best Use of Data**. Fase **F1**, prioridad **P0**.

**Responsable sugerido:** A (A = Codex/ChatGPT; B = Claude ciencia/agronomía; C = Claude interfaz/producto). La asignación es flexible: cualquier integrante o agente puede avanzar esta tarea.

**Dependencias técnicas orientativas:** ABB-02. No son bloqueos de aprobación: se puede trabajar en componentes independientes, tests, prototipos o contratos provisionales mientras se integran dependencias.

## Pasos de implementación
- [ ] Auditar `services/power.py`: parámetros, cobertura temporal, unidades, fill values y validación de coordenadas.
- [ ] Añadir timeouts, retries con backoff, caché, rate limits y estados de error claros.
- [ ] Guardar hash SHA-256, fecha de acceso, versión del producto, URL y resoluciones espaciales/temporales.
- [ ] Probar respuesta real autorizada y fixtures versionados por separado.

## Criterios de aceptación
- [ ] El mismo caso recupera variables con unidades y procedencia.
- [ ] Errores de NASA no devuelven valores simulados como observados.
- [ ] Existen tests de éxito, ausencia de datos, timeout y respuesta incompleta.

## Archivos o dominios afectados
- `backend/agroblackbox/services/power.py`
- `backend/tests/`

## Comprobaciones y entrega
- [ ] Ejecutar las pruebas que correspondan y registrar resultados reales; indicar claramente las no ejecutadas.
- [ ] Mantener contratos y documentación sincronizados con los cambios implementados.
- [ ] Dejar una nota breve de integración o handoff si otro agente utiliza este módulo.

**Flujo de trabajo:** la Issue está lista para implementarse. Coordinad únicamente las interfaces y los archivos compartidos cuando sea necesario. El equipo decidirá cuándo crear ramas, commits o PRs.
