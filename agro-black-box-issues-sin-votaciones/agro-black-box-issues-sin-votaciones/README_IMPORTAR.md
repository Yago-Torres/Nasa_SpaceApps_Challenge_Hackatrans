# AGRO BLACK BOX — Issues listas para desarrollo (sin votaciones)

Repositorio destino: `Yago-Torres/Nasa_SpaceApps_Challenge_Hackatrans`.

Este paquete incluye **34 Issues** en Markdown, JSON y CSV, un roadmap y un importador. Las Issues se pueden ejecutar directamente sin votaciones, sin `team-approved`, sin `needs-vote`, y sin requisitos administrativos de aprobación previa. Las dependencias son orientativas para la integración, no bloqueos. Se mantienen pruebas, privacidad, trazabilidad científica y criterios de aceptación.

## Importación desde WSL / Codex

Con `gh auth status` correcto, extrae el ZIP y abre la terminal en la carpeta que contiene `publish_issues.py`.

```bash
gh auth status
uv run --no-project python publish_issues.py --repo Yago-Torres/Nasa_SpaceApps_Challenge_Hackatrans
uv run --no-project python publish_issues.py --repo Yago-Torres/Nasa_SpaceApps_Challenge_Hackatrans --apply
```

La primera ejecución es una **simulación**. La segunda crea las faltantes, sin alterar las existentes.

### Si ya publicaste Issues antiguas con votaciones

Primero comprueba la simulación y luego ejecuta:

```bash
uv run --no-project python publish_issues.py --repo Yago-Torres/Nasa_SpaceApps_Challenge_Hackatrans --update-existing
uv run --no-project python publish_issues.py --repo Yago-Torres/Nasa_SpaceApps_Challenge_Hackatrans --apply --update-existing --remove-legacy-vote-label
```

Esta acción reemplaza el cuerpo de las Issues `ABB-01` a `ABB-34` existentes por la versión nueva, manteniendo comentarios y números. **No sobrescribe Issues ajenas; sí reemplaza ediciones manuales en el cuerpo de las ABB existentes**, así que revisa la simulación antes. Solo retira la etiqueta `needs-vote` de estas Issues cuando se usa la opción correspondiente.

El importador **no crea ramas, commits, PRs ni hace push**.

Responsables recomendados: A = tú/Codex (NASA, backend, CI), B = Claude (ciencia, agronomía, rotaciones), C = Claude (frontend y producto). Las asignaciones son flexibles.

**Nota importante:** el repositorio original también contiene `AGENTS.md` y `docs/governance/FEATURE_POLICY.md` con reglas antiguas de aprobación. Para evitar que Codex/Claude se bloqueen, actualizad también esos archivos en un cambio de documentación. Este paquete incorpora `POLITICA_AGENTES_SIN_VOTOS.md` con un texto listo para sustituir las reglas de flujo de trabajo del repositorio. No modifica automáticamente esos archivos remotos.
