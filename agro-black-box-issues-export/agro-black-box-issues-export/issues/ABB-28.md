# [ABB-28] Seguridad, privacidad y operaciones de datos

<!-- AGRO-ISSUE-ID: ABB-28 -->
## Objetivo
Seguridad, privacidad y operaciones de datos. Contribución a **Global Connection; Local Impact**. Trabajo de fase **F4**, prioridad **P0**.

**Responsable recomendado:** Persona C (A = usuario/ChatGPT, B = Claude científico, C = Claude producto). Cualquier integrante puede implementarla si el equipo aprueba la asignación.

**Dependencias previas:** ABB-05, ABB-25, ABB-26.
**Votación humana:** 3/3; revisar `docs/governance/FEATURE_POLICY.md`. La creación de esta Issue **no implica aprobación**.

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

## Contrato de entrega
- [ ] Cambios vinculados a esta Issue y revisados por otra persona cuando el equipo habilite su flujo Git.
- [ ] Tests/comprobaciones ejecutados y resultados registrados en la Issue o en la revisión (no inventados).
- [ ] Contratos y ADR actualizados si cambian; `CURRENT_STATE.md` solo tras validación.
- [ ] Handoff entre agentes según `docs/ai/HANDOFF_TEMPLATE.md`.

**Aprobaciones humanas (completar antes de programar):**
- [ ] Voto 1:
- [ ] Voto 2:
- [ ] Voto 3 (si se requieren 3/3):

