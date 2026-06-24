# Anoven Monitoring

**Owner**: ops
**Implementado**: 2026-06-23 (M3 del curso bitácora-port)
**Status**: deployado

Sistema simple de health-check + alertas Telegram. Nace del post-mortem `docs/post-mortems/layer2-abandonment.md` (action item #3).

---

## Qué chequea (9 checks)

| # | Check | Detección |
|---|---|---|
| 1 | **Symlinks rotos en `/home/*/.claude/`** | `find /home -path "*/.claude/*" -xtype l` — exactamente la falla del Layer 2 |
| 2 | **Failed systemd services** | `systemctl --failed` (cualquier service en estado failed) |
| 3 | **HTTPS Layer 1** | `curl -sf https://anoven.ai` (200 OK en <10s) |
| 4 | **FastAPI backend** | `curl -sf http://127.0.0.1:8000/docs` |
| 5 | **Frontend Next.js** | `curl -sf http://127.0.0.1:3100` |
| 6 | **PostgreSQL ready** | `pg_isready -h 127.0.0.1 -p 5432` |
| 7 | **Engram daemon listening** | `ss -tln` busca `:7437` |
| 8 | **Disk usage `/`** | > 80% usado dispara alerta |
| 9 | **Memoria disponible** | < 200MB available dispara alerta |

---

## Cómo está deployado

- **Script**: `scripts/monitoring/check_health.sh` (~120 líneas, bash, sin deps externas más allá de curl + standard utils)
- **Env file**: `/home/anoven/anoven-app/.env.monitoring` (NO en git — contiene secret del bot)
- **Cron**: `/etc/cron.d/anoven-monitoring` — corre cada 15 min como root
- **Log**: `/var/log/anoven-monitoring.log` (cada run, pass o fail, deja un line)
- **Alert channel**: Telegram bot `@anovenBot`

---

## Setup inicial (cuando se crea el bot por primera vez)

1. Crear bot en Telegram via `@BotFather` (`/newbot`)
2. Anotar el bot token que devuelve BotFather
3. Mandar `/start` (o cualquier mensaje) al bot recién creado **desde la cuenta que recibirá las alertas**
4. Obtener el `chat_id`:
   ```bash
   curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getUpdates" \
     | jq '.result[-1].message.chat.id'
   ```
5. Pegar token y chat_id en `/home/anoven/anoven-app/.env.monitoring`:
   ```
   TELEGRAM_BOT_TOKEN=<token>
   TELEGRAM_CHAT_ID=<chat_id>
   ```
6. Permisos: `chmod 600 .env.monitoring`, owner `anoven:anoven`
7. Probar: `sudo /home/anoven/anoven-app/scripts/monitoring/check_health.sh; echo $?`

**Si `TELEGRAM_CHAT_ID` está vacío**, el script sigue chequeando + logueando, pero **no envía mensajes** (solo warning a stderr y log).

---

## Cómo probar que las alertas llegan

Forzar un fail temporal:

```bash
# Crear un symlink roto a propósito en una carpeta de testing
mkdir -p /tmp/test-claude
ln -s /nonexistent/path /tmp/test-claude/broken
# Pero check_health.sh chequea /home/*/.claude/* — no /tmp.
# Mejor: tocar temporariamente el threshold de disk a 1%, ejecutar, restaurar.
```

Alternativa más simple: mandar un mensaje de prueba a mano:

```bash
source /home/anoven/anoven-app/.env.monitoring
curl -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  -d chat_id="${TELEGRAM_CHAT_ID}" \
  -d text="Test desde anoven server $(date)"
```

---

## Cómo silenciar temporalmente

Comentar el cron line:

```bash
sudo sed -i 's/^\*\/15/#\*\/15/' /etc/cron.d/anoven-monitoring
```

Restaurar:
```bash
sudo sed -i 's/^#\*\/15/\*\/15/' /etc/cron.d/anoven-monitoring
```

---

## Cómo agregar un check nuevo

Editar `scripts/monitoring/check_health.sh`. Patrón:

```bash
# ---- Check N: <descripción> ----
if ! <comando que devuelve 0 si OK>; then
  failed_checks+=("<nombre_del_check>: <breve detalle>")
fi
```

Al final, contar y reportar se hace automático.

---

## Cómo regenerar token si se compromete

1. Hablar con `@BotFather` → `/revoke` → seleccionar bot → recibe token nuevo
2. Actualizar `.env.monitoring` con token nuevo
3. Hacer un test send (sección de arriba)

---

## Limitaciones conocidas (v0)

- **Sin deduplicación**: si un check falla 96 veces (cada 15min × 24h), te llegan 96 mensajes en un día. Próxima iteración: agregar debounce (no mandar la misma alerta dos veces en menos de X horas).
- **Sin escalation**: si Telegram cae, no hay fallback (email, SMS, otro canal).
- **Sin dashboard**: el log es plano. Para verlo lindo, hay que parsearlo a mano.

Estas limitaciones se atacan en Fase 3 del curso (curso #2, Bitácora-style observability).
