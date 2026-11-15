# [ABB-05] Diseñar y aplicar permisos y autenticación segura

<!-- AGRO-ISSUE-ID: ABB-05 -->
## Objetivo
Diseñar y aplicar permisos y autenticación segura. Contribución a **Global Connection; Local Impact**. Fase **F0**, prioridad **P0**.

**Responsable sugerido:** C (A = Codex/ChatGPT; B = Claude ciencia/agronomía; C = Claude interfaz/producto). La asignación es flexible: cualquier integrante o agente puede avanzar esta tarea.

**Dependencias técnicas orientativas:** ABB-02, ABB-03. No son bloqueos de aprobación: se puede trabajar en componentes independientes, tests, prototipos o contratos provisionales mientras se integran dependencias.

## Pasos de implementación
- [ ] Seleccionar implementación de sesiones/autenticación y documentar la decisión técnica en un ADR.
- [ ] Crear roles owner, editor, reviewer; casos privados por defecto y acceso por invitación.
- [ ] Incluir consentimiento para compartir y posibilidad de revocarlo.
- [ ] Escribir pruebas de autorización negativas, expiración y acceso entre usuarios.

## Criterios de aceptación
- [ ] Usuarios sin permiso no acceden a casos, fuentes ni coordenadas.
- [ ] Rol reviewer solo modifica contenido autorizado.
- [ ] Revocar invitación bloquea inmediatamente el acceso.

## Archivos o dominios afectados
- `backend/agroblackbox/`
- `frontend/src/`
- `docs/architecture/ADRs/`

## Comprobaciones y entrega
- [ ] Ejecutar las pruebas que correspondan y registrar resultados reales; indicar claramente las no ejecutadas.
- [ ] Mantener contratos y documentación sincronizados con los cambios implementados.
- [ ] Dejar una nota breve de integración o handoff si otro agente utiliza este módulo.

**Flujo de trabajo:** la Issue está lista para implementarse. Coordinad únicamente las interfaces y los archivos compartidos cuando sea necesario. El equipo decidirá cuándo crear ramas, commits o PRs.
