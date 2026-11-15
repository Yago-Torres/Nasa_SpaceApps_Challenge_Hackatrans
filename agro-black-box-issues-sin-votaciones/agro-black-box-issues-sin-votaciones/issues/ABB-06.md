# [ABB-06] Gestión completa de investigaciones y parcelas

<!-- AGRO-ISSUE-ID: ABB-06 -->
## Objetivo
Gestión completa de investigaciones y parcelas. Contribución a **Local Impact**. Fase **F1**, prioridad **P0**.

**Responsable sugerido:** C (A = Codex/ChatGPT; B = Claude ciencia/agronomía; C = Claude interfaz/producto). La asignación es flexible: cualquier integrante o agente puede avanzar esta tarea.

**Dependencias técnicas orientativas:** ABB-03, ABB-05. No son bloqueos de aprobación: se puede trabajar en componentes independientes, tests, prototipos o contratos provisionales mientras se integran dependencias.

## Pasos de implementación
- [ ] Implementar CRUD de caso con zona, precisión espacial, fecha de evento, cultivo, cronología y observaciones aportadas.
- [ ] Validar lat/lon, fechas, consentimiento y entradas no válidas; permitir editar sin perder versiones.
- [ ] Implementar workflow draft → investigating → reviewed → published y su historial.
- [ ] Conectar primera pantalla web a API persistente, sin fixtures ocultos.

## Criterios de aceptación
- [ ] Crear, reabrir y actualizar un caso desde UI persiste tras reinicio.
- [ ] Un usuario sin acceso no puede listar ni obtener un caso privado.
- [ ] Toda edición conserva autor, fecha, revisión y procedencia.

## Archivos o dominios afectados
- `backend/agroblackbox/`
- `frontend/src/`

## Comprobaciones y entrega
- [ ] Ejecutar las pruebas que correspondan y registrar resultados reales; indicar claramente las no ejecutadas.
- [ ] Mantener contratos y documentación sincronizados con los cambios implementados.
- [ ] Dejar una nota breve de integración o handoff si otro agente utiliza este módulo.

**Flujo de trabajo:** la Issue está lista para implementarse. Coordinad únicamente las interfaces y los archivos compartidos cuando sea necesario. El equipo decidirá cuándo crear ramas, commits o PRs.
