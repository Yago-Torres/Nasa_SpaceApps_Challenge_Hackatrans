# [ABB-28] Seguridad, privacidad y operaciones de datos

<!-- AGRO-ISSUE-ID: ABB-28 -->
## Objetivo
Seguridad, privacidad y operaciones de datos. Contribución a **Global Connection; Local Impact**. Fase **F4**, prioridad **P0**.

**Responsable sugerido:** C (A = Codex/ChatGPT; B = Claude ciencia/agronomía; C = Claude interfaz/producto). La asignación es flexible: cualquier integrante o agente puede avanzar esta tarea.

**Dependencias técnicas orientativas:** ABB-05, ABB-25, ABB-26. No son bloqueos de aprobación: se puede trabajar en componentes independientes, tests, prototipos o contratos provisionales mientras se integran dependencias.

## Pasos de implementación
- [ ] Definir minimización de datos, retención, borrado/exportación, consentimiento y perfiles de acceso.
- [ ] Auditar secretos, tokens, CORS, rate limit, logs y datos sensibles de ubicación.
- [ ] Añadir pruebas negativas de permisos para endpoints y descargas.
- [ ] Documentar aviso legal, descargo agronómico y política para datos de terceros.

## Criterios de aceptación
- [ ] Un usuario puede exportar y solicitar borrar sus datos según política definida.
- [ ] Ninguna coordenada ni token aparece en logs/PRs por defecto.
- [ ] Suite de permisos y compartición cubre denegación y revocación.

## Archivos o dominios afectados
- `backend/`
- `frontend/`
- `docs/operations/`

## Comprobaciones y entrega
- [ ] Ejecutar las pruebas que correspondan y registrar resultados reales; indicar claramente las no ejecutadas.
- [ ] Mantener contratos y documentación sincronizados con los cambios implementados.
- [ ] Dejar una nota breve de integración o handoff si otro agente utiliza este módulo.

**Flujo de trabajo:** la Issue está lista para implementarse. Coordinad únicamente las interfaces y los archivos compartidos cuando sea necesario. El equipo decidirá cuándo crear ramas, commits o PRs.
