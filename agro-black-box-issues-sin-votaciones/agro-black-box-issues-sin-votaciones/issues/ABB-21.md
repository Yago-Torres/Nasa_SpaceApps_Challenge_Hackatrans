# [ABB-21] Wizard de incidente y mapa geoespacial con privacidad

<!-- AGRO-ISSUE-ID: ABB-21 -->
## Objetivo
Wizard de incidente y mapa geoespacial con privacidad. Contribución a **Local Impact; Global Connection**. Fase **F3**, prioridad **P0**.

**Responsable sugerido:** C (A = Codex/ChatGPT; B = Claude ciencia/agronomía; C = Claude interfaz/producto). La asignación es flexible: cualquier integrante o agente puede avanzar esta tarea.

**Dependencias técnicas orientativas:** ABB-05, ABB-06, ABB-20. No son bloqueos de aprobación: se puede trabajar en componentes independientes, tests, prototipos o contratos provisionales mientras se integran dependencias.

## Pasos de implementación
- [ ] Crear formulario guiado de incidente y selección espacial, con precisión configurable.
- [ ] Mostrar datos introducidos y alertas de variables/campos faltantes.
- [ ] Integrar guardado/autosave y control de autorización.
- [ ] Ocultar coordenadas exactas al compartir externamente, salvo consentimiento explícito.

## Criterios de aceptación
- [ ] Un usuario crea un caso desde cero y vuelve a editarlo.
- [ ] Datos incorrectos reciben mensajes útiles, sin perder información.
- [ ] Un invitado no ve la ubicación exacta de la parcela privada.

## Archivos o dominios afectados
- `frontend/src/`
- `docs/product/UX_FLOWS.md`

## Comprobaciones y entrega
- [ ] Ejecutar las pruebas que correspondan y registrar resultados reales; indicar claramente las no ejecutadas.
- [ ] Mantener contratos y documentación sincronizados con los cambios implementados.
- [ ] Dejar una nota breve de integración o handoff si otro agente utiliza este módulo.

**Flujo de trabajo:** la Issue está lista para implementarse. Coordinad únicamente las interfaces y los archivos compartidos cuando sea necesario. El equipo decidirá cuándo crear ramas, commits o PRs.
