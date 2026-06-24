# Anoven Deploy

**Owner**: ops
**Implementado**: 2026-06-23 (M4 del curso bitácora-port)
**Status**: deployado

Deploy atómico con verify post-restart y rollback automático si la verificación falla. Nace del post-mortem `docs/post-mortems/layer2-abandonment.md` (action item #4).

---

## Uso

```bash
# Deploy real (requiere sudo)
sudo /home/anoven/anoven-app/scripts/deploy/deploy.sh

# Dry-run (planea, no toca nada)
sudo /home/anoven/anoven-app/scripts/deploy/deploy.sh --dry-run
```

---

## Qué hace, paso a paso

| Paso | Acción | Si falla |
|---|---|---|
| 1 | Pre-checks: branch=`main`, working tree clean | Aborta antes de cualquier change |
| 2 | Captura commit actual (rollback target) | — |
| 3 | `git fetch + merge --ff-only origin/main` | Aborta si no es fast-forward |
| 4 | Si `backend/requirements.txt` cambió → `pip install` | Aborta y rollback |
| 5 | Si `frontend/package.json` cambió → `npm ci` | Aborta y rollback |
| 6 | Si `frontend/` cambió → `npm run build` | Aborta y rollback |
| 7 | Migrations pendientes en `backend/migrations/*.sql` → `psql -v ON_ERROR_STOP=1` | **Rollback automático** (git reset + restart) |
| 8 | `systemctl restart anoven-app-backend.service anoven-app-frontend.service` | — |
| 9 | Wait 5s + verify: services activos + `https://anoven.ai` 200 + `:8000/docs` 200 | **Rollback automático** |
| 10 | Alert success/failure a Telegram | — |

---

## Rollback automático (cómo funciona)

Si los chequeos del paso 9 fallan:

1. `git reset --hard <commit-previo>` (el capturado en paso 2)
2. `systemctl restart` de los services nuevamente
3. Mensaje Telegram: `DEPLOY ROLLBACK on <host> at <ts> — reason: <detalle>`
4. Exit code != 0

**NO hay rollback de migraciones SQL aplicadas**. Si una migration corrupta pasa el `ON_ERROR_STOP` check pero rompe la app, el rollback de código no la deshace. Recomendación: cada migration nueva debería traer su `.rollback.sql` correspondiente (patrón ya usado: `20260608_per_mentor_model_rollback.sql`).

---

## Rollback manual (si automático falla o es necesario)

```bash
# Ver últimos commits
sudo -u anoven git -C /home/anoven/anoven-app log --oneline -10

# Volver a un commit específico
sudo -u anoven git -C /home/anoven/anoven-app reset --hard <hash>

# Restart services
sudo systemctl restart anoven-app-backend.service anoven-app-frontend.service

# Verificar
curl -sf https://anoven.ai && echo OK
```

---

## Pre-requisitos

- `git`, `curl`, `psql`, `systemctl`, `npm` instalados en el server
- `sudo` access (script corre con permisos elevados)
- `.env.monitoring` con `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` (para alertas — opcional pero recomendado)
- Branch `main` configurado para tracking de `origin/main`
- SSH key del server agregada al repo de GitHub (deploy key o user key)

---

## Schema migrations tracking

La tabla `schema_migrations` se crea automáticamente en `anoven_app_dev` la primera vez que corre `deploy.sh`. En esa primera ejecución, **todas las migrations existentes en `backend/migrations/*.sql` se marcan como 'ya aplicadas'** (asumiendo que el state inicial del server es consistente con ellas).

Para agregar una migration nueva:

1. Crear archivo `backend/migrations/YYYYMMDD_descripcion.sql`
2. Commit + push
3. Correr `deploy.sh` — detecta + aplica la nueva
4. Schema_migrations se actualiza automáticamente

---

## Cómo agregar un step nuevo al deploy

Editar `scripts/deploy/deploy.sh`. Patrón general (después del paso 3, antes del paso 7):

```bash
# ---- Step X: descripción ----
if echo "$CHANGED_FILES" | grep -qE "patrón regex"; then
  log "patrón cambió → acción"
  run sudo -u anoven <comando>
fi
```

Si el step puede fallar de manera que requiera rollback, usar `set -e` (ya activado) — cualquier comando que retorne != 0 hace abort.

---

## Limitaciones conocidas (v0)

- **No corre tests pre-deploy**: si los tests están rotos en main, el deploy igual va. Próxima iteración: agregar `pytest` + `npm test` antes del restart.
- **No rollback de migrations**: ver sección "Rollback automático".
- **Sin blue/green**: hay downtime durante `systemctl restart` (~3-5s). Próxima iteración: usar systemd socket activation o reverse proxy con dos backends.
- **Sin notificación al equipo**: solo Telegram al operator. Próxima iteración: webhook a Slack/Discord/etc.

Estas limitaciones se atacan en módulos futuros o en Fase 3 del curso (cuando construyamos los patrones operacionales de Bitácora).
