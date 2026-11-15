# [ABB-20] Sistema de diseño, navegación, accesibilidad e idioma EN/ES

<!-- AGRO-ISSUE-ID: ABB-20 -->
## Objetivo
Sistema de diseño, navegación, accesibilidad e idioma EN/ES. Contribución a **Global Connection; Local Impact**. Fase **F3**, prioridad **P0**.

**Responsable sugerido:** C (A = Codex/ChatGPT; B = Claude ciencia/agronomía; C = Claude interfaz/producto). La asignación es flexible: cualquier integrante o agente puede avanzar esta tarea.

**Dependencias técnicas orientativas:** ABB-02. No son bloqueos de aprobación: se puede trabajar en componentes independientes, tests, prototipos o contratos provisionales mientras se integran dependencias.

## Pasos de implementación
- [ ] Definir layout, estados vacíos, skeleton, error, componente de fuentes y avisos de simulación.
- [ ] Crear rutas principales: Dashboard, Cases, Investigation, Evidence, Rotations, Collaboration, Report.
- [ ] Incorporar internacionalización EN/ES, responsive y navegación teclado.
- [ ] Probar build TS y accesibilidad de interacciones críticas.

## Criterios de aceptación
- [ ] Frontend navega entre pantallas con estados definidos.
- [ ] Los textos principales están disponibles en español e inglés.
- [ ] No hay errores TS y los flujos críticos son utilizables con teclado.

## Archivos o dominios afectados
- `frontend/src/`
- `frontend/package.json`

## Comprobaciones y entrega
- [ ] Ejecutar las pruebas que correspondan y registrar resultados reales; indicar claramente las no ejecutadas.
- [ ] Mantener contratos y documentación sincronizados con los cambios implementados.
- [ ] Dejar una nota breve de integración o handoff si otro agente utiliza este módulo.

**Flujo de trabajo:** la Issue está lista para implementarse. Coordinad únicamente las interfaces y los archivos compartidos cuando sea necesario. El equipo decidirá cuándo crear ramas, commits o PRs.
