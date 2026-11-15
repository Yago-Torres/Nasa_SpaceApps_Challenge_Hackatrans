# Política operativa simplificada para agentes — AGRO BLACK BOX

## Modo de trabajo
- Una Issue del roadmap está disponible para implementación inmediatamente; no se requieren votos, etiquetas `team-approved` ni confirmaciones formales antes de empezar.
- Priorizar el trabajo por impacto y dependencias técnicas, no por procesos administrativos.
- Los responsables A/B/C son orientativos; cualquier integrante puede trabajar en cualquier Issue.
- Ante contratos o archivos compartidos, coordinar cambios mediante comentarios, tipos, tests y notas de integración. Los agentes pueden continuar con trabajo desacoplado mientras esperan componentes externos.
- No hace falta crear ramas/commits/PRs al iniciar cada Issue; los humanos decidirán cuándo publicar cambios.
- Cada entrega incluye pruebas ejecutadas, limitaciones, rutas modificadas y un handoff breve. No afirmar como implementado lo que todavía no se ha probado.
- Mantener privacidad por defecto, seguridad, fuentes NASA reales y procedencia científica. La ausencia de votos no reduce estos requisitos técnicos.

## Sustituciones recomendadas en el repositorio
- `AGENTS.md`: eliminar obligaciones `team-approved`, aprobación humana previa y votos 2/3 o 3/3; referir a esta política para el flujo de trabajo.
- `CLAUDE.md`: no exigir la lectura de políticas antiguas como barrera para trabajar.
- `docs/governance/FEATURE_POLICY.md`: reemplazar por esta política o un equivalente sin votaciones.
- `docs/ai/PROMPTS.md` y plantillas de Issues: eliminar referencias a etiquetas de aprobación.
- `docs/operations/CURRENT_STATE.md`: seguir distinguiendo hechos implementados de tareas pendientes.

La coordinación de publicación en Git se decide dentro del equipo. No conceder acceso a secretos ni omitir comprobaciones de seguridad.
