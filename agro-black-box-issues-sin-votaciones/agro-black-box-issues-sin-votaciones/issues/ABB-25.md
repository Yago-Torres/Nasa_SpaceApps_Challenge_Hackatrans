# [ABB-25] Invitaciones, revisión y colaboración entre comunidades

<!-- AGRO-ISSUE-ID: ABB-25 -->
## Objetivo
Invitaciones, revisión y colaboración entre comunidades. Contribución a **Global Connection**. Fase **F3**, prioridad **P0**.

**Responsable sugerido:** C (A = Codex/ChatGPT; B = Claude ciencia/agronomía; C = Claude interfaz/producto). La asignación es flexible: cualquier integrante o agente puede avanzar esta tarea.

**Dependencias técnicas orientativas:** ABB-05, ABB-06, ABB-14, ABB-20. No son bloqueos de aprobación: se puede trabajar en componentes independientes, tests, prototipos o contratos provisionales mientras se integran dependencias.

## Pasos de implementación
- [ ] Permitir invitación revocable a personas identificadas, con permisos definidos.
- [ ] Registrar comentarios, revisión de hipótesis/claims, decisiones y marca de autoría.
- [ ] Ofrecer vista pública anonimizada/compartida solo con consentimiento.
- [ ] Prevenir XSS, acceso no autorizado y cambios de revisión sin auditoría.

## Criterios de aceptación
- [ ] Dos usuarios distintos colaboran en un caso sin exposición de información privada.
- [ ] Un invitado puede comentar y otro revisar o revocar permisos.
- [ ] El registro de revisiones conserva autor, instante y evidencia.

## Archivos o dominios afectados
- `backend/agroblackbox/`
- `frontend/src/`

## Comprobaciones y entrega
- [ ] Ejecutar las pruebas que correspondan y registrar resultados reales; indicar claramente las no ejecutadas.
- [ ] Mantener contratos y documentación sincronizados con los cambios implementados.
- [ ] Dejar una nota breve de integración o handoff si otro agente utiliza este módulo.

**Flujo de trabajo:** la Issue está lista para implementarse. Coordinad únicamente las interfaces y los archivos compartidos cuando sea necesario. El equipo decidirá cuándo crear ramas, commits o PRs.
