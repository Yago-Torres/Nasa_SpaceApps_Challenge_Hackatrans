# [ABB-06] Gestión completa de investigaciones y parcelas

<!-- AGRO-ISSUE-ID: ABB-06 -->
## Objetivo
Gestión completa de investigaciones y parcelas. Contribución a **Local Impact**. Trabajo de fase **F1**, prioridad **P0**.

**Responsable recomendado:** Persona C (A = usuario/ChatGPT, B = Claude científico, C = Claude producto). Cualquier integrante puede implementarla si el equipo aprueba la asignación.

**Dependencias previas:** ABB-03, ABB-05.
**Votación humana:** 2/3; revisar `docs/governance/FEATURE_POLICY.md`. La creación de esta Issue **no implica aprobación**.

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

## Contrato de entrega
- [ ] Cambios vinculados a esta Issue y revisados por otra persona cuando el equipo habilite su flujo Git.
- [ ] Tests/comprobaciones ejecutados y resultados registrados en la Issue o en la revisión (no inventados).
- [ ] Contratos y ADR actualizados si cambian; `CURRENT_STATE.md` solo tras validación.
- [ ] Handoff entre agentes según `docs/ai/HANDOFF_TEMPLATE.md`.

**Aprobaciones humanas (completar antes de programar):**
- [ ] Voto 1:
- [ ] Voto 2:
- [ ] Voto 3 (si se requieren 3/3):

